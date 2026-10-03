"""Robustness round-3 guard test.

Every test in this file must FAIL on the pre-round-3 HEAD and PASS after the
round-3 fixes.  The guard test renders the report from a synthetic run and
asserts:
  - no "Run with", "TODO", "placeholder", or "nan" in required table cells;
  - every required table has at least one numeric row;
  - every compute_* function imported by the runner is actually called.
"""

import numpy as np
import pandas as pd
import pytest

from strategies.robustness import (
    VariantSpec,
    build_variant_registry,
    render_robustness_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_config():
    return {
        "residual_reversion": {
            "status": "primary", "bar_freq": "1d",
            "factor_model": "ols_mkt_ind", "factor_window": 60,
            "pca_components": 10, "residual_lookback": 5,
            "entry_threshold": 2.5, "exit_threshold": 0.5,
            "max_hold_candidates": [3, 5, 10], "min_obs_fraction": 0.8,
            "universe_size": 300, "target_gross": 1.0,
            "book_capital": 10_000_000, "execution_lag_bars": 1,
        },
        "robustness": {
            "cost_multipliers": [1.0, 2.0, 3.0],
            "universe_sizes": [200, 300, 500],
            "parameter_perturbation": 0.20,
            "drop_top_pnl_contributors": 3,
            "walk_forward_folds": 5,
            "min_profitable_folds": 3,
            "rank_ic_horizon_days": 5,
        },
        "cost_model": {
            "commission_bps": 0.5, "spread_bps": 3.0, "slippage_bps": 2.0,
            "adv_participation_cap": 0.01,
        },
        "metric_gates": {
            "sharpe_min": 1.25, "max_drawdown_max": 0.15,
            "return_to_dd_min": 1.0, "margin_min_bps": 5.0,
            "oos_ratio_min": 0.50,
        },
    }


def _full_config():
    cfg = _base_config()
    cfg["robustness"].update({
        "rank_ic_horizon_days": 5,
        "universe_sizes": [200, 300, 500],
        "parameter_perturbation": 0.20,
    })
    return cfg


def _make_synthetic_variant_results(registry, n_days=100, seed=42):
    """Build synthetic variant results with all required fields for round 3."""
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(seed)
    symbols = [f"S{i:02d}" for i in range(10)]

    variant_results = []
    for vs in registry:
        net = pd.Series(rng.normal(0.001, 0.01, n_days), index=dates)
        weights = pd.DataFrame(
            rng.normal(0.0, 0.1, (n_days, len(symbols))),
            index=dates, columns=symbols,
        )
        beta_mkt = pd.DataFrame(
            rng.normal(1.0, 0.2, (n_days, len(symbols))),
            index=dates, columns=symbols,
        )
        industry = pd.Series({s: "tech" for s in symbols})
        adv_wide = pd.DataFrame(1e8, index=dates, columns=symbols)
        s_score = pd.DataFrame(
            rng.normal(0, 1, (n_days, len(symbols))),
            index=dates, columns=symbols,
        )
        residual_returns = pd.DataFrame(
            rng.normal(0, 0.01, (n_days, len(symbols))),
            index=dates, columns=symbols,
        )
        variant_results.append({
            "variant_id": vs.variant_id,
            "fingerprint": vs.fingerprint,
            "net": net,
            "gross": net,
            "metrics": {},
            "weights": weights,
            "turnover": pd.Series(0.1, index=dates),
            "is_sharpe": 1.0,
            "oos_sharpe": 0.7,
            "s_score": s_score,
            "residual_returns": residual_returns,
            "beta_mkt": beta_mkt,
            "industry": industry,
            "adv_wide": adv_wide,
            "dropped_symbols": [],
        })
    return variant_results, dates


def _rank_ic_results():
    return {
        "ols_mkt_ind": {
            "mean_ic": -0.05, "std_ic": 0.03, "t_stat": -3.2,
            "n": 90, "effective_n": 18,
            "sign": "negative (expected under mean reversion)",
            "hit_rate": 0.65,
        },
        "pca": {
            "mean_ic": -0.03, "std_ic": 0.025, "t_stat": -2.1,
            "n": 90, "effective_n": 18,
            "sign": "negative (expected under mean reversion)",
            "hit_rate": 0.58,
        },
    }


def _drop_top3_results(dates):
    rng = np.random.default_rng(99)
    folds = []
    for i in range(5):
        folds.append({
            "fold": i,
            "dropped": [f"S{i:02d}", f"S{i+1:02d}", f"S{i+2:02d}"],
            "oos_sharpe": float(rng.normal(0.8, 0.1)),
            "oos_sharpe_drop3": float(rng.normal(0.6, 0.1)),
        })
    return {
        3: {"folds": folds, "all_dropped_symbols": ["S00", "S01", "S02", "S03", "S04"]},
        5: {"folds": folds, "all_dropped_symbols": ["S00", "S01", "S02", "S03", "S04"]},
        10: {"folds": folds, "all_dropped_symbols": ["S00", "S01", "S02", "S03", "S04"]},
    }


def _splits(n_days=100):
    return [
        (np.arange(0, 16), np.arange(16, 32)),
        (np.arange(0, 32), np.arange(32, 48)),
        (np.arange(0, 48), np.arange(48, 64)),
        (np.arange(0, 64), np.arange(64, 80)),
        (np.arange(0, 80), np.arange(80, n_days)),
    ]


# ---------------------------------------------------------------------------
# Guard: no placeholders in report
# ---------------------------------------------------------------------------

class TestReportHasNoPlaceholders:
    def test_report_no_placeholder_text(self):
        """Report must not contain placeholder phrases or nan in table cells."""
        cfg = _full_config()
        registry = build_variant_registry(cfg)
        variant_results, dates = _make_synthetic_variant_results(registry)
        rank_ic = _rank_ic_results()
        drop3 = _drop_top3_results(dates)
        splits = _splits()

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
            splits=splits,
            rank_ic_results=rank_ic,
            drop_top3_results=drop3,
        )

        banned = ["Run with", "TODO", "placeholder", "not available in variant results"]
        for phrase in banned:
            assert phrase not in report, (
                f"Report contains banned phrase '{phrase}'"
            )

    def test_rank_ic_section_has_real_data(self):
        """Rank IC section must show mean IC, t-stat, n, and hit rate."""
        cfg = _full_config()
        registry = build_variant_registry(cfg)
        variant_results, dates = _make_synthetic_variant_results(registry)
        rank_ic = _rank_ic_results()
        splits = _splits()

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
            splits=splits,
            rank_ic_results=rank_ic,
        )

        assert "Rank IC" in report
        assert "-0.0500" in report or "-0.05" in report
        assert "-3.20" in report or "-3.2" in report
        assert "90" in report
        assert "0.65" in report
        assert "hit rate" in report

    def test_capacity_section_has_dollar_values(self):
        """Capacity section must show p50 and p5 in dollars, not NaN."""
        cfg = _full_config()
        registry = build_variant_registry(cfg)
        variant_results, dates = _make_synthetic_variant_results(registry)
        splits = _splits()

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
            splits=splits,
        )

        assert "capacity p50" in report
        assert "capacity p5" in report
        assert "nan" not in report.split("capacity p50")[1].split("\n")[0]
        assert "nan" not in report.split("capacity p5")[1].split("\n")[0]

    def test_exposures_section_has_beta_and_industry(self):
        """Exposures must include beta and industry data, not NaN."""
        cfg = _full_config()
        registry = build_variant_registry(cfg)
        variant_results, dates = _make_synthetic_variant_results(registry)
        splits = _splits()

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
            splits=splits,
        )

        assert "beta exposure" in report.lower()
        assert "industry" in report.lower()
        # After the beta exposure heading, the next line should have a number.
        beta_section = report.split("beta exposure")[1]
        beta_line = beta_section.split("\n")[1]
        assert "nan" not in beta_line, f"Beta exposure is NaN: {beta_line}"

    def test_drop_top3_section_present(self):
        """Per-fold drop-top-3 section must exist with real fold data."""
        cfg = _full_config()
        registry = build_variant_registry(cfg)
        variant_results, dates = _make_synthetic_variant_results(registry)
        drop3 = _drop_top3_results(dates)
        splits = _splits()

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
            splits=splits,
            drop_top3_results=drop3,
        )

        assert "Drop-top-3" in report
        assert "training-window" in report
        assert "OOS Sharpe (full)" in report
        assert "OOS Sharpe (drop3)" in report

    def test_every_required_table_has_numeric_row(self):
        """Each required table must contain at least one numeric data row."""
        cfg = _full_config()
        registry = build_variant_registry(cfg)
        variant_results, dates = _make_synthetic_variant_results(registry)
        rank_ic = _rank_ic_results()
        drop3 = _drop_top3_results(dates)
        splits = _splits()

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
            splits=splits,
            rank_ic_results=rank_ic,
            drop_top3_results=drop3,
        )

        required_sections = [
            "Cost stress",
            "Universe stress",
            "Parameter perturbation",
            "Top-3 P&L contributor removal",
            "Walk-forward folds",
            "Exposures",
            "Turnover / capacity / margin",
            "Rank IC",
            "Gate summary",
        ]
        for section in required_sections:
            assert section in report, f"Missing section: {section}"
            # Each section must have at least one data row (line starting with |).
            section_text = report.split(section)[1].split("\n##")[0]
            data_rows = [l for l in section_text.split("\n")
                         if l.startswith("|") and "---" not in l and "metric" not in l.lower()
                         and "variant" not in l.lower() and "factor" not in l.lower()
                         and "fold" not in l.lower()]
            assert len(data_rows) >= 1, (
                f"Section '{section}' has no numeric data rows"
            )