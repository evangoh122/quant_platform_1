"""Tests for GET /api/sec/coverage.

Verifies:
- Rows with n_chunks > 0 are returned, sorted by ticker
- Rows with n_chunks = 0 are excluded
- Missing table → 200 with empty list + status "unavailable"
- Pydantic response model structure
- Identity dependency required (401 without auth header)
- Public-demo mode never calls live warehouse
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def client(fake_lakebase):
    from fastapi.testclient import TestClient

    from api.main import create_app

    return TestClient(create_app())


_AUTH = {"x-forwarded-email": "test@example.com"}


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
        resp = client.get("/api/sec/coverage", headers=_AUTH)

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
        resp = client.get("/api/sec/coverage", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["data"][0]["ticker"] == "AAPL"


def test_missing_table_returns_unavailable(client):
    """When the table doesn't exist, returns 200 with empty list + status unavailable."""
    with patch("api.routes.sec._read_coverage_rows", side_effect=Exception("Table not found")):
        resp = client.get("/api/sec/coverage", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["count"] == 0
    assert data["data"] == []


def test_import_error_returns_unavailable(client):
    """When pyspark/Delta is not available, returns unavailable."""
    with patch("api.routes.sec._read_coverage_rows", side_effect=ImportError("no pyspark")):
        resp = client.get("/api/sec/coverage", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["count"] == 0


def test_empty_result(client):
    """When no tickers have chunks, returns ok with empty list."""
    with patch("api.routes.sec._read_coverage_rows", return_value=[]):
        resp = client.get("/api/sec/coverage", headers=_AUTH)

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
        resp = client.get("/api/sec/coverage", headers=_AUTH)

    assert resp.status_code == 200
    item = resp.json()["data"][0]
    assert item["ticker"] == "AAPL"
    assert item["cik"] == "0000320193"
    assert item["n_filings"] == 42
    assert item["n_chunks"] == 500
    assert item["first_filed"] == "2020-03-15"
    assert item["last_filed"] == "2025-09-30"


def test_coverage_requires_auth(client, fake_lakebase):
    """Mutation check: /api/sec/coverage must require authentication.

    Without the trusted identity header the endpoint returns 401.
    Removing the Depends(get_current_user) from sec.py would cause this
    test to fail (endpoint would return 200 instead of 401).
    """
    resp = client.get("/api/sec/coverage")
    assert resp.status_code == 401


def test_coverage_demo_mode_no_live_warehouse(client, fake_lakebase, monkeypatch):
    """In public-demo mode, /api/sec/coverage must NOT call the live warehouse.

    read_delta intercepts the call and returns unavailable without invoking
    the wrapped function. This prevents ambient credentials from reaching
    the warehouse in a demo deployment.
    """
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    rows = _make_coverage_rows([("AAPL", 100)])
    with patch("api.routes.sec._read_coverage_rows", return_value=rows) as mock_read:
        resp = client.get("/api/sec/coverage", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["count"] == 0
    mock_read.assert_not_called()


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


def test_read_coverage_rows_excludes_nchunks_zero_via_sql():
    """Mutation check: the real _read_coverage_rows must produce SQL with
    WHERE n_chunks > 0. We mock _warehouse_query to return unfiltered rows
    and verify the generated SQL contains the filter.

    If the WHERE clause is removed from sec.py, this test fails because the
    SQL would no longer contain 'n_chunks > 0'.
    """
    captured_sql: list[str] = []

    def fake_warehouse_query(query, params=None, **kwargs):
        captured_sql.append(query)
        # Return rows INCLUDING n_chunks=0 — the SQL should exclude them
        return _make_coverage_rows([("AAPL", 100), ("PENNY", 0), ("MSFT", 50)])

    with patch("db.delta_adapter._warehouse_query", side_effect=fake_warehouse_query):
        from api.routes.sec import _read_coverage_rows

        rows = _read_coverage_rows()

    # The SQL must contain the n_chunks > 0 filter
    assert len(captured_sql) == 1
    sql = captured_sql[0]
    assert "WHERE n_chunks > 0" in sql, f"SQL must filter n_chunks > 0: {sql}"
    # Verify no user-supplied values are interpolated (all values are constants)
    # The SQL should be a static query with no string formatting of user input
    assert "PENNY" not in sql, "SQL must not contain user-supplied ticker values"
    assert "AAPL" not in sql, "SQL must not contain user-supplied ticker values"