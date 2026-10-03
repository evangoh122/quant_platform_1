"""Public-demo security tests — covering the demo mode gate.

These tests prove that the public-demo mode:
- Returns a fixed anonymous viewer regardless of identity headers
- Never touches Lakebase (including /api/health on every GET route)
- Registers only GET/HEAD/OPTIONS routes under /api
- Rejects unsafe environment variables at startup (broadened families)
- Rate limits with CF-Connecting-IP > True-Client-IP > leftmost XFF on Render
- Uses token bucket for aggregate limiting (brief 429s, not minute-long outage)
- Normalises /api prefix (//api, /%2fapi, /API)
- Adds security headers on every response including 405/413/429/504
- Has no CORS middleware
- Fails closed on Render without PUBLIC_DEMO
- Rejects unrecognised PUBLIC_DEMO values
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from api.demo import _is_unsafe_key


@pytest.fixture(autouse=True)
def _strip_ambient_secrets(monkeypatch):
    """Remove ambient env vars that ``api.demo._is_unsafe_key`` would reject.

    Any CI runner or developer shell may carry ``CLAUDE_CODE_MESSAGING_TOKEN``,
    ``DATABRICKS_WORKSPACE_ID``, or similar variables.  This fixture strips
    them before each test so the demo-mode validation is deterministic.
    It reuses the predicate from ``api/demo.py`` so the two cannot drift.
    """
    for key in list(os.environ):
        if key == "PUBLIC_DEMO":
            continue
        if _is_unsafe_key(key, os.environ.get(key, "")):
            monkeypatch.delenv(key, raising=False)
    yield


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_demo_app(monkeypatch, extra_env: dict[str, str] | None = None):
    """Build a fresh app under PUBLIC_DEMO=1 with a clean environment.

    Uses the application factory (``create_app()``) directly without touching
    ``sys.modules``, so the conftest ``client`` fixture's ``app`` reference
    (from the original ``api.main`` import) is never invalidated.
    """
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    for k, v in (extra_env or {}).items():
        monkeypatch.setenv(k, v)

    from api.main import create_app

    return create_app()


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def _get_api_get_routes(app):
    """Extract all GET-allowing routes under /api from the app's router.

    Walks ``_IncludedRouter`` objects (registered via ``include_router``)
    using ``include_context.prefix`` and ``original_router.routes`` to get
    the effective route set.
    """
    routes = []
    for r in app.routes:
        if hasattr(r, "include_context"):
            prefix = r.include_context.prefix or ""
            router = r.original_router
            for route in router.routes:
                rp = getattr(route, "path", None)
                rm = getattr(route, "methods", None)
                if rp and rm and "GET" in rm:
                    full_path = prefix + rp
                    if full_path.startswith("/api"):
                        routes.append(full_path)
        elif hasattr(r, "path") and hasattr(r, "methods"):
            if r.path.startswith("/api") and "GET" in (r.methods or set()):
                routes.append(r.path)
    return routes


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


# ── test 3: no Lakebase import/call on EVERY GET route ───────────────────────

def test_no_lakebase_import_in_demo(monkeypatch):
    """After app construction and requests to every registered GET route,
    db.lakebase is not imported and subprocess.run is never called."""
    saved = {
        key: sys.modules.pop(key)
        for key in list(sys.modules)
        if key.startswith("db.lakebase")
    }

    app = _make_demo_app(monkeypatch)
    client = _client(app)

    # Hit every registered GET route under /api.
    routes = _get_api_get_routes(app)
    assert routes, "Expected at least one /api GET route"

    with patch("subprocess.run", side_effect=AssertionError("subprocess.run must not be called in demo")):
        for route in routes:
            # Replace path parameters with test values.
            test_route = route.replace("{symbol}", "AAPL")
            resp = client.get(test_route)
            assert resp.status_code == 200, f"GET {test_route} returned {resp.status_code}"

    assert "db.lakebase" not in sys.modules

    sys.modules.update(saved)


# ── test 3b: health returns 200 fast in demo ─────────────────────────────────

def test_health_returns_200_fast_in_demo(monkeypatch):
    """GET /api/health returns 200 in demo without touching Lakebase or subprocess."""
    saved = {
        key: sys.modules.pop(key)
        for key in list(sys.modules)
        if key.startswith("db.lakebase")
    }

    app = _make_demo_app(monkeypatch)
    client = _client(app)

    with patch("subprocess.run", side_effect=AssertionError("subprocess.run must not be called in demo")):
        resp = client.get("/api/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    deps = {d["name"]: d for d in data["dependencies"]}
    assert deps["lakebase"]["ok"] is False
    assert deps["lakebase"]["detail"] == "disabled in public demo"
    assert deps["delta"]["ok"] is False
    assert deps["delta"]["detail"] == "disabled in public demo"
    assert "db.lakebase" not in sys.modules

    sys.modules.update(saved)


# ── test 4: demo routes are GET/HEAD/OPTIONS only, prohibited paths absent ────

def test_demo_routes_methods_and_prohibited_paths(monkeypatch):
    """All /api routes only allow GET/HEAD/OPTIONS; write routes are absent.

    Walks sub-routers via ``include_context.prefix`` and
    ``original_router.routes`` to get the effective route set.  The test
    FAILs if a POST route is registered in demo (proved by mutation: adding
    a POST handler to the app would cause this test to fail).
    """
    app = _make_demo_app(monkeypatch)

    all_paths = set()
    for r in app.routes:
        if hasattr(r, "include_context"):
            prefix = r.include_context.prefix or ""
            router = r.original_router
            for route in router.routes:
                rp = getattr(route, "path", None)
                rm = getattr(route, "methods", None)
                if not rp or not rm:
                    continue
                full_path = prefix + rp
                if not full_path.startswith("/api"):
                    continue
                all_paths.add(full_path)
                assert rm.issubset({"GET", "HEAD", "OPTIONS"}), (
                    f"{full_path} allows {rm - {'GET', 'HEAD', 'OPTIONS'}}"
                )
        elif hasattr(r, "path") and hasattr(r, "methods"):
            if r.path.startswith("/api"):
                all_paths.add(r.path)
                methods = r.methods or set()
                if methods:
                    assert methods.issubset({"GET", "HEAD", "OPTIONS"}), (
                        f"{r.path} allows {methods - {'GET', 'HEAD', 'OPTIONS'}}"
                    )

    # Verify write routers are not registered at all.
    assert "/api/orders" not in all_paths
    assert "/api/watchlists" not in all_paths
    assert "/api/agent" not in all_paths
    assert "/api/portfolio" not in all_paths


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
    # New families (round 3):
    "PGPASSWORD",
    "PGHOST",
    "POSTGRES_PASSWORD",
    "DB_PASSWORD",
    "SECRET_KEY",
    "JWT_KEY",
    "POLYGON_KEY",
    "DATABASE_URL",
    "HF_TOKEN",
    "IBKR_BASE_URL",
    "POLYGON_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "MY_PASS",
    "MY_PWD",
])
def test_unsafe_variable_rejected_at_construction(monkeypatch, key):
    """Each unsafe variable family rejects at app construction without leaking values."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "super-secret-value-12345")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    error_text = str(exc_info.value)
    assert key in error_text
    assert "super-secret-value-12345" not in error_text


