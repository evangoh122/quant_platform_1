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
from typing import Callable, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"

# The Databricks App proxy injects the authenticated user's email into
# ``x-forwarded-email`` (OBO). ``x-databricks-user`` / ``x-databricks-user-email``
# are accepted as fallbacks, and finally a configured dev user so local
# development works without the proxy. The user identity is always taken from a
# request header, never from the request body.
_AUTH_USER_HEADERS = (
    os.getenv("AUTH_USER_HEADER", "x-forwarded-email"),
    "x-databricks-user",
    "x-databricks-user-email",
    "x-forwarded-user",
)
_DEV_USER = os.getenv("AUTH_DEV_USER", "default")
_DEFAULT_ROLE = "trader"


class AppUser:
    """The authenticated principal, mapped to a Lakebase ``user_id``."""

    def __init__(self, user_id: str, role: str = _DEFAULT_ROLE):
        self.user_id = user_id
        self.role = role

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AppUser(user_id={self.user_id!r}, role={self.role!r})"


def _ensure_user(user_id: str) -> str:
    """Idempotent upsert of the principal into ``users``; returns the role.

    Best-effort: if Lakebase is unreachable we fall back to the default role so
    the app still boots, but any *write* that requires a role will fail closed
    at the Lakebase boundary rather than silently skipping authorization.
    """
    try:
        from db.lakebase import get_lakebase

        db = get_lakebase()
        rows = db.execute(
            """
            INSERT INTO users (user_id, display_name, role, created_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (user_id) DO NOTHING
            RETURNING role
            """,
            (user_id, user_id, _DEFAULT_ROLE),
        )
        if rows:
            return rows[0][0]
        row = db.fetchone(
            "SELECT role FROM users WHERE user_id = %s", (user_id,)
        )
        return row[0] if row else _DEFAULT_ROLE
    except Exception:
        return _DEFAULT_ROLE


def get_current_user(request: Request) -> AppUser:
    """Resolve the authenticated user from the Databricks App proxy headers.

    The user identity is threaded from the request, never accepted from the
    request body, so a client cannot impersonate another principal.
    """
    user_id: Optional[str] = None
    for header in _AUTH_USER_HEADERS:
        value = request.headers.get(header)
        if value:
            user_id = value.strip()
            break
    user_id = user_id or _DEV_USER
    role = _ensure_user(user_id)
    return AppUser(user_id=user_id, role=role)


def require_role(*allowed_roles: str):
    """Dependency factory enforcing server-side role membership."""

    def _check(user: AppUser = Depends(get_current_user)) -> AppUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"role '{user.role}' not permitted; required one of {list(allowed_roles)}",
            )
        return user

    return _check


def get_lakebase():
    """Lazily return the process-wide Lakebase singleton."""
    from db.lakebase import get_lakebase as _get

    return _get()


def read_delta(fn: Callable[[], List[dict]]) -> Tuple[List[dict], str, str]:
    """Run a Delta-backed read, mapping failure modes to a freshness state.

    Returns ``(rows, state, detail)`` where state is one of ``fresh``,
    ``stale``, ``empty``, ``unavailable``. Never raises: a missing pyspark or a
    failing Spark call degrades to ``unavailable`` so the route can return a
    well-formed empty envelope instead of crashing.
    """
    try:
        rows = fn() or []
    except ImportError as exc:
        return [], "unavailable", f"pyspark/Delta not available: {exc}"
    except Exception as exc:  # noqa: BLE001 - degrade, never crash the API
        return [], "unavailable", f"delta read failed: {type(exc).__name__}"
    if not rows:
        return [], "empty", "0 rows"
    return rows, "fresh", f"{len(rows)} rows"
