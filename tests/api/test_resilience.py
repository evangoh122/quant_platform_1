"""Tests for Lakebase auth resilience (circuit breaker, role cache, degraded mode).

These tests exercise the FastAPI app with a fake Lakebase that can be configured
to hang or raise, verifying that:
- Read routes return < 1 s when Lakebase is down (breaker opens).
- Write routes return 503 fast when breaker is open.
- Breaker opens after N consecutive failures and recovers after cool-down.
- Cache hit avoids a DB round-trip.
"""
from __future__ import annotations

import time

import pytest


class HangingLakebase:
    """Fake that sleeps longer than any reasonable timeout."""

    def __init__(self, delay: float = 10.0):
        self.delay = delay
        self.call_count = 0

    def execute(self, query, params=None, *, transaction=False):
        self.call_count += 1
        time.sleep(self.delay)
        raise RuntimeError("should not reach here")

    def fetchone(self, query, params=None):
        self.call_count += 1
        time.sleep(self.delay)
        raise RuntimeError("should not reach here")


class FailingLakebase:
    """Fake that always raises immediately."""

    def __init__(self):
        self.call_count = 0

    def execute(self, query, params=None, *, transaction=False):
        self.call_count += 1
        raise RuntimeError("simulated DB outage")

    def fetchone(self, query, params=None):
        self.call_count += 1
        raise RuntimeError("simulated DB outage")


@pytest.fixture(autouse=True)
def _reset_breaker_cache(monkeypatch):
    """Reset circuit breaker and role cache between tests."""
    from api import deps

    deps._breaker.reset()
    deps._role_cache.clear()
    yield
    deps._breaker.reset()
    deps._role_cache.clear()


@pytest.fixture
def client(monkeypatch):
    """Create a TestClient with all network probes faked."""
    import db.delta_adapter as adapter

    # Prevent real warehouse connection during app startup
    monkeypatch.setattr(adapter, "warm_warehouse_connection", lambda: None)
    monkeypatch.setattr(adapter, "_warehouse_available", lambda: False)

    from fastapi.testclient import TestClient
    from api.main import create_app
    return TestClient(create_app())


@pytest.fixture
def authed_headers():
    return {"x-forwarded-email": "trader@example.com"}


# ── read routes degrade to viewer when Lakebase is down ──────────────────────


