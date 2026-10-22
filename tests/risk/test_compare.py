"""The comparison harness must make vol targeting measurable, not decorative."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import polars as pl

from risk.compare import compare_sizers
from risk.config import load_config
from risk.run_compare import render_markdown
from risk.sizing import METHODS
from risk.synthetic import synthetic_pair_panel


def _constant_signal(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(
        pl.col("date"),
        pl.lit(1.0, dtype=pl.Float64).alias("signal"),
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
