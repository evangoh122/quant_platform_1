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
    adv_participation_cap: float = 0.02  # max 2 % of ADV per order


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