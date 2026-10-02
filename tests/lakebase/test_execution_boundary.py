"""Execution-boundary tests — offline (no live Lakebase, no network).

These prove the boundary the LLM cannot bypass: for every risk check, the *real*
public placement path (``agent.tools_write.approve_and_place_paper_order``) is
driven with a mocked broker bridge and asserted that ``submit_order`` is never
called. No trusted risk state is passed into the function — the DB acquisition,
risk engine construction, market clock, and broker construction are patched at
their construction sites, exactly as the public entry point acquires them.

The DB is a small in-memory fake keyed on query substrings; it only needs to
return the handful of rows the placement path reads.
"""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import agent.tools_write as tw


class _FakeCursor:
    def __init__(self, state):
        self._state = state
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self._state["executed"].append((query, params))
        self._rows = self._state["rows_for"](query, params)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, state):
        self._state = state

    def cursor(self):
        return _FakeCursor(self._state)

    def commit(self):
        pass

    def rollback(self):
        pass


class FakeLakebase:
    def __init__(self, state):
        self._state = state

    @contextmanager
    def transaction(self):
        yield _FakeConn(self._state)


# Baseline order row columns:
#   order_id, user_id, signal_id, broker, side, quantity, notional,
#   order_type, limit_price, status, idempotency_key, symbol, broker_order_id
_BASE_ORDER = (
    "ord_1", "user_1", None, "PAPER", "BUY", 10, 1000.0,
    "MARKET", None, "PENDING_APPROVAL", "key_1", "AAPL", None,
)


def _rows_for(state, query, params):
    q = query
    if "SELECT order_id, user_id, signal_id, broker, side" in q:
        return [state["order"]] if state["order"] is not None else []
    if "FROM approvals" in q:
        return [state["approval"]] if state["approval"] is not None else []
    if "FROM accounts" in q:
        return [state["account"]] if state["account"] is not None else []
    if "SUM(quantity * avg_cost)" in q:
        return [(state["position_notional"],)]
    if "SELECT order_id, symbol, side, status FROM orders" in q:
        return state["open_orders"]
    if "FROM signals" in q:
        return [state["signal"]] if state["signal"] is not None else []
    return []


def _make_state(**overrides):
    state = {
        "order": _BASE_ORDER,
        "approval": ("alice",),
        "account": (100000.0,),
        "position_notional": 0.0,
        "open_orders": [],
        "signal": None,
        "executed": [],
    }
    state.update(overrides)
    state["rows_for"] = lambda q, p: _rows_for(state, q, p)
    return state


def _run(state, *, market_session_open=True, bridge=None, monkeypatch):
    bridge = bridge or MagicMock()
    # Patch the construction sites the public entry point uses, never the
    # function arguments — the public signature cannot accept these at all.
    monkeypatch.setattr(tw, "get_lakebase", lambda: FakeLakebase(state))
    monkeypatch.setattr(tw, "is_market_session_open", lambda: market_session_open)
    monkeypatch.setattr(tw, "IBKRBridge", lambda: bridge)
    return tw.approve_and_place_paper_order("ord_1")


def _order(**fields):
    row = list(_BASE_ORDER)
    mapping = {
        "signal_id": 2, "broker": 3, "side": 4, "quantity": 5, "notional": 6,
        "order_type": 7, "limit_price": 8, "status": 9, "idempotency_key": 10,
        "symbol": 11, "broker_order_id": 12,
    }
    for key, value in fields.items():
        row[mapping[key]] = value
    return tuple(row)


def _not_allowlisted_symbol():
    """Return a symbol guaranteed absent from the production allow-list."""
    from config.tickers import get_all_ticker_symbols

    allowlist = set(get_all_ticker_symbols())
    for candidate in ("ZZZZZ", "ZZZZZZ", "ZZZZZZZ", "ZZZZZZZZ", "ZZZZZZZZZ",
                      "ZZZZZZZZZZ"):
        if candidate not in allowlist:
            return candidate
    raise AssertionError("all synthetic symbols unexpectedly allow-listed")


