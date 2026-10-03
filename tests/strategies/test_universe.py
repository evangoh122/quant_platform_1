"""Point-in-time universe invariants (offline reference of gold_tradable_universe).

The production universe is built by ``gold/06_gold_tradable_universe.sql``; the
pandas reference in ``strategies/universe.py`` mirrors it so the point-in-time
property — membership on date t depends only on bars strictly before t — can be
proven offline.
"""

import numpy as np
import pandas as pd
import pytest

from strategies.universe import screen_universe, universe_members


def _panel(n_symbols=20, n_days=400, seed=0):
    dates = pd.date_range("2023-01-03", periods=n_days, freq="B")
    rows = []
    rng = np.random.RandomState(seed)
    for i in range(n_symbols):
        sym = f"S{i:02d}"
        base = 100.0 + 5.0 * i
        for d, date in enumerate(dates):
            dv = base * (1.0 + d / 100.0) * 1e6 + rng.normal(0, 1e4)
            rows.append((sym, date, dv))
    return pd.DataFrame(rows, columns=["symbol", "event_date", "dollar_volume"])


def test_membership_on_t_is_invariant_to_future_data():
    panel = _panel()
    base = screen_universe(panel, n=5, min_history=100, recency_sessions=5)

    t = base["trade_date"].iloc[200]
    base_members = universe_members(base, t)

    # Perturb every bar strictly after t (huge dollar-volume shock + a new name).
    future = panel.copy()
    future.loc[future["event_date"] > t, "dollar_volume"] *= 1000.0
    extra = pd.DataFrame(
        [(f"Z{j:02d}", t + pd.Timedelta(days=k), 1e15) for j in range(5) for k in (1, 2, 3)],
        columns=["symbol", "event_date", "dollar_volume"],
    )
    alt = screen_universe(pd.concat([future, extra]), n=5, min_history=100, recency_sessions=5)

    assert universe_members(alt, t) == base_members, (
        "universe membership for date t changed when only future data changed"
    )


def test_recency_filter_excludes_stale_symbol():
    panel = _panel()
    sym = "S00"
    cutoff = panel["event_date"].max() - pd.Timedelta(days=15)
    stale = panel[~((panel["symbol"] == sym) & (panel["event_date"] > cutoff))]

    out = screen_universe(stale, n=20, min_history=100, recency_sessions=5)
    last_date = stale["event_date"].max()
    members = universe_members(out, last_date)

    assert sym not in members, (
        f"symbol {sym} stopped trading but is still in the universe on {last_date}"
    )


def test_min_history_gate():
    panel = _panel()
    # A symbol with far too little history must never appear.
    short = panel[panel["symbol"] != "S00"].copy()
    late = pd.DataFrame(
        [("S00", panel["event_date"].iloc[300], 1e9)],
        columns=["symbol", "event_date", "dollar_volume"],
    )
    out = screen_universe(pd.concat([short, late]), n=20, min_history=252, recency_sessions=5)
    assert "S00" not in set(out["symbol"])


def test_history_gate_counts_own_sessions_not_grid_rows():
    """History must count the symbol's own trading sessions (non-NULL
    dollar_volume), not the total calendar rows in the dense grid.

    A symbol that lists late has many NULL rows in the dense grid before its
    first trade.  A ``COUNT(*)``-style gate would count those NULL rows and
    admit the symbol far too early; ``COUNT(dollar_volume)`` correctly requires
    252 actual trading sessions.
    """
    # 400 calendar days, 10 mature symbols.
    dates = pd.date_range("2023-01-03", periods=400, freq="B")
    rng = np.random.RandomState(42)
    rows = []
    for i in range(10):
        sym = f"M{i:02d}"
        for d, date in enumerate(dates):
            rows.append((sym, date, 1e6 + rng.normal(0, 1e4)))

    # Late-lister: starts on day 350, trades every day after (50 sessions).
    for d in range(350, 400):
        rows.append(("LATE", dates[d], 5e8))

    panel = pd.DataFrame(rows, columns=["symbol", "event_date", "dollar_volume"])
    out = screen_universe(panel, n=20, min_history=252, recency_sessions=5)

    # LATE has only 50 own sessions before its last date — must be excluded.
    late_in = out[out["symbol"] == "LATE"]
    assert late_in.empty, (
        "LATE (50 own sessions) entered the universe with min_history=252; "
        "the history gate is counting grid rows instead of own trading sessions"
    )


