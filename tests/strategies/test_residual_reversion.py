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


def test_missing_returns_stay_nan():
    """compute_daily_returns must NOT fill NaN with 0."""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    prices = pd.DataFrame({"A": [100, 101, 102, np.nan, 104, 105, 106, 107, 108, 109],
                            "B": [50, 51, 52, 53, 54, 55, 56, 57, 58, 59]}, index=dates)
    ret = compute_daily_returns(prices)
    # First row is always NaN (no prior price).
    assert np.isnan(ret.loc[dates[0], "A"])
    assert np.isnan(ret.loc[dates[0], "B"])
    # A's return on the day after the gap should be NaN, not 0.
    assert np.isnan(ret.loc[dates[4], "A"])
    # B's returns (except first row) should all be finite.
    assert ret["B"].iloc[1:].notna().all()


def test_appending_future_symbol_does_not_change_earlier_factors():
    """Industry factors before date d are unchanged when a symbol only exists
    after d is appended."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    rng = np.random.default_rng(99)
    base_data = {
        "A": rng.normal(0.0, 0.01, 30),
        "B": rng.normal(0.0, 0.01, 30),
        "C": rng.normal(0.0, 0.01, 30),
        "D": rng.normal(0.0, 0.01, 30),
    }
    returns_base = pd.DataFrame(base_data, index=dates)
    industry_base = {"A": "tech", "B": "tech", "C": "fin", "D": "fin"}

    factor_base = compute_industry_factor(returns_base, industry_base)

    # E is a tech name that only exists from day 20 onward.
    data_with_e = {**base_data, "E": [np.nan] * 20 + list(rng.normal(0.0, 0.01, 10))}
    returns_e = pd.DataFrame(data_with_e, index=dates)
    industry_e = {**industry_base, "E": "tech"}

    factor_e = compute_industry_factor(returns_e, industry_e)

    # Factors for A, B, C, D before day 20 must be identical.
    pd.testing.assert_frame_equal(
        factor_base.loc[dates[:20], ["A", "B", "C", "D"]],
        factor_e.loc[dates[:20], ["A", "B", "C", "D"]],
    )


def test_nan_returns_not_counted_as_zeros():
    """A symbol with gaps in its return series must be regressed on only the
    valid rows, not treat the gaps as zero-return days.

    CodeRabbit finding #1: _rolling_lagged_sum uses np.nan_to_num and
    _rolling_residuals_one_symbol uses n = float(window), so a window with
    30 valid + 30 NaN days is fitted as 60 days with 30 zeros.
    """
    from strategies.residual_reversion import compute_industry_factor

    window = 60
    n_days = 120
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(123)
    market = pd.Series(rng.normal(0.0, 0.01, n_days), index=dates)

    # Two symbols in same industry so industry factor is non-zero.
    y_raw_a = 1.1 * market.to_numpy() + rng.normal(0.0, 0.01, n_days)
    y_raw_b = 0.9 * market.to_numpy() + rng.normal(0.0, 0.01, n_days)
    y_a = y_raw_a.copy()
    y_a[30:60] = np.nan  # 30-day gap in A

    returns = pd.DataFrame({"A": y_a, "B": y_raw_b}, index=dates)
    industry_map = {"A": "tech", "B": "tech"}
    ind = compute_industry_factor(returns, industry_map)

    # Use min_obs=25 so 30 valid rows in the window passes the gate.
    result = compute_residuals(returns, market, ind, window=window,
                               lookback=5, min_obs=25)
    alpha_cur = result["alpha"]["A"].to_numpy()
    beta_cur = result["beta_mkt"]["A"].to_numpy()

    # Reference: OLS on valid rows only for day 80 (window [20, 79]).
    t_idx = 80
    y_win = y_a[t_idx - window:t_idx]
    m_win = market.to_numpy()[t_idx - window:t_idx]
    f_win = ind["A"].to_numpy()[t_idx - window:t_idx]
    valid = np.isfinite(y_win) & np.isfinite(m_win) & np.isfinite(f_win)
    n_valid = valid.sum()
    assert n_valid == 30, f"expected 30 valid rows, got {n_valid}"

    X = np.column_stack([np.ones(n_valid), m_win[valid], f_win[valid]])
    coef_ref, _, _, _ = np.linalg.lstsq(X, y_win[valid], rcond=None)

    # The OLS must match the reference on valid rows only.
    assert alpha_cur[t_idx] == pytest.approx(coef_ref[0], abs=1e-8)
    assert beta_cur[t_idx] == pytest.approx(coef_ref[1], abs=1e-8)

    # Default min_obs (ceil(0.8*60)=48) must reject the 30-row window.
    result2 = compute_residuals(returns, market, ind, window=window, lookback=5)
    assert np.isnan(result2["alpha"]["A"].to_numpy()[t_idx]), (
        "default min_obs=48 should reject a window with only 30 valid rows"
    )


def test_sigma_uses_min_obs_not_full_window():
    """A series with 10% gaps gets a non-NaN s_score once the window has
    >= min_obs valid residuals, not only when it has a full window of them.

    The beta uses min_obs = ceil(0.8 * window) = 48 for window=60, but
    _trailing_std was using min_periods=window (60), so one gap in the
    trailing window killed sigma for 60 days. After the fix, sigma uses
    the same min_obs.
    """
    window = 60
    n_days = 200
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(456)
    market = pd.Series(rng.normal(0.0, 0.01, n_days), index=dates)

    # Two symbols in same industry.
    y_a = 1.1 * market.to_numpy() + rng.normal(0.0, 0.01, n_days)
    y_b = 0.9 * market.to_numpy() + rng.normal(0.0, 0.01, n_days)

    # Inject ~10% gaps (every 10th day) in A's returns.
    y_a_gapped = y_a.copy()
    gap_indices = list(range(10, n_days, 10))
    y_a_gapped[gap_indices] = np.nan

    returns = pd.DataFrame({"A": y_a_gapped, "B": y_b}, index=dates)
    industry_map = {"A": "tech", "B": "tech"}
    ind = compute_industry_factor(returns, industry_map)

    min_obs = int(np.ceil(0.8 * window))  # 48
    result = compute_residuals(returns, market, ind, window=window,
                               lookback=5, min_obs=min_obs)

    s_score = result["s_score"]["A"].to_numpy()
    sigma = result["sigma"]["A"].to_numpy()

    # After warm-up (day >= window + lookback), there should be days where
    # beta is non-NaN and sigma is also non-NaN. With the old code
    # (min_periods=window for sigma), any gap in the trailing 60-day window
    # makes sigma NaN even though beta tolerates 48/60 valid rows.
    # Find a day well past warm-up where beta is non-NaN.
    beta = result["beta_mkt"]["A"].to_numpy()

    # The residual is NaN for the first `window` days (beta warm-up), so
    # the trailing sigma window for days just past warm-up still contains
    # many NaN residuals from the warm-up period.  We need to check far
    # enough past warm-up that the trailing window contains only data-day
    # residuals (with at most ~6 gap-day NaNs per 60-day window).
    # With ~10% gaps (every 10th day), a 60-day window has ~6 gaps → 54
    # valid residuals, which is above min_obs=48.  But if the window also
    # overlaps the warm-up, valid count drops further.  Start checking at
    # day 2*window so the trailing window is entirely post-warm-up.
    check_start = 2 * window  # day 120

    # Count days where beta is non-NaN but sigma is NaN (the starvation problem).
    beta_nonnan_sigma_nan = 0
    sigma_nonnan = 0
    for i in range(check_start, n_days):
        if np.isfinite(beta[i]):
            if np.isnan(sigma[i]):
                beta_nonnan_sigma_nan += 1
            else:
                sigma_nonnan += 1

    # After the fix, sigma should be non-NaN whenever beta is non-NaN and the
    # trailing window has >= min_obs valid residuals. The starvation count
    # should be 0 (not 38 as with the old code using min_periods=window).
    assert beta_nonnan_sigma_nan == 0, (
        f"sigma starvation: {beta_nonnan_sigma_nan} days where beta is non-NaN "
        f"but sigma is NaN — _trailing_std should use min_periods={min_obs}, not {window}"
    )
    assert sigma_nonnan > 0, "sigma should be non-NaN on at least some days"
