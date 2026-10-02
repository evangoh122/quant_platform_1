"""tests/gold/test_pit_leakage.py — point-in-time (no-look-ahead) guard.

Proves the guard fires on an injected leaking row (a happy-path-only test is a
blocking defect). Run standalone (the project conftest imports db.database,
which does not exist on this branch):

    python -m pytest tests/gold/test_pit_leakage.py --noconftest -v
"""
from datetime import datetime, timezone

import pytest

from gold.pit_guard import (
    LookaheadLeakError,
    find_lookahead_leaks,
    validate_no_lookahead,
    validate_rows_no_lookahead,
)


def _t(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# Prediction made at 2026-09-02 16:00:00 UTC (market close).
PRED_TS = _t("2026-09-02T16:00:00+00:00")


@pytest.fixture
def clean_features():
    """Features all available at or before the prediction timestamp."""
    return [
        {"name": "ohlcv_return_1m", "information_available_ts": _t("2026-09-02T15:59:00+00:00")},
        {"name": "options_put_call_ratio", "information_available_ts": _t("2026-09-02T00:36:00+00:00")},
        {"name": "sec_sentiment", "information_available_ts": _t("2026-09-01T12:03:00+00:00")},
        {"name": "cot_positioning", "information_available_ts": _t("2025-09-12T19:30:00+00:00")},
        {"name": "ohlcv_close", "information_available_ts": _t("2026-09-02T16:00:00+00:00")},  # == prediction_ts
    ]


@pytest.fixture
def leaking_features(clean_features):
    """A feature available only after the prediction timestamp (injected leak)."""
    return clean_features + [
        {"name": "future_quote", "information_available_ts": _t("2026-09-02T16:05:00+00:00")},
    ]


def test_no_lookahead_happy_path_passes(clean_features):
    validate_no_lookahead(clean_features, PRED_TS)


def test_boundary_equal_ts_is_allowed(clean_features):
    # The row at exactly prediction_ts must NOT be flagged (rule is <=).
    validate_no_lookahead(clean_features, PRED_TS)
    assert find_lookahead_leaks(
        [{"information_available_ts": PRED_TS, "prediction_ts": PRED_TS}]
    ) == []


def test_leak_guard_fires_on_injected_leaking_row(leaking_features):
    with pytest.raises(LookaheadLeakError):
        validate_no_lookahead(leaking_features, PRED_TS)


def test_find_lookahead_leaks_returns_only_leaking_row(leaking_features):
    leaks = find_lookahead_leaks(
        [{"information_available_ts": f["information_available_ts"],
          "prediction_ts": PRED_TS} for f in leaking_features]
    )
    assert len(leaks) == 1
    assert leaks[0]["information_available_ts"] == _t("2026-09-02T16:05:00+00:00")


def test_validate_rows_no_lookahead_counts_leaks(leaking_features):
    rows = [{"information_available_ts": f["information_available_ts"],
             "prediction_ts": PRED_TS} for f in leaking_features]
    assert validate_rows_no_lookahead(rows) == 1


def test_none_availability_is_ignored(clean_features):
    # A feature with no availability timestamp cannot leak.
    validate_no_lookahead(
        clean_features + [{"name": "no_ts", "information_available_ts": None}], PRED_TS
    )
