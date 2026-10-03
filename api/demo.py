"""api/demo.py — Public demo mode gate and environment validation.

When ``PUBLIC_DEMO`` is set to a truthy value the application runs in
public-demo mode: anonymous read-only access, no Lakebase, no broker,
no write tools, and startup refuses unsafe credential configuration.
"""
from __future__ import annotations

import os
from typing import Mapping

PUBLIC_DEMO_USER_ID = "public-demo"
PUBLIC_DEMO_ROLE = "viewer"

_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})


def is_public_demo() -> bool:
    """Return ``True`` when the app is running in public-demo mode.

    Reads ``PUBLIC_DEMO`` from the environment at call time so tests and
    app-factory reloads are deterministic.  Only normalized truthy values
    (``1``, ``true``, ``yes``, ``on``) activate the mode.
    """
    return os.environ.get("PUBLIC_DEMO", "").strip().lower() in _TRUTHY_VALUES


class PublicDemoConfigurationError(RuntimeError):
    """Raised when public-demo mode is active but unsafe env vars are set."""


# Variable families rejected in public-demo mode.
_LAKEBASE_PREFIX = "LAKEBASE_"
_DATABRICKS_PREFIX = "DATABRICKS_"
_EXPLICIT_BROKER_KEYS = frozenset({
    "IBKR_HOST",
    "IBKR_PORT",
    "IBKR_CLIENT_ID",
    "IBKR_ACCOUNT",
    "IBKR_USERNAME",
    "IBKR_PASSWORD",
    "BROKER_API_KEY",
})


def _is_unsafe_key(key: str, value: str) -> bool:
    """Return ``True`` if *key* with a non-empty *value* is rejected in demo."""
    if not value:
        return False
    if key.startswith(_LAKEBASE_PREFIX) or key.startswith(_DATABRICKS_PREFIX):
        return True
    if key in _EXPLICIT_BROKER_KEYS:
        return True
    if key.endswith(("_API_KEY", "_TOKEN", "_SECRET")):
        return True
    return False


def validate_public_demo_environment(
    environ: Mapping[str, str] | None = None,
) -> None:
    """Reject unsafe environment variables when public-demo mode is active.

    Called synchronously from ``create_app()`` so the process refuses to start
    with an unsafe configuration.  Error text lists variable **names** only,
    never values.  ``PUBLIC_DEMO`` itself is never rejected.
    """
    if not is_public_demo():
        return

    env = environ if environ is not None else os.environ
    violations = sorted(
        key for key, value in env.items() if _is_unsafe_key(key, value)
    )
    if violations:
        raise PublicDemoConfigurationError(
            "PUBLIC_DEMO is enabled but the following environment variables "
            "contain secrets or credentials and must be removed: "
            + ", ".join(violations)
        )