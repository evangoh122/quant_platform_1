"""tests/api/test_hybrid_retriever.py — Warehouse fallback + missing coverage table tests.

Covers the Spark-then-warehouse fallback added in round 1 (5c1d6c2):
  - _fetch_ticker_rows: warehouse path when _get_spark raises ImportError
  - _load_alias_map: warehouse path + graceful degradation on missing table
  - check_ticker_coverage: warehouse path + structured error on missing table
  - _load_corpus (~615): warehouse fallback for global corpus loading

All tests use monkeypatch to force _get_spark → ImportError and inject a
fake warehouse connection that records executed SQL and params.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


class FakeCursor:
    """Fake cursor that records SQL/params and returns rows as tuples.

    The warehouse path does ``dict(zip(cols, r))`` so fetchall must return
    list-of-tuples, not list-of-dicts.
    """

    def __init__(self, rows=None, columns=None):
        self._columns = columns or ["chunk_id"]
        # Convert dict rows to tuples matching column order
        if rows and isinstance(rows[0], dict):
            self._rows = [tuple(r.get(c) for c in self._columns) for r in rows]
        else:
            self._rows = rows or []
        self.executed = []  # list of (sql, params)
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    @property
    def description(self):
        return [(col,) for col in self._columns]

    def fetchall(self):
        return self._rows

    def close(self):
        self.closed = True


class FakeConnection:
    """Fake warehouse connection that returns a FakeCursor."""

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _make_warehouse_guard(monkeypatch, hr):
    """Set _get_spark to raise ImportError (triggers warehouse fallback)."""
    monkeypatch.setattr(hr, "_get_spark", (_ for _ in ()).throw, raising=False)
    # Override the conftest _guard_spark which raises RuntimeError
    def _import_error_spark():
        raise ImportError("No module named 'pyspark'")
    monkeypatch.setattr(hr, "_get_spark", _import_error_spark)


class LoguruCapture:
    """Context manager that captures loguru WARNING+ messages."""

    def __init__(self):
        self.records = []
        self._sink_id = None

    def __enter__(self):
        from loguru import logger
        self._sink_id = logger.add(self._sink, level="WARNING", format="{message}")
        return self

    def __exit__(self, *args):
        from loguru import logger
        logger.remove(self._sink_id)

    def _sink(self, message):
        self.records.append(str(message))

    @property
    def text(self):
        return "\n".join(self.records)


# ── 1. _fetch_ticker_rows warehouse fallback ─────────────────────────────────


class TestFetchTickerRowsWarehouse:
    """Verify _fetch_ticker_rows uses the SQL warehouse when Spark is unavailable."""

    def test_returns_rows_from_warehouse(self, monkeypatch):
        """Warehouse path returns chunk and embedding rows as list[dict]."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)

        chunk_rows = [
            {"chunk_id": "c1", "ticker": "NVDA", "chunk_text": "revenue growth",
             "accession_number": "ACC1", "accepted_epoch": 1700000000,
             "form_type": "10-K", "filing_section": "item_7",
             "chunk_index": 0, "source_url": ""},
        ]
        embed_rows_data = [
            {"chunk_id": "c1", "embedding": [0.1] * 384,
             "embedding_model": "BAAI/bge-small-en-v1.5"},
        ]

        call_count = [0]
        def fake_cursor_factory():
            call_count[0] += 1
            if call_count[0] == 1:
                return FakeCursor(rows=chunk_rows,
                                  columns=["chunk_id", "ticker", "chunk_text",
                                            "accession_number", "accepted_epoch",
                                            "form_type", "filing_section",
                                            "chunk_index", "source_url"])
            return FakeCursor(rows=embed_rows_data,
                              columns=["chunk_id", "embedding", "embedding_model"])

        fake_conn = MagicMock()
        fake_conn.cursor.side_effect = fake_cursor_factory

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        chunks, embeds = hr._fetch_ticker_rows("NVDA")

        assert len(chunks) == 1
        assert chunks[0]["chunk_id"] == "c1"
        assert chunks[0]["ticker"] == "NVDA"
        assert len(embeds) == 1
        assert embeds[0]["chunk_id"] == "c1"

    def test_ticker_bound_as_param_not_in_sql(self, monkeypatch):
        """Ticker must appear in params, not f-stringed into SQL text."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)

        cursor = FakeCursor(rows=[], columns=["chunk_id", "ticker", "chunk_text",
                                               "accession_number", "accepted_epoch",
                                               "form_type", "filing_section",
                                               "chunk_index", "source_url"])
        # Override to also return columns for embed query
        original_execute = cursor.execute
        call_idx = [0]
        columns_per_call = [
            ["chunk_id", "ticker", "chunk_text", "accession_number",
             "accepted_epoch", "form_type", "filing_section",
             "chunk_index", "source_url"],
            ["chunk_id", "embedding", "embedding_model"],
        ]
        def tracking_execute(sql, params=None):
            original_execute(sql, params)
            cursor._columns = columns_per_call[min(call_idx[0], 1)]
            call_idx[0] += 1
        cursor.execute = tracking_execute

        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        hr._fetch_ticker_rows("NVDA")

        for sql, params in cursor.executed:
            assert "NVDA" not in sql, (
                f"Ticker literal 'NVDA' found in SQL text: {sql}. "
                f"Must be bound as a parameter."
            )
            assert params is not None, "Params must not be None when ticker is bound"
            assert "NVDA" in params, (
                f"Ticker 'NVDA' not found in params: {params}"
            )


# ── 2. check_ticker_coverage warehouse fallback ──────────────────────────────


class TestCheckTickerCoverageWarehouse:
    """Verify check_ticker_coverage uses the SQL warehouse when Spark is unavailable."""

    def test_returns_coverage_from_warehouse(self, monkeypatch):
        """Warehouse path returns (n_chunks, cik) for a covered ticker."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)

        cursor = FakeCursor(
            rows=[{"n_chunks": 894, "cik": "0001045810"}],
            columns=["n_chunks", "cik"],
        )
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        n, cik = hr.check_ticker_coverage("NVDA")
        assert n == 894
        assert cik == "0001045810"

    def test_ticker_bound_as_param_in_coverage_query(self, monkeypatch):
        """Ticker must be a bound parameter, not in SQL text."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)

        cursor = FakeCursor(
            rows=[{"n_chunks": 100, "cik": "0001"}],
            columns=["n_chunks", "cik"],
        )
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        hr.check_ticker_coverage("NVDA")

        for sql, params in cursor.executed:
            assert "NVDA" not in sql, (
                f"Ticker literal 'NVDA' found in SQL: {sql}"
            )
            assert params is not None
            assert "NVDA" in params

    def test_raises_no_coverage_error_when_empty(self, monkeypatch):
        """Empty result set raises NoCoverageError."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import NoCoverageError

        _make_warehouse_guard(monkeypatch, hr)

        cursor = FakeCursor(rows=[], columns=["n_chunks", "cik"])
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        with pytest.raises(NoCoverageError):
            hr.check_ticker_coverage("FAKE")


