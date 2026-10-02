"""Scoring-path tests: signal-row construction against the real table schema.

The gold_trading_signals table (introspected) has exactly these 10 columns,
in order:

    signal_id, symbol, prediction_ts, horizon, direction, probability,
    model_version, feature_snapshot_id, status, processed_ts

These tests pin the row builder to that contract. The Spark/Delta write itself
is marked ``spark`` and deselected in the fast run.
"""

import pandas as pd

from ml.score import GOLD_SIGNAL_COLUMNS, build_signal_rows


def test_gold_signal_columns_match_table_schema():
    assert GOLD_SIGNAL_COLUMNS == [
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


def test_build_signal_rows_direction_and_determinism():
    pred = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "prediction_ts": pd.to_datetime(
                ["2026-01-05T09:30:00Z", "2026-01-05T09:30:00Z"], utc=True
            ),
            "probability": [0.71, 0.42],
            "feature_snapshot_id": ["snap-1", "snap-1"],
        }
    )
    rows = build_signal_rows(pred, model_version="v1", horizon="30m")

    assert list(rows.columns) == GOLD_SIGNAL_COLUMNS
    assert rows.loc[0, "direction"] == "UP"
    assert rows.loc[1, "direction"] == "DOWN"
    assert rows["probability"].tolist() == [0.71, 0.42]

    # Idempotency: rebuilding the same rows yields identical signal_ids.
    rows2 = build_signal_rows(pred, model_version="v1", horizon="30m")
    assert rows["signal_id"].tolist() == rows2["signal_id"].tolist()
