"""Evaluation for the ML ablation lane.

Three families of metrics, per the build request:

* **Predictive** — ROC-AUC, precision/recall, directional accuracy, Brier
  score/calibration, information coefficient (rank IC).
* **Economic** — transaction-cost-adjusted return, Sharpe, max drawdown, hit
  rate, turnover, average holding period. Costs reuse
  ``strategies/cost_model.py``; nothing here re-implements them.
* **Operational** — p50/p95 inference latency.

Everything is pure ``pandas``/``numpy``/``scikit-learn`` so it runs without a
Spark cluster.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn import metrics as skm
from scipy.stats import norm

from strategies.cost_model import CostParams, cost_per_trade


# ── Predictive ───────────────────────────────────────────────────────────────

def predictive_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    y_cont: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """Predictive metrics for a binary (up/down) probability model.

    Args:
        y_true: binary labels (1 = forward return > 0).
        y_prob: predicted P(forward return > 0).
        y_cont: continuous forward returns (optional). Enables information
            coefficient (rank IC); set to NaN when absent.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)

    if len(np.unique(y_true)) < 2:
        auc = float("nan")
    else:
        auc = float(skm.roc_auc_score(y_true, y_prob))

    pred = (y_prob >= 0.5).astype(int)
    out: Dict[str, float] = {
        "roc_auc": auc,
        "precision": float(skm.precision_score(y_true, pred, zero_division=0)),
        "recall": float(skm.recall_score(y_true, pred, zero_division=0)),
        "directional_accuracy": float(np.mean(pred == y_true)),
        "brier_score": float(skm.brier_score_loss(y_true, y_prob)),
    }

    if y_cont is not None and len(y_cont) == len(y_prob):
        out["information_coefficient"] = float(
            pd.Series(y_prob).rank().corr(pd.Series(y_cont).rank())
        )
    else:
        out["information_coefficient"] = float("nan")
    return out


def daily_rank_ic(
    predictions: pd.DataFrame,
    time_col: str = "prediction_ts",
    score_col: str = "y_prob",
    return_col: str = "forward_return",
) -> Dict[str, float]:
    """Cross-sectional Spearman IC summary, computed separately each day."""
    frame = predictions.copy()
    frame["_day"] = pd.to_datetime(frame[time_col]).dt.date
    values = []
    for _, group in frame.groupby("_day"):
        if len(group) < 2 or group[score_col].nunique() < 2 or group[return_col].nunique() < 2:
            continue
        values.append(group[score_col].rank().corr(group[return_col].rank()))
    ic = pd.Series(values, dtype=float).dropna()
    mean = float(ic.mean()) if len(ic) else float("nan")
    std = float(ic.std(ddof=1)) if len(ic) > 1 else float("nan")
    t_stat = mean / (std / np.sqrt(len(ic))) if len(ic) > 1 and std > 0 else float("nan")
    return {
        "daily_rank_ic_mean": mean,
        "daily_rank_ic_std": std,
        "daily_rank_ic_t_stat": float(t_stat),
        "daily_rank_ic_n": float(len(ic)),
    }


def deflated_sharpe_ratio(
    returns: np.ndarray,
    n_trials: int = 4,
    periods_per_year: int = 252,
) -> float:
    """Probability Sharpe exceeds the multiple-testing expected maximum.

    This is the Bailey/Lopez de Prado normal approximation.  ``n_trials``
    should be the actual number of configurations evaluated in the run
    (arms x models x label methods) so the penalty is honest rather than
    hard-coded.
    """
    values = pd.Series(np.asarray(returns, dtype=float)).dropna().to_numpy()
    if len(values) < 3 or np.std(values, ddof=1) == 0:
        return float("nan")
    sr = np.mean(values) / np.std(values, ddof=1) * np.sqrt(periods_per_year)
    expected_max = norm.ppf(1.0 - 1.0 / max(n_trials, 2))
    skew = pd.Series(values).skew()
    kurt = pd.Series(values).kurt() + 3.0
    denom = np.sqrt(max(1e-12, 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr))
    statistic = (sr - expected_max) * np.sqrt(len(values) - 1.0) / denom
    return float(norm.cdf(statistic))


# ── Economic ─────────────────────────────────────────────────────────────────