# ── one no-broker-call test per risk check ────────────────────────────────────
def test_no_broker_call_symbol_not_allowed(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(order=_order(symbol=_not_allowlisted_symbol())),
               bridge=bridge, monkeypatch=monkeypatch)
    assert res["ok"] is False
    assert res["status"] == "REJECTED"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_not_paper_mode(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(order=_order(broker="LIVE")), bridge=bridge,
               monkeypatch=monkeypatch)
    assert res["ok"] is False
    assert res["risk"]["violations"][0]["code"] == "NOT_PAPER_MODE"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_non_positive_quantity(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(order=_order(quantity=0)), bridge=bridge,
               monkeypatch=monkeypatch)
    assert res["risk"]["violations"][0]["code"] == "NON_POSITIVE_QUANTITY"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_non_positive_notional(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(order=_order(notional=0)), bridge=bridge,
               monkeypatch=monkeypatch)
    assert res["risk"]["violations"][0]["code"] == "NON_POSITIVE_NOTIONAL"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_notional_exceeds_max(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(order=_order(notional=30000)), bridge=bridge,
               monkeypatch=monkeypatch)
    assert res["risk"]["violations"][0]["code"] == "NOTIONAL_EXCEEDS_MAX"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_concentration_exceeds_max(monkeypatch):
    bridge = MagicMock()
    res = _run(
        _make_state(order=_order(notional=25000), position_notional=30000.0),
        bridge=bridge, monkeypatch=monkeypatch,
    )
    assert res["risk"]["violations"][0]["code"] == "CONCENTRATION_EXCEEDS_MAX"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_insufficient_buying_power(monkeypatch):
    bridge = MagicMock()
    res = _run(
        _make_state(order=_order(notional=2000), account=(1500.0,)),
        bridge=bridge, monkeypatch=monkeypatch,
    )
    assert res["risk"]["violations"][0]["code"] == "INSUFFICIENT_BUYING_POWER"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_duplicate_open_order_opposite_side(monkeypatch):
    bridge = MagicMock()
    open_orders = [("ord_2", "AAPL", "SELL", "PENDING_APPROVAL")]
    res = _run(_make_state(open_orders=open_orders), bridge=bridge,
               monkeypatch=monkeypatch)
    assert res["risk"]["violations"][0]["code"] == "DUPLICATE_OPEN_ORDER"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_market_closed(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(), market_session_open=False, bridge=bridge,
               monkeypatch=monkeypatch)
    assert res["risk"]["violations"][0]["code"] == "MARKET_CLOSED"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_stale_signal(monkeypatch):
    bridge = MagicMock()
    old = datetime(2000, 1, 1, tzinfo=timezone.utc)
    res = _run(
        _make_state(order=_order(signal_id="sig_1"), signal=(old,)),
        bridge=bridge, monkeypatch=monkeypatch,
    )
    assert res["risk"]["violations"][0]["code"] == "STALE_SIGNAL"
    bridge.submit_order.assert_not_called()


# ── fail-closed service-level checks ──────────────────────────────────────────
def test_no_broker_call_signal_not_found(monkeypatch):
    bridge = MagicMock()
    res = _run(
        _make_state(order=_order(signal_id="missing_sig"), signal=None),
        bridge=bridge, monkeypatch=monkeypatch,
    )
    assert res["risk"]["violations"][0]["code"] == "SIGNAL_NOT_FOUND"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_account_not_found(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(account=None), bridge=bridge, monkeypatch=monkeypatch)
    assert res["risk"]["violations"][0]["code"] == "ACCOUNT_NOT_FOUND"
    bridge.submit_order.assert_not_called()


def test_no_broker_call_missing_approval_record(monkeypatch):
    bridge = MagicMock()
    res = _run(_make_state(approval=None), bridge=bridge, monkeypatch=monkeypatch)
    assert res["risk"]["violations"][0]["code"] == "MISSING_APPROVAL"
    bridge.submit_order.assert_not_called()


# ── idempotent replay never re-calls the broker ───────────────────────────────
def test_no_broker_call_already_submitted_replay(monkeypatch):
    bridge = MagicMock()
    res = _run(
        _make_state(order=_order(status="SUBMITTED", broker_order_id="PAPER-9")),
        bridge=bridge, monkeypatch=monkeypatch,
    )
    assert res["ok"] is True
    assert res.get("replay") is True
    bridge.submit_order.assert_not_called()


# ── the public signature cannot override risk state ───────────────────────────
def test_public_signature_cannot_override_risk_state():
    sig = inspect.signature(tw.approve_and_place_paper_order)
    params = set(sig.parameters)
    for forbidden in ("engine", "bridge", "market_session_open",
                      "human_approved", "approved_by", "db"):
        assert forbidden not in params


def test_public_cancel_signature_has_no_bridge():
    sig = inspect.signature(tw.cancel_paper_order)
    assert "bridge" not in sig.parameters


def test_private_seam_excluded_from_star_import_only():
    # ``__all__`` governs ``from agent.tools_write import *``. It is not an
    # enforcement boundary: the private seams remain directly reachable by a
    # same-process caller. Assert both halves so the test does not overclaim.
    assert "approve_and_place_paper_order" in tw.__all__
    assert "record_approval" in tw.__all__
    assert "ApprovalContext" in tw.__all__
    assert "_approve_and_place_paper_order" not in tw.__all__
    assert "_cancel_paper_order" not in tw.__all__
    assert hasattr(tw, "_approve_and_place_paper_order")
    assert hasattr(tw, "_cancel_paper_order")


def test_record_approval_requires_context_object():
    sig = inspect.signature(tw.record_approval)
    assert "approver_id" not in sig.parameters
    assert "approver" in sig.parameters
