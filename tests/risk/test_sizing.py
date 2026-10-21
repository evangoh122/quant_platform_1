"""Worked example, hedge/spread math, floors and the gross cap."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import polars as pl
import pytest

from risk.config import load_config
from risk.sizing import hedge_ratio, size, spread_variance, spread_volatility


def _estimate(
    vol_a: float | None, vol_b: float | None, corr: float | None
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": pl.Series("date", [date(2024, 1, 2)], dtype=pl.Date),
            "vol_a": [vol_a],
            "vol_b": [vol_b],
            "corr": [corr],
        }
    )


def _signal(value: float = 1.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": pl.Series("date", [date(2024, 1, 2)], dtype=pl.Date),
            "signal": [value],
        }
    )


def test_worked_example_hedge_ratio_and_spread_vol() -> None:
    params = load_config().sizing
    assert hedge_ratio(0.25, 0.40, params) == pytest.approx(0.625, abs=1e-12)
    assert spread_volatility(0.25, 0.40, 0.8, params) == pytest.approx(0.158, abs=1e-3)

    weights = size(
        _signal(1.0),
        _estimate(0.25, 0.40, 0.8),
        replace(params, method="covariance_aware"),
    )
    # scale = min(0.10 / 0.1581139, 2.0 / (1 + 0.625)) = 0.6324555
    assert float(weights["w_a"][0]) == pytest.approx(0.632455532, abs=1e-6)
    assert float(weights["w_b"][0]) == pytest.approx(-0.395284708, abs=1e-6)


def test_floors_and_non_finite_inputs_keep_weights_finite() -> None:
    params = load_config().sizing
    cases = [
        (0.0, 0.0, 0.0),
        (0.20, 0.20, 1.0),
        (0.20, 0.20, 1.5),
        (None, 0.20, 0.5),
        (0.20, None, 0.5),
        (0.20, 0.20, None),
        (float("nan"), 0.20, 0.5),
        (0.20, float("inf"), 0.5),
        (0.20, 0.20, float("nan")),
    ]
    for vol_a, vol_b, corr in cases:
        weights = size(
            _signal(1.0),
            _estimate(vol_a, vol_b, corr),
            replace(params, method="covariance_aware"),
        )
        assert weights.height == 1
        for column in ("w_a", "w_b"):
            value = float(weights[column][0])
            assert math.isfinite(value)
        gross = abs(float(weights["w_a"][0])) + abs(float(weights["w_b"][0]))
        assert gross <= params.max_gross + 1e-9

    # The variance floor is a production invariant, including numerical noise
    # that makes the raw spread variance negative.
    assert spread_variance(0.20, 0.20, 1.0, params) >= params.spread_var_floor
    assert spread_variance(0.20, 0.20, 1.5, params) >= params.spread_var_floor
    assert spread_variance(0.20, 0.20, 1.5, params) == pytest.approx(
        params.spread_var_floor
    )


def test_gross_never_exceeds_max_gross_when_scale_wants_more() -> None:
    params = replace(load_config().sizing, target_vol=0.90, max_gross=2.0)
    weights = size(
        _signal(1.0),
        _estimate(0.25, 0.40, 0.8),
        replace(params, method="covariance_aware"),
    )
    gross = abs(float(weights["w_a"][0])) + abs(float(weights["w_b"][0]))
    assert gross <= params.max_gross + 1e-9
    # The cap binds: without it the target-vol scale would be far above 2.
    assert gross == pytest.approx(params.max_gross, rel=1e-9)


def test_vol_target_clips_alpha_and_respects_gross_cap() -> None:
    params = replace(load_config().sizing, target_vol=0.90, max_gross=2.0)
    weights = size(
        _signal(50.0),
        _estimate(0.25, 0.40, 0.8),
        replace(params, method="vol_target"),
    )
    gross = abs(float(weights["w_a"][0])) + abs(float(weights["w_b"][0]))
    assert gross <= params.max_gross + 1e-9


def test_equal_dollar_and_inverse_vol_are_finite_and_hedged() -> None:
    params = load_config().sizing
    for method in ("equal_dollar", "inverse_vol"):
        weights = size(
            _signal(-1.0),
            _estimate(0.25, 0.40, 0.8),
            replace(params, method=method),
        )
        assert float(weights["w_a"][0]) < 0.0
        assert float(weights["w_b"][0]) > 0.0
        gross = abs(float(weights["w_a"][0])) + abs(float(weights["w_b"][0]))
        assert gross <= params.max_gross + 1e-9
