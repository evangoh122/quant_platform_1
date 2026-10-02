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