def build_backtest(
    signals: pd.DataFrame,
    cost_params: Optional[CostParams] = None,
    periods_per_year: int = 3276,  # 252 trading days x 13 half-hour bars
) -> Dict[str, float]:
    """Transaction-cost-adjusted strategy metrics from per-row signals.

    ``signals`` must contain ``symbol``, ``prediction_ts``, ``y_prob`` and
    ``forward_return``. Position is +1 when ``y_prob >= 0.5`` and -1 otherwise
    (long/short). Turnover is the fraction of positions flipped between
    consecutive bars of the same symbol, and each flip is charged one-way cost
    via ``strategies/cost_model.py``.
    """
    if cost_params is None:
        cost_params = CostParams()

    df = signals.sort_values(["symbol", "prediction_ts"]).copy()
    df["position"] = np.where(df["y_prob"] >= 0.5, 1.0, -1.0)
    df["gross_return"] = df["position"] * df["forward_return"]

    # Turnover: |position_t - position_{t-1}| per symbol (0/2).
    df["prev_position"] = df.groupby("symbol")["position"].shift(1)
    df["turnover"] = (df["position"] - df["prev_position"].fillna(df["position"])).abs()
    # A long→short (or reverse) flip = |Δ| of 2; scale to fraction [0,1].
    df["turnover"] = (df["turnover"] / 2.0).clip(0.0, 1.0)

    # One-way cost in bps per trade; cost drag = turnover * cost_bps / 1e4.
    cost_bps = cost_per_trade(1.0, adv=1.0, params=cost_params)
    df["cost_drag"] = df["turnover"] * cost_bps / 1e4
    df["net_return"] = df["gross_return"] - df["cost_drag"]

    net = df["net_return"].dropna()
    if net.empty:
        return {
            "net_return": float("nan"),
            "sharpe": float("nan"),
            "max_drawdown": float("nan"),
            "hit_rate": float("nan"),
            "turnover": float("nan"),
            "avg_holding_period": float("nan"),
        }

    mean = float(net.mean())
    std = float(net.std(ddof=0)) if len(net) > 1 else 0.0
    sharpe = (mean / std * np.sqrt(periods_per_year)) if std > 0 else float("nan")

    equity = (1.0 + net).cumprod()
    running_max = equity.cummax()
    max_dd = float(((equity - running_max) / running_max).min())

    hit = float(np.mean(np.sign(df["forward_return"]) == np.sign(df["position"])))

    avg_turnover = float(df["turnover"].mean()) if len(df) else float("nan")

    # Average holding period: mean run length of an unchanged position sign.
    runs: List[int] = []
    for _, grp in df.groupby("symbol"):
        pos = grp["position"].values
        if len(pos) == 0:
            continue
        run = 1
        for i in range(1, len(pos)):
            if pos[i] == pos[i - 1]:
                run += 1
            else:
                runs.append(run)
                run = 1
        runs.append(run)
    avg_holding = float(np.mean(runs)) if runs else float("nan")

    return {
        "net_return": mean,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "hit_rate": hit,
        "turnover": avg_turnover,
        "avg_holding_period": avg_holding,
    }


# ── Operational ──────────────────────────────────────────────────────────────

def operational_metrics(latencies_ms: List[float]) -> Dict[str, float]:
    """Inference latency percentiles (p50, p95) in milliseconds."""
    if not latencies_ms:
        return {"p50_latency_ms": float("nan"), "p95_latency_ms": float("nan")}
    arr = np.asarray(latencies_ms, dtype=float)
    return {
        "p50_latency_ms": float(np.percentile(arr, 50)),
        "p95_latency_ms": float(np.percentile(arr, 95)),
    }


def evaluate_predictions(
    pred_df: pd.DataFrame,
    cost_params: Optional[CostParams] = None,
    latencies_ms: Optional[List[float]] = None,
    n_trials: int = 4,
) -> Dict[str, float]:
    """Combined predictive + economic + operational metric bundle for one arm.

    ``pred_df`` must contain ``y_true``, ``y_prob`` and ``forward_return``.
    ``n_trials`` is the actual number of configurations evaluated in the run
    (arms x models x label methods) and is passed to the deflated Sharpe ratio.
    """
    metrics = predictive_metrics(
        pred_df["y_true"].values,
        pred_df["y_prob"].values,
        pred_df["forward_return"].values
        if "forward_return" in pred_df.columns
        else None,
    )
    metrics.update(build_backtest(pred_df, cost_params=cost_params))
    if "forward_return" in pred_df:
        metrics.update(daily_rank_ic(pred_df))
        position = np.where(pred_df["y_prob"].to_numpy() >= 0.5, 1.0, -1.0)
        strategy_ret = position * pred_df["forward_return"].to_numpy()
        ts_col = "prediction_ts"
        if ts_col in pred_df.columns:
            sr = pd.Series(strategy_ret, index=pred_df[ts_col])
            agg = sr.groupby(level=0).mean().sort_index()
            agg_values = agg.to_numpy()
            periods_per_year = 252
        else:
            agg_values = strategy_ret
            periods_per_year = 252
        metrics["deflated_sharpe_ratio"] = deflated_sharpe_ratio(
            agg_values, n_trials=n_trials, periods_per_year=periods_per_year
        )
    metrics.update(operational_metrics(latencies_ms or []))
    return metrics
