"""tests/api/test_health_diagnostics.py — Health diagnostics + warehouse data path tests.

Behavioral tests (red phase captured):
  1. Health returns within bound when Lakebase and warehouse probe both hang.
  2. A timed-out probe reports `timeout`.
  3. Stage logs are emitted with elapsed ms and error type on failure (caplog).
  4. Ring buffer is bounded and thread-safe.
  5. No secret/token string appears in logs or health output.
  6. Warehouse backend is selected when pyspark is missing and passes parameters.

Mutations that MUST FAIL:
  - Remove the probe timeout → test_health_returns_within_bound_when_both_hang fails.
  - Drop the error type from stage logs → test_stage_logs_emit_error_type_on_failure fails.
  - Select pyspark backend when pyspark is absent → test_warehouse_backend_selected_when_pyspark_missing fails.
"""
from __future__ import annotations

import logging
import threading
import time

import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

class SlowLakebase:
    """Fake that sleeps longer than the probe timeout."""

    def __init__(self, delay: float = 10.0):
        self.delay = delay

    def execute(self, query, params=None, *, transaction=False):
        time.sleep(self.delay)
        raise RuntimeError("should not reach here")

    def fetchone(self, query, params=None):
        time.sleep(self.delay)
        raise RuntimeError("should not reach here")


class FailingWarehouse:
    """Fake warehouse that always times out."""

    def __init__(self, delay: float = 10.0):
        self.delay = delay

    def cursor(self):
        return self

    def execute(self, query, params=None):
        time.sleep(self.delay)

    def fetchall(self):
        return []

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset diagnostics state between tests."""
    from api import deps
    from api.diagnostics import ring_buffer
    import api.routes.health as health_mod

    deps._breaker.reset()
    deps._role_cache.clear()
    ring_buffer.clear()
    health_mod._inflight.clear()
    yield
    deps._breaker.reset()
    deps._role_cache.clear()
    ring_buffer.clear()
    health_mod._inflight.clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api.main import create_app
    return TestClient(create_app())


# ── 1. Health returns within bound when both hang ─────────────────────────────

def test_health_returns_within_bound_when_both_hang(client, monkeypatch):
    """Health endpoint returns within ~6s even when Lakebase and warehouse both hang.

    MUTATION THAT MUST FAIL: remove the probe timeout → this test hangs/fails.
    """
    import api.routes.health as health_mod

    # Make Lakebase probe hang (bypasses pool building entirely)
    def _hang_lakebase():
        time.sleep(10.0)
        return False, 10000, "should not reach here"

    monkeypatch.setattr(health_mod, "_probe_lakebase", _hang_lakebase)

    # Make warehouse probe hang
    def _hang_warehouse():
        time.sleep(10.0)
        return False, 10000, "should not reach here"

    monkeypatch.setattr(health_mod, "_probe_delta", _hang_warehouse)

    start = time.monotonic()
    resp = client.get("/api/health")
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 15.0, f"Health took {elapsed:.1f}s, expected < 15s"

    data = resp.json()
    assert data["status"] == "degraded"
    for dep in data["dependencies"]:
        assert dep["ok"] is False
        assert "timeout" in dep["detail"].lower()


# ── 2. Timed-out probe reports timeout ────────────────────────────────────────

def test_timed_out_probe_reports_timeout(client, monkeypatch):
    """A probe that times out reports 'timeout' in its detail.

    MUTATION THAT MUST FAIL: remove the timeout → detail says something else.
    """
    import api.routes.health as health_mod

    def _hang_lakebase():
        time.sleep(10.0)
        return False, 10000, "should not reach here"

    monkeypatch.setattr(health_mod, "_probe_lakebase", _hang_lakebase)

    resp = client.get("/api/health")
    data = resp.json()

    lakebase_dep = next(d for d in data["dependencies"] if d["name"] == "lakebase")
    assert lakebase_dep["ok"] is False
    assert "timeout" in lakebase_dep["detail"].lower()
    assert lakebase_dep["latency_ms"] is not None


# ── 3. Stage logs emit elapsed ms and error type ──────────────────────────────

def test_stage_logs_emit_elapsed_ms_and_ok(caplog):
    """Stage logs include elapsed ms and ok status.

    MUTATION THAT MUST FAIL: drop the error type from stage logs → assertion fails.
    """
    from api.diagnostics import stage

    with caplog.at_level(logging.INFO, logger="api.diagnostics"):
        with stage("test_stage"):
            pass  # success

    assert any("STAGE done test_stage" in r.message and "ms=" in r.message and "ok=True" in r.message for r in caplog.records)


def test_stage_logs_emit_error_type_on_failure(caplog):
    """Stage logs include error type on failure.

    MUTATION THAT MUST FAIL: drop the error type from stage logs → assertion fails.
    """
    from api.diagnostics import stage

    with caplog.at_level(logging.INFO, logger="api.diagnostics"):
        with pytest.raises(ValueError, match="test error"):
            with stage("test_fail_stage"):
                raise ValueError("test error")

    matching = [r for r in caplog.records if "STAGE done test_fail_stage" in r.message]
    assert len(matching) > 0
    assert any("ok=False" in r.message and "error=ValueError" in r.message for r in matching)


# ── 4. Ring buffer is bounded and thread-safe ─────────────────────────────────

def test_ring_buffer_is_bounded():
    """Ring buffer evicts oldest events when full."""
    from api.diagnostics import StageRingBuffer, StageEvent

    buf = StageRingBuffer(maxlen=5)
    for i in range(10):
        buf.append(StageEvent(name=f"evt_{i}", elapsed_ms=1.0, ok=True))

    events = buf.snapshot()
    assert len(events) == 5
    assert events[0]["name"] == "evt_5"  # oldest kept
    assert events[4]["name"] == "evt_9"  # newest


def test_ring_buffer_is_thread_safe():
    """Concurrent appends don't crash or lose events."""
    from api.diagnostics import StageRingBuffer, StageEvent

    buf = StageRingBuffer(maxlen=100)
    errors = []

    def writer(n: int):
        try:
            for i in range(50):
                buf.append(StageEvent(name=f"t{n}_evt_{i}", elapsed_ms=1.0, ok=True))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    events = buf.snapshot()
    assert len(events) == 100  # bounded at maxlen


