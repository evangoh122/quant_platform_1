"""tests/agent/test_delta_adapter_ordering.py — r2: Spark orderBy before limit.

Verifies that the PySpark branches of the changed ``db/delta_adapter.py``
reads apply ``orderBy`` with a DESCENDING column matching the warehouse
fallback's ordering BEFORE ``.limit()``, so the two backends agree on which
rows survive the limit.

Each test calls the real production function with a recording Spark stub
(``_has_pyspark=True``, stubbed ``_spark()``) and asserts on the recorded
call chain — no production logic is copied here.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest


class _RecordingDF:
    """Stub DataFrame that records method call order (test infrastructure)."""

    def __init__(self, rows=None):
        self._calls: list[str] = []
        self._order_args: tuple = ()
        self._limit_n = None
        self._rows = rows or []

    def where(self, *a, **kw):
        self._calls.append("where")
        return self

    def select(self, *a, **kw):
        self._calls.append("select")
        return self

    def orderBy(self, *a, **kw):
        self._calls.append("orderBy")
        self._order_args = a
        return self

    def limit(self, n):
        self._calls.append("limit")
        self._limit_n = n
        return self

    def collect(self):
        self._calls.append("collect")
        return self._rows


def _assert_desc_order_before_limit(rec: _RecordingDF, expected_col: str, site: str) -> None:
    """orderBy on a DESCENDING expected column must happen before limit."""
    assert "orderBy" in rec._calls, f"{site}: Spark branch never applied orderBy before limit"
    assert "limit" in rec._calls, f"{site}: Spark branch never reached limit"
    order_idx = rec._calls.index("orderBy")
    limit_idx = rec._calls.index("limit")
    assert order_idx < limit_idx, (
        f"{site}: orderBy (index {order_idx}) must come before limit (index {limit_idx})"
    )
    assert rec._order_args, f"{site}: orderBy was called but no column was passed"
    col_str = str(rec._order_args[0])
    assert expected_col in col_str, (
        f"{site}: orderBy must order by {expected_col}, got: {col_str}"
    )
    assert re.search(r"\bDESC\b", col_str), (
        f"{site}: orderBy must be descending (newest first), got: {col_str}"
    )


def test_market_features_orders_event_date_desc_before_limit():
    """market_features PySpark branch: orderBy(event_date DESC) before limit.

    The warehouse fallback (_build_market_features_daily_query) orders
    ``event_date DESC``; the Spark branch must match or the two backends
    return different rows for the same limit.
    """
    rec = _RecordingDF()
    stub_spark = MagicMock()
    stub_spark.table.return_value = rec

    with patch("db.delta_adapter._has_pyspark", True), \
         patch("db.delta_adapter._spark", return_value=stub_spark):
        from db.delta_adapter import market_features
        market_features("AAPL", "2026-01-01", "2026-06-01", limit=100)

    _assert_desc_order_before_limit(rec, "event_date", "db.delta_adapter.market_features")


def test_read_analytics_table_orders_event_date_desc_before_limit():
    """read_analytics_table PySpark branch: orderBy(event_date DESC) before limit.

    Its warehouse fallback orders ``ORDER BY event_date DESC`` (bounded
    recent rows); the Spark branch must match.
    """
    rec = _RecordingDF()
    stub_spark = MagicMock()
    stub_spark.table.return_value = rec

    with patch("db.delta_adapter._has_pyspark", True), \
         patch("db.delta_adapter._spark", return_value=stub_spark):
        from db.delta_adapter import read_analytics_table
        read_analytics_table("usage_daily", limit=500)

    _assert_desc_order_before_limit(rec, "event_date", "db.delta_adapter.read_analytics_table")


def test_read_analytics_table_ordering_applies_to_all_sections():
    """Every analytics section goes through the same ordered limit."""
    for section in ("agent_activity", "watchlist_changes", "order_funnel",
                    "usage_daily", "model_performance", "latency",
                    "stream_freshness"):
        rec = _RecordingDF()
        stub_spark = MagicMock()
        stub_spark.table.return_value = rec

        with patch("db.delta_adapter._has_pyspark", True), \
             patch("db.delta_adapter._spark", return_value=stub_spark):
            from db.delta_adapter import read_analytics_table
            read_analytics_table(section, limit=500)

        _assert_desc_order_before_limit(rec, "event_date", f"read_analytics_table[{section}]")