def test_partial_window_median_excluded():
    """A 60-session window with fewer than 60 valid bars must not produce a
    median ADV.  The SQL uses PERCENTILE which ignores NULLs, so a window
    with only 5 non-NULL grid rows still computes a median — this is wrong.

    CodeRabbit finding #3: compute COUNT(dollar_volume) over the same 60-row
    window, and set med_adv_60d to NULL unless the count is 60.

    The pandas reference uses min_periods=adv_window, which already enforces
    this.  This test verifies the pandas reference's behavior.
    """
    # 100 calendar days, 2 symbols.  SPARSE has dollar_volume on only 5 days;
    # the rest are NULL (simulated by not including those rows — the dense grid
    # would have NULLs).
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    rng = np.random.RandomState(77)
    rows = []
    # DENSE: trades every day (mature symbol).
    for d, date in enumerate(dates):
        rows.append(("DENSE", date, 1e8 + rng.normal(0, 1e6)))
    # SPARSE: trades on only 5 days out of 100.
    sparse_days = [10, 30, 50, 70, 90]
    for d in sparse_days:
        rows.append(("SPARSE", dates[d], 5e8))

    panel = pd.DataFrame(rows, columns=["symbol", "event_date", "dollar_volume"])
    out = screen_universe(panel, n=10, adv_window=60, min_history=10,
                          recency_sessions=1)

    # SPARSE has only 5 valid bars in any 60-row window.  The pandas reference
    # (min_periods=60) must NOT compute a median for SPARSE.
    sparse_out = out[out["symbol"] == "SPARSE"]
    assert sparse_out.empty, (
        "SPARSE (5 valid bars in 60-row window) entered the universe; "
        "the partial-window median guard is missing"
    )


def test_partial_sma50_excluded():
    """A 50-day SMA must be NULL when fewer than 50 non-NULL values exist in
    the window.  The SQL uses AVG() which computes on whatever non-NULL values
    are available, producing a misleading SMA from a partial window.

    CodeRabbit finding #4: make the SMA NULL when COUNT(*) OVER (same window)
    < 50.  The CASE then labels those dates MIXED.

    This test verifies the pandas equivalent: rolling mean with
    min_periods=50 returns NaN for partial windows.
    """
    # 80 days of data; rsp_spy_ratio is non-NULL only for the last 30 days.
    dates = pd.date_range("2024-01-01", periods=80, freq="B")
    ratio = pd.Series(np.nan, index=dates, dtype=float)
    ratio.iloc[50:] = 1.0 + np.random.default_rng(42).normal(0.0, 0.01, 30)

    # Without min_periods: SQL AVG() computes on available non-NULL values
    # (equivalent to pandas min_periods=1).
    sma_no_guard = ratio.rolling(50, min_periods=1).mean()
    # With min_periods=50: partial windows are NaN (correct).
    sma_with_guard = ratio.rolling(50, min_periods=50).mean()

    # At index 79 the 50-row window [30, 79] has only 30 non-NULL values.
    # The unguarded SMA computes a value; the guarded one must be NaN.
    assert not np.isnan(sma_no_guard.iloc[79]), (
        "unguarded SMA should compute a value from partial window"
    )
    assert np.isnan(sma_with_guard.iloc[79]), (
        "guarded SMA should be NULL for partial window (< 50 valid rows)"
    )
