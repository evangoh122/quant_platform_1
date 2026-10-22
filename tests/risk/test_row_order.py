"""Row-order independence: shuffled input must equal the chronological run.

Every frame-level entry point sorts stably by date itself (or rejects the
input), so a caller cannot turn a trailing window into a look-ahead merely by
permuting rows.  These tests permute with several seeds and compare the whole
output frame against the chronological run, then pin the duplicate-date
rejection that makes the ordering unambiguous.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from risk.compare import build_signal, compare_sizers
from risk.config import RegimeParams, load_config
from risk.estimators import estimate_pair
from risk.pair_backtest import backtest_vol_pair, performance_metrics
from risk.regimes import label_regimes
from risk.sizing import size
from risk.synthetic import synthetic_pair_panel

SEEDS = (0, 1, 2, 3, 7)


def _shuffled(frame: pl.DataFrame, seed: int) -> pl.DataFrame:
    """A deterministic permutation of every row."""
    return frame.sample(n=frame.height, shuffle=True, seed=seed)


def _finding_frame() -> pl.DataFrame:
    start = date(2026, 1, 1)
    return pl.DataFrame(
        {
            "date": pl.Series(
                "date",
                [start + timedelta(days=offset) for offset in range(4)],
                dtype=pl.Date,
            ),
            "vol_a": [0.1, 0.2, 0.3, 0.4],
        }
    )


def _finding_params() -> RegimeParams:
    return RegimeParams(
        percentile_window=3,
        percentile_min_history=3,
        low_threshold=0.33,
        high_threshold=0.67,
        unknown_label="unknown",
    )


def test_label_regimes_reversed_input_does_not_read_the_future() -> None:
    """The exact finding: reversing four rows must not relabel the first day."""
    frame = _finding_frame()
    params = _finding_params()
    chronological = label_regimes(frame, params, "vol_a")
    reversed_rows = label_regimes(frame.reverse(), params, "vol_a")

    assert chronological["date"].to_list() == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 4),
    ]
    first = chronological.filter(pl.col("date") == date(2026, 1, 1))
    # Three sessions of history do not exist yet on the first day.
    assert first["vol_pct"].to_list() == [None]
    assert first["regime"].to_list() == ["unknown"]
    assert_frame_equal(reversed_rows, chronological, check_exact=True)


@pytest.mark.parametrize("seed", SEEDS)
def test_label_regimes_is_invariant_to_row_order(seed: int) -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=340, seed=21), 252)
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    chronological = label_regimes(estimates, cfg.regimes, "vol_a")
    shuffled = label_regimes(_shuffled(estimates, seed), cfg.regimes, "vol_a")

    # Non-vacuous: the window is long enough to have produced real percentiles.
    assert chronological["vol_pct"].null_count() < chronological.height
    assert_frame_equal(shuffled, chronological, check_exact=True)
    assert shuffled["date"].to_list() == chronological["date"].to_list()


@pytest.mark.parametrize("seed", SEEDS)
def test_estimate_pair_is_invariant_to_row_order(seed: int) -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=260, seed=31), 252)
    chronological = estimate_pair(panel, cfg.estimators, cfg.columns)
    shuffled = estimate_pair(_shuffled(panel, seed), cfg.estimators, cfg.columns)

    assert chronological["vol_a"].null_count() < chronological.height
    assert_frame_equal(shuffled, chronological, check_exact=True)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("method", ["covariance_aware", "vol_target"])
def test_size_is_invariant_to_row_order(seed: int, method: str) -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=260, seed=41), 252)
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signals = build_signal(panel, cfg.signals, cfg.columns)
    params = replace(cfg.sizing, method=method)
    chronological = size(signals, estimates, params)
    shuffled = size(
        _shuffled(signals, seed + 100),
        _shuffled(estimates, seed),
        params,
    )

    assert float(chronological["w_a"].abs().sum()) > 0.0
    assert_frame_equal(shuffled, chronological, check_exact=True)


@pytest.mark.parametrize("seed", SEEDS)
def test_pair_backtest_is_invariant_to_row_order(seed: int) -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=300, seed=51), 252)
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signal = build_signal(panel, cfg.signals, cfg.columns)
    weights = size(signal, estimates, cfg.sizing)

    chronological = backtest_vol_pair(
        panel, weights, cfg.backtest, columns=cfg.columns
    )
    shuffled = backtest_vol_pair(
        _shuffled(panel, seed + 7),
        _shuffled(weights, seed),
        cfg.backtest,
        columns=cfg.columns,
    )

    assert chronological.daily.height > 0
    assert chronological.metrics["turnover_avg"] > 0.0
    assert_frame_equal(shuffled.daily, chronological.daily, check_exact=True)
    assert shuffled.metrics == chronological.metrics


def test_performance_metrics_is_invariant_to_row_order() -> None:
    """A cumulative path is order-dependent, so the metric helper must sort."""
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=180, seed=61), 252)
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signal = build_signal(panel, cfg.signals, cfg.columns)
    weights = size(signal, estimates, cfg.sizing)
    daily = backtest_vol_pair(
        panel, weights, cfg.backtest, columns=cfg.columns
    ).daily

    chronological = performance_metrics(daily, cfg.backtest)
    shuffled = performance_metrics(_shuffled(daily, 5), cfg.backtest)

    # Non-vacuous: the drawdown statistic really is path-dependent.
    assert chronological["max_drawdown"] < 0.0
    assert shuffled == chronological


def test_duplicate_dates_are_rejected_by_every_frame_entry_point() -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=40, seed=71), 252)
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signals = build_signal(panel, cfg.signals, cfg.columns)
    weights = size(signals, estimates, cfg.sizing)
    daily = backtest_vol_pair(
        panel, weights, cfg.backtest, columns=cfg.columns
    ).daily

    duplicated_panel = pl.concat([panel, panel.head(1)])
    duplicated_estimates = pl.concat([estimates, estimates.head(1)])
    duplicated_signals = pl.concat([signals, signals.head(1)])
    duplicated_weights = pl.concat([weights, weights.head(1)])
    duplicated_daily = pl.concat([daily, daily.head(1)])

    with pytest.raises(ValueError, match="duplicate dates"):
        estimate_pair(duplicated_panel, cfg.estimators, cfg.columns)
    with pytest.raises(ValueError, match="duplicate dates"):
        build_signal(duplicated_panel, cfg.signals, cfg.columns)
    with pytest.raises(ValueError, match="duplicate dates"):
        label_regimes(duplicated_estimates, cfg.regimes, "vol_a")
    with pytest.raises(ValueError, match="duplicate dates"):
        size(signals, duplicated_estimates, cfg.sizing)
    with pytest.raises(ValueError, match="duplicate dates"):
        size(duplicated_signals, estimates, cfg.sizing)
    with pytest.raises(ValueError, match="duplicate dates"):
        backtest_vol_pair(
            duplicated_panel, weights, cfg.backtest, columns=cfg.columns
        )
    with pytest.raises(ValueError, match="duplicate dates"):
        backtest_vol_pair(
            panel, duplicated_weights, cfg.backtest, columns=cfg.columns
        )
    with pytest.raises(ValueError, match="duplicate dates"):
        performance_metrics(duplicated_daily, cfg.backtest)
    with pytest.raises(ValueError, match="duplicate dates"):
        compare_sizers(
            duplicated_panel,
            cfg,
            signals=signals,
            methods=("equal_dollar",),
            cost_levels=(cfg.costs.baseline_bps,),
        )

SIGNAL_MODES = ("momentum", "reversal", "momentum_z", "constant")


def _adv_frame(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(
        pl.col("date"),
        (pl.col("close_a") * 1_000_000.0).alias("adv_a"),
        (pl.col("close_b") * 1_000_000.0).alias("adv_b"),
    )


def _with_null_dates(frame: pl.DataFrame, count: int) -> pl.DataFrame:
    dates = frame["date"].to_list()
    for index in range(count):
        dates[index] = None
    return frame.with_columns(pl.Series("date", dates, dtype=pl.Date))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", SIGNAL_MODES)
def test_build_signal_is_invariant_to_row_order(seed: int, mode: str) -> None:
    """The lookback and rolling scale read row order: the sort is pinned."""
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=260, seed=81), 252)
    params = replace(cfg.signals, mode=mode)

    chronological = build_signal(panel, params, cfg.columns)
    reversed_rows = build_signal(panel.reverse(), params, cfg.columns)
    shuffled = build_signal(_shuffled(panel, seed), params, cfg.columns)

    dates = chronological["date"].to_list()
    assert dates == sorted(dates)
    # Non-vacuous for every mode: a real signal came out, not all zeros.
    assert float(chronological["signal"].abs().sum()) > 0.0
    assert_frame_equal(reversed_rows, chronological, check_exact=True)
    assert_frame_equal(shuffled, chronological, check_exact=True)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("precomputed", [False, True])
def test_compare_sizers_is_invariant_to_row_order(
    seed: int, precomputed: bool
) -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=240, seed=83), 252)
    signals = (
        build_signal(panel, cfg.signals, cfg.columns) if precomputed else None
    )
    kwargs = {
        "methods": ("equal_dollar", "vol_target"),
        "cost_levels": (cfg.costs.baseline_bps,),
    }

    chronological = compare_sizers(panel, cfg, signals=signals, **kwargs)
    reversed_rows = compare_sizers(
        panel.reverse(),
        cfg,
        signals=None if signals is None else signals.reverse(),
        **kwargs,
    )
    shuffled = compare_sizers(
        _shuffled(panel, seed),
        cfg,
        signals=None if signals is None else _shuffled(signals, seed + 100),
        **kwargs,
    )

    # Non-vacuous: two variants with real turnover and finite metrics.
    assert chronological.height == 2
    assert float(chronological["turnover_avg"].min()) > 0.0
    assert_frame_equal(reversed_rows, chronological, check_exact=True)
    assert_frame_equal(shuffled, chronological, check_exact=True)


@pytest.mark.parametrize("seed", SEEDS)
def test_adv_cost_mode_is_invariant_to_row_order(seed: int) -> None:
    """The ADV join also reads row order; shuffle prices, weights and adv."""
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=240, seed=85), 252)
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signal = build_signal(panel, cfg.signals, cfg.columns)
    weights = size(signal, estimates, cfg.sizing)
    params = replace(cfg.backtest, cost_mode="adv")
    adv = _adv_frame(panel)

    chronological = backtest_vol_pair(
        panel, weights, params, columns=cfg.columns, adv=adv
    )
    shuffled = backtest_vol_pair(
        _shuffled(panel, seed + 11),
        _shuffled(weights, seed),
        params,
        columns=cfg.columns,
        adv=_shuffled(adv, seed + 23),
    )

    # Non-vacuous: the ADV participation model charged real turnover.
    assert float(chronological.daily["turnover_cost"].sum()) > 0.0
    assert_frame_equal(shuffled.daily, chronological.daily, check_exact=True)
    assert shuffled.metrics == chronological.metrics


@pytest.mark.parametrize("nulls", [1, 2])
def test_null_dates_are_rejected_with_the_count(nulls: int) -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=40, seed=87), 252)
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signals = build_signal(panel, cfg.signals, cfg.columns)
    null_panel = _with_null_dates(panel, nulls)
    null_estimates = _with_null_dates(estimates, nulls)
    null_signals = _with_null_dates(signals, nulls)
    message = rf"{nulls} null date"

    with pytest.raises(ValueError, match=message):
        estimate_pair(null_panel, cfg.estimators, cfg.columns)
    with pytest.raises(ValueError, match=message):
        build_signal(null_panel, cfg.signals, cfg.columns)
    with pytest.raises(ValueError, match=message):
        label_regimes(null_estimates, cfg.regimes, "vol_a")
    with pytest.raises(ValueError, match=message):
        size(null_signals, estimates, cfg.sizing)
    with pytest.raises(ValueError, match=message):
        size(signals, null_estimates, cfg.sizing)
