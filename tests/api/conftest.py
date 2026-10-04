"""Fixtures for the API-layer authentication/authorization test suite.

These tests exercise the FastAPI app with the Lakebase and Spark/Delta
dependencies overridden, so no network or live backend is required. The only
module under test is ``api.deps`` (and the routes that consume it); the Lakebase
store is replaced by an in-memory :class:`FakeLakebase`.
"""

from __future__ import annotations

import pytest


class FakeLakebase:
    """In-memory stand-in for ``db.lakebase.Lakebase``.

    Models just enough of the ``users`` table for ``api.deps._ensure_user``:
    an idempotent upsert that provisions new principals as ``viewer`` and reads
    existing roles back. Setting ``fail = True`` simulates a database outage.
    """

    def __init__(self, roles: dict[str, str] | None = None):
        self.roles: dict[str, str] = dict(roles or {})
        self.fail = False

    def execute(self, query: str, params=None, *, transaction: bool = False):
        if self.fail:
            raise RuntimeError("simulated database outage")
        if "INSERT INTO users" in query:
            user_id, role = params[0], params[2]
            if user_id not in self.roles:
                self.roles[user_id] = role
                return [(role,)]
            return []
        return []

    def fetchone(self, query: str, params=None):
        if self.fail:
            raise RuntimeError("simulated database outage")
        user_id = params[0]
        if user_id in self.roles:
            return (self.roles[user_id],)
        return None


@pytest.fixture(autouse=True)
def _prod_env(monkeypatch):
    """Run in production auth mode by default; individual tests may opt into dev."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("AUTH_DEV_USER", raising=False)


@pytest.fixture
def fake_lakebase(monkeypatch) -> FakeLakebase:
    fake = FakeLakebase()
    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: fake)
    # agent.* bind ``get_lakebase`` at import time; patch those references too
    # so any route that reads/writes through a tool uses the fake store.
    for module_name in ("agent.tools_retrieval", "agent.tools_write"):
        try:
            import importlib

            module = importlib.import_module(module_name)
            monkeypatch.setattr(module, "get_lakebase", lambda: fake)
        except Exception:  # noqa: BLE001 - tools may be absent in some layouts
            pass
    return fake


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.main import create_app

    return TestClient(create_app())


@pytest.fixture
def authed_headers():
    return {"x-forwarded-email": "trader@example.com"}
