"""Execution lag, costs, borrow side and cost-model parity."""

from __future__ import annotations

import math
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


def test_borrow_accrues_on_the_book_held_over_the_interval() -> None:
    """Borrow bills the book held over open-to-open, not the book filled today."""
    cfg = load_config()
    panel = _panel([100.0 * (1.001**index) for index in range(14)])
    schedule_a = [
        0.6, -0.4, 0.0, 0.5, -0.5, 0.25, 0.0, -0.75, 0.4, -0.2, 0.3, -0.1, 0.2, -0.3
    ]
    schedule_b = [-0.5 * weight for weight in schedule_a]
    weights = _weights(panel["date"], schedule_a, schedule_b)
    result = backtest_vol_pair(
        panel,
        weights,
        replace(cfg.backtest, cost_bps_per_side=0.0),
        columns=cfg.columns,
    )
    daily = result.daily
    rate = borrow_rate_daily(cfg.backtest.borrow_bucket) / 10_000.0
    # The first row has no open-to-open return, so daily row i is panel row i+1.
    assert daily.height == panel.height - 1

    held_rows = [schedule_a[row - 2] if row >= 2 else 0.0 for row in range(1, panel.height)]
    expected_held = []
    expected_exec = []
    for row in range(1, panel.height):
        held_a = schedule_a[row - 2] if row >= 2 else 0.0
        held_b = schedule_b[row - 2] if row >= 2 else 0.0
        exec_a, exec_b = schedule_a[row - 1], schedule_b[row - 1]
        expected_held.append((max(-held_a, 0.0) + max(-held_b, 0.0)) * rate)
        expected_exec.append((max(-exec_a, 0.0) + max(-exec_b, 0.0)) * rate)

    assert daily["borrow_cost"].to_list() == pytest.approx(
        expected_held, rel=1e-12, abs=1e-18
    )
    assert [float(value) for value in daily["w_a_held"]] == pytest.approx(held_rows)

    held_total = sum(expected_held)
    exec_total = sum(expected_exec)
    assert held_total > 0.0
    # The two candidate books really differ here, so the pin above is not vacuous.
    assert not math.isclose(held_total, exec_total, rel_tol=1e-6)


def test_realized_vol_ddof_follows_config() -> None:
    cfg = load_config()
    closes = [
        100.0 * (1.004**index) * (1.0 + 0.01 * (-1) ** index) for index in range(40)
    ]
    panel = _panel(closes)
    # Only leg A is traded: the fixture gives both legs identical returns, so a
    # hedged book would have zero gross variance and prove nothing.
    weights = _weights(panel["date"], [0.5] * panel.height, [0.0] * panel.height)
    population = backtest_vol_pair(
        panel, weights, replace(cfg.backtest, sharpe_ddof=0), columns=cfg.columns
    )
    sample = backtest_vol_pair(
        panel, weights, replace(cfg.backtest, sharpe_ddof=1), columns=cfg.columns
    )
    n_days = population.metrics["n_days"]
    ratio = math.sqrt(n_days / (n_days - 1.0))
    assert population.metrics["realized_vol_gross"] > 0.0
    assert population.metrics["realized_vol_net"] > 0.0
    for key in ("realized_vol_gross", "realized_vol_net"):
        assert sample.metrics[key] == pytest.approx(
            population.metrics[key] * ratio, rel=1e-12
        )
        assert not math.isclose(
            sample.metrics[key], population.metrics[key], rel_tol=1e-6
        )


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
