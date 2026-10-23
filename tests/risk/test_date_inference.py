"""The inferring entry points resolve a frame's date column deterministically.

MiMo r6 finding F1: ``label_regimes`` (and ``performance_metrics``, the other
entry point that infers the name) rejected a legitimate estimates frame that
kept ``date`` and carried a second ``pl.Date`` column from a join (say
``listing_date``).  ``risk.frames.date_column`` resolves the name in this
order: (1) a column literally named ``date`` when it is ``pl.Date``; (2)
otherwise the frame's single ``pl.Date`` column; (3) otherwise ``TypeError``
listing the candidates.  Every frame accepted before keeps the same column
choice; only that rejection was loosened.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from risk.compare import build_signal
from risk.config import load_config
from risk.estimators import estimate_pair
from risk.frames import date_column
from risk.pair_backtest import backtest_vol_pair, performance_metrics
from risk.regimes import label_regimes
from risk.sizing import size
from risk.synthetic import synthetic_pair_panel

SEEDS = (0, 7)


def _estimates(n_days: int = 340) -> pl.DataFrame:
    cfg = load_config()
    panel = synthetic_pair_panel(
        replace(cfg.experiment, n_days=n_days, seed=21),
        cfg.estimators.annualization,
    )
    return estimate_pair(panel, cfg.estimators, cfg.columns)


def _daily() -> pl.DataFrame:
    cfg = load_config()
    panel = synthetic_pair_panel(
        replace(cfg.experiment, n_days=320, seed=23),
        cfg.estimators.annualization,
    )
    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signal = build_signal(panel, cfg.signals, cfg.columns)
    weights = size(signal, estimates, cfg.sizing)
    return backtest_vol_pair(panel, weights, cfg.backtest, columns=cfg.columns).daily


def _with_second_date(
    frame: pl.DataFrame, name: str = "listing_date", source: str = "date"
) -> pl.DataFrame:
    """Add a second ``pl.Date`` column stored in reverse date order.

    Reversing the values matters: if the resolver picked the wrong column the
    output order (and every trailing-window value) would differ, so the
    equality assertions below are not vacuous.
    """
    reversed_dates = list(reversed(frame[source].to_list()))
    return frame.with_columns(pl.Series(name, reversed_dates, dtype=pl.Date))


def _shuffled(frame: pl.DataFrame, seed: int) -> pl.DataFrame:
    return frame.sample(n=frame.height, shuffle=True, seed=seed)


def test_date_column_resolution_order() -> None:
    """Pin all three rules of ``date_column`` directly."""
    days = [date(2026, 1, 1), date(2026, 1, 2)]

    assert (
        date_column(
            pl.DataFrame(
                {
                    "listing_date": pl.Series(days, dtype=pl.Date),
                    "date": pl.Series(days, dtype=pl.Date),
                }
            )
        )
        == "date"
    )
    assert (
        date_column(
            pl.DataFrame({"session": pl.Series(days, dtype=pl.Date)})
        )
        == "session"
    )
    # A ``date`` column that is not pl.Date must not win: fall through.
    assert (
        date_column(
            pl.DataFrame(
                {
                    "date": pl.Series(days, dtype=pl.Date).cast(pl.String),
                    "session": pl.Series(days, dtype=pl.Date),
                }
            )
        )
        == "session"
    )
    with pytest.raises(TypeError, match="session.*asof"):
        date_column(
            pl.DataFrame(
                {
                    "session": pl.Series(days, dtype=pl.Date),
                    "asof": pl.Series(days, dtype=pl.Date),
                }
            )
        )
    with pytest.raises(TypeError, match=r"found \[\]"):
        date_column(pl.DataFrame({"date": pl.Series([1.0])}))


@pytest.mark.parametrize("seed", (None, *SEEDS))
def test_label_regimes_accepts_a_second_date_column(seed: int | None) -> None:
    cfg = load_config()
    estimates = _estimates()
    baseline = label_regimes(estimates, cfg.regimes)
    extended = _with_second_date(estimates)
    source = extended if seed is None else _shuffled(extended, seed)

    out = label_regimes(source, cfg.regimes)

    # Non-vacuous: real percentiles, ordered by ``date`` (ascending) rather
    # than by ``listing_date`` (which is stored in reverse).
    assert baseline["vol_pct"].null_count() < baseline.height
    assert out["date"].to_list() == sorted(out["date"].to_list())
    listing = out["listing_date"].to_list()
    assert listing == sorted(listing, reverse=True)
    assert_frame_equal(out.drop("listing_date"), baseline, check_exact=True)


@pytest.mark.parametrize("seed", (None, *SEEDS))
def test_performance_metrics_accepts_a_second_date_column(seed: int | None) -> None:
    cfg = load_config()
    daily = _daily()
    baseline = performance_metrics(daily, cfg.backtest)
    extended = _with_second_date(daily)
    source = extended if seed is None else _shuffled(extended, seed)

    # Path-dependent, so sorting by the reversed column would change it.
    assert baseline["max_drawdown"] < 0.0
    assert performance_metrics(source, cfg.backtest) == baseline


def test_a_single_other_date_column_is_still_inferred() -> None:
    cfg = load_config()
    estimates = _estimates()
    baseline = label_regimes(estimates, cfg.regimes)

    renamed = estimates.rename({"date": "session"})
    out = label_regimes(renamed, cfg.regimes)

    assert out.columns[0] == "session"
    assert_frame_equal(out.rename({"session": "date"}), baseline, check_exact=True)


def test_two_date_columns_without_a_date_name_raise_listing_both() -> None:
    cfg = load_config()
    estimates = _estimates().rename({"date": "session"})

    with pytest.raises(TypeError) as error:
        label_regimes(
            _with_second_date(estimates, "asof", source="session"), cfg.regimes
        )

    message = str(error.value)
    assert "pl.Date" in message
    assert "'session'" in message
    assert "'asof'" in message


def test_no_date_column_raises() -> None:
    cfg = load_config()
    without_dates = _estimates().with_columns(pl.col("date").cast(pl.String))

    with pytest.raises(TypeError) as error:
        label_regimes(without_dates, cfg.regimes)

    assert "found []" in str(error.value)


@pytest.mark.parametrize("dtype", [pl.Datetime, pl.String])
def test_a_non_date_column_named_date_falls_through_to_inference(
    dtype: pl.DataType,
) -> None:
    cfg = load_config()
    estimates = _estimates()
    baseline = label_regimes(estimates, cfg.regimes)

    frame = estimates.rename({"date": "session"}).with_columns(
        pl.col("session").cast(dtype).alias("date")
    )
    assert frame.schema["date"] == dtype
    assert frame.schema["session"] == pl.Date

    out = label_regimes(frame, cfg.regimes)

    assert out["session"].to_list() == sorted(out["session"].to_list())
    assert_frame_equal(
        out.drop("date").rename({"session": "date"}),
        baseline,
        check_exact=True,
    )
