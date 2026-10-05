"""Run the A/B/C/D ablation study end-to-end and write the comparison artifact.

The gold/silver Unity Catalog tables were empty (0 rows) at build time, so this
runner defaults to the deterministic synthetic dataset in ``ml/synthetic_data.py``
(which mirrors the real schema). When live data lands, point this at the
warehouse read path in ``ml/score.py`` / the SQL probe in ``.agentlogs`` — the
ablation logic itself is data-agnostic.

Writes:
  * ``ml/results/ablation_abcd.md`` — the A/B/C/D comparison table (committed);
  * MLflow runs (feature-set version + seed + metrics) to the local store.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_p = globals().get("__file__") or sys.argv[0]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(_p))))
from pipelines._runtime import repo_root

import numpy as np
import pandas as pd

from ml import evaluate, registry
from ml.features import FEATURE_SETS
from ml.synthetic_data import make_synthetic_matrix
from ml.train import make_baseline, make_challenger, run_ablation


def _resolve_output_dir(output_dir: str | None) -> Path:
    """Return an absolute path for ablation artifacts.

    Priority:
      1. Explicit ``--output-dir`` (used as-is, must be absolute or made absolute).
      2. Databricks runtime → ``/Volumes/{CATALOG}/{SCHEMA}/ml_artifacts``.
      3. Local fallback   → ``<repo_root>/artifacts``.
    """
    if output_dir:
        p = Path(output_dir)
        return p if p.is_absolute() else Path.cwd() / p

    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        catalog = os.getenv("CATALOG", "bootcamp_students")
        schema = os.getenv("SCHEMA", "evangoh_capstone")
        return Path("/Volumes") / catalog / schema / "ml_artifacts"

    return repo_root() / "artifacts"


def _measure_latency(model, X: pd.DataFrame, repeats: int = 200) -> list:
    """Measure per-call inference latency (ms) on a single-row input."""
    x = X.iloc[[0]]
    # warm-up
    if hasattr(model, "predict_proba"):
        model.predict_proba(x)
    else:
        model.predict(x)
    lat = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        if hasattr(model, "predict_proba"):
            model.predict_proba(x)
        else:
            model.predict(x)
        lat.append((time.perf_counter() - t0) * 1000.0)
    return lat


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ML ablation study")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-symbols", type=int, default=18)
    parser.add_argument("--n-bars", type=int, default=400)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--min-train", type=int, default=60)
    parser.add_argument("--include-challenger", action="store_true")
    parser.add_argument("--label-method", choices=["fixed", "triple_barrier"], default="fixed")
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for ablation artifacts. "
        "Default: /Volumes/{CATALOG}/{SCHEMA}/ml_artifacts when DATABRICKS_RUNTIME_VERSION is set, "
        "else <repo_root>/artifacts.",
    )
    args = parser.parse_args()

    if args.tracking_uri:
        import mlflow

        mlflow.set_tracking_uri(args.tracking_uri)

    data_window = "synthetic (live gold tables empty)"
    matrix = make_synthetic_matrix(
        n_symbols=args.n_symbols, n_bars=args.n_bars, seed=args.seed,
        label_method=args.label_method,
    )

    models = {"baseline": make_baseline}
    if args.include_challenger:
        models["challenger"] = make_challenger

    result = run_ablation(
        matrix,
        feature_sets=FEATURE_SETS,
        models=models,
        n_splits=args.n_splits,
        min_train=args.min_train,
        seed=args.seed,
        label_method=args.label_method,
    )

    comparison = result["comparison"]

    # Attach operational latency (p50/p95) per model type by timing inference
    # on the full feature set.
    from ml.train import prepare_features

    X_full = prepare_features(matrix, FEATURE_SETS["D"])
    y_full = matrix["label"].to_numpy()
    latency_by_model = {}
    for mname, mfactory in models.items():
        m = mfactory(args.seed)
        m.fit(X_full, y_full)
        latency_by_model[mname] = evaluate.operational_metrics(_measure_latency(m, X_full))
    comparison["p50_latency_ms"] = comparison["model"].map(
        lambda m: latency_by_model[m]["p50_latency_ms"]
    )
    comparison["p95_latency_ms"] = comparison["model"].map(
        lambda m: latency_by_model[m]["p95_latency_ms"]
    )

    # Log each (arm, model) run to MLflow with feature-set version + seed.
    for _, row in comparison.iterrows():
        params = registry.build_run_tags(
            feature_set=row["arm"],
            seed=args.seed,
            model_type=row["model"],
            data_window=data_window,
            label_method=args.label_method,
        )
        metrics = {
            k: row[k]
            for k in (
                "roc_auc",
                "directional_accuracy",
                "precision",
                "recall",
                "brier_score",
                "information_coefficient",
                "net_return",
                "sharpe",
                "max_drawdown",
                "hit_rate",
                "turnover",
                "avg_holding_period",
                "p50_latency_ms",
                "p95_latency_ms",
            )
            if k in row
        }
        registry.log_run(
            run_name=f"ablation-{row['arm']}-{row['model']}",
            params=params,
            metrics={k: v for k, v in metrics.items() if pd.notna(v)},
        )

    # ── Write the committed result artifact ────────────────────────────────
    out_dir = _resolve_output_dir(args.output_dir)
    os.makedirs(out_dir, exist_ok=True)
    lines = [
        "# A/B/C/D Ablation Results",
        "",
        "> **NOTE: synthetic demonstration.** The live Unity Catalog gold tables",
        "> (`gold_ohlcv_features`, `gold_options_features`, `gold_sec_features`,",
        "> `gold_cot_features`, `gold_model_features`, `silver_ohlcv`) were all",
        "> **empty (0 rows)** at build time, so the study below ran on the",
        "> deterministic synthetic dataset in `ml/synthetic_data.py`, which mirrors",
        "> the real schema. The pipeline is data-agnostic: point `ml/run_ablation.py`",
        "> at the warehouse read path once live data lands. Treat the numbers as",
        "> pipeline validation only, not as market findings.",
        "",
        f"Seed: {args.seed} · n_symbols: {args.n_symbols} · n_bars: {args.n_bars} · splits: {args.n_splits} · min_train: {args.min_train} · label_method: {args.label_method}",
        "",
        "| Arm | Feature set | Model | ROC-AUC | Dir. acc | Brier | IC | Sharpe | MaxDD | Hit rate | Turnover | Avg hold | p95 lat (ms) |",
        "| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for _, row in comparison.iterrows():
        label = {
            "A": "OHLCV",
            "B": "OHLCV+options",
            "C": "OHLCV+options+SEC",
            "D": "OHLCV+options+SEC+COT",
        }[row["arm"]]

        def f(v, nd=3):
            return "—" if pd.isna(v) else f"{v:.{nd}f}"

        lines.append(
            f"| {row['arm']} | {label} | {row['model']} | {f(row['roc_auc'])} | "
            f"{f(row['directional_accuracy'])} | {f(row['brier_score'])} | "
            f"{f(row['information_coefficient'])} | {f(row['sharpe'], 2)} | "
            f"{f(row['max_drawdown'])} | {f(row['hit_rate'])} | "
            f"{f(row['turnover'])} | {f(row['avg_holding_period'], 2)} | "
            f"{f(row['p95_latency_ms'], 2)} |"
        )

    path = os.path.join(out_dir, "ablation_abcd.md")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Wrote {path}")
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
