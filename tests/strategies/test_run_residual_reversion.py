"""Tests for run_residual_reversion helpers."""

import numpy as np
import pandas as pd
import pytest

from strategies.run_residual_reversion import _render, parse_round_from_output


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
def test_leverage_wording_says_50pct():
    """Gross 1.0 with dollar neutrality is 50% long / 50% short, not 100%/100%.

    The rendered configuration line must say '50% long / 50% short'.
    """
    bm = {
        "gross_ann_return": 0.01, "net_ann_return": 0.005,
        "net_2x_ann_return": 0.0, "gross_sharpe": 0.5, "net_sharpe": 0.3,
        "net_2x_sharpe": 0.1, "gross_max_drawdown": -0.1,
        "net_max_drawdown": -0.12, "net_2x_max_drawdown": -0.15,
        "hit_rate": 0.52, "turnover_avg_daily": 0.05, "avg_hold_days": 5.0,
        "deflated_sharpe_ratio": 0.0,
    }
    gm = dict(bm)
    base_res = {"metrics": bm}
    gated_res = {"metrics": gm}
    oos_net = pd.Series([0.001, 0.002, 0.003])

    lines = _render(
        base_res, gated_res, oos_net, n_trials=3, capacity=1e8,
        book_capital=10_000_000.0, window=60, lookback=5, entry=2.5,
        exit_thresh=0.5, date_start=pd.Timestamp("2024-01-01"),
        date_end=pd.Timestamp("2024-12-31"), n_dates=252, n_folds=5,
        round_num=7,
    )

    config_line = [l for l in lines if "target gross" in l]
    assert config_line, "no 'target gross' line found in rendered output"
    line = config_line[0]

    assert "50% long / 50% short" in line, (
        f"should say '50% long / 50% short', got: {line}"
    )
    assert "100% long / 100% short" not in line, (
        f"should NOT say '100% long / 100% short', got: {line}"
    )


def test_build_cost_params_from_real_config_is_numeric():
    """The shipped strategies/config.yaml must produce numeric cost params.

    PyYAML (YAML 1.1) parses exponent literals like ``5.0e7`` as strings, which
    crashed the live run in ``liquidity_bucket``. Guard both the file and the coercion.
    """
    import yaml
    from strategies.run_residual_reversion import build_cost_params

    with open("strategies/config.yaml") as f:
        cfg = yaml.safe_load(f)
    p = build_cost_params(cfg)
    assert all(isinstance(x, float) for x in p.borrow_bucket_thresholds)
    assert all(isinstance(v, float) for v in p.borrow_bps_daily.values())
    for name in ("commission_bps", "spread_bps", "slippage_bps", "adv_participation_cap"):
        assert isinstance(getattr(p, name), float)
    # String exponents in a config must still be coerced.
    p2 = build_cost_params({"cost_model": {"borrow_bucket_thresholds": ["5.0e7", "2.0e7"]}})
    assert p2.borrow_bucket_thresholds == (5.0e7, 2.0e7)
