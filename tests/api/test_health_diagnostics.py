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
    import db.delta_adapter as adapter

    deps._breaker.reset()
    deps._role_cache.clear()
    ring_buffer.clear()
    health_mod._inflight.clear()
    with adapter._warm_lock:
        adapter._warm_state = "idle"
        adapter._warm_detail = ""
    yield
    deps._breaker.reset()
    deps._role_cache.clear()
    ring_buffer.clear()
    health_mod._inflight.clear()
    with adapter._warm_lock:
        adapter._warm_state = "idle"
        adapter._warm_detail = ""


@pytest.fixture
def client(monkeypatch):
    """Create a TestClient with all network probes faked.

    Prevents real warehouse connections, Lakebase connections, and
    subprocess calls from blocking tests.
    """
    import db.delta_adapter as adapter

    # Prevent real warehouse connection during app startup
    monkeypatch.setattr(adapter, "warm_warehouse_connection", lambda: None)
    monkeypatch.setattr(adapter, "_warehouse_available", lambda: False)

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
    assert calls[0]["params"] == {"symbol": "AAPL"}
    assert "LIMIT" in calls[0]["query"].upper() or calls[0]["kwargs"].get("limit") == 10


def test_warehouse_query_uses_parameterized_params(monkeypatch):
    """Warehouse query passes params as dict with :name markers, not %s."""
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

    adapter._warehouse_query("SELECT * FROM t WHERE x = :val", params={"val": "value"})

    assert captured["params"] == {"val": "value"}
    assert ":val" in captured["query"]


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
    """Fake warehouse query that returns realistic rows with real column names."""
    q = query.upper()
    if "GOLD_TRADING_SIGNALS" in q:
        return [{"signal_id": "s1", "symbol": "AAPL", "direction": "long",
                 "probability": 0.8, "prediction_ts": "2024-01-01T00:00:00Z",
                 "model_version": "v1", "horizon": "1d", "status": "active"}]
    if "SILVER_OHLCV_DAY_ADJUSTED" in q:
        return [{"symbol": "AAPL", "feature_ts": "2024-01-01",
                 "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                 "volume": 1000000, "vwap": 100.1, "return_1d": 0.005}]
    if "GOLD_OHLCV_FEATURES" in q:
        return [{"symbol": "AAPL", "feature_ts": "2024-01-01",
                 "return_1m": 0.001, "return_5m": 0.005, "return_15m": 0.01,
                 "return_30m": 0.02, "rvol_5m": 1.1, "rvol_15m": 1.2, "rvol_30m": 1.3,
                 "atr_14": 2.5, "momentum_5m": 0.003, "momentum_15m": 0.008,
                 "rsi_14": 55.0, "vwap_deviation": 0.001, "relative_volume": 1.05,
                 "dist_session_high": 0.5, "dist_session_low": 1.0}]
    if "GOLD_OPTIONS_FEATURES" in q:
        return [{"symbol": "AAPL", "feature_ts": "2024-01-01",
                 "put_volume": 5000, "call_volume": 8000, "put_call_ratio": 0.625,
                 "iv_atm": 0.25, "iv_25d_put": 0.28, "iv_25d_call": 0.22,
                 "iv_skew": 0.06, "iv_term_slope": 0.02, "avg_spread_pct": 0.01,
                 "volume_anomaly_zscore": 1.5, "oi_concentration": 0.3,
                 "net_delta_exposure": 1500.0}]
    if "GOLD_COT_FEATURES" in q:
        return [{"mapped_asset": "equity_index", "report_date": "2024-01-01",
                 "lev_money_net": 50000, "lev_money_net_chg_1w": 5000,
                 "lev_money_pctile_52w": 0.75, "lev_money_zscore_52w": 1.2,
                 "asset_mgr_net": 30000, "asset_mgr_pctile_52w": 0.6,
                 "crowding_score": 0.4, "regime_label": "risk_on"}]
    if "DESCRIBE" in q:
        # Return fake DESCRIBE output for schema contract checks
        table_cols = {
            "GOLD_TRADING_SIGNALS": ["signal_id", "symbol", "prediction_ts", "horizon",
                                     "direction", "probability", "model_version",
                                     "feature_snapshot_id", "status", "processed_ts"],
            "GOLD_OHLCV_FEATURES": ["symbol", "feature_ts", "information_available_ts",
                                    "return_1m", "return_5m", "return_15m", "return_30m",
                                    "rvol_5m", "rvol_15m", "rvol_30m", "atr_14",
                                    "momentum_5m", "momentum_15m", "rsi_14",
                                    "vwap_deviation", "relative_volume",
                                    "dist_session_high", "dist_session_low", "processed_ts"],
            "GOLD_OPTIONS_FEATURES": ["symbol", "feature_ts", "information_available_ts",
                                      "put_volume", "call_volume", "put_call_ratio",
                                      "iv_atm", "iv_25d_put", "iv_25d_call", "iv_skew",
                                      "iv_term_slope", "avg_spread_pct",
                                      "volume_anomaly_zscore", "oi_concentration",
                                      "net_delta_exposure", "processed_ts"],
            "GOLD_COT_FEATURES": ["mapped_asset", "report_date", "information_available_ts",
                                  "lev_money_net", "lev_money_net_chg_1w",
                                  "lev_money_pctile_52w", "lev_money_zscore_52w",
                                  "asset_mgr_net", "asset_mgr_pctile_52w",
                                  "crowding_score", "regime_label", "processed_ts"],
            "SILVER_OHLCV_DAY_ADJUSTED": ["symbol", "event_date", "adj_open", "adj_high",
                                          "adj_low", "adj_close", "adj_vwap", "adj_volume",
                                          "return_1d", "information_available_ts"],
        }
        for key, cols in table_cols.items():
            if key in q:
                return [{"col_name": c} for c in cols]
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
    assert "iv_atm" in rows[0]
    assert "put_volume" in rows[0]
    assert "call_volume" in rows[0]
    assert "volume_anomaly_zscore" in rows[0]


def test_cot_positioning_warehouse_e2e(monkeypatch):
    """get_cot_positioning returns real rows through warehouse backend.

    MUTATION: remove warehouse fallback → ImportError when pyspark absent.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", _fake_warehouse_query)

    from agent.tools_retrieval import get_cot_positioning
    result = get_cot_positioning("equity_index")
    assert result["mapped_asset"] == "equity_index"
    assert "lev_money_net" in result
    assert "crowding_score" in result


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


# ── 11. Fake cursor validates :name markers (rejects %s / ?) ────────────────

import re


class _NamedParamValidatingCursor:
    """Fake cursor that rejects %s/? placeholders; only :name markers allowed.

    The params dict keys must exactly match the :name markers in the SQL.
    """

    _INVALID_RE = re.compile(r"%s|\?")
    _NAME_RE = re.compile(r":(\w+)")

    def __init__(self):
        self.executed_query = None
        self.executed_params = None

    def execute(self, query, params=None):
        if self._INVALID_RE.search(query):
            raise ValueError(
                f"Query uses legacy %s/? placeholders — must use :name markers: {query}"
            )
        names = set(self._NAME_RE.findall(query))
        if params is not None:
            param_keys = set(params.keys())
            if names != param_keys:
                raise ValueError(
                    f":name markers {names} do not match params keys {param_keys}: {query}"
                )
        self.executed_query = query
        self.executed_params = params

    @property
    def description(self):
        return [("col",)]

    def fetchall(self):
        return []

    def close(self):
        pass

    def cancel(self):
        pass


class _NamedParamValidatingConn:
    def __init__(self):
        self.cursor_instance = _NamedParamValidatingCursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        pass


def test_warehouse_latest_signals_uses_named_params(monkeypatch):
    """latest_signals warehouse path uses :symbol marker, not %s.

    MUTATION: put back one %s → FAIL (fake cursor rejects legacy placeholders).
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)

    conn = _NamedParamValidatingConn()
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: conn)

    rows = adapter.latest_signals("AAPL", limit=3)
    assert conn.cursor_instance.executed_query is not None
    assert ":symbol" in conn.cursor_instance.executed_query
    assert conn.cursor_instance.executed_params == {"symbol": "AAPL"}