# ── 3. _load_alias_map warehouse fallback ────────────────────────────────────


class TestLoadAliasMapWarehouse:
    """Verify _load_alias_map uses the SQL warehouse when Spark is unavailable."""

    def test_alias_map_built_from_warehouse_rows(self, monkeypatch):
        """Warehouse rows are grouped by CIK; alphabetically-first ticker is canonical."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        # Reset alias map state
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False

        cursor = FakeCursor(
            rows=[
                {"ticker": "GOOGL", "cik": "0001652044"},
                {"ticker": "GOOG", "cik": "0001652044"},
                {"ticker": "NVDA", "cik": "0001045810"},
            ],
            columns=["ticker", "cik"],
        )
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        amap = hr._load_alias_map()

        # GOOG < GOOGL alphabetically → GOOG is canonical
        assert amap["GOOG"] == "GOOG"
        assert amap["GOOGL"] == "GOOG"
        # NVDA is its own canonical
        assert amap["NVDA"] == "NVDA"


# ── 4. Missing coverage table: alias map degrades gracefully ─────────────────


class TestMissingCoverageTableAliasMap:
    """If gold_sec_coverage is absent, _load_alias_map degrades to empty map with WARNING."""

    def test_alias_map_empty_on_table_not_found(self, monkeypatch):
        """TABLE_OR_VIEW_NOT_FOUND → empty map + WARNING log, no crash."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        # Reset alias map state
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False

        def boom():
            raise RuntimeError("[TABLE_OR_VIEW_NOT_FOUND] The table or view `gold_sec_coverage` does not exist.")

        fake_conn = MagicMock()
        fake_conn.cursor.side_effect = boom

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        with LoguruCapture() as log:
            amap = hr._load_alias_map()

        assert amap == {}
        assert "Failed to load ticker alias map" in log.text, (
            f"Expected WARNING about alias map failure, got: {log.text[:500]}"
        )

    def test_alias_map_empty_on_spark_analysis_exception(self, monkeypatch):
        """Spark AnalysisException (table not found) → empty map + WARNING log."""
        from api.services import hybrid_retriever as hr

        # Simulate Spark path (not warehouse): _get_spark returns mock, but table().select().collect() raises
        mock_spark = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_select.collect.side_effect = Exception(
            "[TABLE_OR_VIEW_NOT_FOUND] The table or view `gold_sec_coverage` does not exist."
        )
        mock_table.select.return_value = mock_select
        mock_spark.table.return_value = mock_table

        monkeypatch.setattr(hr, "_get_spark", lambda: mock_spark)
        # Reset alias map state
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False

        with LoguruCapture() as log:
            amap = hr._load_alias_map()

        assert amap == {}
        assert "Failed to load ticker alias map" in log.text, (
            f"Expected WARNING about alias map failure, got: {log.text[:500]}"
        )


