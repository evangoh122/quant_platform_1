"""Tests for run_residual_reversion helpers."""

import pytest

from strategies.run_residual_reversion import parse_round_from_output


class TestParseRoundFromOutput:
    def test_parses_r1(self):
        assert parse_round_from_output("strategies/results/residual_reversion_r1.md") == 1

    def test_parses_r4(self):
        assert parse_round_from_output("strategies/results/residual_reversion_r4.md") == 4

    def test_parses_r12(self):
        assert parse_round_from_output("residual_reversion_r12.md") == 12

    def test_raises_on_no_match(self):
        with pytest.raises(ValueError, match="cannot derive round"):
            parse_round_from_output("strategies/results/residual_reversion.md")

    def test_raises_on_wrong_suffix(self):
        with pytest.raises(ValueError, match="cannot derive round"):
            parse_round_from_output("strategies/results/residual_reversion_r3.txt")


class TestConfigHelpers:
    def test_load_strategy_config(self):
        from strategies.run_residual_reversion import load_strategy_config
        cfg = load_strategy_config("strategies/config.yaml")
        assert "residual_reversion" in cfg
        assert "cost_model" in cfg
        assert "metric_gates" in cfg

    def test_validate_accepts_valid_config(self):
        from strategies.run_residual_reversion import validate_residual_config
        cfg = {
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
            }
        }
        validate_residual_config(cfg)

    def test_validate_rejects_unknown_key(self):
        from strategies.run_residual_reversion import validate_residual_config
        cfg = {
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
                "bogus_key": 42,
            }
        }
        with pytest.raises(ValueError, match="unknown"):
            validate_residual_config(cfg)

    def test_validate_rejects_missing_key(self):
        from strategies.run_residual_reversion import validate_residual_config
        cfg = {
            "residual_reversion": {
                "status": "primary",
                "bar_freq": "1d",
                # missing factor_model
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
            }
        }
        with pytest.raises(ValueError, match="missing"):
            validate_residual_config(cfg)

    def test_build_cost_params_from_config(self):
        from strategies.run_residual_reversion import build_cost_params
        cfg = {
            "cost_model": {
                "commission_bps": 1.0,
                "spread_bps": 4.0,
                "slippage_bps": 3.0,
                "adv_participation_cap": 0.02,
                "borrow_bps_daily": {"liquid": 0.5, "medium": 1.0, "illiquid": 3.0},
                "borrow_bucket_thresholds": [6e7, 3e7],
            }
        }
        params = build_cost_params(cfg)
        assert params.commission_bps == 1.0
        assert params.spread_bps == 4.0
        assert params.adv_participation_cap == 0.02
        assert params.borrow_bps_daily["liquid"] == 0.5

    def test_no_module_state_leak_in_config(self):
        """Repeated load_strategy_config calls don't leak state."""
        from strategies.run_residual_reversion import load_strategy_config
        cfg1 = load_strategy_config("strategies/config.yaml")
        cfg2 = load_strategy_config("strategies/config.yaml")
        assert cfg1 == cfg2
        # Mutating one shouldn't affect the other.
        cfg1["residual_reversion"]["entry_threshold"] = 999
        assert cfg2["residual_reversion"]["entry_threshold"] != 999