def test_warehouse_market_features_uses_named_params(monkeypatch):
    """market_features warehouse path uses :symbol/:start_ts/:end_ts markers.

    Now reads from silver_ohlcv_day_adjusted (single query, no options join).

    MUTATION: put back one %s → FAIL.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)

    conns = []

    def _make_conn():
        c = _NamedParamValidatingConn()
        conns.append(c)
        return c

    monkeypatch.setattr(adapter, "_get_warehouse_connection", _make_conn)

    rows = adapter.market_features("AAPL", "2024-01-01", "2024-12-31", limit=100)
    assert len(conns) == 1  # single daily bars query
    c = conns[0]
    q = c.cursor_instance.executed_query
    assert ":symbol" in q
    assert ":start_ts" in q
    assert ":end_ts" in q
    assert "silver_ohlcv_day_adjusted" in q.lower()
    assert c.cursor_instance.executed_params == {
        "symbol": "AAPL", "start_ts": "2024-01-01", "end_ts": "2024-12-31",
    }


def test_warehouse_daily_query_has_order_by_desc(monkeypatch):
    """Daily query must ORDER BY event_date DESC before LIMIT.

    MUTATION: remove ORDER BY → latest row is arbitrary, not the most recent.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)

    conn = _NamedParamValidatingConn()
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: conn)

    rows = adapter.market_features("AAPL", "2024-01-01", "2024-12-31", limit=100)
    q = conn.cursor_instance.executed_query
    assert "ORDER BY" in q, f"Missing ORDER BY in daily query: {q}"
    assert "event_date" in q.split("ORDER BY")[1], f"ORDER BY must include event_date: {q}"
    assert "DESC" in q.split("ORDER BY")[1].upper(), f"ORDER BY must be DESC: {q}"