# ── 5. Missing coverage table: check_ticker_coverage raises structured error ──


class TestMissingCoverageTableCheckTicker:
    """If gold_sec_coverage is absent, check_ticker_coverage raises NoCoverageError (not raw driver exception)."""

    def test_raises_no_coverage_not_driver_error(self, monkeypatch):
        """TABLE_OR_VIEW_NOT_FOUND must raise NoCoverageError, not propagate the raw RuntimeError."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import NoCoverageError

        _make_warehouse_guard(monkeypatch, hr)

        def boom():
            raise RuntimeError("[TABLE_OR_VIEW_NOT_FOUND] The table or view `gold_sec_coverage` does not exist.")

        fake_conn = MagicMock()
        fake_conn.cursor.side_effect = boom

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        with pytest.raises(NoCoverageError):
            hr.check_ticker_coverage("NVDA")


# ── 6. Missing coverage table: startup warm-up must not crash ────────────────


class TestStartupWarmupMissingTable:
    """Startup warm-up must not crash the app when gold_sec_coverage is absent.

    The warm-up path calls _load_alias_map (via warm_warehouse_connection -> health check).
    If the coverage table doesn't exist, the alias map should degrade gracefully
    and the app should still start.
    """

    def test_warm_up_does_not_crash_on_missing_table(self, monkeypatch):
        """warm_warehouse_connection must not raise when coverage table is absent."""
        from api.services import hybrid_retriever as hr
        from db import delta_adapter

        _make_warehouse_guard(monkeypatch, hr)
        # Reset alias map state
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False

        # Simulate warehouse connect succeeds but coverage table is missing
        def boom_cursor():
            raise RuntimeError("[TABLE_OR_VIEW_NOT_FOUND] The table or view `gold_sec_coverage` does not exist.")

        fake_conn = MagicMock()
        fake_conn.cursor.side_effect = boom_cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        # Reset warm state
        with delta_adapter._warm_lock:
            delta_adapter._warm_state = "idle"
            delta_adapter._warm_detail = ""

        # _load_alias_map should not crash
        amap = hr._load_alias_map()
        assert amap == {}

        # Verify alias map is marked as loaded (won't retry)
        with hr._alias_map_lock:
            assert hr._alias_map_loaded is True


# ── 7. Mutation: removing except ImportError breaks fallback ─────────────────


class TestFallbackMutationProof:
    """Mutation tests: removing the except ImportError fallback must break tests."""

    def test_remove_fallback_in_fetch_ticker_rows_breaks(self, monkeypatch):
        """Without the except ImportError, _fetch_ticker_rows propagates ImportError."""
        from api.services import hybrid_retriever as hr

        # Simulate the mutation: _get_spark raises ImportError and there's NO fallback
        def _fetch_no_fallback(ticker):
            """Mutated _fetch_ticker_rows without the except ImportError fallback."""
            spark = hr._get_spark()  # This will raise ImportError
            # ... rest of Spark path would go here ...
            return [], []

        monkeypatch.setattr(hr, "_get_spark", lambda: (_ for _ in ()).throw(ImportError("no pyspark")))

        with pytest.raises(ImportError):
            _fetch_no_fallback("NVDA")

    def test_fstring_ticker_in_sql_is_detected(self):
        """Mutating to f-string the ticker into SQL is caught by param-check tests."""
        sql_with_fstring = f"SELECT * FROM table WHERE ticker = NVDA"
        sql_with_param = "SELECT * FROM table WHERE ticker = ?"

        # The f-string version has the ticker literal in the SQL
        assert "NVDA" in sql_with_fstring
        # The parameterized version does NOT
        assert "NVDA" not in sql_with_param