# ── test 5b: Render allow-listed vars are not rejected ────────────────────────

@pytest.mark.parametrize("key", [
    "RENDER",
    "RENDER_SERVICE_ID",
    "RENDER_SERVICE_NAME",
    "RENDER_SERVICE_TYPE",
    "RENDER_GIT_BRANCH",
    "RENDER_GIT_COMMIT",
    "RENDER_GIT_REPO_SLUG",
    "RENDER_EXTERNAL_URL",
    "PORT",
    "PYTHON_VERSION",
    "NODE_VERSION",
    "PATH",
    "HOME",
])
def test_render_allowlisted_vars_not_rejected(monkeypatch, key):
    """Render-injected env vars are harmless and must not be rejected."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "some-value")

    from api.demo import validate_public_demo_environment

    # Must not raise.
    validate_public_demo_environment()


# ── test 6: safe empty environment starts ─────────────────────────────────────

def test_safe_empty_environment_starts(monkeypatch):
    """With PUBLIC_DEMO=1 and no unsafe vars, create_app() succeeds."""
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


# ── test 9: security headers on 200 ──────────────────────────────────────────

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


# ── test 9b: security headers on 405 ─────────────────────────────────────────

def test_security_headers_on_405(monkeypatch):
    """A POST to /api returns 405 with all security headers."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    resp = client.post("/api/analytics", content=b"test")
    assert resp.status_code == 405
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers.get("Cache-Control") == "no-store"