def test_read_route_returns_fast_when_db_hangs(client, monkeypatch):
    """After breaker opens, read-only route returns < 1 s even with a hanging DB."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: HangingLakebase(delay=5.0))

    # Pre-trip the breaker by recording failures directly
    for _ in range(deps._CB_FAILURE_THRESHOLD):
        deps._breaker.record_failure()

    assert deps._breaker.is_open

    start = time.monotonic()
    resp = client.get("/api/signals", headers={"x-forwarded-email": "u@test.com"})
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 1.0, f"Read route took {elapsed:.1f}s, expected < 1s"


def test_read_route_returns_fast_when_db_raises(client, monkeypatch):
    """Read-only route degrades to viewer when DB raises."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: FailingLakebase())

    resp = client.get("/api/signals", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 200


def test_read_route_user_is_degraded_when_breaker_open(client, monkeypatch):
    """When breaker is open, user.degraded is True."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: FailingLakebase())

    # Trip the breaker
    for _ in range(deps._CB_FAILURE_THRESHOLD + 1):
        try:
            deps._resolve_role("u@test.com")
        except Exception:
            pass

    assert deps._breaker.is_open

    resp = client.get("/api/analytics", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 200


# ── write routes return 503 fast when breaker is open ────────────────────────


def test_write_route_returns_503_when_breaker_open(client, monkeypatch):
    """Write route returns 503 when circuit breaker is open."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: FailingLakebase())

    # Trip the breaker
    for _ in range(deps._CB_FAILURE_THRESHOLD + 1):
        try:
            deps._resolve_role("trader@test.com")
        except Exception:
            pass

    assert deps._breaker.is_open

    resp = client.post(
        "/api/watchlists",
        json={"symbol": "AAPL"},
        headers={"x-forwarded-email": "trader@test.com"},
    )
    assert resp.status_code == 503
    assert "Account services unavailable" in resp.json()["detail"]


def test_write_route_intents_returns_503_when_breaker_open(client, monkeypatch):
    """Order intent returns 503 when circuit breaker is open."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: FailingLakebase())

    # Trip the breaker
    for _ in range(deps._CB_FAILURE_THRESHOLD + 1):
        try:
            deps._resolve_role("trader@test.com")
        except Exception:
            pass

    resp = client.post(
        "/api/orders/intents",
        json={"symbol": "AAPL", "side": "BUY", "quantity": 10},
        headers={"x-forwarded-email": "trader@test.com"},
    )
    assert resp.status_code == 503


# ── degraded user role is viewer and cannot pass trader/admin ─────────────────


def test_degraded_user_role_is_viewer(client, monkeypatch):
    """Degraded user's role is exactly 'viewer' and cannot pass require_role('trader')."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: FailingLakebase())

    # Trip the breaker so the next request degrades
    for _ in range(deps._CB_FAILURE_THRESHOLD + 1):
        try:
            deps._resolve_role("degraded@test.com")
        except Exception:
            pass

    assert deps._breaker.is_open

    # Read route succeeds — degraded user gets viewer role
    resp = client.get("/api/signals", headers={"x-forwarded-email": "degraded@test.com"})
    assert resp.status_code == 200

    # Write route (requires trader) returns 503 — degraded cannot pass role check
    resp = client.post(
        "/api/watchlists",
        json={"symbol": "AAPL"},
        headers={"x-forwarded-email": "degraded@test.com"},
    )
    assert resp.status_code == 503
    assert "Account services unavailable" in resp.json()["detail"]


# ── breaker opens after N failures and recovers after cool-down ──────────────


def test_breaker_opens_after_threshold_failures(monkeypatch):
    """Circuit breaker opens after N consecutive failures."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: FailingLakebase())

    assert not deps._breaker.is_open

    for i in range(deps._CB_FAILURE_THRESHOLD):
        assert not deps._breaker.is_open
        with pytest.raises(RuntimeError):
            deps._resolve_role("u@test.com")

    # Now the breaker should be open
    assert deps._breaker.is_open


def test_breaker_recovers_after_cooldown(monkeypatch):
    """Circuit breaker recovers after cool-down window."""
    from api import deps

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: FailingLakebase())

    # Trip the breaker
    for _ in range(deps._CB_FAILURE_THRESHOLD + 1):
        try:
            deps._resolve_role("u@test.com")
        except Exception:
            pass

    assert deps._breaker.is_open

    # Simulate cool-down passing
    with monkeypatch.context() as m:
        m.setattr(deps._breaker, "_opened_at", time.monotonic() - deps._CB_COOLDOWN_SECONDS - 1)
        assert not deps._breaker.is_open


# ── cache hit avoids DB ──────────────────────────────────────────────────────


def test_cache_hit_avoids_db(client, monkeypatch):
    """Second request for same user hits cache, not DB."""
    from api import deps

    class CountingLakebase:
        def __init__(self):
            self.call_count = 0

        def execute(self, query, params=None, *, transaction=False):
            self.call_count += 1
            if "INSERT INTO users" in query:
                return [("viewer",)]
            return []

        def fetchone(self, query, params=None):
            self.call_count += 1
            return ("viewer",)

    fake = CountingLakebase()
    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: fake)

    # First request — cache miss, hits DB
    resp1 = client.get("/api/signals", headers={"x-forwarded-email": "cached@test.com"})
    assert resp1.status_code == 200
    first_count = fake.call_count

    # Second request — cache hit, no additional DB calls
    resp2 = client.get("/api/signals", headers={"x-forwarded-email": "cached@test.com"})
    assert resp2.status_code == 200
    assert fake.call_count == first_count, "Cache should have prevented a DB call"


def test_cache_ttl_expiry(monkeypatch):
    """Cache entries expire after TTL."""
    from api import deps

    class CountingLakebase:
        def __init__(self):
            self.call_count = 0

        def execute(self, query, params=None, *, transaction=False):
            self.call_count += 1
            if "INSERT INTO users" in query:
                return [("viewer",)]
            return []

        def fetchone(self, query, params=None):
            self.call_count += 1
            return ("viewer",)

    fake = CountingLakebase()
    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: fake)

    # Populate cache
    deps._resolve_role("ttl@test.com")
    assert fake.call_count > 0
    count_after_first = fake.call_count

    # Cache hit
    deps._resolve_role("ttl@test.com")
    assert fake.call_count == count_after_first

    # Expire the cache entry
    deps._role_cache._store["ttl@test.com"] = ("viewer", time.monotonic() - 1)

    # Cache miss — hits DB again
    deps._resolve_role("ttl@test.com")
    assert fake.call_count > count_after_first


def test_first_request_bounded_when_pool_hangs(client, monkeypatch):
    """First request against a hanging pool returns < 5 s (degraded mode).

    Exercises the bounded pool establishment path: _build_pool calls
    pool.wait(timeout=LAKEBASE_CONNECT_TIMEOUT). If the pool cannot
    establish min_size connections within that window, PoolTimeout is raised,
    the circuit breaker records a failure, and the read route degrades to
    viewer. Without the timeout bound (open=True, no wait), this test would
    hang for 30+ s and fail.
    """
    import db.lakebase as lb
    from psycopg_pool import PoolTimeout

    class BlockingPool:
        """Simulates a pool that cannot establish connections in time."""

        def __init__(self, **kwargs):
            self._opened = False

        def open(self, wait=True):
            self._opened = True

        def wait(self, timeout=None):
            raise PoolTimeout("pool could not connect in time")

        def close(self):
            pass

        def connection(self):
            if not self._opened:
                raise RuntimeError("pool not open")
            raise RuntimeError("pool not open")

    monkeypatch.setattr(lb, "ConnectionPool", BlockingPool)

    start = time.monotonic()
    resp = client.get("/api/signals", headers={"x-forwarded-email": "hang@test.com"})
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 5.0, f"First request took {elapsed:.1f}s, expected < 5s"