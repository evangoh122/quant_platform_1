from __future__ import annotations

import math

import pytest

from strategies.report import performance_metrics


def test_performance_ratios_have_expected_trade_math():
    returns = [0.02, -0.01, 0.03, -0.01]
    result = performance_metrics(returns, periods_per_year=252)

    assert result["profit_factor"] == pytest.approx(2.5)
    assert result["win_rate"] == pytest.approx(0.5)
    assert result["average_win"] == pytest.approx(0.025)
    assert result["average_loss"] == pytest.approx(0.01)
    assert result["payoff_ratio"] == pytest.approx(2.5)
    assert result["max_drawdown"] == pytest.approx(0.01)
    assert result["sharpe_ratio"] > 0
    assert result["sortino_ratio"] > 0
    assert result["calmar_ratio"] > 0


def test_trade_pnls_control_profit_factor_and_win_rate():
    result = performance_metrics(
        [0.001, 0.002, -0.001],
        periods_per_year=252,
        trade_pnls=[100.0, -50.0, 25.0, -25.0],
    )
    assert result["profit_factor"] == pytest.approx(125 / 75)
    assert result["win_rate"] == pytest.approx(0.5)
    assert result["trade_count"] == 4


def test_all_winners_have_infinite_profit_factor():
    result = performance_metrics([0.01, 0.02], periods_per_year=252)
    assert math.isinf(result["profit_factor"])
    assert result["win_rate"] == 1.0


def test_empty_returns_are_reported_as_nan():
    result = performance_metrics([], periods_per_year=252)
    assert math.isnan(result["sharpe_ratio"])
    assert math.isnan(result["profit_factor"])


def test_invalid_annualization_is_rejected():
    with pytest.raises(ValueError, match="periods_per_year"):
        performance_metrics([0.01], periods_per_year=0)