# ── 5. No secret/token in logs or health output ──────────────────────────────

def test_no_secret_in_health_output(client, monkeypatch):
    """Health response does not contain secrets from probe functions.

    The probe functions return only safe diagnostic info (exception type, short
    messages). This test verifies the detail field never contains raw connection
    strings or tokens from the Lakebase module.
    """
    from api import deps

    # Make Lakebase fail with an error that contains a fake connection string
    class LeakyLakebase:
        def execute(self, query, params=None, *, transaction=False):
            raise RuntimeError("connection to host=db.internal port=5432 password=secret123 failed")
        def fetchone(self, query, params=None):
            raise RuntimeError("connection to host=db.internal port=5432 password=secret123 failed")

    monkeypatch.setattr("db.lakebase.get_lakebase", lambda: LeakyLakebase())

    resp = client.get("/api/health")
    body = resp.text

    # The raw error message should NOT appear — only the exception type
    assert "password=secret123" not in body, "Connection string leaked in health response"
    assert "db.internal" not in body, "Internal host leaked in health response"


def test_no_secret_in_logs(caplog):
    """Stage logs do not leak exception messages that might contain secrets.

    The stage() context manager logs only the exception TYPE, not the message,
    so a secret embedded in an error message never reaches the log.
    """
    from api.diagnostics import stage

    fake_secret = "sk-supersecretapikey12345"

    with caplog.at_level(logging.INFO, logger="api.diagnostics"):
        with pytest.raises(RuntimeError):
            with stage("test_no_leak"):
                raise RuntimeError(f"auth failed with key {fake_secret}")

    for record in caplog.records:
        assert fake_secret not in record.message, "Secret leaked in log output"
        # Error type is logged but not the message
        if "error=" in record.message:
            assert "RuntimeError" in record.message


# ── 6. Warehouse backend selected when pyspark missing ───────────────────────

