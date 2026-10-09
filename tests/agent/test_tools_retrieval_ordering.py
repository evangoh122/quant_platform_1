"""tests/agent/test_tools_retrieval_ordering.py — Fix 1: Spark orderBy before limit.

Verifies that the PySpark branches of ``get_options_features`` and
``get_cot_positioning`` apply ``orderBy(...desc())`` BEFORE ``.limit()`` so
that the newest rows are returned deterministically.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest


class _RecordingDF:
    """Stub DataFrame that records method call order."""

    def __init__(self):
        self._calls: list[str] = []
        self._rows = []

    def where(self, *a, **kw):
        self._calls.append("where")
        return self

    def select(self, *a, **kw):
        self._calls.append("select")
        return self

    def orderBy(self, *a, **kw):
        self._calls.append("orderBy")
        self._order_col = a[0] if a else None
        return self

    def limit(self, n):
        self._calls.append("limit")
        self._limit_n = n
        return self

    def collect(self):
        self._calls.append("collect")
        return self._rows

    def asDict(self):
        return {}


def test_orderBy_called_before_limit():
    """orderBy must appear before limit in the call chain."""
    rec = _RecordingDF()
    stub_spark = MagicMock()
    stub_spark.table.return_value = rec

    with patch("db.delta_adapter._has_pyspark", True), \
         patch("agent.tools_retrieval._spark", return_value=stub_spark), \
         patch("db.delta_adapter._fqn", return_value="cat.schema.gold_options_features"), \
         patch("agent.guardrails.normalize_symbol", side_effect=lambda s: s):
        from agent.tools_retrieval import get_options_features
        get_options_features("AAPL", limit=100)

    order_idx = rec._calls.index("orderBy")
    limit_idx = rec._calls.index("limit")
    assert order_idx < limit_idx, (
        f"orderBy (index {order_idx}) must come before limit (index {limit_idx})"
    )


def test_orderBy_uses_feature_ts_desc():
    """orderBy must use feature_ts descending (newest first)."""
    rec = _RecordingDF()
    stub_spark = MagicMock()
    stub_spark.table.return_value = rec

    with patch("db.delta_adapter._has_pyspark", True), \
         patch("agent.tools_retrieval._spark", return_value=stub_spark), \
         patch("db.delta_adapter._fqn", return_value="cat.schema.gold_options_features"), \
         patch("agent.guardrails.normalize_symbol", side_effect=lambda s: s):
        from agent.tools_retrieval import get_options_features
        get_options_features("AAPL", limit=50)

    assert rec._order_col is not None, "orderBy was called but no column was passed"
    col_str = str(rec._order_col)
    assert "feature_ts" in col_str, f"orderBy column should reference feature_ts, got: {col_str}"


def test_shuffled_rows_returned_newest_first_when_ordered():
    """Behavioral: with orderBy, the stub returns rows in the ordered sequence.
    Without orderBy, the stub returns shuffled rows (simulating nondeterminism)."""

    class OrderedDF:
        """Returns rows only when orderBy has been called before limit."""
        def __init__(self):
            self._ordered = False
            self._rows = [
                MagicMock(asDict=lambda: {"feature_ts": "2026-01-03", "symbol": "AAPL"}),
                MagicMock(asDict=lambda: {"feature_ts": "2026-01-02", "symbol": "AAPL"}),
                MagicMock(asDict=lambda: {"feature_ts": "2026-01-01", "symbol": "AAPL"}),
            ]

        def where(self, *a, **kw):
            return self

        def select(self, *a, **kw):
            return self

        def orderBy(self, *a, **kw):
            self._ordered = True
            return self

        def limit(self, n):
            if not self._ordered:
                return MagicMock(collect=lambda: list(reversed(self._rows[:n])))
            return MagicMock(collect=lambda: self._rows[:n])

    odf = OrderedDF()
    stub_spark = MagicMock()
    stub_spark.table.return_value = odf

    with patch("db.delta_adapter._has_pyspark", True), \
         patch("agent.tools_retrieval._spark", return_value=stub_spark), \
         patch("db.delta_adapter._fqn", return_value="cat.schema.gold_options_features"), \
         patch("agent.guardrails.normalize_symbol", side_effect=lambda s: s):
        from agent.tools_retrieval import get_options_features
        result = get_options_features("AAPL", limit=2)

    assert result[0]["feature_ts"] == "2026-01-03"
    assert result[1]["feature_ts"] == "2026-01-02"


# ——— r2: get_cot_positioning (single-row .limit(1) lookup) ————————————


def test_cot_positioning_orders_report_date_desc_before_limit():
    """get_cot_positioning PySpark branch: orderBy(report_date DESC) before limit(1).

    A .limit(1) over a time series is nondeterministic without ordering; the
    warehouse path (_build_cot_query) orders ``report_date DESC``, so the
    Spark branch must return the same (newest) row.
    """
    rec = _RecordingDF()
    stub_spark = MagicMock()
    stub_spark.table.return_value = rec

    with patch("db.delta_adapter._has_pyspark", True), \
         patch("agent.tools_retrieval._spark", return_value=stub_spark):
        from agent.tools_retrieval import get_cot_positioning
        get_cot_positioning("equity_index")

    assert "orderBy" in rec._calls, (
        "get_cot_positioning Spark branch never applied orderBy before limit"
    )
    assert "limit" in rec._calls, "get_cot_positioning Spark branch never reached limit"
    order_idx = rec._calls.index("orderBy")
    limit_idx = rec._calls.index("limit")
    assert order_idx < limit_idx, (
        f"orderBy (index {order_idx}) must come before limit (index {limit_idx})"
    )
    assert rec._order_col is not None, "orderBy was called but no column was passed"
    col_str = str(rec._order_col)
    assert "report_date" in col_str, f"orderBy column should reference report_date, got: {col_str}"
    assert re.search(r"\bDESC\b", col_str), (
        f"orderBy must be descending (newest report first), got: {col_str}"
    )


def test_cot_query_orders_report_date_desc():
    """The warehouse COT query must order report_date DESC (mirrors the Spark
    branch and makes the single-row lookup deterministic on both backends)."""
    from agent.tools_retrieval import _build_cot_query

    sql, params = _build_cot_query("rate")
    assert "ORDER BY" in sql, f"Missing ORDER BY in COT query: {sql}"
    order_clause = sql.split("ORDER BY", 1)[1]
    assert "report_date" in order_clause, f"ORDER BY must include report_date: {sql}"
    assert "DESC" in order_clause.upper(), f"ORDER BY must be DESC: {sql}"
    assert params == {"mapped_asset": "rate"}