def test_warehouse_daily_query_order_enables_latest(monkeypatch):
    """Daily query returns rows in DESC order so row 0 is the latest date."""
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)

    captured_queries = []

    def _capture_query(query, params=None, **kwargs):
        captured_queries.append(query)
        return [
            {"symbol": "AAPL", "event_date": "2024-03-15", "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 1000000, "vwap": 100.1, "return_1d": 0.005},
            {"symbol": "AAPL", "event_date": "2024-03-14", "open": 99.0, "high": 100.0,
             "low": 98.0, "close": 99.5, "volume": 900000, "vwap": 99.1, "return_1d": -0.005},
        ]

    monkeypatch.setattr(adapter, "_warehouse_query", _capture_query)

    rows = adapter.market_features("AAPL", "2024-01-01", "2024-12-31", limit=100)
    assert len(rows) == 2
    # Row 0 should be the latest (DESC order from warehouse)
    assert rows[0]["event_date"] == "2024-03-15"


def test_warehouse_options_features_uses_named_params(monkeypatch):
    """get_options_features warehouse path uses :symbol only (no expiry column).

    MUTATION: put back one %s → FAIL.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)

    conn = _NamedParamValidatingConn()
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: conn)

    from agent.tools_retrieval import get_options_features
    rows = get_options_features("AAPL", limit=100)
    q = conn.cursor_instance.executed_query
    assert ":symbol" in q
    assert "expiry" not in q.lower()
    assert conn.cursor_instance.executed_params == {"symbol": "AAPL"}


def test_warehouse_options_query_has_order_by_desc(monkeypatch):
    """Options query must ORDER BY feature_ts DESC before LIMIT.

    MUTATION: remove ORDER BY → latest row is arbitrary, not the most recent.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)

    conn = _NamedParamValidatingConn()
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: conn)

    from agent.tools_retrieval import get_options_features
    rows = get_options_features("AAPL", limit=100)
    q = conn.cursor_instance.executed_query
    assert "ORDER BY" in q, f"Missing ORDER BY in options query: {q}"
    assert "feature_ts" in q.split("ORDER BY")[1], f"ORDER BY must include feature_ts: {q}"
    assert "DESC" in q.split("ORDER BY")[1].upper(), f"ORDER BY must be DESC: {q}"
    """get_cot_positioning warehouse path uses :mapped_asset marker.

    MUTATION: put back one %s → FAIL.
    """
    import db.delta_adapter as adapter

    monkeypatch.setattr(adapter, "_has_pyspark", False)

    conn = _NamedParamValidatingConn()
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: conn)

    from agent.tools_retrieval import get_cot_positioning
    rows = get_cot_positioning("equity_index")
    q = conn.cursor_instance.executed_query
    assert ":mapped_asset" in q
    assert conn.cursor_instance.executed_params == {"mapped_asset": "equity_index"}


