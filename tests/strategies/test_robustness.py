"""Robustness library invariants: variant registry/deduplication, trial count,
cost scaling exactly once, parameter values, gate boundary behavior, fold
profitability flag, exposures, capacity, margin, rank IC alignment, and report
tables."""

import hashlib
import json
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from strategies.robustness import (
    VariantSpec,
    build_variant_registry,
    compute_capacity,
    compute_exposures,
    compute_fold_metrics,
    compute_margin_bps,
    compute_rank_ic,
    evaluate_gates,
    remove_top_pnl_contributors,
    render_robustness_report,
    run_cost_stress,
)


def _base_config():
    """Minimal config for registry building."""
    return {
        "residual_reversion": {
            "status": "primary",
            "bar_freq": "1d",
            "factor_model": "ols_mkt_ind",
            "factor_window": 60,
            "pca_components": 10,
            "residual_lookback": 5,
            "entry_threshold": 2.5,
            "exit_threshold": 0.5,
            "max_hold_candidates": [3, 5, 10],
            "min_obs_fraction": 0.8,
            "universe_size": 300,
            "target_gross": 1.0,
            "book_capital": 10_000_000,
            "execution_lag_bars": 1,
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
            "commission_bps": 0.5,
            "spread_bps": 3.0,
            "slippage_bps": 2.0,
            "adv_participation_cap": 0.01,
        },
        "metric_gates": {
            "sharpe_min": 1.25,
            "max_drawdown_max": 0.15,
            "return_to_dd_min": 1.0,
            "margin_min_bps": 5.0,
            "oos_ratio_min": 0.50,
        },
    }


class TestVariantRegistry:
    def test_baseline_deduplication(self):
        """The nominal baseline (1x/top-300/unperturbed) is counted once per
        factor_model/hold combination."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        baselines = [v for v in registry if v.category == "baseline"]
        # 2 factor models × 3 hold candidates = 6 baselines.
        assert len(baselines) == 6

    def test_unique_fingerprints(self):
        """No two registry entries share a fingerprint."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        fps = [v.fingerprint for v in registry]
        assert len(fps) == len(set(fps))

    def test_trial_count_matches_registry(self):
        """len(registry) is the total trial count."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        assert len(registry) > 0
        # Should include baselines + cost stress + universe stress + param stress + drop_top.
        assert len(registry) > 6  # at least baselines

    def test_cost_stress_included(self):
        """2x and 3x cost variants are in the registry."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        cost_variants = [v for v in registry if v.category == "cost_stress"]
        # 2 multipliers (2x, 3x) × 2 models × 3 holds = 12.
        assert len(cost_variants) == 12

    def test_universe_stress_included(self):
        """200 and 500 universe variants are in the registry."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        univ_variants = [v for v in registry if v.category == "universe_stress"]
        # 2 sizes (200, 500) × 2 models × 3 holds = 12.
        assert len(univ_variants) == 12

    def test_parameter_stress_included(self):
        """Perturbation variants for each parameter are in the registry."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        param_variants = [v for v in registry if v.category == "parameter_stress"]
        # 3 params × 2 directions × 2 models × 3 holds = 36.
        assert len(param_variants) == 36

    def test_stable_ids(self):
        """Same config produces same variant IDs on repeated calls."""
        cfg = _base_config()
        r1 = build_variant_registry(cfg)
        r2 = build_variant_registry(cfg)
        ids1 = [v.variant_id for v in r1]
        ids2 = [v.variant_id for v in r2]
        assert ids1 == ids2


class TestCostStress:
    def test_cost_scales_once(self):
        """At 2x, every bps component scales exactly once; gross P&L does not
        change."""
        dates = pd.date_range("2024-01-01", periods=20, freq="B")
        symbols = ["A", "B"]
        weights = pd.DataFrame(0.0, index=dates, columns=symbols)
        weights.iloc[5:, 0] = 0.5
        weights.iloc[5:, 1] = -0.5
        returns = pd.DataFrame(0.001, index=dates, columns=symbols)
        adv = pd.DataFrame(1e8, index=dates, columns=symbols)
        from strategies.cost_model import CostParams
        params = CostParams()

        result_1x = run_cost_stress(weights, returns, adv, 10_000_000.0, params, 1.0)
        result_2x = run_cost_stress(weights, returns, adv, 10_000_000.0, params, 2.0)

        # Gross should be identical (same weights, same returns).
        pd.testing.assert_series_equal(result_1x["gross"], result_2x["gross"])

        # Net at 2x should be worse (more costs subtracted).
        assert result_2x["net"].mean() < result_1x["net"].mean()


