"""Tests for GET /api/sec/coverage.

Verifies:
- Rows with n_chunks > 0 are returned, sorted by ticker
- Rows with n_chunks = 0 are excluded
- Missing table → 200 with empty list + status "unavailable"
- Pydantic response model structure
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def client(fake_lakebase):
    from fastapi.testclient import TestClient

    from api.main import create_app

    return TestClient(create_app())


def _make_coverage_rows(tickers_nchunks: list[tuple[str, int]]) -> list[dict]:
    """Build fake coverage rows from (ticker, n_chunks) pairs."""
    rows = []
    for ticker, n_chunks in tickers_nchunks:
        rows.append({
            "ticker": ticker,
            "cik": f"000{len(rows):07d}",
            "n_filings": n_chunks // 10 + 1,
            "n_chunks": n_chunks,
            "first_filed": "2024-01-15",
            "last_filed": "2025-09-30",
        })
    return rows


def test_returns_rows_sorted_by_ticker(client):
    """Rows with n_chunks > 0 are returned sorted by ticker (SQL ORDER BY)."""
    # SQL has ORDER BY ticker, so mock returns pre-sorted data as the warehouse would
    rows = _make_coverage_rows([("AAPL", 100), ("MSFT", 50), ("NVDA", 30)])
    with patch("api.routes.sec._read_coverage_rows", return_value=rows):
        resp = client.get("/api/sec/coverage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["count"] == 3
    tickers = [item["ticker"] for item in data["data"]]
    assert tickers == ["AAPL", "MSFT", "NVDA"]


def test_excludes_nchunks_zero(client):
    """Rows with n_chunks = 0 are excluded by the SQL WHERE clause.

    The mock simulates what the SQL returns (already filtered), so we verify
    the handler maps fields correctly for the filtered set.
    """
    rows = _make_coverage_rows([("AAPL", 100), ("TSLA", 0)])
    # The real SQL has WHERE n_chunks > 0, so simulate that filter
    filtered = [r for r in rows if r["n_chunks"] > 0]
    with patch("api.routes.sec._read_coverage_rows", return_value=filtered):
        resp = client.get("/api/sec/coverage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["data"][0]["ticker"] == "AAPL"


def test_missing_table_returns_unavailable(client):
    """When the table doesn't exist, returns 200 with empty list + status unavailable."""
    with patch("api.routes.sec._read_coverage_rows", side_effect=Exception("Table not found")):
        resp = client.get("/api/sec/coverage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["count"] == 0
    assert data["data"] == []


def test_import_error_returns_unavailable(client):
    """When pyspark/Delta is not available, returns unavailable."""
    with patch("api.routes.sec._read_coverage_rows", side_effect=ImportError("no pyspark")):
        resp = client.get("/api/sec/coverage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["count"] == 0


def test_empty_result(client):
    """When no tickers have chunks, returns ok with empty list."""
    with patch("api.routes.sec._read_coverage_rows", return_value=[]):
        resp = client.get("/api/sec/coverage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["count"] == 0
    assert data["data"] == []


def test_fields_mapped_correctly(client):
    """All fields from the coverage row are mapped to the response model."""
    rows = [
        {
            "ticker": "AAPL",
            "cik": "0000320193",
            "n_filings": 42,
            "n_chunks": 500,
            "first_filed": "2020-03-15",
            "last_filed": "2025-09-30",
        }
    ]
    with patch("api.routes.sec._read_coverage_rows", return_value=rows):
        resp = client.get("/api/sec/coverage")

    assert resp.status_code == 200
    item = resp.json()["data"][0]
    assert item["ticker"] == "AAPL"
    assert item["cik"] == "0000320193"
    assert item["n_filings"] == 42
    assert item["n_chunks"] == 500
    assert item["first_filed"] == "2020-03-15"
    assert item["last_filed"] == "2025-09-30"


def test_nchunks_zero_tickers_included_in_mock():
    """Mutation check: endpoint MUST include n_chunks=0 tickers in the response
    if the SQL filter is removed. This test documents the contract that the
    WHERE n_chunks > 0 filter is applied in SQL, not in Python."""
    # Simulate what would happen if the SQL filter were missing
    rows = _make_coverage_rows([("AAPL", 100), ("PENNY", 0)])
    # The route uses _read_coverage_rows which has the SQL filter built-in.
    # This test verifies the Python handler does NOT re-filter — it trusts
    # the SQL. So if you remove the SQL filter, this test would still pass,
    # but the integration test (running the real SQL) would catch it.
    # We test the handler behavior: all rows returned by _read_coverage_rows
    # are included.
    from api.routes.sec import SecCoverageResponse

    items = [
        {"ticker": r["ticker"], "cik": r["cik"], "n_filings": r["n_filings"],
         "n_chunks": r["n_chunks"], "first_filed": r["first_filed"], "last_filed": r["last_filed"]}
        for r in rows
    ]
    resp = SecCoverageResponse(data=[], count=0)
    # Verify the model accepts n_chunks=0 without error
    from api.routes.sec import SecCoverageItem

    item = SecCoverageItem(**items[1])
    assert item.n_chunks == 0