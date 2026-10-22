"""Phase-1 synthetic experiment: compare sizers at 5/10/15 bps per side.

Run from the repository root::

    python -m risk.run_compare

The panel is seeded and synthetic.  The output proves the plumbing (estimators,
sizing, lag, costs, reporting) and says nothing about real MAGS/SOXX or any
other instrument's performance.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from risk.compare import compare_sizers
from risk.config import RiskConfig, load_config
from risk.synthetic import synthetic_pair_panel

_COLUMNS = (
    "variant",
    "cost_bps",
    "oos_sharpe",
    "ann_return",
    "realized_vol_gross",
    "target_vol",
    "vol_gap",
    "max_drawdown",
    "gross_exposure_avg",
    "net_exposure_avg",
    "turnover_avg",
    "borrow_cost_total",
    "net_pnl_total",
)


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(table: pl.DataFrame, config: RiskConfig) -> str:
    lines = [
        "# Phase 1 — volatility-aware sizing vs fixed sizing (synthetic)",
        "",
        "**This is a seeded synthetic experiment. It proves the plumbing, not alpha.**",
        "No claim is made about real MAGS/SOXX or any live instrument.",
        "",
        f"- seed: `{config.experiment.seed}`",
        f"- days: `{config.experiment.n_days}`",
        f"- pair correlation of shocks: `{config.experiment.rho}`",
        f"- target vol: `{config.sizing.target_vol}`",
        f"- max gross: `{config.sizing.max_gross}`",
        f"- OOS fraction: `{config.compare.oos_fraction}`",
        f"- signal: `{config.signals.mode}` (lookback `{config.signals.lookback}`)",
        "",
        "Execution is identical across variants: signal at close t, fill at open",
        "t+1, open-to-open P&L, flat per-side cost plus borrow on short notional.",
        "",
        "`vol_target` multiplies the covariance-aware book by the alpha",
        "magnitude; `covariance_aware` uses its sign. The `momentum_z` reference",
        "signal varies in magnitude, so the two variants differ.",
        "",
        "| " + " | ".join(_COLUMNS) + " |",
        "|" + "|".join(["---"] * len(_COLUMNS)) + "|",
    ]
    for row in table.select(_COLUMNS).iter_rows(named=True):
        lines.append(
            "| " + " | ".join(_fmt(row[column]) for column in _COLUMNS) + " |"
        )
    lines.extend(
        [
            "",
            "`realized_vol_gross` is the annualized volatility of the OOS gross",
            "return path; `vol_gap` is its absolute distance from the configured",
            "target. `turnover_avg` is the mean daily `sum |delta w|` (two-way",
            "traded notional) and ignores intraday weight drift.",
        ]
    )
    # No trailing blank line: the writer appends exactly one newline, and
    # `git diff --check` rejects a blank line at EOF.
    return "\n".join(lines).rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=None,
        help="path to risk/config.yaml (default: package config)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="override the markdown output path from the config",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    panel = synthetic_pair_panel(config.experiment, config.estimators.annualization)
    table = compare_sizers(panel, config)
    markdown = render_markdown(table, config)

    if args.out is not None:
        output = Path(args.out)
    else:
        output = Path(__file__).resolve().parents[1] / config.experiment.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown + "\n", encoding="utf-8")
    print(markdown)
    print(f"\nwritten: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
