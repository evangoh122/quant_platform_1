"""Estimator invariants: past-only windows, sample EWMA, gap vs intraday vol."""

from __future__ import annotations

import math
import statistics
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from risk.config import load_config
from risk.estimators import (
    estimate_pair,
    intraday_vol,
    overnight_vol,
    price_returns,
    rolling_vol,
)
from risk.regimes import label_regimes
from risk.sizing import size
from risk.synthetic import synthetic_pair_panel


def _perturb(panel: pl.DataFrame, start_index: int, factor: float = 3.0) -> pl.DataFrame:
    indexed = panel.with_row_index("_i")
    scaled = indexed.with_columns(
        [
            pl.when(pl.col("_i") >= start_index)
            .then(pl.col(column) * factor)
            .otherwise(pl.col(column))
            .alias(column)
            for column in ("open_a", "close_a", "open_b", "close_b")
        ]
    )
    return scaled.drop("_i")


def test_past_weights_unchanged_by_future_perturbation() -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(
        replace(cfg.experiment, n_days=420, seed=11), cfg.estimators.annualization
    )
    cut = 340
    dates = panel["date"].to_list()
    first_future = dates[cut]

    base_est = estimate_pair(panel, cfg.estimators, cfg.columns)
    base_signal = base_est.select(
        pl.col("date"), pl.lit(1.0, dtype=pl.Float64).alias("signal")
    )
    base_weights = size(base_signal, base_est, replace(cfg.sizing, method="covariance_aware"))

    shocked = _perturb(panel, cut)
    shocked_est = estimate_pair(shocked, cfg.estimators, cfg.columns)
    shocked_weights = size(
        base_signal, shocked_est, replace(cfg.sizing, method="covariance_aware")
    )

    assert_frame_equal(
        base_weights.filter(pl.col("date") < first_future),
        shocked_weights.filter(pl.col("date") < first_future),
        check_exact=True,
    )


def test_future_perturbation_leaves_estimators_and_regime_unchanged() -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(
        replace(cfg.experiment, n_days=420, seed=12), cfg.estimators.annualization
    )
    cut = 340
    dates = panel["date"].to_list()
    last_known = dates[cut]

    base_est = estimate_pair(panel, cfg.estimators, cfg.columns)
    base_regime = label_regimes(base_est, cfg.regimes, "vol_a")
    base_signal = base_est.select(
        pl.col("date"), pl.lit(1.0, dtype=pl.Float64).alias("signal")
    )
    base_weights = size(
        base_signal, base_est, replace(cfg.sizing, method="covariance_aware")
    )

    future_only = _perturb(panel, cut + 1)
    future_est = estimate_pair(future_only, cfg.estimators, cfg.columns)
    future_regime = label_regimes(future_est, cfg.regimes, "vol_a")
    future_weights = size(
        base_signal, future_est, replace(cfg.sizing, method="covariance_aware")
    )

    columns = [
        "r_a",
        "r_b",
        "vol_a",
        "vol_b",
        "corr",
        "cov",
        "overnight_vol_a",
        "intraday_vol_a",
        "overnight_vol_b",
        "intraday_vol_b",
        "vol_pct_a",
    ]
    assert_frame_equal(
        base_est.filter(pl.col("date") <= last_known).select(columns),
        future_est.filter(pl.col("date") <= last_known).select(columns),
        check_exact=True,
    )
    assert_frame_equal(
        base_regime.filter(pl.col("date") <= last_known).select("date", "vol_pct", "regime"),
        future_regime.filter(pl.col("date") <= last_known).select(
            "date", "vol_pct", "regime"
        ),
        check_exact=True,
    )
    # Strictly future bars cannot move a weight dated at or before the boundary.
    assert_frame_equal(
        base_weights.filter(pl.col("date") <= last_known),
        future_weights.filter(pl.col("date") <= last_known),
        check_exact=True,
    )


def test_overnight_and_intraday_vol_use_different_return_definitions() -> None:
    cfg = load_config()
    n_days = 90
    start = date(2020, 1, 1)
    gaps = [0.01 if index % 2 == 0 else -0.01 for index in range(n_days)]
    intraday = [0.001 if index % 2 == 0 else -0.001 for index in range(n_days)]

    opens: list[float] = []
    closes: list[float] = []
    previous_close = 100.0
    for gap, move in zip(gaps, intraday):
        open_price = previous_close * float(np.exp(gap))
        close_price = open_price * float(np.exp(move))
        opens.append(open_price)
        closes.append(close_price)
        previous_close = close_price

    frame = pl.DataFrame(
        {
            "date": pl.Series(
                "date", [start + timedelta(days=i) for i in range(n_days)], dtype=pl.Date
            ),
            "open_a": opens,
            "close_a": closes,
        }
    )
    vols = frame.select(
        overnight_vol(pl.col("open_a"), pl.col("close_a"), cfg.estimators).alias(
            "overnight"
        ),
        intraday_vol(pl.col("open_a"), pl.col("close_a"), cfg.estimators).alias(
            "intraday"
        ),
    )
    overnight = float(vols["overnight"][-1])
    intraday_value = float(vols["intraday"][-1])
    assert overnight > 0.0
    assert intraday_value > 0.0
    assert 8.0 < overnight / intraday_value < 12.0


def test_short_history_regime_is_unknown_not_a_number() -> None:
    cfg = load_config()
    frame = pl.DataFrame(
        {
            "date": pl.Series(
                "date", [date(2020, 1, 1) + timedelta(days=i) for i in range(10)],
                dtype=pl.Date,
            ),
            "vol_a": [0.1 + 0.01 * i for i in range(10)],
        }
    )
    labeled = label_regimes(frame, cfg.regimes, "vol_a")
    assert labeled["vol_pct"].null_count() == labeled.height
    assert set(labeled["regime"].to_list()) == {cfg.regimes.unknown_label}


def test_rolling_vol_pins_sample_ddof_one_and_annualization() -> None:
    """``ddof=1`` is a documented invariant, so it must be observable."""
    cfg = load_config()
    params = replace(cfg.estimators, rolling_windows=(5,), rolling_min_samples=5)
    prices = [100.0, 101.0, 99.5, 100.4, 98.9, 99.7, 100.2]
    frame = pl.DataFrame(
        {
            "date": pl.Series(
                "date",
                [date(2021, 1, 4) + timedelta(days=i) for i in range(len(prices))],
                dtype=pl.Date,
            ),
            "close_a": prices,
        }
    )
    got = float(
        frame.select(
            rolling_vol(
                price_returns(pl.col("close_a"), params), 5, params
            ).alias("vol")
        )["vol"][-1]
    )
    returns = (
        frame.select(price_returns(pl.col("close_a"), params).alias("r"))["r"]
        .drop_nulls()
        .to_list()
    )
    scale = math.sqrt(params.annualization)
    assert got == pytest.approx(statistics.stdev(returns[-5:]) * scale, rel=1e-12)
    # The population convention differs by sqrt(n / (n - 1)); the pin is real.
    population = statistics.pstdev(returns[-5:]) * scale
    assert not math.isclose(got, population, rel_tol=1e-6)
