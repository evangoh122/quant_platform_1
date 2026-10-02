"""Pure deterministic risk-engine tests — no network, no DB.

One test per check, asserting the machine-readable violation code.
"""
from datetime import datetime, timedelta, timezone

import pytest

from agent.guardrails import (
    CONCENTRATION_EXCEEDS_MAX,
    DUPLICATE_IDEMPOTENCY_KEY,
    DUPLICATE_OPEN_ORDER,
    INSUFFICIENT_BUYING_POWER,
    MARKET_CLOSED,
    MISSING_IDEMPOTENCY_KEY,
    NON_POSITIVE_NOTIONAL,
    NON_POSITIVE_QUANTITY,
    NOTIONAL_EXCEEDS_MAX,
    NOT_PAPER_MODE,
    STALE_SIGNAL,
    SYMBOL_NOT_ALLOWED,
    OrderContext,
    RiskEngine,
    is_market_session_open,
    load_allow_list,
)


def _ctx(**overrides) -> OrderContext:
    base = dict(
        symbol="AAPL",
        side="BUY",
        quantity=10,
        notional=1000.0,
        order_type="MARKET",
        is_paper=True,
        market_session_open=True,
        idempotency_key="key-1",
        idempotency_key_seen=False,
    )
    base.update(overrides)
    return OrderContext(**base)


def _engine(**overrides) -> RiskEngine:
    return RiskEngine(**overrides)


def _codes(result):
    return {v.code for v in result.violations}


def test_symbol_allowlist():
    engine = _engine(allowed_symbols={"MSFT"})
    result = engine.check(_ctx(symbol="AAPL"))
    assert result.blocked
    assert SYMBOL_NOT_ALLOWED in _codes(result)


def test_paper_mode_required():
    result = _engine().check(_ctx(is_paper=False))
    assert result.blocked
    assert NOT_PAPER_MODE in _codes(result)


def test_positive_quantity():
    result = _engine().check(_ctx(quantity=0))
    assert result.blocked
    assert NON_POSITIVE_QUANTITY in _codes(result)


def test_positive_notional():
    result = _engine().check(_ctx(notional=-5))
    assert result.blocked
    assert NON_POSITIVE_NOTIONAL in _codes(result)


def test_max_notional_per_order():
    engine = _engine(max_order_notional=500)
    result = engine.check(_ctx(notional=501))
    assert result.blocked
    assert NOTIONAL_EXCEEDS_MAX in _codes(result)


def test_max_position_concentration():
    engine = _engine(max_position_notional=500)
    result = engine.check(_ctx(notional=300, current_position_notional=300))
    assert result.blocked
    assert CONCENTRATION_EXCEEDS_MAX in _codes(result)


def test_sufficient_buying_power():
    result = _engine().check(_ctx(notional=2000, buying_power=1500))
    assert result.blocked
    assert INSUFFICIENT_BUYING_POWER in _codes(result)


def test_duplicate_open_order():
    result = _engine().check(
        _ctx(open_orders=[{"symbol": "AAPL", "side": "BUY", "order_id": "o1"}])
    )
    assert result.blocked
    assert DUPLICATE_OPEN_ORDER in _codes(result)


def test_opposite_side_open_order_is_conflict():
    # An opposite-side open order on the same symbol must also be rejected.
    result = _engine().check(
        _ctx(open_orders=[{"symbol": "AAPL", "side": "SELL", "order_id": "o1"}])
    )
    assert result.blocked
    assert DUPLICATE_OPEN_ORDER in _codes(result)


def test_sell_reduces_concentration():
    # A risk-reducing SELL must not be rejected as concentration.
    engine = _engine(max_position_notional=5000)
    result = engine.check(
        _ctx(side="SELL", notional=3000, current_position_notional=4000)
    )
    assert result.passed


def test_sell_that_overshoots_concentration_is_rejected():
    engine = _engine(max_position_notional=5000)
    result = engine.check(
        _ctx(side="SELL", notional=12000, current_position_notional=4000)
    )
    assert result.blocked
    assert CONCENTRATION_EXCEEDS_MAX in _codes(result)


def test_market_session_closed():
    result = _engine().check(_ctx(market_session_open=False))
    assert result.blocked
    assert MARKET_CLOSED in _codes(result)


def test_stale_signal():
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    result = _engine(stale_signal_minutes=5).check(_ctx(signal_prediction_ts=old))
    assert result.blocked
    assert STALE_SIGNAL in _codes(result)


def test_missing_idempotency_key():
    result = _engine().check(_ctx(idempotency_key=""))
    assert result.blocked
    assert MISSING_IDEMPOTENCY_KEY in _codes(result)


def test_duplicate_idempotency_key():
    result = _engine().check(_ctx(idempotency_key="k", idempotency_key_seen=True))
    assert result.blocked
    assert DUPLICATE_IDEMPOTENCY_KEY in _codes(result)


def test_all_checks_pass():
    result = _engine(allowed_symbols={"AAPL"}).check(_ctx())
    assert result.passed
    assert result.violations == []


def test_market_session_deterministic():
    # Weekend must be closed; a weekday within the session must be open.
    saturday = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)  # Sat
    assert is_market_session_open(saturday) is False
    monday_open = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)  # Mon 10:00 ET
    assert is_market_session_open(monday_open) is True
    monday_closed = datetime(2026, 10, 5, 20, 30, tzinfo=timezone.utc)  # Mon 16:30 ET
    assert is_market_session_open(monday_closed) is False


def test_load_allow_list_fails_closed(monkeypatch):
    # A broken allow-list config must raise, never degrade to "admit everything".
    def _boom():
        raise RuntimeError("tickers config unavailable")

    monkeypatch.setattr("config.tickers.get_all_ticker_symbols", _boom)
    with pytest.raises(RuntimeError):
        load_allow_list()
