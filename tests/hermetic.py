"""tests/hermetic.py — Hermetic test guard plugin.

Loaded via ``pytest.ini`` ``addopts = -p tests.hermetic``.  Provides two
autouse fixtures that make every test hermetic by construction:

1. **Session-scoped env scrub** — removes ambient credentials so tests
   cannot accidentally reach live services through SDK auto-auth.
2. **Function-scoped network guard** — patches ``socket.socket.connect``,
   ``socket.socket.connect_ex``, ``socket.create_connection``, and
   ``socket.getaddrinfo`` so any destination other than loopback
   (``127.0.0.0/8``, ``::1``, ``localhost``) and Unix sockets raises
   ``HermeticViolation`` immediately.  Also patches ``databricks.sdk.WorkspaceClient``
   and ``databricks.sql.connect`` when those packages are importable.

**Opt-out markers** (registered in ``pytest.ini``):
- ``databricks`` — tests that need a live Databricks workspace
- ``spark`` — tests that need PySpark / Databricks Connect
- ``lakebase`` — tests that need a live Lakebase instance
- ``network`` — tests that need real outbound network access

Tests marked with any of these skip both guards.  In CI, the marker
expression ``-m "not spark and not lakebase and not databricks and not network"``
deselects them so guards are never bypassed on CI runners.
"""

from __future__ import annotations

import ipaddress
import os
import socket

import pytest


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class HermeticViolation(AssertionError):
    """Raised when a test attempts a non-hermetic operation."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRUB_PREFIXES = (
    "DATABRICKS_",
    "MASSIVE_",
    "HF_",
    "HUGGINGFACE",
    "OPENAI_",
    "ANTHROPIC_",
    "AWS_",
    "AZURE_",
    "GOOGLE_",
)

_SCRUB_SUFFIXES = (
    "_TOKEN",
    "_API_KEY",
    "_SECRET",
    "_PASSWORD",
)


def _is_loopback(host: str) -> bool:
    """Return *True* if *host* is a loopback address."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_opt_out(request) -> bool:
    """Return *True* if the test should skip hermetic guards."""
    for name in ("databricks", "spark", "lakebase", "network"):
        if request.node.get_closest_marker(name):
            return True
    return False


# ---------------------------------------------------------------------------
# Session-scoped env scrub
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _hermetic_env_scrub():
    """Remove ambient credentials for the entire test session.

    Scrubs every env var whose name starts with a known cloud/AI prefix or
    ends with a secret-bearing suffix, then sets
    ``DATABRICKS_CONFIG_FILE=/nonexistent/none.cfg`` so the default SDK auth
    cannot locate a profile.  Original values are restored at session end.
    """
    saved: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if any(upper.startswith(p) for p in _SCRUB_PREFIXES):
            saved[key] = value
        elif any(upper.endswith(s) for s in _SCRUB_SUFFIXES):
            saved[key] = value

    for key in saved:
        os.environ.pop(key, None)

    os.environ["DATABRICKS_CONFIG_FILE"] = "/nonexistent/none.cfg"

    yield

    for key in saved:
        os.environ[key] = saved[key]
    os.environ.pop("DATABRICKS_CONFIG_FILE", None)


