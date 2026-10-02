"""Cost model invariants: the ADV participation cap scales/rejects oversized
orders, and shorts pay an explicit borrow haircut by liquidity bucket."""

import pytest

from strategies.cost_model import (
    CostParams,
    borrow_bps_daily,
    borrow_cost_bps,
    cost_per_trade,
    liquidity_bucket,
    scale_order_to_adv_cap,
)


def test_adv_cap_scales_oversized_order():
    params = CostParams(adv_participation_cap=0.01)
    notional, capped = scale_order_to_adv_cap(10_000_000.0, 100_000_000.0, params)
    assert capped is True
    assert notional == pytest.approx(1_000_000.0)  # 1 % of ADV


def test_adv_cap_lets_small_order_through_unchanged():
    params = CostParams(adv_participation_cap=0.01)
    notional, capped = scale_order_to_adv_cap(500_000.0, 100_000_000.0, params)
    assert capped is False
    assert notional == pytest.approx(500_000.0)


def test_adv_cap_rejects_when_no_volume():
    notional, capped = scale_order_to_adv_cap(1000.0, 0.0, CostParams())
    assert notional == 0.0
    assert capped is True


def test_shorts_pay_borrow_haircut_by_bucket():
    p = CostParams()
    assert liquidity_bucket(1e8, p) == "liquid"
    assert liquidity_bucket(3e7, p) == "medium"
    assert liquidity_bucket(1e6, p) == "illiquid"
    assert borrow_bps_daily(1e8, p) == 0.25
    assert borrow_bps_daily(3e7, p) == 0.75
    assert borrow_bps_daily(1e6, p) == 2.0
    # Illiquid shorts pay more to borrow than liquid shorts.
    assert borrow_bps_daily(1e6, p) > borrow_bps_daily(1e8, p)


def test_borrow_scales_with_holding_period():
    p = CostParams()
    assert borrow_cost_bps(1e8, 10, p) == pytest.approx(0.25 * 10)
    assert borrow_cost_bps(1e8, 0, p) == 0.0


def test_cost_per_trade_is_monotonic_in_participation():
    p = CostParams()
    small = cost_per_trade(1_000_000.0, 100_000_000.0, p)
    large = cost_per_trade(50_000_000.0, 100_000_000.0, p)
    assert large >= small
