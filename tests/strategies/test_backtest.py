"""Backtester invariants: the one-bar execution lag is structural, trades
outside the point-in-time universe are prevented, and the neutralised book is
dollar/beta/industry neutral."""

import numpy as np
import pandas as pd
import pytest

from strategies.backtest import (
    compute_costs,
    enforce_execution_lag,
    filter_to_universe,
    neutralize_daily,
    run_backtest,
)
from strategies.cost_model import CostParams


@pytest.fixture
def dates():
    return pd.date_range("2024-01-01", periods=20, freq="B")


@pytest.fixture
def symbols():
    return ["A", "B", "C", "D"]


def test_signal_on_day_t_cannot_fill_on_day_t(dates, symbols):
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[3], "A"] = 1.0  # a single signal at day 3's close

    fills = enforce_execution_lag(desired)

    # No same-bar fill: day 3 must still be flat.
    assert fills.loc[dates[3], "A"] == 0.0
    # The fill lands on day 4.
    assert fills.loc[dates[4], "A"] == 1.0
    # And it never leaks backwards.
    assert (fills.loc[:dates[3], "A"] == 0.0).all()


def test_full_backtest_signal_earns_no_return_on_signal_day(dates, symbols):
    returns = pd.DataFrame(0.0, index=dates, columns=symbols)
    returns.loc[dates[5], "A"] = 0.10  # big return on day 5

    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[4], "A"] = 1.0  # signal at day 4 close -> fill day 5

    universe = pd.DataFrame({"trade_date": dates, "symbol": ["A"] * len(dates)})
    universe = pd.concat([universe] * len(symbols), ignore_index=True)
    universe = universe.drop_duplicates()
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)

    res = run_backtest(desired, returns, universe, adv, target_gross=1.0)

    # The position from day 4's signal is filled on day 5, so it earns day 6's
    # return, not day 5's. Gross PnL on day 5 must be 0.
    assert res["gross"].loc[dates[5]] == pytest.approx(0.0)


def test_trade_outside_universe_is_zeroed(dates, symbols):
    fills = pd.DataFrame(1.0, index=dates, columns=symbols)
    # Universe only ever contains A; B/C/D are never tradable.
    universe = pd.DataFrame({"trade_date": dates, "symbol": ["A"] * len(dates)})

    filtered = filter_to_universe(fills, universe)

    assert (filtered["A"] == 1.0).all()
    assert (filtered[["B", "C", "D"]] == 0.0).all().all()


def test_neutralized_book_is_dollar_beta_industry_neutral(dates, symbols):
    # Asymmetric weights so the book has an idiosyncratic component that survives
    # neutralisation (a pure [1,-1,1,-1] book is exactly a systematic bet and
    # neutralising it correctly yields zero).
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    for d in dates:
        weights.loc[d] = {"A": 0.5, "B": -1.0, "C": 0.3, "D": -0.8}

    beta = pd.DataFrame(1.0, index=dates, columns=symbols)
    beta[["A", "C"]] = 1.2
    beta[["B", "D"]] = 0.8
    industry = pd.Series({"A": "tech", "B": "tech", "C": "fin", "D": "fin"})

    out = neutralize_daily(weights, beta=beta, industry=industry, target_gross=1.0)

    for d in dates:
        w = out.loc[d]
        assert abs(w.sum()) < 1e-9                      # dollar neutral
        assert abs((w * beta.loc[d]).sum()) < 1e-9      # beta neutral
        assert abs(w["A"] + w["B"]) < 1e-9              # industry neutral (tech)
        assert abs(w["C"] + w["D"]) < 1e-9              # industry neutral (fin)


def test_compute_costs_charges_borrow_on_shorts(dates, symbols):
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    weights["A"] = 0.6   # long
    weights["B"] = -0.6  # short (pays borrow)
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)  # liquid bucket
    params = CostParams()
    costs = compute_costs(weights, adv, book_capital=10_000_000.0, params=params)
    # Borrow is charged for the short leg only.
    assert (costs["borrow_cost"] > 0).all()


def test_run_backtest_reports_gross_net_and_net_2x(dates, symbols):
    returns = pd.DataFrame(np.random.default_rng(0).normal(0.001, 0.01, (20, 4)),
                           index=dates, columns=symbols)
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[2], "A"] = 1.0
    desired.loc[dates[2], "C"] = -1.0

    universe = pd.DataFrame(
        [(d, s) for d in dates for s in symbols],
        columns=["trade_date", "symbol"],
    )
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)

    res = run_backtest(desired, returns, universe, adv, target_gross=1.0)
    m = res["metrics"]
    for k in ("gross_ann_return", "net_ann_return", "net_2x_ann_return",
              "gross_sharpe", "net_sharpe", "net_2x_sharpe", "turnover_avg_daily"):
        assert k in m