# ── 12. Background connection warming ────────────────────────────────────────

def test_warm_warehouse_connection_starts_background_thread():
    """warm_warehouse_connection starts a background thread and transitions state."""
    import db.delta_adapter as adapter
    import threading as _threading

    connect_called = _threading.Event()

    def _fake_connect():
        connect_called.set()
        return "fake_conn"

    original_get = adapter._get_warehouse_connection

    with adapter._warm_lock:
        assert adapter._warm_state == "idle"

    # Patch _get_warehouse_connection to simulate slow connect
    import time as _time

    def _slow_connect():
        _time.sleep(0.2)
        connect_called.set()
        return "fake_conn"

    adapter._get_warehouse_connection = _slow_connect
    try:
        adapter.warm_warehouse_connection()
        with adapter._warm_lock:
            assert adapter._warm_state == "warming"
            assert adapter._warm_detail == "connecting"

        # Wait for background thread
        connect_called.wait(timeout=5.0)
        _time.sleep(0.1)  # let state update

        with adapter._warm_lock:
            assert adapter._warm_state == "ready"
            assert adapter._warm_detail == "reachable"
    finally:
        adapter._get_warehouse_connection = original_get


def test_warm_warehouse_connection_reports_error_on_failure():
    """warm_warehouse_connection reports error state when connect fails."""
    import db.delta_adapter as adapter
    import time as _time

    def _fail_connect():
        raise RuntimeError("connection refused")

    original_get = adapter._get_warehouse_connection
    adapter._get_warehouse_connection = _fail_connect
    try:
        adapter.warm_warehouse_connection()
        _time.sleep(0.3)  # let background thread run

        with adapter._warm_lock:
            assert adapter._warm_state == "error"
            assert adapter._warm_detail == "RuntimeError"
    finally:
        adapter._get_warehouse_connection = original_get


def test_warm_warehouse_connection_is_idempotent():
    """Calling warm_warehouse_connection twice does not start a second thread."""
    import db.delta_adapter as adapter
    import time as _time
    import threading as _threading

    call_count = [0]

    def _counting_connect():
        call_count[0] += 1
        _time.sleep(0.1)
        return "fake_conn"

    original_get = adapter._get_warehouse_connection
    adapter._get_warehouse_connection = _counting_connect
    try:
        adapter.warm_warehouse_connection()
        _time.sleep(0.05)
        adapter.warm_warehouse_connection()  # should be no-op
        _time.sleep(0.3)

        assert call_count[0] == 1
    finally:
        adapter._get_warehouse_connection = original_get


def test_check_warehouse_health_reports_warming():
    """check_warehouse_health returns (False, 'connecting') while warming."""
    import db.delta_adapter as adapter

    with adapter._warm_lock:
        adapter._warm_state = "warming"
        adapter._warm_detail = "connecting"

    ok, detail = adapter.check_warehouse_health()
    assert ok is False
    assert detail == "connecting"


def test_health_probe_reports_warming_state(client, monkeypatch):
    """Health endpoint reports 'connecting' detail when warehouse is warming."""
    import db.delta_adapter as adapter
    import api.routes.health as health_mod

    with adapter._warm_lock:
        adapter._warm_state = "warming"
        adapter._warm_detail = "connecting"

    # Make lakebase probe succeed fast
    monkeypatch.setattr(health_mod, "_probe_lakebase", lambda: (True, 1.0, "reachable"))

    resp = client.get("/api/health")
    data = resp.json()

    delta_dep = next(d for d in data["dependencies"] if d["name"] == "delta")
    assert delta_dep["ok"] is False
    assert delta_dep["detail"] == "connecting"


def test_warehouse_available_detects_installed_connector():
    """_warehouse_available returns True when databricks-sql-connector is installed."""
    import db.delta_adapter as adapter

    # The connector is installed in the test environment (4.6.0+).
    # This test guards against a regression where import detection breaks.
    assert adapter._warehouse_available() is True


