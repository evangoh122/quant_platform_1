"""
tests/bronze/test_refresh_bronze_options.py
Bronze options refresh (lane `options`): pure parsing / key-selection helpers.

These tests exercise only the pure, import-safe helpers in
``notebooks/refresh_bronze_options.py`` — no Spark, no S3, no Databricks, no
live ingestion. The notebook guards all live work under ``main()`` so importing
it here does not start any ingestion.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from notebooks import refresh_bronze_options as m


# ---------------------------------------------------------------------------
# OPRA symbol parsing
# ---------------------------------------------------------------------------

def test_parse_opra_symbol_call():
    underlying, expiry, right, strike = m.parse_opra_symbol(
        "O:AAPL250117C00200000"
    )
    assert underlying == "AAPL"
    assert expiry.isoformat() == "2025-01-17"
    assert right == "CALL"
    assert strike == 200.0


def test_parse_opra_symbol_put():
    underlying, expiry, right, strike = m.parse_opra_symbol(
        "O:SPY251219P00430000"
    )
    assert underlying == "SPY"
    assert expiry.isoformat() == "2025-12-19"
    assert right == "PUT"
    assert strike == 430.0


def test_parse_opra_symbol_rejects_malformed():
    for bad in [
        "",
        None,
        "AAPL250117C00200000",          # missing O: prefix
        "O:AAPL250117X00200000",        # bad right letter
        "O:AAPL25C00200000",            # bad expiry width
        "O:AAPL250117C00",              # bad strike width
        "O:250117C00200000",            # missing underlying
    ]:
        assert m.parse_opra_symbol(bad) is None


def test_parse_opra_symbol_rejects_bad_expiry():
    # 99 is not a valid month -> strptime raises -> None
    assert m.parse_opra_symbol("O:AAPL259917C00200000") is None


# ---------------------------------------------------------------------------
# Field conversion helpers
# ---------------------------------------------------------------------------

def test_ns_to_ts():
    # 1_700_000_000_000_000_000 ns == 2023-11-14T22:13:20Z
    ts = m.ns_to_ts(1_700_000_000_000_000_000)
    assert ts == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_ns_to_ts_nulls_and_garbage():
    assert m.ns_to_ts(None) is None
    assert m.ns_to_ts("") is None
    assert m.ns_to_ts("not-a-number") is None


def test_as_float():
    assert m.as_float("3.14") == 3.14
    assert m.as_float(5) == 5.0
    assert m.as_float(None) is None
    assert m.as_float("") is None
    assert m.as_float("n/a") is None


def test_as_int():
    assert m.as_int("42") == 42
    assert m.as_int("42.9") == 42
    assert m.as_int(None) is None
    assert m.as_int("") is None
    assert m.as_int("abc") is None


# ---------------------------------------------------------------------------
# Date window discovery + S3 key layout
# ---------------------------------------------------------------------------

def test_date_window_inclusive():
    assert m.date_window("2026-09-05", "2026-09-07") == [
        "2026-09-05", "2026-09-06", "2026-09-07",
    ]


def test_date_window_single_day():
    assert m.date_window("2026-09-05", "2026-09-05") == ["2026-09-05"]


def test_date_window_rejects_reversed():
    with pytest.raises(ValueError):
        m.date_window("2026-10-03", "2026-09-05")


def test_s3_key_for_date():
    assert m.s3_key_for_date("2026-09-05") == (
        "us_options_opra/day_aggs_v1/2026/09/2026-09-05.csv.gz"
    )


# ---------------------------------------------------------------------------
# Natural-key columns match the plan
# ---------------------------------------------------------------------------

def test_day_key_columns():
    assert m.DAY_KEY_COLUMNS == ["contract_symbol", "event_ts", "timespan"]


def test_snapshot_key_columns():
    assert m.SNAPSHOT_KEY_COLUMNS == ["option_symbol", "participant_ts"]


# ---------------------------------------------------------------------------
# Snapshot timestamp resolution
# ---------------------------------------------------------------------------

def test_resolve_snapshot_ts_prefers_provider():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    provider = datetime(2026, 10, 3, 15, 59, 58, tzinfo=timezone.utc)
    assert m.resolve_snapshot_ts(provider, snap_ts) == provider


def test_resolve_snapshot_ts_falls_back():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    assert m.resolve_snapshot_ts(None, snap_ts) == snap_ts


# ---------------------------------------------------------------------------
# Snapshot row mapping (shape_quote_row)
# ---------------------------------------------------------------------------

def _make_snapshot(contract_type="call", sip_timestamp=None):
    snap = MagicMock()
    snap.details = MagicMock()
    snap.details.ticker = "O:SPY261218C00600000"
    snap.details.expiration_date = "2026-12-18"
    snap.details.strike_price = 600.0
    snap.details.contract_type = contract_type

    snap.last_quote = MagicMock()
    snap.last_quote.bid = 10.0
    snap.last_quote.ask = 10.5
    snap.last_quote.bid_size = 12
    snap.last_quote.ask_size = 34
    snap.last_quote.midpoint = None
    snap.last_quote.sip_timestamp = sip_timestamp
    snap.last_quote.participant_timestamp = None

    snap.greeks = MagicMock()
    snap.greeks.delta = 0.6
    snap.greeks.gamma = 0.01
    snap.greeks.theta = -0.2
    snap.greeks.vega = 0.3

    snap.last_trade = MagicMock()
    snap.last_trade.price = 10.25
    snap.day = MagicMock()
    snap.day.volume = 500
    snap.open_interest = 1234
    snap.implied_volatility = 0.35
    return snap


def test_shape_quote_row_full():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    row = m.shape_quote_row(_make_snapshot(), "SPY", snap_ts)
    assert row is not None
    assert row["option_symbol"] == "O:SPY261218C00600000"
    assert row["underlying"] == "SPY"
    assert row["expiry"] == "2026-12-18"
    assert row["strike"] == 600.0
    assert row["right"] == "C"
    assert row["midpoint"] == 10.25  # (10.0 + 10.5) / 2
    assert row["delta"] == 0.6
    assert row["gamma"] == 0.01
    assert row["theta"] == -0.2
    assert row["vega"] == 0.3
    assert row["implied_volatility"] == 0.35
    assert row["open_interest"] == 1234.0
    assert row["volume"] == 500
    assert row["last_price"] == 10.25
    assert row["source"] == "polygon"


def test_shape_quote_row_right_put():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    row = m.shape_quote_row(_make_snapshot(contract_type="put"), "SPY", snap_ts)
    assert row["right"] == "P"


def test_shape_quote_row_uses_provider_ts():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    # 1_700_000_000_000_000_000 ns == 2023-11-14T22:13:20Z
    row = m.shape_quote_row(
        _make_snapshot(sip_timestamp=1_700_000_000_000_000_000), "SPY", snap_ts
    )
    assert row["participant_ts"] == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
    )


def test_shape_quote_row_falls_back_to_snapshot_ts():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    row = m.shape_quote_row(_make_snapshot(sip_timestamp=None), "SPY", snap_ts)
    assert row["participant_ts"] == snap_ts


def test_shape_quote_row_no_symbol_returns_none():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    snap = _make_snapshot()
    snap.details = None
    assert m.shape_quote_row(snap, "SPY", snap_ts) is None


def test_shape_quote_row_right_normalisation():
    assert m._right_from_contract_type("call") == "C"
    assert m._right_from_contract_type("CALL") == "C"
    assert m._right_from_contract_type("put") == "P"
    assert m._right_from_contract_type("P") == "P"
    assert m._right_from_contract_type("weird") is None
    assert m._right_from_contract_type(None) is None
