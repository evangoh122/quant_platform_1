"""api/deps.py — FastAPI dependency providers.

Providers for:

* the authenticated Databricks App user (mapped to a Lakebase ``user_id``),
* server-side role checks,
* the Lakebase connection (pooled, token minted on demand by ``db.lakebase``),
* the Delta / Spark reader (lazy — pyspark is only imported when a read is
  actually attempted, so ``import api.main`` never requires pyspark locally).

All outbound calls (Lakebase, Delta, SEC, market-data, IBKR) stay server-side;
the browser only ever talks to the ``/api`` endpoints.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Tuple

from fastapi import Depends, HTTPException, Request
from loguru import logger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"

# The Databricks App proxy injects the authenticated principal's email into a
# single trusted header (``x-forwarded-email`` by default, overridable via
# ``AUTH_USER_HEADER``). No other header is trusted: a client that can set
# ``x-forwarded-user`` / ``x-databricks-user`` cannot spoof an identity, because
# those headers are never read.
_AUTH_USER_HEADER = os.getenv("AUTH_USER_HEADER", "x-forwarded-email")
_DEV_USER = os.getenv("AUTH_DEV_USER", "default")

# Least-privilege role for a newly provisioned principal. Approver (and any other
# elevated) authority is granted out-of-band and only ever read back from the
# ``users`` table; this module never assigns it.
_VIEWER_ROLE = "viewer"


def _is_dev() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "dev"


class AppUser:
    """The authenticated principal, mapped to a Lakebase ``user_id``.

    ``authenticated`` is ``True`` only when the identity came from the trusted
    proxy header. The ``APP_ENV=dev`` fallback principal is intentionally marked
    ``authenticated=False`` so it can never reach a write operation.
    """

    def __init__(self, user_id: str, role: str, authenticated: bool = True):
        self.user_id = user_id
        self.role = role
        self.authenticated = authenticated

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"AppUser(user_id={self.user_id!r}, role={self.role!r}, "
            f"authenticated={self.authenticated!r})"
        )


def _ensure_user(user_id: str) -> str:
    """Idempotent upsert of the principal into ``users``; returns the role.

    New users are provisioned with the least privilege (``viewer``). Any database
    failure propagates to the caller so it can fail closed (``503``); this
    function never substitutes a role when the store is unreachable.
    """
    from db.lakebase import get_lakebase

    db = get_lakebase()
    rows = db.execute(
        """
        INSERT INTO users (user_id, display_name, role, created_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (user_id) DO NOTHING
        RETURNING role
        """,
        (user_id, user_id, _VIEWER_ROLE),
    )
    if rows:
        return rows[0][0]
    row = db.fetchone("SELECT role FROM users WHERE user_id = %s", (user_id,))
    if row is None:
        raise RuntimeError(f"identity lookup failed for {user_id!r}")
    return row[0]


def get_current_user(request: Request) -> AppUser:
    """Resolve the authenticated user from the single Databricks proxy header.

    Fails closed: without the trusted header the request is rejected with
    ``401`` unless ``APP_ENV=dev`` is set explicitly, in which case the
    ``AUTH_DEV_USER`` fallback is used — but that fallback is never treated as an
    authenticated principal. A database error during role lookup returns ``503``,
    never a role.

    In public-demo mode, returns a fixed anonymous viewer immediately — every
    identity header is ignored and no database is touched.
    """
    from api.demo import PUBLIC_DEMO_ROLE, PUBLIC_DEMO_USER_ID, is_public_demo

    if is_public_demo():
        return AppUser(
            user_id=PUBLIC_DEMO_USER_ID,
            role=PUBLIC_DEMO_ROLE,
            authenticated=False,
        )

    header_value = request.headers.get(_AUTH_USER_HEADER)
    if header_value and header_value.strip():
        user_id = header_value.strip()
        authenticated = True
    elif _is_dev():
        user_id = _DEV_USER
        authenticated = False
    else:
        raise HTTPException(status_code=401, detail="authentication required")

    try:
        role = _ensure_user(user_id)
    except Exception:  # noqa: BLE001 - fail closed, never leak the cause
        logger.exception("identity/role lookup failed for %r", user_id)
        raise HTTPException(
            status_code=503, detail="identity service unavailable"
        ) from None

    return AppUser(user_id=user_id, role=role, authenticated=authenticated)


def ensure_role(user: AppUser, *roles: str) -> AppUser:
    """Raise ``401`` unless authenticated, ``403`` unless a role is held.

    Callable directly (from routes that perform conditional writes) or via the
    :func:`require_role` dependency factory.
    """
    if not user.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    if user.role not in roles:
        raise HTTPException(
            status_code=403,
            detail=f"role '{user.role}' not permitted; required one of {list(roles)}",
        )
    return user


def require_role(*allowed_roles: str):
    """Dependency factory enforcing authentication + server-side role membership."""

    def _check(user: AppUser = Depends(get_current_user)) -> AppUser:
        return ensure_role(user, *allowed_roles)

    return _check


def get_lakebase():
    """Lazily return the process-wide Lakebase singleton."""
    from db.lakebase import get_lakebase as _get

    return _get()


def read_delta(
    fn: Callable[[], List[dict]],
    *,
    snapshot_key: str | None = None,
) -> Tuple[List[dict], str, str]:
    """Run a Delta-backed read, mapping failure modes to a freshness state.

    Returns ``(rows, state, detail)`` where state is one of ``fresh``,
    ``stale``, ``empty``, ``unavailable``. Never raises: a missing pyspark or a
    failing Spark call degrades to ``unavailable`` so the route can return a
    well-formed empty envelope instead of crashing.

    In public-demo mode the live *fn* is never called.  If a *snapshot_key* is
    provided the function lazily imports ``api.demo_data.read_snapshot`` and
    serves the pre-exported JSON.  Missing key, missing module, or any
    validation failure degrades to ``([], "unavailable", <detail>)`` without
    exposing raw exception text.
    """
    from api.demo import is_public_demo

    if is_public_demo():
        if not snapshot_key:
            return [], "unavailable", "no snapshot key"
        try:
            from api.demo_data import read_snapshot

            rows = read_snapshot(snapshot_key)
            if not rows:
                return [], "empty", "0 rows"
            return rows, "fresh", f"{len(rows)} rows"
        except Exception:  # noqa: BLE001 - never expose exception text
            return [], "unavailable", "snapshot read failed"

    try:
        rows = fn() or []
    except ImportError:
        return [], "unavailable", "pyspark/Delta not available"
    except Exception as exc:  # noqa: BLE001 - degrade, never crash the API
        return [], "unavailable", f"delta read failed: {type(exc).__name__}"
    if not rows:
        return [], "empty", "0 rows"
    return rows, "fresh", f"{len(rows)} rows"