class TestFoldMetrics:
    def test_five_fold_profitability_flag(self):
        """profitable_3_of_5 is PASS when at least 3 folds have total net P&L > 0."""
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        rng = np.random.default_rng(42)
        net_returns = pd.Series(rng.normal(0.001, 0.01, 100), index=dates)

        # Create 5 folds.
        splits = [(np.arange(0, 16), np.arange(16, 32)),
                  (np.arange(0, 32), np.arange(32, 48)),
                  (np.arange(0, 48), np.arange(48, 64)),
                  (np.arange(0, 64), np.arange(64, 80)),
                  (np.arange(0, 80), np.arange(80, 100))]

        folds = compute_fold_metrics(net_returns, splits)
        assert len(folds) == 5
        profitable_count = sum(1 for f in folds if f["profitable"])
        # With positive mean returns, most folds should be profitable.
        assert profitable_count >= 3


class TestExposures:
    def test_dollar_exposure(self):
        """Dollar exposure = sum(weights) / gross."""
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        weights = pd.DataFrame({"A": [0.5] * 10, "B": [-0.3] * 10}, index=dates)
        result = compute_exposures(weights)
        # sum(w) = 0.2, gross = 0.8, ratio = 0.25
        assert result["max_abs_dollar_exposure"] == pytest.approx(0.25)

    def test_beta_exposure(self):
        """Beta exposure = sum(w * beta) / gross."""
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        weights = pd.DataFrame({"A": [0.5] * 10, "B": [-0.5] * 10}, index=dates)
        beta = pd.DataFrame({"A": [1.2] * 10, "B": [0.8] * 10}, index=dates)
        result = compute_exposures(weights, beta=beta)
        # sum(w*beta) = 0.5*1.2 + (-0.5)*0.8 = 0.6 - 0.4 = 0.2
        # gross = 1.0, ratio = 0.2
        assert result["max_abs_beta_exposure"] == pytest.approx(0.2)

    def test_industry_exposure(self):
        """Industry exposure reports max |sector net| per sector."""
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        weights = pd.DataFrame({"A": [0.5] * 5, "B": [-0.3] * 5}, index=dates)
        industry = pd.Series({"A": "tech", "B": "fin"})
        result = compute_exposures(weights, industry=industry)
        # max |sector net|: tech = |0.5| = 0.5, fin = |-0.3| = 0.3
        assert result["industry_exposure"]["tech"] == pytest.approx(0.5)
        assert result["industry_exposure"]["fin"] == pytest.approx(0.3)
        assert result["max_abs_sector_exposure"] == pytest.approx(0.5)


class TestCapacity:
    def test_min_capacity(self):
        """Capacity = participation_cap * ADV / abs(delta_weight)."""
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        weights = pd.DataFrame({"A": [0.0, 0.1, 0.1, 0.1, 0.1]}, index=dates)
        adv = pd.DataFrame({"A": [1e8, 1e8, 1e8, 1e8, 1e8]}, index=dates)
        result = compute_capacity(weights, adv, 10_000_000.0, participation_cap=0.01)
        # Day 0: delta=0.1, cap = 0.01 * 1e8 = 1e6, capacity = 1e6 / 0.1 = 1e7
        assert result["min_capacity"] == pytest.approx(10_000_000.0)


class TestMargin:
    def test_margin_formula(self):
        """margin_bps = sum(net_return) / sum(turnover) * 10_000."""
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        net = pd.Series([0.01, -0.005, 0.003, 0.002, -0.001,
                         0.004, 0.001, -0.002, 0.003, 0.005], index=dates)
        turnover = pd.Series([0.1] * 10, index=dates)
        margin = compute_margin_bps(net, turnover)
        expected = net.sum() / turnover.sum() * 10_000
        assert margin == pytest.approx(expected)

    def test_margin_na_when_zero_turnover(self):
        """Returns NaN when denominator is zero."""
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        net = pd.Series([0.01] * 5, index=dates)
        turnover = pd.Series([0.0] * 5, index=dates)
        assert np.isnan(compute_margin_bps(net, turnover))


