"""db/lakebase.py — Lakebase (Postgres) connection + transaction layer.

Responsibilities:
  * Mint the short-lived OAuth token on demand via the `databricks` CLI and
    refresh it before expiry. The token lives only in memory — it is never
    written to disk and never appears in committed code.
  * Explicit connection pooling via `psycopg_pool.ConnectionPool` (min/max size
    configurable, never defaulted).
  * Context-managed transactions with autocommit off for multi-statement writes.
  * Parameterized queries only — every statement is `%s`-placeholdered.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

import psycopg
from psycopg_pool import ConnectionPool
from psycopg_pool import PoolTimeout

# ── configuration (env-var driven; names only — no secrets in this file) ─────
LAKEBASE_INSTANCE = os.getenv("LAKEBASE_INSTANCE", "evangoh-capstone-lakebase")
LAKEBASE_HOST = os.getenv(
    "LAKEBASE_HOST", "ep-steep-truth-d1ex36nr.database.us-west-2.cloud.databricks.com"
)
LAKEBASE_PORT = int(os.getenv("LAKEBASE_PORT", "5432"))
LAKEBASE_DBNAME = os.getenv("LAKEBASE_DBNAME", "databricks_postgres")
LAKEBASE_USER = os.getenv("LAKEBASE_USER", "evangohsg@gmail.com")
LAKEBASE_SCHEMA = os.getenv("LAKEBASE_SCHEMA", "public")
LAKEBASE_SSLMODE = os.getenv("LAKEBASE_SSLMODE", "require")
LAKEBASE_CONNECT_TIMEOUT = int(os.getenv("LAKEBASE_CONNECT_TIMEOUT", "3"))

POOL_MIN_SIZE = int(os.getenv("LAKEBASE_POOL_MIN_SIZE", "1"))
POOL_MAX_SIZE = int(os.getenv("LAKEBASE_POOL_MAX_SIZE", "5"))

# The credential endpoint returns a token valid ~1 hour. Refresh this many
# seconds before expiry so a live pool never hands out an expired password.
TOKEN_REFRESH_MARGIN_SECONDS = int(os.getenv("LAKEBASE_TOKEN_REFRESH_MARGIN", "300"))
DEFAULT_TOKEN_TTL_SECONDS = 3600


def mint_token_via_cli(instance_name: str = LAKEBASE_INSTANCE) -> dict:
    """Mint a short-lived OAuth token for the Lakebase instance.

    Uses the `databricks` CLI (already authenticated via databricks-cli).
    Returns ``{"token": ..., "expiration_time": ...}``. Never persisted.
    """
    request_id = str(uuid.uuid4())
    payload = json.dumps(
        {"request_id": request_id, "instance_names": [instance_name]}
    )
    proc = subprocess.run(
        ["databricks", "api", "post", "/api/2.0/database/credentials", "--json", payload],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        # Never propagate raw CLI stderr/stdout: it may contain credential or
        # session material. Report only the exit code and request id.
        raise RuntimeError(
            f"Lakebase credential mint failed (exit code {proc.returncode}, "
            f"request_id={request_id}). Raw CLI output withheld."
        )
    return json.loads(proc.stdout)


def _parse_expiry(expiration_time: Optional[str]) -> float:
    if not expiration_time:
        return time.time() + DEFAULT_TOKEN_TTL_SECONDS
    ts = expiration_time.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return time.time() + DEFAULT_TOKEN_TTL_SECONDS


class LakebaseToken:
    """In-memory token cache with refresh-before-expiry. Never written to disk."""

    def __init__(self, provider: Callable[[], dict] = mint_token_via_cli):
        self._provider = provider
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._token is None or time.time() >= (
                self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS
            ):
                cred = self._provider()
                self._token = cred["token"]
                self._expires_at = _parse_expiry(cred.get("expiration_time"))
            return self._token

    @property
    def near_expiry(self) -> bool:
        return time.time() >= (self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS)

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = 0.0


class Lakebase:
    """Pooled connection + transaction layer for the Lakebase Postgres."""

    def __init__(
        self,
        *,
        token_provider: Optional[Callable[[], dict]] = None,
        pool_kwargs: Optional[dict] = None,
    ):
        self._token = LakebaseToken(token_provider or mint_token_via_cli)
        self._pool_kwargs = pool_kwargs or {}
        self._pool: Optional[ConnectionPool] = None
        self._lock = threading.Lock()

    # ── pool management ───────────────────────────────────────────────────────
    def _conninfo(self) -> dict:
        return {
            "host": LAKEBASE_HOST,
            "port": LAKEBASE_PORT,
            "dbname": LAKEBASE_DBNAME,
            "user": LAKEBASE_USER,
            "password": self._token.get(),
            "sslmode": LAKEBASE_SSLMODE,
            "connect_timeout": LAKEBASE_CONNECT_TIMEOUT,
        }

    def _configure(self, conn: psycopg.Connection) -> None:
        # Run session setup in autocommit mode so no transaction is left open
        # (psycopg_pool discards connections returned in INTRANS status).
        conn.autocommit = True
        with conn.cursor() as cur:
            # set_config is parameterized, unlike SET.
            cur.execute(
                "SELECT set_config('search_path', %s, false)", (LAKEBASE_SCHEMA,)
            )
        conn.autocommit = False

    def _build_pool(self) -> ConnectionPool:
        pool = ConnectionPool(
            kwargs=self._conninfo(),
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            open=False,
            configure=self._configure,
            **self._pool_kwargs,
        )
        # Bound total connection establishment so a disabled/hanging endpoint
        # raises promptly (within ~3-4 s) instead of retrying for 30+ s.
        # PoolTimeout is raised if min_size connections are not ready in time.
        pool.wait(timeout=LAKEBASE_CONNECT_TIMEOUT)
        return pool

    def _ensure_pool(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None or self._token.near_expiry:
                if self._pool is not None:
                    self._pool.close()
                self._token.invalidate()
                self._pool = self._build_pool()
            return self._pool

    @property
    def pool(self) -> ConnectionPool:
        return self._ensure_pool()

    # ── connection / transaction contexts ─────────────────────────────────────
    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        pool = self._ensure_pool()
        with pool.connection() as conn:
            yield conn

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection]:
        """Multi-statement transaction. Commits on success, rolls back on error."""
        with self.connection() as conn:
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            else:
                conn.commit()

    # ── parameterized helpers ─────────────────────────────────────────────────
    def execute(
        self, query: str, params: Optional[tuple] = None, *, transaction: bool = False
    ) -> list[tuple]:
        """Run a parameterized query; return all rows. No string interpolation."""
        if transaction:
            with self.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    return cur.fetchall()
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()

    def fetchone(self, query: str, params: Optional[tuple] = None) -> Optional[tuple]:
        rows = self.execute(query, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None


# Process-wide singleton. Modules that need a connection go through here so the
# token/pool lifecycle is shared, not duplicated per tool call.
_default: Optional[Lakebase] = None
_default_lock = threading.Lock()


def get_lakebase() -> Lakebase:
    global _default
    with _default_lock:
        if _default is None:
            _default = Lakebase()
        return _default