# ── 13. cursor.cancel() on timeout + bounded semaphore ───────────────────────

def test_warehouse_query_calls_cancel_on_timeout(monkeypatch):
    """On timeout, cursor.cancel() is called before cursor.close().

    MUTATION: drop cancel() → test FAILS (cancel_called stays False).
    """
    import db.delta_adapter as adapter

    cancel_called = []
    close_called = []

    class SlowCursor:
        def execute(self, query, params=None):
            import time as _time
            _time.sleep(9999)
        def fetchall(self):
            return []
        @property
        def description(self):
            return []
        def cancel(self):
            cancel_called.append(True)
        def close(self):
            close_called.append(True)

    class FakeConn:
        def cursor(self):
            return SlowCursor()
        def close(self):
            pass

    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: FakeConn())

    with pytest.raises(TimeoutError, match="timed out"):
        adapter._warehouse_query("SELECT 1", timeout=1, limit=1)

    assert len(cancel_called) == 1, "cancel() was not called on timeout"
    assert len(close_called) >= 1, "close() was not called after cancel()"


def test_warehouse_query_semaphore_bounded(monkeypatch):
    """Stuck queries are capped by the bounded semaphore.

    With _MAX_CONCURRENT_QUERIES=2, a 3rd concurrent query should block on
    semaphore acquire.  The test verifies that exactly 2 queries execute
    concurrently (the rest block until slots free up).

    Uses a SHARED lock-guarded counter (not threading.local) so all workers
    increment the same state.  The counter increments on cursor.execute entry,
    sleeps, then decrements on exit — proving the semaphore was actually acquired.

    MUTATION: remove semaphore acquire at db/delta_adapter.py:172 →
    all 6 workers start immediately → max_concurrent > 2 → FAIL.
    """
    import db.delta_adapter as adapter
    import threading as _threading
    import time as _time

    monkeypatch.setattr(adapter, "_MAX_CONCURRENT_QUERIES", 2)
    monkeypatch.setattr(adapter, "_query_semaphore", _threading.Semaphore(2))

    # Shared state: lock-guarded counter visible to all threads
    state = {"cur": 0, "max": 0}
    state_lock = _threading.Lock()

    class HangingCursor:
        def execute(self, query, params=None):
            with state_lock:
                state["cur"] += 1
                if state["cur"] > state["max"]:
                    state["max"] = state["cur"]
            _time.sleep(9999)

        def fetchall(self):
            return []

        @property
        def description(self):
            return []

        def cancel(self):
            pass

        def close(self):
            pass

    class FakeConn:
        def cursor(self):
            return HangingCursor()
        def close(self):
            pass

    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: FakeConn())

    started = []
    results = []

    def _run_query(i):
        started.append(i)
        try:
            adapter._warehouse_query("SELECT 1", timeout=1, limit=1)
        except TimeoutError:
            results.append(("timeout", i))
        except Exception as e:
            results.append(("error", i, type(e).__name__))

    # Launch 6 concurrent queries with semaphore size 2
    threads = [_threading.Thread(target=_run_query, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    # All should eventually resolve to timeout
    assert len(results) == 6, f"Expected 6 resolved queries, got {results}"
    # Max concurrent must be exactly 2 — prove the semaphore was reached
    assert state["max"] == 2, f"Max concurrent was {state['max']}, expected exactly 2"


def test_warehouse_query_semaphore_timeout(monkeypatch):
    """Semaphore wait itself times out when all slots are busy.

    MUTATION: remove semaphore.acquire timeout → blocks forever.
    """
    import db.delta_adapter as adapter
    import threading as _threading
    import time as _time

    # Set max concurrent to 1 and pre-occupy the slot
    monkeypatch.setattr(adapter, "_MAX_CONCURRENT_QUERIES", 1)
    sem = _threading.Semaphore(0)  # already exhausted
    monkeypatch.setattr(adapter, "_query_semaphore", sem)

    start = _time.monotonic()
    with pytest.raises(TimeoutError, match="semaphore"):
        adapter._warehouse_query("SELECT 1", timeout=1, limit=1)
    elapsed = _time.monotonic() - start

    assert elapsed < 3.0, f"Semaphore wait took {elapsed:.1f}s, expected < 3s"


# ── 15. Schema contract validation ────────────────────────────────────────────

def test_schema_contract_passes():
    """db/schema_contract.py: validate_query_columns returns no errors.

    MUTATION: reference 'open' from gold_ohlcv_features → FAIL.
    """
    from db.schema_contract import validate_query_columns

    errors = validate_query_columns()
    assert errors == [], f"Schema contract errors: {errors}"


def test_schema_contract_rejects_bad_column():
    """Mutation: add 'open' to gold_ohlcv_features query → contract fails."""
    from db.schema_contract import QUERY_COLUMNS, validate_query_columns
    import db.schema_contract as sc

    # Mutate: add a bad column
    original = sc.QUERY_COLUMNS["market_features_intraday"]["gold_ohlcv_features"]
    sc.QUERY_COLUMNS["market_features_intraday"]["gold_ohlcv_features"] = original | {"open"}

    try:
        errors = validate_query_columns()
        assert any("open" in e for e in errors), f"Expected 'open' error, got {errors}"
    finally:
        sc.QUERY_COLUMNS["market_features_intraday"]["gold_ohlcv_features"] = original


def test_actual_queries_match_contract():
    """Actual SQL queries in delta_adapter/tools_retrieval match the contract.

    MUTATION: change intraday query to select 'open' → FAIL because 'open' is
    not in the gold_ohlcv_features contract.
    """
    from db.schema_contract import validate_actual_queries

    errors = validate_actual_queries()
    assert errors == [], f"Actual query contract errors: {errors}"


def test_actual_queries_catch_bad_intraday_column():
    """Mutation: add 'open' to intraday column list → contract fails."""
    from db.schema_contract import validate_actual_queries, QUERY_COLUMNS
    import db.schema_contract as sc

    # Mutate: add 'open' to the intraday contract (simulates a bad SQL change)
    original = sc.QUERY_COLUMNS["market_features_intraday"]["gold_ohlcv_features"]
    sc.QUERY_COLUMNS["market_features_intraday"]["gold_ohlcv_features"] = original | {"open"}
    try:
        errors = validate_actual_queries()
        assert any("open" in e for e in errors), f"Expected 'open' error, got {errors}"
    finally:
        sc.QUERY_COLUMNS["market_features_intraday"]["gold_ohlcv_features"] = original


# ── 16. Signals: no_signals_published explicit state ──────────────────────────

def test_signals_empty_table_returns_no_signals_published(client, monkeypatch):
    """Empty gold_trading_signals returns no_signals_published detail.

    MUTATION: remove the override → detail is '0 rows' instead.
    """
    import db.delta_adapter as adapter

    def _empty_query(*a, **kw):
        return []

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", _empty_query)

    resp = client.get("/api/signals", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["empty"] is True
    assert data["freshness"]["state"] == "empty"
    assert data["freshness"]["detail"] == "no_signals_published"


# ── 17. COT: ticker → asset class mapping ─────────────────────────────────────

def test_cot_ticker_mapping_to_asset_class(monkeypatch):
    """SPY maps to equity_index, not passed as-is.

    MUTATION: skip mapping → SPY passed as mapped_asset, query returns empty.
    """
    import db.delta_adapter as adapter

    captured_params = {}

    def _capture_query(query, params=None, **kwargs):
        captured_params.update(params or {})
        return [{"mapped_asset": "equity_index", "report_date": "2024-01-01",
                 "lev_money_net": 50000}]

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", _capture_query)

    from agent.tools_retrieval import get_cot_positioning
    result = get_cot_positioning("SPY")
    assert captured_params.get("mapped_asset") == "equity_index"
    assert result["mapped_asset"] == "equity_index"


def test_cot_unknown_ticker_returns_no_mapping():
    """Unknown ticker returns explicit no_mapping error dict.

    MUTATION: return empty dict instead → looks like 'no data' not 'no mapping'.
    """
    from agent.tools_retrieval import get_cot_positioning

    result = get_cot_positioning("ZZZZZZ")
    assert result.get("error") == "no_mapping"
    assert "ZZZZZZ" in result.get("ticker", "")
    assert "no cot" in result.get("message", "").lower() or "no mapping" in result.get("message", "").lower()


def test_cot_valid_asset_class_direct():
    """Passing asset class directly (lowercase) works without mapping."""
    import db.delta_adapter as adapter

    captured_params = {}

    def _capture_query(query, params=None, **kwargs):
        captured_params.update(params or {})
        return [{"mapped_asset": "commodity", "report_date": "2024-01-01"}]

    import db.delta_adapter as da
    import unittest.mock as mock
    with mock.patch.object(da, "_has_pyspark", False), \
         mock.patch.object(da, "_warehouse_query", _capture_query):
        from agent.tools_retrieval import get_cot_positioning
        result = get_cot_positioning("commodity")
        assert captured_params.get("mapped_asset") == "commodity"


# ── 18. Options: expiry rejection ─────────────────────────────────────────────

def test_options_expiry_returns_error():
    """Passing expiry returns explicit error dict.

    MUTATION: silently ignore expiry → user doesn't know filter was dropped.
    """
    from agent.tools_retrieval import get_options_features

    result = get_options_features("AAPL", expiry="2024-02-01")
    assert len(result) == 1
    assert result[0].get("error") == "expiry_not_supported"


# ── 19. get_latest_signal: explicit no_signals_published on empty ─────────────

def test_get_latest_signal_empty_returns_no_signals_published(monkeypatch):
    """Empty table returns {"status": "no_signals_published"}, not {}.

    MUTATION: revert to returning {} → agent misreads empty as generic no-data.
    """
    import db.delta_adapter as adapter
    from agent.tools_retrieval import get_latest_signal

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_warehouse_query", lambda *a, **kw: [])

    result = get_latest_signal("AAPL")
    assert result == {"status": "no_signals_published"}
    assert result != {}


# ── 20. _warehouse_query: LIMIT only on SELECT ───────────────────────────────

def test_warehouse_query_no_limit_on_describe(monkeypatch):
    """DESCRIBE/SHOW statements must not have LIMIT appended.

    MUTATION: remove the SELECT-only guard → DESCRIBE gets LIMIT → PARSE_SYNTAX_ERROR.
    """
    import db.delta_adapter as adapter

    captured = {}

    class _FakeCursor:
        description = [("col_name", None)]
        def execute(self, query, params=None):
            captured["query"] = query
        def fetchall(self):
            return [("symbol",)]
        def close(self):
            pass

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: _FakeConn())
    monkeypatch.setattr(adapter, "_query_semaphore", __import__("threading").Semaphore(10))

    adapter._warehouse_query("DESCRIBE bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted", limit=1000)
    assert "LIMIT" not in captured["query"]


def test_warehouse_query_limit_on_bare_select(monkeypatch):
    """SELECT without LIMIT gets one appended.

    MUTATION: skip appending → unbounded query hits warehouse.
    """
    import db.delta_adapter as adapter

    captured = {}

    class _FakeCursor:
        description = [("col", None)]
        def execute(self, query, params=None):
            captured["query"] = query
        def fetchall(self):
            return [(1,)]
        def close(self):
            pass

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: _FakeConn())
    monkeypatch.setattr(adapter, "_query_semaphore", __import__("threading").Semaphore(10))

    adapter._warehouse_query("SELECT * FROM t", limit=500)
    assert "LIMIT 500" in captured["query"]


def test_warehouse_query_preserves_existing_limit(monkeypatch):
    """SELECT already with LIMIT is not double-limited.

    MUTATION: ignore existing LIMIT → query becomes "... LIMIT 100 LIMIT 500".
    """
    import db.delta_adapter as adapter

    captured = {}

    class _FakeCursor:
        description = [("col", None)]
        def execute(self, query, params=None):
            captured["query"] = query
        def fetchall(self):
            return [(1,)]
        def close(self):
            pass

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(adapter, "_has_pyspark", False)
    monkeypatch.setattr(adapter, "_get_warehouse_connection", lambda: _FakeConn())
    monkeypatch.setattr(adapter, "_query_semaphore", __import__("threading").Semaphore(10))

    adapter._warehouse_query("SELECT * FROM t LIMIT 100", limit=500)
    assert captured["query"] == "SELECT * FROM t LIMIT 100"