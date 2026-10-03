"""Scoring path: turn the promoted model's probabilities into trading signals.

Writes to ``gold_trading_signals`` with **exactly** the columns that table has
(introspected from Unity Catalog):

    signal_id, symbol, prediction_ts, horizon, direction, probability,
    model_version, feature_snapshot_id, status, processed_ts

Spark/PySpark is imported lazily so the row-building logic can be unit-tested
without a Spark cluster.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional

import pandas as pd

# Ordered to match the Unity Catalog table definition (positions 0..9).
GOLD_SIGNAL_COLUMNS: list = [
    "signal_id",
    "symbol",
    "prediction_ts",
    "horizon",
    "direction",
    "probability",
    "model_version",
    "feature_snapshot_id",
    "status",
    "processed_ts",
]


def _signal_id(symbol: str, prediction_ts, model_version: str) -> str:
    """Deterministic idempotency key — the same row always gets the same id."""
    key = f"{symbol}|{pd.Timestamp(prediction_ts).isoformat()}|{model_version}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def build_signal_rows(
    pred_df: pd.DataFrame,
    model_version: str,
    horizon: str = "30m",
    status: str = "ACTIVE",
    processed_ts=None,
) -> pd.DataFrame:
    """Build ``gold_trading_signals``-shaped rows from scored probabilities.

    ``pred_df`` must contain ``symbol``, ``prediction_ts``, ``probability`` and
    ``feature_snapshot_id``.
    """
    if processed_ts is None:
        processed_ts = datetime.now(timezone.utc)

    rows = []
    for _, r in pred_df.iterrows():
        prob = float(r["probability"])
        rows.append(
            {
                "signal_id": _signal_id(
                    r["symbol"], r["prediction_ts"], model_version
                ),
                "symbol": r["symbol"],
                "prediction_ts": pd.Timestamp(r["prediction_ts"]),
                "horizon": horizon,
                "direction": "UP" if prob >= 0.5 else "DOWN",
                "probability": prob,
                "model_version": model_version,
                "feature_snapshot_id": r["feature_snapshot_id"],
                "status": status,
                "processed_ts": pd.Timestamp(processed_ts),
            }
        )
    out = pd.DataFrame(rows, columns=GOLD_SIGNAL_COLUMNS)
    return out


def score_rows(
    features: pd.DataFrame,
    model,
    model_version: str,
    horizon: str = "30m",
    feature_snapshot_id_col: str = "feature_snapshot_id",
    feature_cols: Optional[Iterable[str]] = None,
    status: str = "ACTIVE",
) -> pd.DataFrame:
    """Score the latest feature rows and return ready-to-write signal rows.

    ``features`` must contain ``symbol``, ``prediction_ts`` and the feature
    columns the model was trained on (``feature_cols``, or the model's own
    ``feature_names_in_`` when available).
    """
    if feature_cols is None:
        feature_cols = list(getattr(model, "feature_names_in_", features.columns))
    X = features[list(feature_cols)]
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)[:, 1]
    else:
        proba = model.predict(X)

    scored = features[["symbol", "prediction_ts", feature_snapshot_id_col]].copy()
    scored["probability"] = proba
    return build_signal_rows(
        scored, model_version=model_version, horizon=horizon, status=status
    )


def write_signals(
    signals: pd.DataFrame,
    catalog: str = "bootcamp_students",
    schema: str = "evangoh_capstone",
    table: str = "gold_trading_signals",
) -> int:
    """Append signal rows to the gold table via Spark/Delta.

    Requires a Spark session with Delta support (Databricks runtime or a local
    install with delta-spark). Not exercised by the non-spark test run.
    """
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    sdf = spark.createDataFrame(signals)
    sdf.write.format("delta").mode("append").saveAsTable(
        f"{catalog}.{schema}.{table}"
    )
    return len(signals)
