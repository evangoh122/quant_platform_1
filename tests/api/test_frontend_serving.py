"""Tests for frontend serving behavior.

Verifies that:
- When frontend/dist exists, GET / serves index.html
- When frontend/dist is missing, GET / returns a JSON hint
- API routes work regardless of frontend/dist presence
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from api.demo import _is_unsafe_key


@pytest.fixture(autouse=True)
def _demo_env(monkeypatch):
    """Run in public-demo mode so auth and lakebase are skipped.

    Strips any ambient env vars that ``api.demo._is_unsafe_key`` would reject
    so the demo-mode validation is deterministic regardless of the caller's
    shell (e.g. ``CLAUDE_CODE_MESSAGING_TOKEN``, ``DATABRICKS_WORKSPACE_ID``).
    """
    for key in list(os.environ):
        if key == "PUBLIC_DEMO":
            continue
        if _is_unsafe_key(key, os.environ.get(key, "")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.delenv("DATABRICKS_APP_PORT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)


@pytest.fixture()
def app_with_dist(tmp_path):
    """App with a temporary frontend/dist directory."""
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>test</html>")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('test')")

    with patch("api.main.FRONTEND_DIST", dist):
        from api.main import create_app
        yield create_app(), dist


@pytest.fixture()
def app_without_dist(tmp_path):
    """App without frontend/dist."""
    missing = tmp_path / "frontend" / "dist"

    with patch("api.main.FRONTEND_DIST", missing):
        from api.main import create_app
        yield create_app()


class TestFrontendServed:
    """When frontend/dist exists, the SPA is served at /."""

    def test_root_returns_index_html(self, app_with_dist):
        app, dist = app_with_dist
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "<html>test</html>" in resp.text

    def test_assets_are_served(self, app_with_dist):
        app, dist = app_with_dist
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/assets/app.js")
        assert resp.status_code == 200
        assert "console.log" in resp.text

    def test_deep_link_returns_index_html(self, app_with_dist):
        app, dist = app_with_dist
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/results/walk-forward")
        assert resp.status_code == 200
        assert "<html>test</html>" in resp.text


class TestFrontendMissing:
    """When frontend/dist is absent, GET / returns a JSON hint."""

    def test_root_returns_hint_json(self, app_without_dist):
        from fastapi.testclient import TestClient

        app = app_without_dist
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "frontend not built"
        assert "build_frontend" in data["hint"]

    def test_api_health_still_works(self, app_without_dist):
        from fastapi.testclient import TestClient

        app = app_without_dist
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_api_signals_still_works(self, app_without_dist):
        from fastapi.testclient import TestClient

        app = app_without_dist
        client = TestClient(app)
        resp = client.get("/api/signals")
        assert resp.status_code == 200

    def test_api_analytics_still_works(self, app_without_dist):
        from fastapi.testclient import TestClient

        app = app_without_dist
        client = TestClient(app)
        resp = client.get("/api/analytics")
        assert resp.status_code == 200


class TestAmbientSecretsIsolation:
    """Ambient secret-looking env vars must not break these fixtures."""

    def test_secret_env_var_does_not_break_demo_app(self, app_with_dist):
        """The _demo_env fixture strips ambient secrets, so the app starts.

        This test proves the fixture works: even though the caller's shell may
        carry secret-looking vars, the fixture removes them before create_app()
        runs.  The app_with_dist fixture would have raised
        PublicDemoConfigurationError if any leaked through.
        """
        app, dist = app_with_dist
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_safety_check_raises_when_own_env_has_secret(self, monkeypatch):
        """The safety check still raises when the app's OWN env has a secret.

        This proves the fixture is not accidentally disabling the guard — it
        only strips *ambient* vars, not ones injected after the fixture.
        """
        monkeypatch.setenv("PUBLIC_DEMO", "1")
        monkeypatch.setenv("APP_ENV", "demo")
        monkeypatch.setenv("INJECTED_SECRET_TOKEN", "s3cret")

        from api.main import create_app
        from api.demo import PublicDemoConfigurationError

        with pytest.raises(PublicDemoConfigurationError, match="INJECTED_SECRET_TOKEN"):
            create_app()