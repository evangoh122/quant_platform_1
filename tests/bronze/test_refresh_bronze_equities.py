"""
tests/bronze/test_refresh_bronze_equities.py

Self-contained tests for the pure parsing / key-selection helpers in
`notebooks/refresh_bronze_equities.py`.

The notebook is loaded via importlib (the `notebooks/` directory is not a
Python package) so no Databricks context is required. Importing the module
must not start a live ingestion: the pure helpers are module-level, while the
Spark / boto3 / dbutils runtime lives behind the `if __name__ == "__main__"`
guard in `main()`.
"""
import gzip
import io
import importlib.util
import csv
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


_NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_equities.py"
_SPEC = importlib.util.spec_from_file_location("refresh_bronze_equities", _NOTEBOOK)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

ns_to_ts = _MOD.ns_to_ts
as_float = _MOD.as_float
as_int = _MOD.as_int
parse_object_key_date = _MOD.parse_object_key_date
key_in_window = _MOD.key_in_window
parse_minute_file = _MOD.parse_minute_file
parse_day_file = _MOD.parse_day_file
KEY_COLUMNS = _MOD.KEY_COLUMNS
TICKERS = _MOD.TICKERS


def _gzip_csv(fieldnames, rows):
    """Encode a list of row dicts as a gzipped CSV byte stream (file-like)."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text_stream:
            writer = csv.DictWriter(text_stream, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    buf.seek(0)
    return buf


def test_import_has_no_side_effects():
    """Importing the notebook module must not touch Spark, boto3 or dbutils."""
    assert callable(_MOD.parse_minute_file)
    assert callable(_MOD.parse_day_file)
    assert hasattr(_MOD, "main")
    assert KEY_COLUMNS == ["symbol", "event_ts", "timespan"]


def test_ns_to_ts_epoch():
    assert ns_to_ts(0) == datetime(1970, 1, 1, 0, 0, 0)
    assert ns_to_ts(1_000_000_000) == datetime(1970, 1, 1, 0, 0, 1)


def test_ns_to_ts_is_naive_utc():
    ns = 1_756_000_000_000_000_000  # a known 2026 nanosecond timestamp
    result = ns_to_ts(ns)
    assert result is not None
    assert result.tzinfo is None  # naive UTC, as Spark expects


def test_ns_to_ts_bad_inputs():
    assert ns_to_ts(None) is None
    assert ns_to_ts("") is None
    assert ns_to_ts("not-a-number") is None


def test_as_float():
    assert as_float({"open": "1.5"}, "open") == 1.5
    assert as_float({"open": ""}, "open") is None
    assert as_float({"open": None}, "open") is None
    assert as_float({}, "open") is None


def test_as_int():
    assert as_int({"volume": "100"}, "volume") == 100
    assert as_int({"volume": "100.0"}, "volume") == 100
    assert as_int({"volume": ""}, "volume") is None
    assert as_int({}, "volume") is None


def test_parse_object_key_date():
    key = "us_stocks_sip/minute_aggs_v1/2026/09/2026-09-04.csv.gz"
    assert parse_object_key_date(key) == date(2026, 9, 4)
    assert parse_object_key_date("no-date-here.csv") is None
    assert parse_object_key_date("us_stocks_sip/minute_aggs_v1/2026/09/bad.csv.gz") is None


def test_key_in_window():
    start = date(2026, 9, 4)
    end = date(2026, 10, 3)
    assert key_in_window("us_stocks_sip/minute_aggs_v1/2026/09/2026-09-04.csv.gz", start, end)
    assert key_in_window("us_stocks_sip/minute_aggs_v1/2026/10/2026-10-03.csv.gz", start, end)
    assert not key_in_window("us_stocks_sip/minute_aggs_v1/2026/09/2026-09-03.csv.gz", start, end)
    assert not key_in_window("us_stocks_sip/minute_aggs_v1/2026/10/2026-10-04.csv.gz", start, end)
    assert not key_in_window("malformed", start, end)


def test_parse_minute_file_filters_universe_and_maps_fields():
    key = "us_stocks_sip/minute_aggs_v1/2026/09/2026-09-04.csv.gz"
    ingest_ts = datetime(2026, 10, 3, 12, 0, 0)
    body = _gzip_csv(
        ["ticker", "window_start", "open", "high", "low", "close", "volume", "vwap", "transactions"],
        [
            {"ticker": "AAPL", "window_start": "1759363200000000000", "open": "100", "high": "101",
             "low": "99", "close": "100.5", "volume": "1000", "vwap": "100.1", "transactions": "50"},
            {"ticker": "AAPL", "window_start": "1759363260000000000", "open": "101", "high": "102",
             "low": "100", "close": "101.5", "volume": "1100", "vwap": "101.1", "transactions": "51"},
            {"ticker": "MSFT", "window_start": "1759363200000000000", "open": "200", "high": "201",
             "low": "199", "close": "200.5", "volume": "2000", "vwap": "200.1", "transactions": "60"},
            {"ticker": "ZZZZ", "window_start": "1759363200000000000", "open": "1", "high": "1",
             "low": "1", "close": "1", "volume": "1", "vwap": "1", "transactions": "1"},
            {"ticker": "AAPL", "window_start": "", "open": "1", "high": "1",
             "low": "1", "close": "1", "volume": "1", "vwap": "1", "transactions": "1"},
        ],
    )

    rows = parse_minute_file(body, key, ingest_ts, TICKERS)

    symbols = sorted({r["symbol"] for r in rows})
    assert symbols == ["AAPL", "MSFT"]  # ZZZZ filtered; empty-ts row dropped
    assert len(rows) == 3

    aapl0 = next(r for r in rows if r["symbol"] == "AAPL" and r["trade_count"] == 50)
    assert aapl0["open"] == 100.0
    assert aapl0["volume"] == 1000
    assert aapl0["timespan"] == "minute"
    assert aapl0["source"] == "massive_flatfile"
    assert aapl0["source_file"] == key
    assert aapl0["ingest_ts"] == ingest_ts
    assert aapl0["event_ts"] == datetime.fromtimestamp(
        1759363200, tz=timezone.utc).replace(tzinfo=None)


def test_parse_day_file_is_full_market_and_derives_dates():
    key = "us_stocks_sip/day_aggs_v1/2026/09/2026-09-05.csv.gz"
    ingest_ts = datetime(2026, 10, 3, 12, 0, 0)
    body = _gzip_csv(
        ["ticker", "window_start", "open", "high", "low", "close", "volume", "vwap", "transactions"],
        [
            {"ticker": "AAPL", "window_start": "1759536000000000000", "open": "100", "high": "101",
             "low": "99", "close": "100.5", "volume": "1000", "vwap": "100.1", "transactions": "50"},
            {"ticker": "ZZZZ", "window_start": "1759536000000000000", "open": "1", "high": "1",
             "low": "1", "close": "1", "volume": "1", "vwap": "1", "transactions": "1"},
        ],
    )

    rows = parse_day_file(body, key, ingest_ts, tickers=None)

    # Full market: no universe filter, both tickers retained.
    assert sorted({r["symbol"] for r in rows}) == ["AAPL", "ZZZZ"]

    aapl = next(r for r in rows if r["symbol"] == "AAPL")
    assert aapl["timespan"] == "day"
    assert aapl["source"] == "massive_flatfile"
    assert aapl["source_file"] == key
    assert aapl["event_date"] == aapl["event_ts"].date()
    assert aapl["event_year"] == aapl["event_ts"].year