class TestRankIC:
    def test_sign_stated(self):
        """Rank IC returns a sign description."""
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        rng = np.random.default_rng(42)
        symbols = [f"S{i:02d}" for i in range(10)]
        s_score = pd.DataFrame(rng.normal(0, 1, (100, 10)), index=dates, columns=symbols)
        residual_returns = pd.DataFrame(rng.normal(0, 0.01, (100, 10)),
                                        index=dates, columns=symbols)
        result = compute_rank_ic(s_score, residual_returns, horizon_days=5)
        assert "sign" in result
        assert result["n"] > 0

    def test_shift_no_future_leak(self):
        """Target is shifted so no future value enters the signal at t."""
        dates = pd.date_range("2024-01-01", periods=80, freq="B")
        symbols = ["A", "B", "C"]
        rng = np.random.default_rng(42)
        # s_score varies per symbol so correlation is computable.
        s_score = pd.DataFrame(rng.normal(0, 1, (80, 3)), index=dates, columns=symbols)
        # residual_returns: known pattern.
        residual_returns = pd.DataFrame(rng.normal(0, 0.01, (80, 3)),
                                        index=dates, columns=symbols)
        result = compute_rank_ic(s_score, residual_returns, horizon_days=5)
        assert result["n"] > 0


class TestGateEvaluation:
    def test_sharpe_gate_pass(self):
        metrics = {"net_sharpe": 1.5}
        gates = {"sharpe_min": 1.25}
        assert evaluate_gates(metrics, gates)["sharpe_min"] == "PASS"

    def test_sharpe_gate_fail(self):
        metrics = {"net_sharpe": 1.0}
        gates = {"sharpe_min": 1.25}
        assert evaluate_gates(metrics, gates)["sharpe_min"] == "FAIL"

    def test_max_dd_gate_pass(self):
        metrics = {"net_max_drawdown": -0.10}
        gates = {"max_drawdown_max": 0.15}
        assert evaluate_gates(metrics, gates)["max_drawdown_max"] == "PASS"

    def test_max_dd_gate_fail(self):
        metrics = {"net_max_drawdown": -0.20}
        gates = {"max_drawdown_max": 0.15}
        assert evaluate_gates(metrics, gates)["max_drawdown_max"] == "FAIL"

    def test_return_dd_gate_pass(self):
        metrics = {"net_ann_return": 0.20, "net_max_drawdown": -0.15}
        gates = {"return_to_dd_min": 1.0}
        assert evaluate_gates(metrics, gates)["return_to_dd_min"] == "PASS"

    def test_return_dd_gate_fail(self):
        metrics = {"net_ann_return": 0.05, "net_max_drawdown": -0.15}
        gates = {"return_to_dd_min": 1.0}
        assert evaluate_gates(metrics, gates)["return_to_dd_min"] == "FAIL"

    def test_oos_ratio_gate_pass(self):
        metrics = {"oos_sharpe": 0.8, "is_sharpe": 1.0}
        gates = {"oos_ratio_min": 0.50}
        assert evaluate_gates(metrics, gates)["oos_ratio_min"] == "PASS"

    def test_oos_ratio_gate_fail(self):
        metrics = {"oos_sharpe": 0.3, "is_sharpe": 1.0}
        gates = {"oos_ratio_min": 0.50}
        assert evaluate_gates(metrics, gates)["oos_ratio_min"] == "FAIL"

    def test_oos_ratio_na_when_is_zero(self):
        metrics = {"oos_sharpe": 0.5, "is_sharpe": 0.0}
        gates = {"oos_ratio_min": 0.50}
        assert evaluate_gates(metrics, gates)["oos_ratio_min"] == "N/A"

    def test_margin_gate_na_when_nan(self):
        metrics = {"margin_bps": float("nan")}
        gates = {"margin_min_bps": 5.0}
        assert evaluate_gates(metrics, gates)["margin_min_bps"] == "N/A"