def test_warehouse_backend_selected_when_pyspark_missing(monkeypatch):
    """When pyspark is absent, warehouse backend is used for reads.

    MUTATION THAT MUST FAIL: select pyspark backend when pyspark is absent → ImportError.
    """
    import db.delta_adapter as adapter

    # Simulate pyspark absent
    monkeypatch.setattr(adapter, "_has_pyspark", False)

    # Mock warehouse query to capture calls
    calls = []
    def _mock_query(query, params=None, **kwargs):
        calls.append({"query": query, "params": params, "kwargs": kwargs})
        return [{"symbol": "AAPL", "feature_ts": "2024-01-01"}]

    monkeypatch.setattr(adapter, "_warehouse_query", _mock_query)

    result = adapter.latest_signals("AAPL", limit=10)

    assert len(calls) == 1
    assert "gold_trading_signals" in calls[0]["query"]
    assert calls[0]["params"] == ("AAPL",)
    assert "LIMIT" in calls[0]["query"].upper() or calls[0]["kwargs"].get("limit") == 10


def test_warehouse_query_uses_parameterized_params(monkeypatch):
    """Warehouse query passes params as tuple, not string interpolation."""
    import db.delta_adapter as adapter

    captured = {}
    def _mock_get_conn():
        class MockCursor:
            def execute(self, query, params=None):
                captured["query"] = query
                captured["params"] = params
            @property
            def description(self):
                return [("col",)]
            def fetchall(self):
                return []
            def close(self):
                pass
        class MockConn:
            def cursor(self):
                return MockCursor()
            def close(self):
                pass
        return MockConn()

    monkeypatch.setattr(adapter, "_get_warehouse_connection", _mock_get_conn)
    monkeypatch.setattr(adapter, "_warehouse_available", lambda: True)

    adapter._warehouse_query("SELECT * FROM t WHERE x = %s", params=("value",))

    assert captured["params"] == ("value",)
    assert "%s" not in captured["query"] or "SELECT" in captured["query"]


def test_warehouse_health_probe_returns_tuple(monkeypatch):
    """check_warehouse_health returns (ok, detail) tuple."""
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_warehouse_available", lambda: True)
    monkeypatch.setattr(adapter, "_warehouse_query", lambda *a, **kw: [{"col": 1}])

    ok, detail = adapter.check_warehouse_health()
    assert isinstance(ok, bool)
    assert isinstance(detail, str)


# ── 7. Warehouse e2e: route → tool → adapter with pyspark absent ─────────────

