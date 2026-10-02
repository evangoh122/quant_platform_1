"""The single most important test in the ML lane: no lookahead.

If any assembled training row contains a feature whose
``information_available_ts > prediction_ts``, the build must fail. This file
contains both halves of that guarantee:

1. the happy path — clean data passes the guard;
2. the failure path — a deliberately injected leak makes the guard raise.

A test that only checks the happy path would be a blocking defect.
"""

import numpy as np
import pandas as pd
import pytest

from ml.features import (
    LookaheadError,
    OHLCV_FEATURES,
    asof_join,
    assert_no_lookahead,
)


def _make_ohlcv(times, symbols=("AAPL",), information_available_ts=None):
    rows = []
    for sym in symbols:
        for t in times:
            avail = t if information_available_ts is None else information_available_ts
            row = {"symbol": sym, "feature_ts": t, "information_available_ts": avail}
            for f in OHLCV_FEATURES:
                row[f] = 0.0
            rows.append(row)
    return pd.DataFrame(rows)


def test_no_lookahead_passes_on_clean_data():
    times = pd.date_range("2026-01-05T09:30:00", periods=10, freq="1min", tz="UTC")
    pred = pd.DataFrame(
        {"symbol": "AAPL", "prediction_ts": times}
    )
    ohlcv = _make_ohlcv(times)
    matrix = asof_join(pred, ohlcv, OHLCV_FEATURES, on="information_available_ts")
    matrix["max_information_available_ts"] = matrix["information_available_ts"]

    # Must not raise.
    assert_no_lookahead(matrix)


def test_no_lookahead_detects_injected_leak():
    """A row whose availability time is in the future MUST raise LookaheadError."""
    times = pd.date_range("2026-01-05T09:30:00", periods=10, freq="1min", tz="UTC")
    pred = pd.DataFrame({"symbol": "AAPL", "prediction_ts": times})
    ohlcv = _make_ohlcv(times)
    matrix = asof_join(pred, ohlcv, OHLCV_FEATURES, on="information_available_ts")

    # Inject the leak: the *last* prediction row claims a feature that was only
    # "available" 5 minutes after its own decision time. This is the exact bug
    # the guard exists to catch.
    matrix.loc[matrix.index[-1], "information_available_ts"] = (
        times[-1] + pd.Timedelta(minutes=5)
    )
    matrix["max_information_available_ts"] = matrix["information_available_ts"]

    with pytest.raises(LookaheadError):
        assert_no_lookahead(matrix)


def test_asof_join_never_selects_future_availability():
    """The as-of join itself must not select a feature row whose availability
    time is after the prediction time, even if the bar-close time is before it.
    """
    times = pd.date_range("2026-01-05T09:30:00", periods=5, freq="1min", tz="UTC")
    pred = pd.DataFrame({"symbol": "AAPL", "prediction_ts": times})

    # A feature computed on the first bar but whose availability is delayed
    # until *after* the last prediction time. The join keys on availability,
    # so this row must never be selected for predictions before it is known.
    ohlcv = _make_ohlcv([times[0]])
    ohlcv.loc[0, "information_available_ts"] = times[-1] + pd.Timedelta(hours=1)

    merged = asof_join(pred, ohlcv, OHLCV_FEATURES, on="information_available_ts")

    # Every prediction_ts < that future availability time must get NaN (no row).
    assert merged["return_1m"].isna().all()
