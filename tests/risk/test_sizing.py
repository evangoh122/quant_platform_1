"""Worked example, hedge/spread math, floors, gross cap and input rejection."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from risk.config import load_config
from risk.sizing import METHODS, hedge_ratio, size, spread_variance, spread_volatility


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


def test_vol_target_gross_cap_holds_when_signal_cap_exceeds_one() -> None:
    """The cap must bind on the alpha-scaled book, not on the bare scale."""
    params = replace(
        load_config().sizing,
        method="vol_target",
        signal_cap=2.0,
        target_vol=0.90,
        max_gross=2.0,
    )
    weights = size(_signal(2.0), _estimate(0.25, 0.40, 0.8), params)
    gross = abs(float(weights["w_a"][0])) + abs(float(weights["w_b"][0]))
    # Unnormalised this book is gross 4.0 (2 x the limit).
    assert gross <= params.max_gross + 1e-9
    assert gross == pytest.approx(params.max_gross, rel=1e-12)


@pytest.mark.parametrize("signal_cap", [0.5, 1.0, 2.0, 5.0])
@pytest.mark.parametrize("signal", [-5.0, -2.0, -0.5, 0.5, 2.0, 5.0])
def test_vol_target_gross_never_exceeds_max_gross(
    signal_cap: float, signal: float
) -> None:
    params = replace(
        load_config().sizing,
        method="vol_target",
        signal_cap=signal_cap,
        target_vol=0.90,
        max_gross=2.0,
    )
    weights = size(_signal(signal), _estimate(0.25, 0.40, 0.8), params)
    for column in ("w_a", "w_b"):
        assert math.isfinite(float(weights[column][0]))
    gross = abs(float(weights["w_a"][0])) + abs(float(weights["w_b"][0]))
    assert gross <= params.max_gross + 1e-9


def test_vol_target_keeps_sub_unit_alpha_proportional_to_the_signal() -> None:
    """Normalising by max(1, |alpha|) must not rescale ordinary alpha books."""
    params = replace(
        load_config().sizing,
        method="vol_target",
        signal_cap=1.0,
        target_vol=0.90,
        max_gross=2.0,
    )
    unit = size(_signal(1.0), _estimate(0.25, 0.40, 0.8), params)
    half = size(_signal(0.5), _estimate(0.25, 0.40, 0.8), params)
    assert float(half["w_a"][0]) == pytest.approx(
        0.5 * float(unit["w_a"][0]), rel=1e-12
    )
    assert float(half["w_b"][0]) == pytest.approx(
        0.5 * float(unit["w_b"][0]), rel=1e-12
    )


def _assert_zero_weights(
    vol_a: float | None,
    vol_b: float | None,
    corr: float | None,
    method: str,
) -> None:
    weights = size(
        _signal(1.0),
        _estimate(vol_a, vol_b, corr),
        replace(load_config().sizing, method=method),
    )
    assert weights.height == 1
    assert float(weights["w_a"][0]) == 0.0
    assert float(weights["w_b"][0]) == 0.0


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize(
    "corr",
    [float("inf"), float("-inf"), float("nan"), None],
    ids=["inf", "-inf", "nan", "none"],
)
def test_non_finite_or_missing_corr_zeroes_every_sizer(
    method: str, corr: float | None
) -> None:
    _assert_zero_weights(0.20, 0.20, corr, method)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize(
    "vol_a,vol_b",
    [
        (None, 0.20),
        (0.20, None),
        (None, None),
        (float("inf"), 0.20),
        (0.20, float("nan")),
    ],
    ids=["null_a", "null_b", "null_both", "inf_a", "nan_b"],
)
def test_missing_or_non_finite_vol_zeroes_every_sizer(
    method: str, vol_a: float | None, vol_b: float | None
) -> None:
    _assert_zero_weights(vol_a, vol_b, 0.5, method)


@pytest.mark.parametrize("method", METHODS)
def test_all_none_estimates_zero_every_sizer(method: str) -> None:
    _assert_zero_weights(None, None, None, method)


def test_config_rejects_non_positive_or_non_finite_signal_cap(tmp_path) -> None:
    source = Path(__file__).resolve().parents[2] / "risk" / "config.yaml"
    text = source.read_text(encoding="utf-8")
    assert "signal_cap: 1.0" in text
    for index, bad in enumerate(("0.0", "-1.0", ".inf", ".nan")):
        candidate = tmp_path / f"config_bad_{index}.yaml"
        candidate.write_text(
            text.replace("signal_cap: 1.0", f"signal_cap: {bad}"),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            load_config(candidate)

    good = tmp_path / "config_good.yaml"
    good.write_text(
        text.replace("signal_cap: 1.0", "signal_cap: 2.5"), encoding="utf-8"
    )
    assert load_config(good).sizing.signal_cap == pytest.approx(2.5)


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