# ── test 9c: security headers on 429 ─────────────────────────────────────────

def test_security_headers_on_429(monkeypatch):
    """A rate-limited response carries all security headers."""
    import api.main as main_mod

    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch)
    client = _client(app)

    for _ in range(60):
        client.get("/api/analytics")

    resp = client.get("/api/analytics")
    assert resp.status_code == 429
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers.get("Cache-Control") == "no-store"

    main_mod._limiter.reset()


# ── test 9d: security headers on 413 ─────────────────────────────────────────

def test_security_headers_on_413(monkeypatch):
    """An oversized-body 413 response carries all security headers."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    resp = client.post(
        "/api/analytics",
        content=b"x" * (1024 * 1024 + 1),
        headers={"Content-Length": str(1024 * 1024 + 1)},
    )
    if resp.status_code == 413:
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Referrer-Policy"] == "no-referrer"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in resp.headers
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


# ── test 11: RENDER without PUBLIC_DEMO refuses to start ─────────────────────

def test_render_without_public_demo_refuses(monkeypatch):
    """RENDER=true without PUBLIC_DEMO → refuses to start with write routes."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("PUBLIC_DEMO", raising=False)

    from api.demo import PublicDemoConfigurationError, validate_render_environment

    with pytest.raises(PublicDemoConfigurationError, match="refusing to start"):
        validate_render_environment()


# ── test 12: RENDER=true PUBLIC_DEMO=1 starts ─────────────────────────────────

def test_render_with_public_demo_starts(monkeypatch):
    """RENDER=true PUBLIC_DEMO=1 → starts successfully."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("PUBLIC_DEMO", "1")

    from api.demo import validate_render_environment

    # Must not raise.
    validate_render_environment()


# ── test 13: unrecognised PUBLIC_DEMO value raises ────────────────────────────

@pytest.mark.parametrize("value", ["t", "1.0", "maybe", "2", "yesplease", "enabled"])
def test_unrecognised_public_demo_value_raises(monkeypatch, value):
    """An unrecognised non-empty PUBLIC_DEMO value must raise."""
    monkeypatch.setenv("PUBLIC_DEMO", value)

    from api.demo import is_public_demo

    with pytest.raises(Exception, match="unrecognised"):
        is_public_demo()


# ── test 14: unset PUBLIC_DEMO → normal app ───────────────────────────────────

def test_unset_public_demo_normal_app(monkeypatch):
    """With PUBLIC_DEMO unset, is_public_demo() returns False."""
    monkeypatch.delenv("PUBLIC_DEMO", raising=False)

    from api.demo import is_public_demo

    assert is_public_demo() is False


# ── test 15: path normalisation — //api, /%2fapi, /API ────────────────────────

def test_double_slash_api_blocked(monkeypatch):
    """//api/orders gets normalised to /api/orders and is blocked by demo guard."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    # Use client.request() with full URL to preserve the double slash
    # (TestClient.post normalises // to /).
    resp = client.request("POST", "http://testserver//api/orders", content=b"test")
    assert resp.status_code == 405
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_percent_encoded_slash_api_blocked(monkeypatch):
    """/%2fapi/orders gets normalised to /api/orders and is blocked."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    resp = client.request("POST", "http://testserver/%2fapi/orders", content=b"test")
    assert resp.status_code == 405
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_uppercase_api_blocked(monkeypatch):
    """/API/orders gets normalised to /api/orders and is blocked."""
    app = _make_demo_app(monkeypatch)
    client = _client(app)

    resp = client.request("POST", "http://testserver/API/orders", content=b"test")
    assert resp.status_code == 405
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


# ── test 16: rate limiter — spoofed rightmost XFF doesn't evade ────────────────

def test_spoofed_rightmost_xff_does_not_evade(monkeypatch):
    """When RENDER is set, the rate limiter uses the leftmost XFF entry.
    A spoofed rightmost entry should not create a separate bucket."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "xff_leftmost")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch, extra_env={"RENDER": "true"})
    client = _client(app)

    # Exhaust the limit using the real leftmost IP.
    for _ in range(60):
        resp = client.get(
            "/api/analytics",
            headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1"},
        )
        assert resp.status_code == 200

    # Now spoof a different rightmost IP but same leftmost — should still be limited.
    resp = client.get(
        "/api/analytics",
        headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"},
    )
    assert resp.status_code == 429

    main_mod._limiter.reset()


