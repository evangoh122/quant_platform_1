"""Unit tests for the streaming bundle's pure helpers.

Covers the three correctness-critical helpers the build request calls out: the dedup
key, the availability timestamp, and the quarantine reason.
"""

from datetime import datetime, timezone

import pytest

from pipelines.streaming import helpers


def _valid_bar(**overrides):
    bar = {
        "symbol": "AAPL",
        "event_ts": "2024-01-02T00:00:00Z",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000.0,
        "vwap": 100.4,
        "trade_count": 42,
        "timespan": "minute",
    }
    bar.update(overrides)
    return bar


# ── dedup key ─────────────────────────────────────────────────────────────────

def test_dedup_hash_is_deterministic_and_case_normalised():
    a = helpers.dedup_hash("AAPL", "2024-01-02T00:00:00Z", "minute")
    b = helpers.dedup_hash("aapl", "2024-01-02T00:00:00+00:00", "MINUTE")
    assert a == b
    assert len(a) == 64


def test_dedup_hash_is_sensitive_to_each_key_field():
    base = helpers.dedup_hash("AAPL", "2024-01-02T00:00:00Z", "minute")
    assert base != helpers.dedup_hash("MSFT", "2024-01-02T00:00:00Z", "minute")
    assert base != helpers.dedup_hash("AAPL", "2024-01-02T00:01:00Z", "minute")
    assert base != helpers.dedup_hash("AAPL", "2024-01-02T00:00:00Z", "hour")


def test_safe_dedup_hash_returns_none_instead_of_raising():
    assert helpers.safe_dedup_hash("AAPL", "2024-01-02T00:00:00Z", "minute") is not None
    assert helpers.safe_dedup_hash(None, "2024-01-02T00:00:00Z", "minute") is None
    assert helpers.safe_dedup_hash("AAPL", "not-a-ts", "minute") is None
    # An unsupported timespan still gets a deterministic id; Silver rejects it via
    # validate_bar's unsupported_timespan reason (mirrors the batch layer).
    assert helpers.safe_dedup_hash("AAPL", "2024-01-02T00:00:00Z", "7m") is not None


def test_business_key_fields_are_symbol_event_ts_timespan():
    assert helpers.BUSINESS_KEY_FIELDS == ("symbol", "event_ts", "timespan")


# ── availability timestamp ────────────────────────────────────────────────────

def test_information_available_ts_is_event_ts_plus_bar_interval():
    # Minute bar stamped at start: known only at start + 60s.
    got = helpers.derive_information_available_ts("2024-01-02T00:00:00Z", "minute")
    assert got == datetime(2024, 1, 2, 0, 1, tzinfo=timezone.utc)


def test_information_available_ts_supports_hour_and_day():
    assert helpers.derive_information_available_ts("2024-01-02T00:00:00Z", "hour") == datetime(
        2024, 1, 2, 1, 0, tzinfo=timezone.utc
    )
    assert helpers.derive_information_available_ts("2024-01-02T00:00:00Z", "day") == datetime(
        2024, 1, 3, 0, 0, tzinfo=timezone.utc
    )


def test_safe_information_available_ts_returns_none_instead_of_raising():
    assert helpers.safe_derive_information_available_ts("2024-01-02T00:00:00Z", "minute") is not None
    assert helpers.safe_derive_information_available_ts(None, "minute") is None
    assert helpers.safe_derive_information_available_ts("bad-ts", "minute") is None
    assert helpers.safe_derive_information_available_ts("2024-01-02T00:00:00Z", "7m") is None


def test_interval_seconds_supports_minute_hour_day():
    assert helpers.interval_seconds("minute") == 60
    assert helpers.interval_seconds("hour") == 3600
    assert helpers.interval_seconds("day") == 86400
    with pytest.raises(ValueError):
        helpers.interval_seconds("week")


# ── quarantine reason ─────────────────────────────────────────────────────────

def test_validate_bar_accepts_well_formed_bar():
    assert helpers.validate_bar(_valid_bar()) == []
    assert helpers.is_valid_bar(_valid_bar()) is True


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"symbol": None}, "missing_symbol"),
        ({"event_ts": "not-a-ts"}, "invalid_event_ts"),
        ({"timespan": "week"}, "unsupported_timespan"),
        ({"high": 98.0}, "high_below_components"),
        ({"low": 102.0}, "low_above_components"),
        ({"volume": -1.0}, "negative_volume"),
        ({"trade_count": -3}, "negative_trade_count"),
        ({"close": "nan"}, "invalid_close"),
        ({"vwap": 200.0}, "vwap_out_of_range"),
    ],
)
def test_validate_bar_reports_expected_reason(overrides, expected):
    reasons = helpers.validate_bar(_valid_bar(**overrides))
    assert expected in reasons


def test_validate_bar_reasons_are_sorted_and_deduplicated():
    reasons = helpers.validate_bar(_valid_bar(symbol="", timespan="", event_ts="bad"))
    assert reasons == sorted(reasons)
    assert len(reasons) == len(set(reasons))


def test_real_table_names_never_collide_with_dlt_prefix():
    for name in helpers.REAL_TABLE_NAMES:
        assert not name.startswith("dlt_")
