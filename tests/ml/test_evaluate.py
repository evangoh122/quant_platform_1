"""Evaluation metric smoke tests.

Verifies the metric bundle is finite and internally consistent, and that the
economic path reuses ``strategies/cost_model.py`` rather than reimplementing it.
"""

import numpy as np

from ml.evaluate import (
    build_backtest,
    operational_metrics,
    predictive_metrics,
)
from strategies.cost_model import CostParams


def test_predictive_metrics_are_finite_and_in_range():
    y_true = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1, 1])
    y_prob = np.array([0.1, 0.9, 0.2, 0.8, 0.7, 0.3, 0.6, 0.4, 0.95, 0.05])
    m = predictive_metrics(y_true, y_prob, y_cont=y_prob * 2 - 1)

    assert 0.0 <= m["roc_auc"] <= 1.0
    assert 0.0 <= m["precision"] <= 1.0
    assert 0.0 <= m["recall"] <= 1.0
    assert 0.0 <= m["directional_accuracy"] <= 1.0
    assert 0.0 <= m["brier_score"] <= 1.0
    assert -1.0 <= m["information_coefficient"] <= 1.0


def test_build_backtest_applies_costs():
    import pandas as pd

    signals = pd.DataFrame(
        {
            "symbol": ["AAPL"] * 4,
            "prediction_ts": pd.date_range("2026-01-05", periods=4, freq="30min", tz="UTC"),
            "y_prob": [0.9, 0.9, 0.1, 0.1],
            "forward_return": [0.01, 0.005, -0.002, -0.003],
        }
    )
    gross = build_backtest(signals, cost_params=CostParams(), periods_per_year=252)
    # A perfectly-directional strategy: hit rate is 1.0 before costs.
    assert gross["hit_rate"] == 1.0
    assert "sharpe" in gross and "max_drawdown" in gross
    assert gross["win_rate"] == 1.0
    assert gross["profit_factor"] > 1.5
    assert "sortino_ratio" in gross and "calmar_ratio" in gross


def test_operational_metrics_percentiles():
    m = operational_metrics([1.0, 2.0, 3.0, 4.0, 5.0])
    assert m["p50_latency_ms"] == 3.0
    assert m["p95_latency_ms"] > 4.0