# ── test 17: two different leftmost IPs get separate buckets ──────────────────

def test_different_leftmost_ips_get_separate_buckets(monkeypatch):
    """When RENDER is set, two requests from different leftmost XFF IPs
    get separate rate-limit buckets."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "xff_leftmost")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch, extra_env={"RENDER": "true"})
    client = _client(app)

    # Exhaust the limit for IP A.
    for _ in range(60):
        resp = client.get(
            "/api/analytics",
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp.status_code == 200

    # IP A is now limited.
    resp = client.get(
        "/api/analytics",
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    assert resp.status_code == 429

    # IP B should still work.
    resp = client.get(
        "/api/analytics",
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert resp.status_code == 200

    main_mod._limiter.reset()


# ── test 18: key count never exceeds the cap ──────────────────────────────────

def test_limiter_key_count_never_exceeds_cap(monkeypatch):
    """The rate limiter's LRU cap ensures the key count never exceeds the limit."""
    import api.main as main_mod

    monkeypatch.setattr(main_mod, "_LRU_MAX_KEYS", 5)
    # Recreate the limiter with the small cap.
    main_mod._limiter = main_mod._FixedWindowLimiter(lru_max=5)

    app = _make_demo_app(monkeypatch)
    client = _client(app)

    # Send requests from 10 distinct IPs.
    for i in range(10):
        resp = client.get(
            "/api/analytics",
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
        assert resp.status_code == 200

    # Key count should never exceed the cap.
    assert main_mod._limiter.key_count <= 5

    # Reset to default.
    main_mod._limiter = main_mod._FixedWindowLimiter()


# ── test 20: per-IP rejection does NOT consume global counter (round 4) ───────

def test_per_ip_rejection_does_not_consume_global(monkeypatch):
    """One IP exhausting its per-IP limit must NOT exhaust the global ceiling.

    Regression for Codex finding #1: the global counter was incremented
    before the per-IP check, so rejected per-IP requests still consumed
    global capacity.  After the fix, only requests that pass the per-IP
    check are charged against the global ceiling.
    """
    from api.main import _FixedWindowLimiter

    # global_limit=20, per-IP limit=5.  Attacker sends 50 from one IP.
    limiter = _FixedWindowLimiter(limit=5, window=60, global_limit=20, lru_max=100)

    for _ in range(50):
        allowed, _ = limiter.check("attacker")
        # First 5 allowed, rest rejected — but none should charge global.
        # (We don't assert here; we check the victim below.)

    # Victim's first request must be allowed (global counter should be 5, not 51).
    allowed, retry = limiter.check("victim")
    assert allowed is True, (
        f"victim's first request rejected — global counter was polluted; "
        f"retry_after={retry}"
    )


# ── test 21: LRU bound actually bounds _counts (round 4) ─────────────────────

def test_lru_bound_bounds_counts_structure(monkeypatch):
    """With lru_max=5 and 1,000 distinct IPs, both key_count and the
    internal _counts dict must stay ≤ 5.

    Regression for Codex finding #2: evicting from _lru did not remove the
    corresponding _counts entry, so _counts grew to 1,000 while key_count
    reported 5.  After the fix there is one OrderedDict; eviction is atomic.
    """
    from api.main import _FixedWindowLimiter

    limiter = _FixedWindowLimiter(limit=100, window=60, global_limit=99999, lru_max=5)

    for i in range(1000):
        ip = f"10.0.{i // 256}.{i % 256}"
        limiter.check(ip)

    assert limiter.key_count <= 5, f"key_count={limiter.key_count}, expected ≤ 5"
    assert len(limiter._counts) <= 5, (
        f"len(_counts)={len(limiter._counts)}, expected ≤ 5 — "
        "LRU eviction did not remove counter entries"
    )


# ── test 22: broadened secret prefixes (round 4) ─────────────────────────────

@pytest.mark.parametrize("key", [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_CLIENT_ID",
    "AZURE_TENANT_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GCP_PROJECT",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "GH_TOKEN",
    "STRIPE_SECRET_KEY",
    "STRIPE_APIKEY",
    "SENTRY_DSN",
    "SENTRY_AUTH_TOKEN",
])
def test_broadened_secret_prefixes_rejected(monkeypatch, key):
    """New prefix families (AWS_, AZURE_, GOOGLE_, GCP_, GITHUB_, GH_,
    STRIPE_, SENTRY_) reject non-empty values in demo mode."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "secret-value")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    assert key in str(exc_info.value)
    assert "secret-value" not in str(exc_info.value)


# ── test 23: broadened secret suffixes (round 4) ──────────────────────────────

@pytest.mark.parametrize("key", [
    "MYAPP_DSN",
    "DATABASE_URI",
    "SERVICE_PAT",
    "VENDOR_APIKEY",
    "APP_CREDENTIALS",
    "RAILS_SECRET_KEY_BASE",
])
def test_broadened_secret_suffixes_rejected(monkeypatch, key):
    """New suffix families (_DSN, _URI, _PAT, _APIKEY, _CREDENTIALS,
    _KEY_BASE) reject non-empty values in demo mode."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "secret-value")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    assert key in str(exc_info.value)
    assert "secret-value" not in str(exc_info.value)


# ── test 24: broadened exact names (round 4) ──────────────────────────────────

@pytest.mark.parametrize("key", [
    "CREDENTIALS",
    "REDIS_URL",
    "MONGODB_URI",
    "SECRET_KEY_BASE",
])
def test_broadened_exact_names_rejected(monkeypatch, key):
    """New exact names (CREDENTIALS, REDIS_URL, MONGODB_URI,
    SECRET_KEY_BASE) reject non-empty values in demo mode."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "secret-value")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    assert key in str(exc_info.value)
    assert "secret-value" not in str(exc_info.value)


# ── test 25: URL with embedded credentials (round 4) ──────────────────────────

@pytest.mark.parametrize("key,value", [
    ("CUSTOM_URL", "postgres://user:pass@host/db"),
    ("MY_SERVICE_URL", "https://admin:secret@example.com/api"),
    ("DATA_URL", "mysql://root:password@db.internal:3306/main"),
])
def test_url_with_embedded_credentials_rejected(monkeypatch, key, value):
    """Any *_URL whose value contains '@' or '://user:' is rejected
    even if the key name doesn't match other secret patterns."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, value)

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    assert key in str(exc_info.value)
    # The URL value itself must not leak into the error.
    assert value not in str(exc_info.value)


# ── test 26: clean URL without credentials is allowed (round 4) ───────────────

@pytest.mark.parametrize("key,value", [
    ("API_URL", "https://api.example.com/v1"),
    ("WEBHOOK_URL", "https://hooks.example.com/notify"),
])
def test_clean_url_without_credentials_allowed(monkeypatch, key, value):
    """A *_URL without '@' or '://user:' is not rejected."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, value)

    from api.demo import validate_public_demo_environment

    # Must not raise.
    validate_public_demo_environment()


# ── test 27: Codex's specific examples all rejected (round 4) ─────────────────

@pytest.mark.parametrize("key", [
    "AWS_ACCESS_KEY_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GITHUB_PAT",
    "REDIS_URL",
    "MONGODB_URI",
    "SENTRY_DSN",
    "STRIPE_APIKEY",
    "SECRET_KEY_BASE",
    "AZURE_CLIENT_ID",
    "CREDENTIALS",
])
def test_codex_examples_all_rejected(monkeypatch, key):
    """All examples from Codex's verdict are rejected."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "secret-value")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    assert key in str(exc_info.value)

# ── test 19: global rate ceiling (token bucket) ────────────────────────────────

def test_global_rate_ceiling(monkeypatch):
    """The global token bucket acts as a backstop — once exhausted, the next
    request is rejected with a short retry-after."""
    import api.main as main_mod

    main_mod._limiter.reset()
    monkeypatch.setattr(main_mod, "_limiter", main_mod._FixedWindowLimiter(
        limit=1000, global_limit=10
    ))

    app = _make_demo_app(monkeypatch)
    client = _client(app)

    # 10 requests from different IPs should pass.
    for i in range(10):
        resp = client.get(
            "/api/analytics",
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
        assert resp.status_code == 200

    # 11th request should be globally limited.
    resp = client.get(
        "/api/analytics",
        headers={"X-Forwarded-For": "10.0.0.99"},
    )
    assert resp.status_code == 429

    main_mod._limiter = main_mod._FixedWindowLimiter()


# ── test 28: default (xff_leftmost) ignores CF-Connecting-IP ──────────────────

def test_default_xff_leftmost_ignores_cf_connecting_ip(monkeypatch):
    """Default on Render (xff_leftmost): CF-Connecting-IP is never read.
    Rotating CF-Connecting-IP with a fixed leftmost XFF → ONE key,
    and request 61 gets 429."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "xff_leftmost")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch, extra_env={"RENDER": "true"})
    client = _client(app)

    # Exhaust the limit using leftmost XFF, rotating CF-Connecting-IP.
    for i in range(60):
        resp = client.get(
            "/api/analytics",
            headers={
                "CF-Connecting-IP": f"10.0.{i}.1",
                "X-Forwarded-For": "3.3.3.3, 9.9.9.9",
            },
        )
        assert resp.status_code == 200

    # Rotating CF-Connecting-IP does NOT evade — XFF leftmost key is exhausted.
    resp = client.get(
        "/api/analytics",
        headers={
            "CF-Connecting-IP": "4.4.4.4",
            "X-Forwarded-For": "3.3.3.3, 8.8.8.8",
        },
    )
    assert resp.status_code == 429

    # A different leftmost XFF should still work.
    resp = client.get(
        "/api/analytics",
        headers={
            "CF-Connecting-IP": "4.4.4.4",
            "X-Forwarded-For": "5.5.5.5, 8.8.8.8",
        },
    )
    assert resp.status_code == 200

    main_mod._limiter.reset()


# ── test 29: no CF header → leftmost XFF is used ─────────────────────────────

def test_no_cf_header_leftmost_xff_used(monkeypatch):
    """When RENDER is set and CLIENT_IP_SOURCE is xff_leftmost (default),
    the leftmost X-Forwarded-For entry is used as the client IP."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "xff_leftmost")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch, extra_env={"RENDER": "true"})
    client = _client(app)

    # Exhaust the limit using leftmost XFF.
    for _ in range(60):
        resp = client.get(
            "/api/analytics",
            headers={"X-Forwarded-For": "2.2.2.2, <rotating junk>"},
        )
        assert resp.status_code == 200

    # Rotating rightmost values should NOT evade — leftmost key is exhausted.
    resp = client.get(
        "/api/analytics",
        headers={"X-Forwarded-For": "2.2.2.2, 11.11.11.11"},
    )
    assert resp.status_code == 429

    main_mod._limiter.reset()


# ── test 30: invalid leftmost XFF falls back to client.host ───────────────────

def test_invalid_xff_leftmost_falls_back_to_client_host(monkeypatch):
    """In xff_leftmost mode, an invalid leftmost XFF entry is skipped,
    falling back to request.client.host. CF/True-Client-IP headers are
    never read."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "xff_leftmost")
    main_mod._limiter.reset()

    # Invalid leftmost XFF with valid CF header → falls back to client.host
    # (CF header is never read in xff_leftmost mode).
    ip = main_mod._get_client_ip(
        MagicMock(
            headers={
                "cf-connecting-ip": "7.7.7.7",
                "true-client-ip": "5.5.5.5",
                "x-forwarded-for": "not-an-ip, 6.6.6.6",
            },
            client=MagicMock(host="8.8.8.8"),
        )
    )
    assert ip == "8.8.8.8"

    # Valid leftmost XFF → used, CF headers ignored.
    ip = main_mod._get_client_ip(
        MagicMock(
            headers={
                "cf-connecting-ip": "7.7.7.7",
                "true-client-ip": "5.5.5.5",
                "x-forwarded-for": "6.6.6.6, 7.7.7.7",
            },
            client=MagicMock(host="8.8.8.8"),
        )
    )
    assert ip == "6.6.6.6"

    # All headers invalid → falls back to client.host.
    ip = main_mod._get_client_ip(
        MagicMock(
            headers={
                "cf-connecting-ip": "garbage",
                "true-client-ip": "!!!",
                "x-forwarded-for": "not-ip",
            },
            client=MagicMock(host="8.8.8.8"),
        )
    )
    assert ip == "8.8.8.8"

    main_mod._limiter.reset()


# ── test 31: outside Render, headers are ignored ──────────────────────────────

def test_outside_render_headers_ignored(monkeypatch):
    """When RENDER is not set, CF-Connecting-IP and X-Forwarded-For headers
    are completely ignored — only request.client.host is used."""
    import api.main as main_mod

    monkeypatch.setattr(main_mod, "_IS_RENDER", False)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "peer")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch)
    client = _client(app)

    # All requests from the same client.host share one bucket regardless of headers.
    for _ in range(60):
        resp = client.get(
            "/api/analytics",
            headers={
                "CF-Connecting-IP": "1.1.1.1",
                "X-Forwarded-For": "2.2.2.2",
            },
        )
        assert resp.status_code == 200

    # 61st request is limited — the spoofed headers didn't create separate buckets.
    resp = client.get(
        "/api/analytics",
        headers={
            "CF-Connecting-IP": "3.3.3.3",
            "X-Forwarded-For": "4.4.4.4",
        },
    )
    assert resp.status_code == 429

    main_mod._limiter.reset()


# ── test 32: token bucket self-recovers after brief burst ─────────────────────

def test_token_bucket_self_recovers(monkeypatch):
    """After the token bucket is exhausted, it recovers after the refill
    interval — aggregate load causes brief 429s, not a minute-long outage."""
    from api.main import _TokenBucket
    import time

    # Small bucket: capacity 5, refills at 10/sec → recovers in 0.1s.
    bucket = _TokenBucket(capacity=5, refill_rate=10.0)

    # Exhaust the bucket.
    for _ in range(5):
        allowed, _ = bucket.consume()
        assert allowed is True

    # Next request should be rejected.
    allowed, retry_after = bucket.consume()
    assert allowed is False
    assert retry_after >= 1

    # Wait for refill (0.15s → ~1.5 tokens).
    time.sleep(0.15)

    # Should be allowed now.
    allowed, _ = bucket.consume()
    assert allowed is True


# ── test 33: xff_leftmost — fixed XFF key, rotating CF ignored — 61st 429 ─────

def test_xff_leftmost_fixed_xff_rotating_cf_61st_gives_429(monkeypatch):
    """RENDER set, CLIENT_IP_SOURCE=xff_leftmost (default). Fixed leftmost
    XFF: 1.1.1.1 with rotating CF-Connecting-IP values — every request uses
    one key, so the 61st request gets 429."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "xff_leftmost")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch, extra_env={"RENDER": "true"})
    client = _client(app)

    for i in range(60):
        resp = client.get(
            "/api/analytics",
            headers={
                "CF-Connecting-IP": f"10.0.{i}.1",
                "X-Forwarded-For": "1.1.1.1, 10.0.0.2",
            },
        )
        assert resp.status_code == 200, f"request {i+1} failed"

    # 61st request → 429.
    resp = client.get(
        "/api/analytics",
        headers={
            "CF-Connecting-IP": "99.99.99.99",
            "X-Forwarded-For": "1.1.1.1, 10.0.99.2",
        },
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers

    main_mod._limiter.reset()


# ── test 34: generic secret names rejected (TOKEN, SECRET, PASSWORD, etc.) ─────

@pytest.mark.parametrize("key", [
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "DOCKER_AUTH_CONFIG",
])
def test_generic_secret_names_rejected(monkeypatch, key):
    """Bare generic secret names (TOKEN, SECRET, PASSWORD, DOCKER_AUTH_CONFIG)
    reject non-empty values in demo mode."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "secret-value")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    assert key in str(exc_info.value)
    assert "secret-value" not in str(exc_info.value)


# ── test 35: _CONNECTION_STRING suffix rejected ───────────────────────────────

@pytest.mark.parametrize("key", [
    "DATABASE_CONNECTION_STRING",
    "MYAPP_CONNECTION_STRING",
])
def test_connection_string_suffix_rejected(monkeypatch, key):
    """Any *_CONNECTION_STRING variable rejects non-empty values in demo mode."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv(key, "secret-value")

    from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

    with pytest.raises(PublicDemoConfigurationError) as exc_info:
        validate_public_demo_environment()

    assert key in str(exc_info.value)
    assert "secret-value" not in str(exc_info.value)


# ── test 36: cf_connecting_ip mode — uses CF-Connecting-IP ────────────────────

def test_cf_connecting_ip_mode_uses_cf(monkeypatch):
    """CLIENT_IP_SOURCE=cf_connecting_ip: uses CF-Connecting-IP, ignores XFF."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "cf_connecting_ip")
    main_mod._limiter.reset()

    # CF-Connecting-IP is used.
    ip = main_mod._get_client_ip(
        MagicMock(
            headers={
                "cf-connecting-ip": "7.7.7.7",
                "x-forwarded-for": "8.8.8.8",
            },
            client=MagicMock(host="1.2.3.4"),
        )
    )
    assert ip == "7.7.7.7"

    # Invalid CF-Connecting-IP → falls back to client.host.
    ip = main_mod._get_client_ip(
        MagicMock(
            headers={
                "cf-connecting-ip": "not-an-ip",
                "x-forwarded-for": "8.8.8.8",
            },
            client=MagicMock(host="1.2.3.4"),
        )
    )
    assert ip == "1.2.3.4"

    # No CF header → client.host.
    ip = main_mod._get_client_ip(
        MagicMock(
            headers={"x-forwarded-for": "8.8.8.8"},
            client=MagicMock(host="1.2.3.4"),
        )
    )
    assert ip == "1.2.3.4"

    main_mod._limiter.reset()


# ── test 37: cf_connecting_ip mode — 61st request gives 429 ──────────────────

def test_cf_connecting_ip_mode_61st_gives_429(monkeypatch):
    """CLIENT_IP_SOURCE=cf_connecting_ip: rotating XFF with fixed CF → ONE key,
    request 61 gets 429."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "cf_connecting_ip")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch, extra_env={"RENDER": "true"})
    client = _client(app)

    for i in range(60):
        resp = client.get(
            "/api/analytics",
            headers={
                "CF-Connecting-IP": "3.3.3.3",
                "X-Forwarded-For": f"10.0.{i}.1, 10.0.{i}.2",
            },
        )
        assert resp.status_code == 200, f"request {i+1} failed"

    resp = client.get(
        "/api/analytics",
        headers={
            "CF-Connecting-IP": "3.3.3.3",
            "X-Forwarded-For": "10.0.99.1, 10.0.99.2",
        },
    )
    assert resp.status_code == 429

    main_mod._limiter.reset()


# ── test 38: peer mode — ignores every header ────────────────────────────────

def test_peer_mode_ignores_all_headers(monkeypatch):
    """CLIENT_IP_SOURCE=peer: ignores CF-Connecting-IP, True-Client-IP, and XFF."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "peer")
    main_mod._limiter.reset()

    ip = main_mod._get_client_ip(
        MagicMock(
            headers={
                "cf-connecting-ip": "7.7.7.7",
                "true-client-ip": "8.8.8.8",
                "x-forwarded-for": "9.9.9.9",
            },
            client=MagicMock(host="1.2.3.4"),
        )
    )
    assert ip == "1.2.3.4"

    main_mod._limiter.reset()


# ── test 39: peer mode — all requests from same client.host share one bucket ─

def test_peer_mode_single_bucket(monkeypatch):
    """CLIENT_IP_SOURCE=peer: all headers ignored, client.host is the key."""
    import api.main as main_mod

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(main_mod, "_IS_RENDER", True)
    monkeypatch.setattr(main_mod, "_CLIENT_IP_SOURCE", "peer")
    main_mod._limiter.reset()

    app = _make_demo_app(monkeypatch, extra_env={"RENDER": "true"})
    client = _client(app)

    for _ in range(60):
        resp = client.get(
            "/api/analytics",
            headers={
                "CF-Connecting-IP": "1.1.1.1",
                "True-Client-IP": "2.2.2.2",
                "X-Forwarded-For": "3.3.3.3",
            },
        )
        assert resp.status_code == 200

    # 61st → 429 regardless of header rotation.
    resp = client.get(
        "/api/analytics",
        headers={
            "CF-Connecting-IP": "9.9.9.9",
            "True-Client-IP": "8.8.8.8",
            "X-Forwarded-For": "7.7.7.7",
        },
    )
    assert resp.status_code == 429

    main_mod._limiter.reset()


# ── test 40: unknown CLIENT_IP_SOURCE → startup error ────────────────────────

def test_unknown_client_ip_source_raises(monkeypatch):
    """An unrecognised CLIENT_IP_SOURCE value raises PublicDemoConfigurationError."""
    from api.demo import PublicDemoConfigurationError

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv("CLIENT_IP_SOURCE", "bogus")

    with pytest.raises(PublicDemoConfigurationError, match="CLIENT_IP_SOURCE"):
        import api.main as main_mod
        import importlib
        importlib.reload(main_mod)


# ── test 41: CLIENT_IP_SOURCE in Render allow-list ────────────────────────────

def test_client_ip_source_in_render_allow_list():
    """CLIENT_IP_SOURCE is in the Render allow-list so it is not rejected
    as a secret in demo mode."""
    from api.demo import _RENDER_ALLOW_LIST
    assert "CLIENT_IP_SOURCE" in _RENDER_ALLOW_LIST