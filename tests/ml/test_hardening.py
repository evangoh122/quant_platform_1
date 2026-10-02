import numpy as np
import pandas as pd

from ml.evaluate import daily_rank_ic, deflated_sharpe_ratio
from ml.features import (
    average_uniqueness_weights,
    compute_labels,
    compute_triple_barrier_labels,
    neutralize_features,
)


def test_triple_barrier_hits_first_path_barrier_and_fixed_label_remains():
    times = pd.date_range("2025-01-01", periods=10, freq="D")
    prices = [100, 100, 100, 100, 102, 98, 98, 98, 98, 98]
    bars = pd.DataFrame({"symbol": "A", "event_ts": times, "close": prices})
    triple = compute_triple_barrier_labels(
        bars, horizon_bars=3, volatility_window=2, profit_target=0.5, stop_loss=0.5
    )
    assert set(triple["label"].unique()) <= {-1.0, 0.0, 1.0}
    assert "label_end_ts" in triple
    fixed = compute_labels(bars, horizon_minutes=3, bar_seconds=60)
    assert set(fixed["label"].unique()) <= {0, 1}


def test_uniqueness_penalises_overlapping_events():
    times = pd.date_range("2025-01-01", periods=4, freq="D")
    events = pd.DataFrame(
        {"symbol": "A", "prediction_ts": times, "label_end_ts": times + pd.Timedelta(days=2)}
    )
    weights = average_uniqueness_weights(events)
    assert (weights > 0).all() and (weights <= 1).all()
    assert weights.iloc[1] < weights.iloc[0]


def test_neutralisation_removes_beta_and_industry_loadings():
    frame = pd.DataFrame(
        {
            "prediction_ts": pd.Timestamp("2025-01-01"),
            "market_beta": [-1.5, -0.5, 0.5, 1.5, -1.0, 1.0],
            "industry": ["tech"] * 3 + ["bank"] * 3,
        }
    )
    frame["feature"] = 3 * frame["market_beta"] + (frame["industry"] == "tech") * 2
    result = neutralize_features(frame, ["feature"])
    assert np.max(np.abs(result["feature"])) < 1e-10


def test_daily_rank_ic_and_deflated_sharpe_are_reported():
    pred = pd.DataFrame(
        {
            "prediction_ts": list(pd.to_datetime(["2025-01-01"] * 3 + ["2025-01-02"] * 3)),
            "y_prob": [0.1, 0.5, 0.9] * 2,
            "forward_return": [-0.02, 0.0, 0.02] * 2,
        }
    )
    result = daily_rank_ic(pred)
    assert result["daily_rank_ic_mean"] == 1.0
    assert result["daily_rank_ic_n"] == 2.0
    dsr = deflated_sharpe_ratio(np.array([-0.01, 0.02, 0.01, -0.005, 0.03]))
    assert 0.0 <= dsr <= 1.0
