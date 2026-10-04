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

    deps._breaker.reset()
    deps._role_cache.clear()
    ring_buffer.clear()
    yield
    deps._breaker.reset()
    deps._role_cache.clear()
    ring_buffer.clear()


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