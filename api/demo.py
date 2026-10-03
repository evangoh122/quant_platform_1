"""api/demo.py — Public demo mode gate and environment validation.

When ``PUBLIC_DEMO`` is set to a truthy value the application runs in
public-demo mode: anonymous read-only access, no Lakebase, no broker,
no write tools, and startup refuses unsafe credential configuration.

Fail-closed semantics: on Render (``RENDER`` is set) the app refuses to start
with write routes unless ``PUBLIC_DEMO`` is explicitly enabled.  An
unrecognised non-empty ``PUBLIC_DEMO`` value (e.g. ``"t"``, ``"1.0"``,
``"0"``) raises — only unset or empty means off.
"""
from __future__ import annotations

import os
from typing import Mapping

PUBLIC_DEMO_USER_ID = "public-demo"
PUBLIC_DEMO_ROLE = "viewer"

_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_ALL_KNOWN_DEMO_VALUES = _TRUTHY_VALUES | {"", "0", "false", "no", "off"}


def is_public_demo() -> bool:
    """Return ``True`` when the app is running in public-demo mode.

    Reads ``PUBLIC_DEMO`` from the environment at call time so tests and
    app-factory reloads are deterministic.  Only normalized truthy values
    (``1``, ``true``, ``yes``, ``on``) activate the mode.

    Raises :class:`PublicDemoConfigurationError` for unrecognised non-empty
    values so that typos like ``"t"`` or ``"1.0"`` never silently mean "off".
    """
    raw = os.environ.get("PUBLIC_DEMO", "").strip().lower()
    if raw and raw not in _ALL_KNOWN_DEMO_VALUES:
        raise PublicDemoConfigurationError(
            f"PUBLIC_DEMO has unrecognised value {raw!r}; "
            f"expected one of: {', '.join(sorted(_ALL_KNOWN_DEMO_VALUES))} (or unset/empty)"
        )
    return raw in _TRUTHY_VALUES


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

# Suffixes that indicate secrets.
_SECRET_SUFFIXES = (
    "_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_KEY", "_PASS", "_PWD",
    "_DSN", "_URI", "_PAT", "_APIKEY", "_CREDENTIALS", "_KEY_BASE",
    "_CONNECTION_STRING",
)

# Prefixes that indicate secrets.
_SECRET_PREFIXES = (
    "PG", "POSTGRES_", "IBKR_", "POLYGON_", "OPENAI_", "ANTHROPIC_",
    "AWS_", "AZURE_", "GOOGLE_", "GCP_", "GITHUB_", "GH_",
    "STRIPE_", "SENTRY_",
)

# Exact names that are secrets.
_SECRET_EXACT = frozenset({
    "DATABASE_URL", "HF_TOKEN",
    "CREDENTIALS", "REDIS_URL", "MONGODB_URI", "SECRET_KEY_BASE",
    "TOKEN", "SECRET", "PASSWORD", "DOCKER_AUTH_CONFIG",
})

# Render-injected env vars that are harmless and allowed.
_RENDER_ALLOW_LIST = frozenset({
    "RENDER", "RENDER_SERVICE_ID", "RENDER_SERVICE_NAME", "RENDER_SERVICE_TYPE",
    "RENDER_GIT_BRANCH", "RENDER_GIT_COMMIT", "RENDER_GIT_REPO_SLUG",
    "RENDER_GIT_OWNER", "RENDER_GIT_PROVIDER", "RENDER_GIT_PR_NUMBER",
    "RENDER_INSTANCE_ID", "RENDER_REGION", "RENDER_EXTERNAL_URL",
    "RENDER_EXTERNAL_HOSTNAME", "RENDER_DISK_MOUNT_PATH",
    "CLIENT_IP_SOURCE",
    "PORT", "PYTHON_VERSION", "NODE_VERSION", "PATH", "HOME",
})


def _is_unsafe_key(key: str, value: str) -> bool:
    """Return ``True`` if *key* with a non-empty *value* is rejected in demo."""
    if not value:
        return False
    if key in _RENDER_ALLOW_LIST:
        return False
    if key.startswith(_LAKEBASE_PREFIX) or key.startswith(_DATABRICKS_PREFIX):
        return True
    if key in _EXPLICIT_BROKER_KEYS:
        return True
    if key.endswith(_SECRET_SUFFIXES):
        return True
    if any(key.startswith(p) for p in _SECRET_PREFIXES):
        return True
    if key in _SECRET_EXACT:
        return True
    # Any *_URL whose value contains embedded credentials.
    if key.endswith("_URL") and ("@" in value or "://user:" in value):
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


def validate_render_environment() -> None:
    """Fail-closed guard for Render deployments.

    On Render (``RENDER`` is set to any non-empty value), the app must run in
    public-demo mode.  Refuse to start with write routes if ``PUBLIC_DEMO`` is
    not active.  This prevents the insecure default where ``PUBLIC_DEMO``
    absent means "full write surface" from silently shipping on Render.
    """
    render = os.environ.get("RENDER", "").strip()
    if not render:
        return
    if not is_public_demo():
        raise PublicDemoConfigurationError(
            "refusing to start with write routes on Render; set PUBLIC_DEMO=1"
        )