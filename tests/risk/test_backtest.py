"""Execution lag, costs, borrow side and cost-model parity."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from risk.compare import build_signal
from risk.config import load_config
from risk.estimators import estimate_pair
from risk.pair_backtest import (
    backtest_vol_pair,
    borrow_rate_daily,
    cost_bps_expr,
    cost_bps_per_side,
)
from risk.sizing import size
from strategies.cost_model import CostParams, cost_per_trade


def _panel(closes: list[float], opens: list[float] | None = None) -> pl.DataFrame:
    n_days = len(closes)
    if opens is None:
        opens = [closes[0]] + [closes[i - 1] * 1.001 for i in range(1, n_days)]
    start = date(2022, 1, 3)
    return pl.DataFrame(
        {
            "date": pl.Series(
                "date", [start + timedelta(days=i) for i in range(n_days)], dtype=pl.Date
            ),
            "open_a": opens,
            "close_a": closes,
            "open_b": opens,
            "close_b": closes,
        }
    )


def _weights(dates: pl.Series, w_a: list[float], w_b: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"date": dates, "w_a": w_a, "w_b": w_b})


def test_execution_lag_shock_cannot_affect_earlier_pnl() -> None:
    cfg = load_config()
    closes = [100.0 * (1.01**i) for i in range(60)]
    shock_index = 40
    shocked_closes = list(closes)
    shocked_closes[shock_index] *= 0.5

    results = []
    for series in (closes, shocked_closes):
        panel = _panel(series)
        estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
        signal = build_signal(
            panel,
            replace(cfg.signals, mode="reversal", lookback=1),
            cfg.columns,
        )
        weights = size(
            signal, estimates, replace(cfg.sizing, method="equal_dollar")
        )
        results.append(
            backtest_vol_pair(panel, weights, cfg.backtest, columns=cfg.columns).daily
        )

    baseline, shocked = results
    dates = _panel(closes)["date"]
    shock_date = dates[shock_index]
    next_date = dates[shock_index + 1]

    assert_frame_equal(
        baseline.filter(pl.col("date") <= shock_date).select("date", "net_return"),
        shocked.filter(pl.col("date") <= shock_date).select("date", "net_return"),
        check_exact=True,
    )
    base_next = float(
        baseline.filter(pl.col("date") == next_date)["net_return"][0]
    )
    shocked_next = float(
        shocked.filter(pl.col("date") == next_date)["net_return"][0]
    )
    assert shocked_next != base_next


def test_weight_decided_at_close_cannot_earn_the_next_open_gap() -> None:
    """The fill at open ``t+1`` must not capture the gap into its own fill price.

    A signal at the close of ``t`` fills at the open of ``t+1`` and only earns
    from that open onward.  With a single shift the weight decided at close
    ``t`` would earn the ``t -> t+1`` open gap, which is a one-bar look-ahead.
    """
    cfg = load_config()
    n_days = 12
    start = date(2023, 3, 1)
    dates = [start + timedelta(days=index) for index in range(n_days)]
    signal_row = 5  # weight decided at close 5 ...
    fill_row = 6  # ... fills at open 6, the day of the gap.

    opens = [100.0] * n_days
    closes = [100.0] * n_days
    opens[fill_row] = 110.0  # +10 % gap exactly at the fill price
    closes[fill_row] = 110.0
    opens[fill_row + 1] = 115.5  # +5 % earned by the filled book
    closes[fill_row + 1 :] = [115.5] * (n_days - fill_row - 1)
    opens[fill_row + 2 :] = [115.5] * (n_days - fill_row - 2)

    panel = pl.DataFrame(
        {
            "date": pl.Series("date", dates, dtype=pl.Date),
            "open_a": opens,
            "close_a": closes,
            "open_b": [100.0] * n_days,
            "close_b": [100.0] * n_days,
        }
    )
    weights = _weights(
        panel["date"],
        [0.5 if index >= signal_row else 0.0 for index in range(n_days)],
        [0.0] * n_days,
    )
    result = backtest_vol_pair(
        panel,
        weights,
        replace(cfg.backtest, cost_bps_per_side=10.0),
        columns=cfg.columns,
    )
    daily = result.daily
    fill_day = daily.filter(pl.col("date") == dates[fill_row])
    assert float(fill_day["ret_a"][0]) == pytest.approx(0.10, rel=1e-12)
    # The book was not held over the gap into the fill: no P&L on the fill day.
    assert float(fill_day["gross_return"][0]) == 0.0
    # Entering the new book is a real trade on the fill day and is charged.
    assert float(fill_day["turnover_cost"][0]) == pytest.approx(
        0.5 * 10.0 / 10_000.0, rel=1e-12
    )
    # The filled book does earn the following open-to-open move.
    next_day = daily.filter(pl.col("date") == dates[fill_row + 1])
    assert float(next_day["gross_return"][0]) == pytest.approx(0.025, rel=1e-12)


def test_doubling_cost_lowers_net_pnl_when_turnover_positive() -> None:
    cfg = load_config()
    closes = [100.0 * (1.002**i) for i in range(40)]
    panel = _panel(closes)
    dates = panel["date"]
    signs = [1.0 if i % 2 == 0 else -1.0 for i in range(len(closes))]
    weights = _weights(dates, [0.5 * s for s in signs], [-0.5 * s for s in signs])

    cheap = backtest_vol_pair(
        panel,
        weights,
        replace(cfg.backtest, cost_bps_per_side=5.0),
        columns=cfg.columns,
    )
    expensive = backtest_vol_pair(
        panel,
        weights,
        replace(cfg.backtest, cost_bps_per_side=10.0),
        columns=cfg.columns,
    )
    assert cheap.metrics["turnover_avg"] > 0.0
    assert expensive.metrics["net_pnl_total"] < cheap.metrics["net_pnl_total"]


def test_zero_turnover_has_zero_cost() -> None:
    cfg = load_config()
    panel = _panel([100.0 * (1.001**i) for i in range(30)])
    zeros = _weights(panel["date"], [0.0] * panel.height, [0.0] * panel.height)
    result = backtest_vol_pair(panel, zeros, cfg.backtest, columns=cfg.columns)
    assert result.metrics["turnover_cost_total"] == pytest.approx(0.0, abs=1e-15)
    assert result.metrics["borrow_cost_total"] == pytest.approx(0.0, abs=1e-15)


def test_borrow_only_on_short_notional() -> None:
    cfg = load_config()
    panel = _panel([100.0 * (1.001**i) for i in range(30)])
    long_only = _weights(
        panel["date"], [0.5] * panel.height, [0.0] * panel.height
    )
    hedged = _weights(
        panel["date"], [0.5] * panel.height, [-0.5] * panel.height
    )
    long_result = backtest_vol_pair(
        panel, long_only, cfg.backtest, columns=cfg.columns
    )
    hedged_result = backtest_vol_pair(
        panel, hedged, cfg.backtest, columns=cfg.columns
    )
    assert long_result.metrics["borrow_cost_total"] == pytest.approx(0.0, abs=1e-15)
    assert hedged_result.metrics["borrow_cost_total"] > 0.0

    half_short = _weights(
        panel["date"], [0.5] * panel.height, [-0.25] * panel.height
    )
    half_result = backtest_vol_pair(
        panel, half_short, cfg.backtest, columns=cfg.columns
    )
    assert hedged_result.metrics["borrow_cost_total"] == pytest.approx(
        2.0 * half_result.metrics["borrow_cost_total"], rel=1e-9
    )
    assert borrow_rate_daily("liquid") == CostParams().borrow_bps_daily["liquid"]


def test_polars_cost_expression_matches_scalar_cost_per_trade() -> None:
    params = CostParams()
    notionals = [100_000.0, 1_000_000.0, 5_000_000.0, 20_000_000.0, 0.0]
    advs = [100_000_000.0, 100_000_000.0, 100_000_000.0, 50_000_000.0, 0.0]
    frame = pl.DataFrame({"notional": notionals, "adv": advs})
    got = frame.select(
        cost_bps_expr(pl.col("notional"), pl.col("adv"), params).alias("bps")
    )["bps"].to_list()
    expected = [
        cost_per_trade(notional, adv, params)
        for notional, adv in zip(notionals, advs)
    ]
    assert got == pytest.approx(expected, rel=1e-12, abs=1e-12)
    assert cost_bps_per_side(1_000_000.0, 100_000_000.0, params) == pytest.approx(
        cost_per_trade(1_000_000.0, 100_000_000.0, params)
    )