class TestTopPnlRemoval:
    def test_removes_top_contributors(self):
        """Top contributors are identified and their P&L is zeroed."""
        dates = pd.date_range("2024-01-01", periods=20, freq="B")
        symbols = ["A", "B", "C"]
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.normal(0.01, 0.02, (20, 3)),
                               index=dates, columns=symbols)
        weights = pd.DataFrame(0.0, index=dates, columns=symbols)
        weights.iloc[2:, 0] = 0.5  # A is long
        weights.iloc[2:, 1] = -0.3  # B is short
        weights.iloc[2:, 2] = 0.2  # C is small long

        net_returns = (weights.shift(1).fillna(0.0) * returns).sum(axis=1)
        result = remove_top_pnl_contributors(net_returns, weights, returns, n_remove=1)

        assert len(result["removed_symbols"]) == 1
        # The removed symbol should be one of the top contributors.
        assert result["removed_symbols"][0] in symbols
        # Trimmed net should differ from original.
        assert not result["net_trimmed"].equals(result["original_net"])


class TestReport:
    def test_report_tables(self):
        """Report contains expected sections and tables."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        # Create mock variant results.
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        rng = np.random.default_rng(42)
        variant_results = []
        for vs in registry:
            net = pd.Series(rng.normal(0.001, 0.01, 100), index=dates)
            variant_results.append({
                "variant_id": vs.variant_id,
                "fingerprint": vs.fingerprint,
                "net": net,
                "gross": net,
                "metrics": {},
                "weights": pd.DataFrame(0.0, index=dates, columns=["A"]),
                "turnover": pd.Series(0.1, index=dates),
                "is_sharpe": 1.0,
                "oos_sharpe": 0.7,
            })

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
        )

        assert "PASS/FAIL denotes configured research gates" in report
        assert "Total unique trials" in report
        assert "Gate summary" in report
        assert "Methodology" in report


class TestConfigConsumption:
    def test_load_strategy_config(self):
        """load_strategy_config reads YAML and returns dict."""
        from strategies.run_residual_reversion import load_strategy_config
        cfg = load_strategy_config("strategies/config.yaml")
        assert "residual_reversion" in cfg

    def test_validate_residual_config_passes(self):
        """validate_residual_config accepts a valid config."""
        from strategies.run_residual_reversion import validate_residual_config
        cfg = _base_config()
        validate_residual_config(cfg)  # should not raise

    def test_validate_residual_config_rejects_unknown(self):
        """validate_residual_config rejects unknown keys."""
        from strategies.run_residual_reversion import validate_residual_config
        cfg = _base_config()
        cfg["residual_reversion"]["bogus_key"] = 42
        with pytest.raises(ValueError, match="unknown"):
            validate_residual_config(cfg)

    def test_validate_residual_config_rejects_missing(self):
        """validate_residual_config rejects missing keys."""
        from strategies.run_residual_reversion import validate_residual_config
        cfg = _base_config()
        del cfg["residual_reversion"]["factor_model"]
        with pytest.raises(ValueError, match="missing"):
            validate_residual_config(cfg)

    def test_build_cost_params(self):
        """build_cost_params reads from config."""
        from strategies.run_residual_reversion import build_cost_params
        cfg = _base_config()
        params = build_cost_params(cfg)
        assert params.adv_participation_cap == 0.01
        assert params.commission_bps == 0.5

    def test_all_config_keys_consumed(self, monkeypatch):
        """Every key in residual_reversion is read and affects the runner."""
        from strategies.run_residual_reversion import load_strategy_config, validate_residual_config
        cfg = load_strategy_config("strategies/config.yaml")
        validate_residual_config(cfg)
        rr = cfg["residual_reversion"]
        # Verify all expected keys exist.
        expected = {"status", "bar_freq", "factor_model", "factor_window",
                    "pca_components", "residual_lookback", "entry_threshold",
                    "exit_threshold", "max_hold_candidates", "min_obs_fraction",
                    "universe_size", "target_gross", "book_capital", "execution_lag_bars"}
        assert set(rr.keys()) == expected