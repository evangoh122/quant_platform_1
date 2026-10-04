"""Parameterized transaction cost model.

Spec:
    cost_per_trade = commission_bps
                   + 0.5 * spread_bps          # half-spread crossing
                   + slippage_bps * (order_size / adv_participation_cap)

All parameters are read from config; nothing is hardcoded.
Every reported PnL must be net of this.
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class CostParams:
    """Transaction cost parameters — loaded from strategies/config.yaml."""
    commission_bps: float = 0.5
    spread_bps: float = 3.0
    slippage_bps: float = 2.0
    # ADV participation cap. EXECUTION_PLAN.md: reject/scale orders above 1 %
    # of a name's ADV (capacity guard — a book that ignores this shows returns
    # it could never realise). Default 1 %, not the legacy 2 %.
    adv_participation_cap: float = 0.01

    # ── Short borrow — explicit modelled assumption, never silently zero ─────
    # QUANT_STRATEGIES.md §0 item 8: no borrow/HTB data exists in the lakehouse,
    # so the short-side economics are a stated assumption. Shorts pay a daily
    # borrow haircut in bps by liquidity bucket (illiquid names are costlier to
    # borrow). Buckets are keyed off trailing ADV; thresholds default to the
    # top-300 tradable universe's dollar-volume distribution.
    borrow_bps_daily: dict = field(default_factory=lambda: {
        "liquid": 0.25,     # top ADV bucket
        "medium": 0.75,
        "illiquid": 2.00,
    })
    borrow_bucket_thresholds: tuple = (5.0e7, 2.0e7)  # ADV $: >=5e7 liquid, >=2e7 medium


def cost_per_trade(
    order_notional: float,
    adv: float,
    params: Optional[CostParams] = None,
) -> float:
    """One-way cost in basis points for a single trade.

    Args:
        order_notional: Dollar value of the order.
        adv: Average daily dollar volume of the instrument.
        params: Cost parameters (uses defaults if None).

    Returns:
        Total one-way cost in basis points.
    """
    if params is None:
        params = CostParams()
    participation = order_notional / adv if adv > 0 else 1.0
    participation = min(participation, params.adv_participation_cap)
    return (
        params.commission_bps
        + 0.5 * params.spread_bps
        + params.slippage_bps * (participation / params.adv_participation_cap)
    )


def cost_dollars(
    order_notional: float,
    adv: float,
    params: Optional[CostParams] = None,
) -> float:
    """One-way cost in dollars."""
    bps = cost_per_trade(order_notional, adv, params)
    return order_notional * bps / 10_000


def round_trip_cost_bps(
    order_notional: float,
    adv: float,
    params: Optional[CostParams] = None,
) -> float:
    """Round-trip cost in basis points (entry + exit)."""
    return 2.0 * cost_per_trade(order_notional, adv, params)


def liquidity_bucket(adv: float, params: Optional[CostParams] = None) -> str:
    """Map average daily dollar volume to a liquidity bucket for borrow pricing.

    ``liquid`` / ``medium`` / ``illiquid`` are ordered by ADV. No borrow data
    exists, so the bucket boundaries are a configured assumption
    (``borrow_bucket_thresholds``), not a measurement.
    """
    if params is None:
        params = CostParams()
    if adv >= params.borrow_bucket_thresholds[0]:
        return "liquid"
    if adv >= params.borrow_bucket_thresholds[1]:
        return "medium"
    return "illiquid"


def borrow_bps_daily(adv: float, params: Optional[CostParams] = None) -> float:
    """Daily short-borrow haircut in basis points for a name with the given ADV.

    This is the cost a short position pays each day it is held. It is an
    explicit assumption by liquidity bucket — there is no borrow/HTB feed in the
    lakehouse, so it must never be silently zero.
    """
    if params is None:
        params = CostParams()
    return params.borrow_bps_daily[liquidity_bucket(adv, params)]


def borrow_cost_bps(adv: float, days_held: float, params: Optional[CostParams] = None) -> float:
    """Total borrow cost in basis points for holding a short ``days_held`` days."""
    return borrow_bps_daily(adv, params) * days_held


def scale_order_to_adv_cap(
    order_notional: float,
    adv: float,
    params: Optional[CostParams] = None,
) -> tuple[float, bool]:
    """Cap an order at ``adv_participation_cap`` of the name's ADV.

    Returns ``(scaled_notional, was_capped)``. When ``adv <= 0`` (no volume),
    the order is rejected entirely (scaled to 0.0). The backtester uses this to
    size positions within capacity instead of pretending a 4,120-name book can
    trade unlimited size.
    """
    if params is None:
        params = CostParams()
    if adv <= 0 or order_notional <= 0:
        return 0.0, order_notional > 0
    cap = params.adv_participation_cap * adv
    if order_notional > cap:
        return cap, True
    return order_notional, False


def apply_costs_to_returns(
    returns: pd.Series,
    turnover: pd.Series,
    adv: pd.Series,
    gross_exposure: float,
    params: Optional[CostParams] = None,
) -> pd.Series:
    """Subtract transaction costs from a gross return series.

    Args:
        returns: Gross portfolio returns (per bar or per day).
        turnover: Fraction of portfolio traded each period
                  (sum of |weight changes| / 2).
        adv: Average daily volume per name (use portfolio-weighted avg).
        gross_exposure: Total dollar gross exposure.
        params: Cost parameters.

    Returns:
        Net return series.
    """
    if params is None:
        params = CostParams()
    traded_notional = turnover * gross_exposure
    cost_bps = turnover.apply(
        lambda t: cost_per_trade(t * gross_exposure, adv.mean(), params)
    )
    cost_drag = cost_bps / 10_000
    return returns - cost_drag


# ── Almgren-Chriss temporary market impact (from etl/slippage.py) ─────────

def almgren_chriss_impact_bps(
    order_notional: float,
    adv: float,
    daily_vol: float,
    eta: float = 0.142,
    gamma: float = 0.6,
) -> float:
    """Temporary market impact (square-root model).

    impact = eta * daily_vol * (order_notional / adv) ** gamma

    Args:
        order_notional: Dollar size of the order.
        adv: Average daily dollar volume.
        daily_vol: Annualized daily volatility (e.g. 0.02 for 2%).
        eta: Impact coefficient (calibrate to market).
        gamma: Participation exponent (0.5–0.7 typical).

    Returns:
        Impact in basis points.
    """
    participation = order_notional / adv if adv > 0 else 1.0
    return eta * daily_vol * 10_000 * (participation ** gamma)