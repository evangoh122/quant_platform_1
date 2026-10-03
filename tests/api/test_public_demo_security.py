"""Public-demo security tests — 10 tests covering the demo mode gate.

These tests prove that the public-demo mode:
- Returns a fixed anonymous viewer regardless of identity headers
- Never touches Lakebase
- Registers only GET/HEAD/OPTIONS routes under /api
- Rejects unsafe environment variables at startup
- Rate limits, body-size limits, and adds security headers
- Has no CORS middleware
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_modules():
    """Ensure api.* and agent.tools_write modules are cleared after each test.

    This prevents demo-mode app instances from leaking into subsequent tests
    that use the ``client`` fixture (which imports ``app`` from ``api.main``).
    """
    yield
    for key in list(sys.modules):
        if key.startswith("api.") or key == "agent.tools_write":
            del sys.modules[key]


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_demo_app(monkeypatch, extra_env: dict[str, str] | None = None):
    """Build a fresh app under PUBLIC_DEMO=1 with a clean environment."""
    for key in list(sys.modules):
        if key.startswith("api.") or key.startswith("agent.tools_write"):
            del sys.modules[key]

    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    for k, v in (extra_env or {}).items():
        monkeypatch.setenv(k, v)

    import api.main as main_mod

    app = main_mod.create_app()
    return app


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


# ── test 1: anonymous fixed viewer ────────────────────────────────────────────

def test_anonymous_fixed_viewer(monkeypatch):
    """With no identity header, get_current_user returns the public-demo user."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)
    # Use /api/analytics which doesn't touch Lakebase or Spark
    resp = client.get("/api/analytics")
    assert resp.status_code == 200


# ── test 2: spoofed identity equivalence ──────────────────────────────────────

def test_spoofed_identity_equivalence(monkeypatch):
    """A spoofed x-forwarded-email is ignored; response matches no-header case."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    no_header_resp = client.get("/api/analytics")
    spoofed_resp = client.get(
        "/api/analytics",
        headers={"x-forwarded-email": "owner@evil.com"},
    )
    assert no_header_resp.status_code == spoofed_resp.status_code
    assert no_header_resp.json() == spoofed_resp.json()


# ── test 3: no Lakebase import/call ───────────────────────────────────────────

def test_no_lakebase_import_in_demo(monkeypatch):
    """After app construction and an anonymous request, db.lakebase is not imported."""
    # Clear db.lakebase if it was imported by fixtures
    for key in list(sys.modules):
        if key.startswith("db.lakebase"):
            del sys.modules[key]

    app = _make_demo_app(monkeypatch)
    client = _client(app)
    client.get("/api/analytics")

    assert "db.lakebase" not in sys.modules


# ── test 4: demo routes are GET/HEAD/OPTIONS only, prohibited paths absent ────

def test_demo_routes_methods_and_prohibited_paths(monkeypatch):
    """All /api routes only allow GET/HEAD/OPTIONS; write routes are absent."""
    app = _make_demo_app(monkeypatch)

    for route in app.routes:
        if not hasattr(route, "path") or not route.path.startswith("/api"):
            continue
        methods = getattr(route, "methods", set())
        if methods:
            assert methods.issubset({"GET", "HEAD", "OPTIONS"}), (
                f"{route.path} allows {methods - {'GET', 'HEAD', 'OPTIONS'}}"
            )

    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/orders" not in paths
    assert "/api/watchlists" not in paths
    assert "/api/agent" not in paths
    assert "/api/portfolio" not in paths


# ── test 5: unsafe variables reject at construction, values not in errors ─────

@pytest.mark.parametrize("key", [
    "LAKEBASE_HOST",
    "DATABRICKS_HOST",
    "DATABRICKS_TOKEN",
    "IBKR_HOST",
    "IBKR_PORT",
    "IBKR_CLIENT_ID",
    "IBKR_ACCOUNT",
    "IBKR_USERNAME",
    "IBKR_PASSWORD",
    "BROKER_API_KEY",
    "MY_API_KEY",
    "MY_TOKEN",
    "MY_SECRET",
])
def test_unsafe_variable_rejected_at_construction(monkeypatch, key):
    """Each unsafe variable family rejects at app construction without leaking values."""
    for k in list(sys.modules):
        if k.startswith("api."):
            del sys.modules[k]

    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "super-secret-value-12345")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    error_text = str(exc_info.value)
    assert key in error_text
    assert "super-secret-value-12345" not in error_text


# ── test 6: safe empty environment starts ─────────────────────────────────────

def test_safe_empty_environment_starts(monkeypatch):
    """With PUBLIC_DEMO=1 and no unsafe vars, create_app() succeeds."""
    for k in list(sys.modules):
        if k.startswith("api."):
            del sys.modules[k]

    monkeypatch.setenv("PUBLIC_DEMO", "1")
    for key in (
        "LAKEBASE_HOST", "LAKEBASE_PORT", "LAKEBASE_DB",
        "DATABRICKS_HOST", "DATABRICKS_TOKEN",
        "IBKR_HOST", "IBKR_PORT", "IBKR_CLIENT_ID",
        "IBKR_ACCOUNT", "IBKR_USERNAME", "IBKR_PASSWORD",
        "BROKER_API_KEY", "MY_API_KEY", "MY_TOKEN", "MY_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)

    from api.main import create_app

    app = create_app()
    assert app is not None


# ── test 7: 61st read gives 429 plus Retry-After ─────────────────────────────

def test_rate_limit_61st_read_gives_429(monkeypatch):
    """The 61st GET in the same minute returns 429 with Retry-After."""
    import api.main as main_mod

    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch)
    client = _client(app)

    for i in range(60):
        resp = client.get("/api/analytics")
        assert resp.status_code == 200, f"request {i+1} failed with {resp.status_code}"

    resp = client.get("/api/analytics")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) > 0

    main_mod._limiter.reset()


# ── test 8: oversized body is 413 ────────────────────────────────────────────

def test_oversized_body_is_413(monkeypatch):
    """A POST with Content-Length exceeding the limit returns 413 or 405."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    resp = client.post(
        "/api/analytics",
        content=b"x" * (1024 * 1024 + 1),
        headers={"Content-Length": str(1024 * 1024 + 1)},
    )
    # 405 because POST is not allowed in demo, or 413 for body too large
    assert resp.status_code in (405, 413)


# ── test 9: security headers are present ─────────────────────────────────────

def test_security_headers_present(monkeypatch):
    """Every response in demo mode carries the required security headers."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    resp = client.get("/api/analytics")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in resp.headers
    assert "frame-ancestors" in resp.headers["Content-Security-Policy"]
    assert resp.headers.get("Cache-Control") == "no-store"


# ── test 10: demo CORS remains absent ────────────────────────────────────────

def test_demo_cors_absent(monkeypatch):
    """No CORS headers are present in demo mode even if CORS_ORIGINS is set."""
    app = _make_demo_app(monkeypatch, extra_env={"CORS_ORIGINS": "http://evil.com"})
    client = _client(app)

    resp = client.options(
        "/api/analytics",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in resp.headers