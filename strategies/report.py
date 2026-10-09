"""Economic performance metrics for strategy backtests.

Ratios are calculated from net periodic returns after transaction costs.  The
caller must supply the correct annualization factor for the return frequency
(for example 252 for daily or 252 * 13 for 30-minute bars).
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def performance_metrics(
    returns: Iterable[float],
    *,
    periods_per_year: int,
    trade_pnls: Iterable[float] | None = None,
    risk_free_rate: float = 0.0,
) -> dict[str, float]:
    """Calculate a compact, consistently-defined backtest report.

    ``returns`` is the portfolio return series. ``trade_pnls`` should contain
    one net P&L or net return per completed trade; when omitted, non-zero
    periodic returns are used as a conservative proxy for trades.
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")

    r = pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if r.empty:
        keys = (
            "total_return", "cagr", "annualized_return", "annualized_volatility",
            "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "profit_factor", "win_rate", "average_win", "average_loss",
            "payoff_ratio", "trade_count",
        )
        return {key: float("nan") for key in keys}

    equity = (1.0 + r).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    years = len(r) / periods_per_year
    cagr = (
        float(equity.iloc[-1] ** (1.0 / years) - 1.0)
        if years > 0 and equity.iloc[-1] > 0
        else float("nan")
    )
    annualized_return = float(r.mean() * periods_per_year)
    annualized_volatility = float(r.std(ddof=1) * math.sqrt(periods_per_year))
    periodic_rf = risk_free_rate / periods_per_year
    excess = r - periodic_rf
    excess_std = float(excess.std(ddof=1))
    sharpe = (
        float(excess.mean() / excess_std * math.sqrt(periods_per_year))
        if excess_std > 0
        else float("nan")
    )

    downside = np.minimum(excess.to_numpy(), 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
    sortino = (
        float(excess.mean() / downside_deviation * math.sqrt(periods_per_year))
        if downside_deviation > 0
        else float("nan")
    )

    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(-drawdown.min())
    calmar = cagr / max_drawdown if max_drawdown > 0 else float("nan")

    trades = pd.Series(
        r[r != 0.0] if trade_pnls is None else trade_pnls,
        dtype=float,
    ).replace([np.inf, -np.inf], np.nan).dropna()
    wins = trades[trades > 0]
    losses = trades[trades < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = float("nan")
    win_rate = float((trades > 0).mean()) if len(trades) else float("nan")
    average_win = float(wins.mean()) if len(wins) else float("nan")
    average_loss = float(-losses.mean()) if len(losses) else float("nan")
    payoff_ratio = (
        average_win / average_loss
        if average_loss > 0 and math.isfinite(average_win)
        else float("nan")
    )

    return {
        "total_return": total_return,
        "cagr": cagr,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "average_win": average_win,
        "average_loss": average_loss,
        "payoff_ratio": payoff_ratio,
        "trade_count": float(len(trades)),
    }
