"""The comparison harness must make vol targeting measurable, not decorative."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from risk.compare import build_signal, compare_sizers, signal_varies_in_magnitude
from risk.config import load_config
from risk.run_compare import render_markdown
from risk.sizing import METHODS
from risk.synthetic import synthetic_pair_panel

REPO_ROOT = Path(__file__).resolve().parents[2]


def _constant_signal(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(
        pl.col("date"),
        pl.lit(1.0, dtype=pl.Float64).alias("signal"),
    )


def _sample_table() -> pl.DataFrame:
    """One minimal row with every column ``render_markdown`` selects."""
    return pl.DataFrame(
        [
            {
                "variant": "equal_dollar",
                "cost_bps": 5.0,
                "oos_sharpe": 0.0,
                "ann_return": 0.0,
                "realized_vol_gross": 0.0,
                "target_vol": 0.0,
                "vol_gap": 0.0,
                "max_drawdown": 0.0,
                "gross_exposure_avg": 0.0,
                "net_exposure_avg": 0.0,
                "turnover_avg": 0.0,
                "borrow_cost_total": 0.0,
                "net_pnl_total": 0.0,
            }
        ]
    )


def test_synthetic_panel_is_seeded_and_reproducible() -> None:
    cfg = load_config()
    first = synthetic_pair_panel(replace(cfg.experiment, n_days=200), 252)
    second = synthetic_pair_panel(replace(cfg.experiment, n_days=200), 252)
    assert first.equals(second)
    assert first.height == 200
    assert first["open_a"].min() > 0.0
    assert first["close_b"].min() > 0.0


def test_vol_target_tracks_target_better_than_equal_dollar() -> None:
    cfg = load_config()
    target = 0.05
    config = replace(cfg, sizing=replace(cfg.sizing, target_vol=target))
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=900, seed=7), 252)

    table = compare_sizers(
        panel,
        config,
        signals=_constant_signal(panel),
        methods=("equal_dollar", "vol_target"),
        cost_levels=(cfg.costs.baseline_bps,),
    )
    gaps = {
        row["variant"]: float(row["vol_gap"])
        for row in table.select("variant", "vol_gap").iter_rows(named=True)
    }
    assert set(gaps) == {"equal_dollar", "vol_target"}
    assert gaps["vol_target"] < gaps["equal_dollar"]


def test_committed_report_has_no_blank_line_at_eof() -> None:
    """`git diff --check` rejects a blank line at EOF; the committed report is clean."""
    report = Path(__file__).resolve().parents[2] / "risk" / "results" / "p1_compare.md"
    text = report.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_render_markdown_leaves_the_trailing_newline_to_the_writer() -> None:
    cfg = load_config()
    row = {
        "variant": "equal_dollar",
        "cost_bps": 5.0,
        "oos_sharpe": 0.0,
        "ann_return": 0.0,
        "realized_vol_gross": 0.0,
        "target_vol": 0.0,
        "vol_gap": 0.0,
        "max_drawdown": 0.0,
        "gross_exposure_avg": 0.0,
        "net_exposure_avg": 0.0,
        "turnover_avg": 0.0,
        "borrow_cost_total": 0.0,
        "net_pnl_total": 0.0,
    }
    markdown = render_markdown(pl.DataFrame([row]), cfg)
    assert not markdown.endswith("\n")
    assert (markdown + "\n").endswith(".\n")
    assert not (markdown + "\n").endswith("\n\n")


def test_comparison_covers_every_sizer_with_finite_metrics() -> None:
    cfg = load_config()
    panel = synthetic_pair_panel(replace(cfg.experiment, n_days=400, seed=3), 252)
    table = compare_sizers(
        panel,
        cfg,
        signals=_constant_signal(panel),
        cost_levels=(5.0, 10.0, 15.0),
    )
    assert table.height == len(METHODS) * 3
    assert set(table["variant"].to_list()) == set(METHODS)
    for column in (
        "oos_sharpe",
        "realized_vol_gross",
        "realized_vol_net",
        "max_drawdown",
        "gross_exposure_avg",
        "net_exposure_avg",
        "turnover_avg",
        "borrow_cost_total",
    ):
        assert table[column].null_count() == 0
        assert all(math.isfinite(value) for value in table[column].to_list())


@pytest.mark.parametrize("cost_levels", [None, (2.5, 7.5, 12.0)])
def test_compare_sizers_forces_flat_cost_mode(cost_levels) -> None:
    """CR-2: the comparison varies flat bps only, so ``adv`` changes nothing."""
    cfg = load_config()
    panel = synthetic_pair_panel(
        replace(cfg.experiment, n_days=260, seed=5), 252
    )
    flat = replace(cfg, backtest=replace(cfg.backtest, cost_mode="flat"))
    adv = replace(cfg, backtest=replace(cfg.backtest, cost_mode="adv"))
    kwargs = {} if cost_levels is None else {"cost_levels": cost_levels}

    flat_table = compare_sizers(panel, flat, **kwargs)
    adv_table = compare_sizers(panel, adv, **kwargs)
    assert_frame_equal(adv_table, flat_table, check_exact=True)

    expected = tuple(cfg.costs.bps_per_side) if cost_levels is None else cost_levels
    assert tuple(flat_table["cost_bps"].to_list()) == expected * len(cfg.compare.methods)


MAGNITUDE_SENTENCE = "signal varies in magnitude, so the two variants differ."
SIGN_ONLY_SENTENCE = "property of the signal"


@pytest.mark.parametrize(
    "mode, expected, forbidden",
    [
        ("momentum_z", MAGNITUDE_SENTENCE, SIGN_ONLY_SENTENCE),
        ("momentum", SIGN_ONLY_SENTENCE, MAGNITUDE_SENTENCE),
        ("reversal", SIGN_ONLY_SENTENCE, MAGNITUDE_SENTENCE),
        ("constant", SIGN_ONLY_SENTENCE, MAGNITUDE_SENTENCE),
    ],
)
def test_render_markdown_signal_sentence_follows_the_configured_mode(
    mode: str, expected: str, forbidden: str
) -> None:
    """CR-4: only a magnitude-bearing mode may claim the variants differ."""
    cfg = load_config()
    variant = replace(cfg, signals=replace(cfg.signals, mode=mode))
    markdown = render_markdown(_sample_table(), variant)
    assert f"- signal: `{mode}`" in markdown
    assert expected in markdown
    assert forbidden not in markdown


@pytest.mark.parametrize("mode", ["momentum", "reversal", "momentum_z", "constant"])
def test_magnitude_flag_matches_the_signal_the_code_builds(mode: str) -> None:
    """The report flag and ``build_signal`` share one registry; pin them together."""
    cfg = load_config()
    variant = replace(cfg, signals=replace(cfg.signals, mode=mode))
    panel = synthetic_pair_panel(
        replace(cfg.experiment, n_days=300, seed=2), 252
    )
    signal = build_signal(panel, variant.signals, variant.columns)
    non_zero = signal.filter(pl.col("signal") != 0.0)["signal"].abs()
    assert non_zero.len() > 0
    sign_only = bool((non_zero == 1.0).all())
    assert signal_varies_in_magnitude(mode) is not sign_only


def test_default_report_regenerates_byte_identically() -> None:
    """Regenerate the committed default-config report from production code."""
    cfg = load_config()
    panel = synthetic_pair_panel(cfg.experiment, cfg.estimators.annualization)
    markdown = render_markdown(compare_sizers(panel, cfg), cfg) + "\n"
    committed = (
        REPO_ROOT / "risk" / "results" / "p1_compare.md"
    ).read_text(encoding="utf-8")
    assert markdown == committed