# ---------------------------------------------------------------------------
# Function-scoped network guard
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _hermetic_network_guard(request):
    """Block non-loopback outbound connections for each test function.

    Patches ``socket.socket.connect``, ``socket.socket.connect_ex``,
    ``socket.create_connection``, and ``socket.getaddrinfo`` so that any
    destination other than loopback (``127.0.0.0/8``, ``::1``, ``localhost``)
    and Unix sockets raises ``HermeticViolation`` immediately.  Also patches
    ``databricks.sdk.WorkspaceClient`` and ``databricks.sql.connect`` when
    those packages are importable.
    """
    if _check_opt_out(request):
        yield
        return

    # ── socket-level patches ──────────────────────────────────────────────
    _real_create_connection = socket.create_connection
    _real_socket_connect = socket.socket.connect
    _real_socket_connect_ex = socket.socket.connect_ex
    _real_getaddrinfo = socket.getaddrinfo
    _has_af_unix = hasattr(socket, "AF_UNIX")

    def _extract_host_port(address, sock_family):
        if _has_af_unix and sock_family == socket.AF_UNIX:
            return None, None
        if sock_family == socket.AF_INET6:
            return address[0], address[1] if len(address) > 1 else 0
        return address[0], address[1] if len(address) > 1 else 0

    def _fail_create_connection(address, *args, **kwargs):
        host, port = address
        if _is_loopback(host):
            return _real_create_connection(address, *args, **kwargs)
        raise HermeticViolation(
            f"Blocked outbound connection to {host}:{port} in test "
            f"{request.node.nodeid!r}. Mock the call or mark @pytest.mark.network."
        )

    def _fail_socket_connect(self_addr, address, *args, **kwargs):
        if _has_af_unix and self_addr.family == socket.AF_UNIX:
            return _real_socket_connect(self_addr, address, *args, **kwargs)
        host, port = _extract_host_port(address, self_addr.family)
        if _is_loopback(host):
            return _real_socket_connect(self_addr, address, *args, **kwargs)
        raise HermeticViolation(
            f"Blocked outbound connection to {host}:{port} in test "
            f"{request.node.nodeid!r}. Mock the call or mark @pytest.mark.network."
        )

    def _fail_socket_connect_ex(self_addr, address, *args, **kwargs):
        if _has_af_unix and self_addr.family == socket.AF_UNIX:
            return _real_socket_connect_ex(self_addr, address, *args, **kwargs)
        host, port = _extract_host_port(address, self_addr.family)
        if _is_loopback(host):
            return _real_socket_connect_ex(self_addr, address, *args, **kwargs)
        raise HermeticViolation(
            f"Blocked outbound connection to {host}:{port} in test "
            f"{request.node.nodeid!r}. Mock the call or mark @pytest.mark.network."
        )

    def _fail_getaddrinfo(host, port, *args, **kwargs):
        if host is None or _is_loopback(host):
            return _real_getaddrinfo(host, port, *args, **kwargs)
        raise HermeticViolation(
            f"Blocked DNS lookup for {host}:{port} in test "
            f"{request.node.nodeid!r}. Mock the call or mark @pytest.mark.network."
        )

    socket.create_connection = _fail_create_connection
    socket.socket.connect = _fail_socket_connect
    socket.socket.connect_ex = _fail_socket_connect_ex
    socket.getaddrinfo = _fail_getaddrinfo

    # ── direct SDK / SQL-connector blockers ───────────────────────────────
    _patched_modules: list[tuple[object, str, object]] = []

    try:
        import databricks.sdk as _sdk
        _orig_wc = _sdk.WorkspaceClient
        _orig_cfg = _sdk.core.Config

        def _blocked_workspace_client(*a, **kw):
            host = kw.get("host") or (a[0] if a else None)
            raise HermeticViolation(
                f"Blocked databricks.sdk.WorkspaceClient(host={host!r}) in test "
                f"{request.node.nodeid!r}. Mock the call or mark @pytest.mark.databricks."
            )

        def _blocked_config(*a, **kw):
            host = kw.get("host") or (a[0] if a else None)
            if host:
                raise HermeticViolation(
                    f"Blocked databricks.sdk.core.Config(host={host!r}) in test "
                    f"{request.node.nodeid!r}. Mock the call or mark @pytest.mark.databricks."
                )
            return _orig_cfg(*a, **kw)

        _sdk.WorkspaceClient = _blocked_workspace_client
        _sdk.core.Config = _blocked_config
        _patched_modules.append((_sdk, "WorkspaceClient", _orig_wc))
        _patched_modules.append((_sdk.core, "Config", _orig_cfg))
    except ImportError:
        pass

    _has_sql = False
    try:
        import databricks.sql as _sql
        _has_sql = True
        _orig_connect = _sql.connect

        def _blocked_sql_connect(*a, **kw):
            raise HermeticViolation(
                f"Blocked databricks.sql.connect() in test "
                f"{request.node.nodeid!r}. Mock the call or mark @pytest.mark.databricks."
            )

        _sql.connect = _blocked_sql_connect
        _patched_modules.append((_sql, "connect", _orig_connect))
    except ImportError:
        pass

    yield

    # ── restore everything ────────────────────────────────────────────────
    socket.create_connection = _real_create_connection
    socket.socket.connect = _real_socket_connect
    socket.socket.connect_ex = _real_socket_connect_ex
    socket.getaddrinfo = _real_getaddrinfo

    for module, attr, orig in _patched_modules:
        setattr(module, attr, orig)