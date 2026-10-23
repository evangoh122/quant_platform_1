"""Market Spreads is live-only: ``/api/spreads`` is absent from the public demo.

Every Market Spreads chart reads a lakehouse table (``silver_ohlcv_day_adjusted``
or ``bronze_fed_series``) through ``api.deps.read_delta``.  In public-demo mode
that helper only serves pre-exported snapshots, and no snapshot export exists
for these sources yet (a separate, later PR adds them), so a mounted router
would answer with five "unavailable" charts.  ``create_app()`` therefore mounts
the router only in the production factory, and ``/api/health`` reports
``demo=true`` so the frontend can hide the destination.

Mutation proof: moving ``application.include_router(spreads.router, ...)`` back
into the always-registered block in ``api/main.py`` makes
``test_demo_app_does_not_mount_spreads`` fail (the path appears in the route
table and the request returns 200 instead of 404).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from api.demo import _is_unsafe_key


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """Strip ambient credentials and hosted-public markers for create_app().

    Demo mode refuses to start with credential-looking variables set, so a
    developer shell or CI runner must not decide the outcome of these tests.
    Only the predicate from ``api/demo.py`` is used; no value is read out.
    """
    for key in list(os.environ):
        if key == "PUBLIC_DEMO":
            continue
        if _is_unsafe_key(key, os.environ.get(key, "")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("SPACE_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_APP_PORT", raising=False)
    yield


def _build_app(tmp_path: Path):
    """Build the app factory with no frontend/dist.

    Without the SPA catch-all (``/{full_path:path}``) an unmounted API path
    returns 404 in every checkout, whether or not ``frontend/dist`` was built.
    """
    from api.main import create_app

    with patch("api.main.FRONTEND_DIST", tmp_path / "missing-frontend-dist"):
        return create_app()


def _api_route_paths(app) -> set[str]:
    """Collect every path under ``/api`` the app actually registered.

    ``include_router`` registers an included-router object carrying the prefix
    and the original router's routes; plain routes carry ``path`` directly.
    """
    paths: set[str] = set()
    for route in app.routes:
        if hasattr(route, "include_context"):
            prefix = route.include_context.prefix or ""
            for inner in route.original_router.routes:
                inner_path = getattr(inner, "path", None)
                if inner_path is None:
                    continue
                full_path = f"{prefix}{inner_path}"
                if full_path.startswith("/api"):
                    paths.add(full_path)
        else:
            path = getattr(route, "path", "")
            if path.startswith("/api"):
                paths.add(path)
    return paths


def test_demo_app_does_not_mount_spreads(monkeypatch, tmp_path):
    """PUBLIC_DEMO=1 registers no /api/spreads route at all."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("PUBLIC_DEMO", "1")
    app = _build_app(tmp_path)

    paths = _api_route_paths(app)
    # Prove the walker sees routes registered at the prefix itself (path ""),
    # so the absence below is real rather than a blind enumeration.
    assert "/api/health" in paths
    assert "/api/spreads" not in paths

    response = TestClient(app).get("/api/spreads")
    assert response.status_code == 404


def test_production_factory_mounts_spreads(monkeypatch, tmp_path):
    """The live factory still registers the router (it is live-only, not gone)."""
    monkeypatch.delenv("PUBLIC_DEMO", raising=False)
    app = _build_app(tmp_path)

    paths = _api_route_paths(app)
    assert "/api/spreads" in paths
    # Market Spreads is a sibling of the other always-or-live routers, not a
    # replacement for them: the read-only set must still be mounted.
    assert "/api/health" in paths
    assert "/api/market/{symbol}" in paths or any(
        p.startswith("/api/market") for p in paths
    )


def test_demo_health_reports_demo_true(monkeypatch, tmp_path):
    """The frontend learns demo mode from /api/health, so it must say so."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("PUBLIC_DEMO", "1")
    app = _build_app(tmp_path)

    payload = TestClient(app).get("/api/health").json()

    assert payload["demo"] is True
    assert payload["status"] == "degraded"


def test_health_response_defaults_to_live():
    """A response built without the flag is live, so an old client never hides."""
    from api.schemas import HealthResponse

    assert HealthResponse(status="ok").demo is False
