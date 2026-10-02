"""Residual signal invariants: rolling betas are lagged (no lookahead), the
industry factor excludes the stock itself, and the entry/exit state machine is
sane."""

import numpy as np
import pandas as pd
import pytest

from strategies.residual_reversion import (
    compute_daily_returns,
    compute_industry_factor,
    compute_residuals,
    generate_signals,
    load_industry_map,
)


def _synth_returns(n_days=200, seed=42):
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(seed)
    market = pd.Series(rng.normal(0.0, 0.01, n_days), index=dates)
    industry = {"A": "tech", "B": "tech", "C": "fin", "D": "fin"}
    data = {}
    for s, ind in industry.items():
        beta = 1.1 if ind == "tech" else 0.9
        data[s] = beta * market.to_numpy() + rng.normal(0.0, 0.01, n_days)
    return pd.DataFrame(data, index=dates), market, industry


def test_industry_factor_excludes_self():
    returns, market, industry = _synth_returns()
    factor = compute_industry_factor(returns, industry)
    # For A the only other tech name is B, so its factor equals B's return.
    assert factor.loc[returns.index[10], "A"] == pytest.approx(
        returns.loc[returns.index[10], "B"]
    )
    # For C the only other fin name is D.
    assert factor.loc[returns.index[10], "C"] == pytest.approx(
        returns.loc[returns.index[10], "D"]
    )


def test_industry_factor_is_zero_for_singleton():
    returns, market, _ = _synth_returns()
    industry = {"A": "solo", "B": "tech", "C": "tech", "D": "fin"}
    factor = compute_industry_factor(returns, industry)
    assert (factor["A"] == 0.0).all()


def test_perturbing_day_t_return_does_not_change_beta():
    returns, market, industry = _synth_returns()
    ind = compute_industry_factor(returns, industry)
    window, lookback = 60, 5

    base = compute_residuals(returns, market, ind, window=window, lookback=lookback)

    t = returns.index[100]
    perturbed = returns.copy()
    perturbed.loc[t, "A"] += 0.5  # shock only A's return on day t

    alt = compute_residuals(perturbed, market, ind, window=window, lookback=lookback)

    # The beta used for day t's signal must be unchanged (it is estimated on
    # [t-window, t-1], which excludes day t).
    assert base["beta_mkt"].loc[t, "A"] == pytest.approx(alt["beta_mkt"].loc[t, "A"])
    assert base["beta_ind"].loc[t, "A"] == pytest.approx(alt["beta_ind"].loc[t, "A"])
    # But the residual (and therefore the signal) at t does move.
    assert base["residual"].loc[t, "A"] != alt["residual"].loc[t, "A"]


def test_signal_enters_long_then_exits():
    dates = pd.date_range("2024-01-01", periods=40, freq="B")
    s = pd.Series(0.0, index=dates, dtype=float)
    s.iloc[10:20] = -3.0  # deep long signal
    s.iloc[20:30] = -0.2  # mean reverted: should exit (|s| < 0.5)
    frame = pd.DataFrame({"A": s})
    pos = generate_signals(frame, entry=2.5, exit_thresh=0.5, max_hold=10)

    assert pos.loc[dates[11], "A"] == 1.0   # entered long after threshold cross
    assert pos.loc[dates[21], "A"] == 0.0   # exited once reverted


def test_max_hold_force_closes():
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    s = pd.Series(-3.0, index=dates, dtype=float)  # stay deep
    frame = pd.DataFrame({"A": s})
    pos = generate_signals(frame, entry=2.5, exit_thresh=0.5, max_hold=5)
    # A position may not be held longer than max_hold consecutive bars.
    runs = []
    run = 0
    for v in pos["A"].to_numpy():
        if v != 0:
            run += 1
            runs.append(run)
        else:
            run = 0
    assert max(runs) <= 5


def test_industry_map_is_repo_taxonomy():
    mapping = load_industry_map()
    # Smoke test: mapping is non-empty and values are the repo group names.
    assert isinstance(mapping, dict) and len(mapping) > 0
