"""Economic performance metrics for strategy backtests.

Ratios are calculated from net periodic returns after transaction costs.  The
caller must supply the correct annualization factor for the return frequency
(for example 252 for daily or 252 * 13 for 30-minute bars).
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Iterable

import numpy as np
import pandas as pd

# Two-sided 95% standard-normal critical value z_{0.975} = Phi^-1(0.975).
_Z_975 = NormalDist().inv_cdf(0.975)


def performance_metrics(
    returns: Iterable[float],
    *,
    periods_per_year: int,
    trade_pnls: Iterable[float] | None = None,
    risk_free_rate: float = 0.0,
    min_observations_for_ratios: int = 252,
) -> dict[str, float | int | str]:
    """Calculate a compact, consistently-defined backtest report.

    ``returns`` is the portfolio return series. ``trade_pnls`` should contain
    one net P&L or net return per **completed trade**; when omitted, non-zero
    periodic returns are used as a conservative proxy for trades (one proxy
    trade per nonzero return period).  Do not pass per-row returns as
    ``trade_pnls`` unless each row truly represents a completed trade.

    Annualization transparency
    --------------------------
    ``periods_per_year`` is echoed back as ``result["periods_per_year"]`` so
    every consumer can see the factor behind ``cagr``,
    ``annualized_volatility`` and the ratios.  **The value must match the
    label horizon of the return series** (daily labels -> 252; 30-minute bars
    -> 252 * 13); a mismatch silently mis-scales every annualized quantity.

    Sample sufficiency gate
    -----------------------
    ``sharpe_ratio``, ``sortino_ratio`` and ``calmar_ratio`` are reported only
    when ``observation_count >= min_observations_for_ratios`` (default 252).
    Below the gate they are NaN and ``sample_state`` is
    ``"insufficient_sample"``; at or above it ``sample_state`` is ``"ok"``.
    The standard error of an annualized Sharpe grows like ``sqrt(252 / T)``,
    so with less than a year of observations the annualized ratios are noise.
    ``observation_count`` and ``sample_state`` are always returned.  The other
    metrics (total_return, cagr, volatility, drawdown, win_rate,
    profit_factor, payoff_ratio, ...) stay numeric on short samples.

    Sharpe uncertainty
    ------------------
    When ``sample_state == "ok"``, ``sharpe_ci_95_low`` / ``sharpe_ci_95_high``
    bracket the annualized Sharpe with the iid large-sample standard error

        SE = sqrt((1 + 0.5 * SR_p**2) / T) * sqrt(periods_per_year)

    where ``SR_p`` is the per-period Sharpe (mean excess return over the
    ddof=1 standard deviation of excess returns) and ``T`` is
    ``observation_count``; the half-width is ``z_{0.975} * SE``.
    ``sharpe_ci_method`` names the approximation (``"iid_normal_approx"``).
    **This assumes iid returns and understates uncertainty under
    autocorrelation** — volatility clustering, overlapping labels and stale
    marks all make the true interval wider.  The CI bounds are NaN when the
    sample is insufficient.

    Drawdown is measured from the starting equity of 1.0: a series that begins
    with a loss will report that loss as drawdown even if the running peak
    never exceeds 1.0.
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")

    r = pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    observation_count = int(len(r))
    sample_state = (
        "ok"
        if observation_count >= min_observations_for_ratios
        else "insufficient_sample"
    )
    if r.empty:
        return {
            "total_return": float("nan"),
            "cagr": float("nan"),
            "annualized_return": float("nan"),
            "annualized_volatility": float("nan"),
            "sharpe_ratio": float("nan"),
            "sortino_ratio": float("nan"),
            "max_drawdown": float("nan"),
            "calmar_ratio": float("nan"),
            "profit_factor": float("nan"),
            "win_rate": float("nan"),
            "average_win": float("nan"),
            "average_loss": float("nan"),
            "payoff_ratio": float("nan"),
            "trade_count": float("nan"),
            "observation_count": observation_count,
            "sample_state": sample_state,
            "periods_per_year": periods_per_year,
            "sharpe_ci_95_low": float("nan"),
            "sharpe_ci_95_high": float("nan"),
            "sharpe_ci_method": "iid_normal_approx",
        }

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

    peak = np.maximum(equity.cummax(), 1.0)
    drawdown = equity / peak - 1.0
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

    if sample_state != "ok":
        sharpe = float("nan")
        sortino = float("nan")
        calmar = float("nan")

    sharpe_ci_95_low = float("nan")
    sharpe_ci_95_high = float("nan")
    if sample_state == "ok" and math.isfinite(sharpe) and excess_std > 0:
        sr_p = float(excess.mean() / excess_std)
        se_ann = (
            math.sqrt((1.0 + 0.5 * sr_p * sr_p) / observation_count)
            * math.sqrt(periods_per_year)
        )
        half_width = _Z_975 * se_ann
        sharpe_ci_95_low = sharpe - half_width
        sharpe_ci_95_high = sharpe + half_width

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
        "observation_count": observation_count,
        "sample_state": sample_state,
        "periods_per_year": periods_per_year,
        "sharpe_ci_95_low": sharpe_ci_95_low,
        "sharpe_ci_95_high": sharpe_ci_95_high,
        "sharpe_ci_method": "iid_normal_approx",
    }