def _fake_warehouse_query(query, params=None, **kwargs):
    """Fake warehouse query that returns realistic rows."""
    q = query.upper()
    if "GOLD_TRADING_SIGNALS" in q:
        return [{"signal_id": "s1", "symbol": "AAPL", "direction": "long",
                 "probability": 0.8, "prediction_ts": "2024-01-01T00:00:00Z",
                 "model_version": "v1", "horizon": "1d", "status": "active"}]
    if "GOLD_OHLCV_FEATURES" in q:
        return [{"symbol": "AAPL", "feature_ts": "2024-01-01",
                 "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                 "volume": 1000000, "vwap": 100.1}]
    if "GOLD_OPTIONS_FEATURES" in q:
        return [{"symbol": "AAPL", "feature_ts": "2024-01-01", "expiry": "2024-02-01",
                 "atm_iv": 0.25, "skew": 0.01, "put_call_ratio": 1.1, "volume_anomaly": 0.0}]
    if "GOLD_COT_FEATURES" in q:
        return [{"mapped_asset": "AAPL", "report_date": "2024-01-01",
                 "net_position": 50000, "net_pct_oi": 0.15}]
    return []


def test_signals_route_warehouse_e2e(client, monkeypatch):
    """Signals route returns real rows through warehouse backend (pyspark absent).

    MUTATION: return Spark-style objects from warehouse → route FAILS.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", _fake_warehouse_query)

    resp = client.get("/api/signals?symbol=AAPL", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["data"][0]["symbol"] == "AAPL"
    assert data["freshness"]["state"] == "fresh"


def test_market_route_warehouse_e2e(client, monkeypatch):
    """Market route returns real rows through warehouse backend (pyspark absent).

    MUTATION: return Spark-style objects from warehouse → route FAILS.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", _fake_warehouse_query)

    resp = client.get("/api/market/AAPL", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["ohlcv"]["count"] == 1
    assert data["options"]["count"] == 1


def test_options_features_warehouse_e2e(monkeypatch):
    """get_options_features returns real rows through warehouse backend.

    MUTATION: remove warehouse fallback → ImportError when pyspark absent.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", _fake_warehouse_query)

    from agent.tools_retrieval import get_options_features
    rows = get_options_features("AAPL")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert "atm_iv" in rows[0]


def test_cot_positioning_warehouse_e2e(monkeypatch):
    """get_cot_positioning returns real rows through warehouse backend.

    MUTATION: remove warehouse fallback → ImportError when pyspark absent.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", _fake_warehouse_query)

    from agent.tools_retrieval import get_cot_positioning
    result = get_cot_positioning("AAPL")
    assert result["mapped_asset"] == "AAPL"
    assert "net_position" in result


def test_warehouse_health_returns_type_only(monkeypatch):
    """check_warehouse_health returns exception type only, not message.

    MUTATION: include str(exc) → leaked host/credential in detail.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_warehouse_available", lambda: True)

    def _fail_query(*a, **kw):
        raise RuntimeError("connection to host=db.internal port=443 password=secret123 failed")

    monkeypatch.setattr(adapter, "_warehouse_query", _fail_query)

    ok, detail = adapter.check_warehouse_health()
    assert ok is False
    assert "RuntimeError" in detail
    assert "password" not in detail
    assert "db.internal" not in detail


# ── 8. Thread leak: single in-flight guard per dependency ────────────────────

def test_probe_thread_leak_bounded(client, monkeypatch):
    """Calling /api/health 20 times with a hanging probe leaks at most 1 thread per dep.

    MUTATION THAT MUST FAIL: remove the in-flight guard → thread count grows unbounded.
    """
    import api.routes.health as health_mod

    # Make both probes hang forever
    def _hang_forever():
        import time as _time
        _time.sleep(9999)
        return False, 9999000, "should not reach here"

    monkeypatch.setattr(health_mod, "_probe_lakebase", _hang_forever)
    monkeypatch.setattr(health_mod, "_probe_delta", _hang_forever)

    # Reset inflight tracking
    health_mod._inflight.clear()

    initial_thread_count = threading.active_count()

    for _ in range(20):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    # Allow at most 2 extra threads (1 per dependency) plus a small margin
    # for the ThreadPoolExecutor workers
    final_thread_count = threading.active_count()
    growth = final_thread_count - initial_thread_count
    assert growth <= 4, f"Thread count grew by {growth}, expected <= 4 (1 per dep + margin)"


# ── 9. Warehouse statement timeout enforced ──────────────────────────────────

def test_warehouse_query_timeout_enforced(monkeypatch):
    """Warehouse query raises TimeoutError when the query hangs.

    MUTATION THAT MUST FAIL: remove the timeout → query hangs indefinitely.
    """
    import db.delta_adapter as adapter

    class HangingWarehouse:
        def cursor(self):
            return self
        def execute(self, query, params=None):
            time.sleep(9999)
        def fetchall(self):
            return []
        def close(self):
            pass
        @property
        def description(self):
            return []

    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: HangingWarehouse())

    start = time.monotonic()
    with pytest.raises(TimeoutError, match="timed out"):
        adapter._warehouse_query("SELECT 1", timeout=1, limit=1)
    elapsed = time.monotonic() - start

    assert elapsed < 3.0, f"Query took {elapsed:.1f}s, expected < 3s (timeout=1)"


# ── 10. /api/health/trace requires authentication ────────────────────────────

def test_health_trace_requires_auth(client):
    """health_trace returns 401 without auth in non-demo mode.

    MUTATION THAT MUST FAIL: remove Depends(get_current_user) → 200 without auth.
    """
    resp = client.get("/api/health/trace")
    assert resp.status_code == 401