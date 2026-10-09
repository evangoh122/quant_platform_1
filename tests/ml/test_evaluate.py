"""Evaluation metric smoke tests.

Verifies the metric bundle is finite and internally consistent, and that the
economic path reuses ``strategies/cost_model.py`` rather than reimplementing it.
Also pins the hardening contract: one portfolio return per timestamp, the
one-way turnover convention, the quarantined deflated Sharpe warning, and the
api/frontend import guard for ``ml.evaluate``.
"""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.evaluate import (
    build_backtest,
    deflated_sharpe_ratio,
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


# ── Hardening: portfolio aggregation, turnover, DSR quarantine, guard ───────


def test_build_backtest_one_portfolio_return_per_timestamp():
    """Two symbols at the SAME prediction_ts must yield ONE portfolio period.

    The period count is exposed as ``observation_count``; it must equal the
    number of distinct timestamps (mutation M5 drops the groupby and the count
    doubles to the symbol-row count).
    """
    ts = pd.date_range("2026-01-05", periods=20, freq="B", tz="UTC")
    frames = []
    for symbol, y_prob, fwd in (("AAPL", 0.9, 0.001), ("MSFT", 0.1, -0.002)):
        frame = pd.DataFrame({"symbol": symbol, "prediction_ts": ts})
        frame["y_prob"] = y_prob
        frame["forward_return"] = fwd
        frames.append(frame)
    signals = pd.concat(frames, ignore_index=True)

    result = build_backtest(signals, cost_params=CostParams(), periods_per_year=252)

    n_timestamps = int(signals["prediction_ts"].nunique())
    assert len(signals) == 40
    assert n_timestamps == 20
    assert result["observation_count"] == n_timestamps
    assert result["periods_per_year"] == 252


def test_build_backtest_turnover_is_one_way_flip_fraction():
    """Turnover convention: one-way = |Δposition| / 2 (a flip is 1.0)."""
    signals = pd.DataFrame(
        {
            "symbol": ["AAPL"] * 3,
            "prediction_ts": pd.date_range("2026-01-05", periods=3, freq="B", tz="UTC"),
            "y_prob": [0.9, 0.9, 0.1],
            "forward_return": [0.001, 0.002, -0.003],
        }
    )
    result = build_backtest(signals, cost_params=CostParams(), periods_per_year=252)

    # positions = [+1, +1, -1]; per-row one-way turnover = |Δposition| / 2:
    #   row 0: no predecessor        -> 0.0
    #   row 1: |1 - 1| / 2           = 0.0
    #   row 2: |-1 - 1| / 2          = 1.0  (one two-sided flip)
    # mean over the 3 rows = (0 + 0 + 1) / 3 = 1/3.
    # Mutation M6 (divisor 2 -> 4) would give 1/6.
    assert result["turnover"] == pytest.approx(1.0 / 3.0, abs=1e-12)


def test_deflated_sharpe_ratio_warns_research_only():
    returns = np.array([-0.01, 0.02, 0.01, -0.005, 0.03])
    with pytest.warns(UserWarning, match="RESEARCH-ONLY"):
        dsr = deflated_sharpe_ratio(returns)
    assert 0.0 <= dsr <= 1.0


def test_no_api_or_frontend_imports_ml_evaluate_or_deflated_sharpe():
    """Guard: ``ml.evaluate`` (and its deflated Sharpe) is quarantined.

    Nothing under ``api/`` or ``frontend/`` may import it.  Real source files
    are parsed with ``ast`` (Python imports/references) and every source file
    is text-scanned (covers TS/JS import strings and dynamic references).
    """
    root = Path(__file__).resolve().parents[2]
    skip_parts = {
        "node_modules", ".git", "__pycache__", "dist", "build", "out",
        ".next", ".venv", "venv", "coverage", ".turbo", ".cache",
        ".pytest_cache",
    }
    source_suffixes = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
    violations = []
    for area in ("api", "frontend"):
        base = root / area
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in source_suffixes:
                continue
            if skip_parts.intersection(path.parts):
                continue
            rel = path.relative_to(root)
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                if (
                    "deflated_sharpe_ratio" in line
                    or "ml.evaluate" in line
                    or "ml/evaluate" in line
                ):
                    violations.append(f"{rel}:{lineno}: {line.strip()}")
            if path.suffix.lower() == ".py":
                tree = ast.parse(text, filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.split(".")[0] == "ml":
                                violations.append(f"{rel}:{node.lineno}: import {alias.name}")
                    elif isinstance(node, ast.ImportFrom):
                        mod = node.module or ""
                        if mod.split(".")[0] == "ml":
                            violations.append(
                                f"{rel}:{node.lineno}: from {mod} import ..."
                            )
    assert not violations, (
        "quarantined ml.evaluate leaked into api/ or frontend/:\n"
        + "\n".join(violations)
    )
