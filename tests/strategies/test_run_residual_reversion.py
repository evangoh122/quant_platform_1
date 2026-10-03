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