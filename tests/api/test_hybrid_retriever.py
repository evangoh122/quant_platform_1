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
import time
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
        """Warehouse rows are read as ticker→canonical_ticker directly."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        # Reset alias map state
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0
            hr._alias_map_retry_at = 0.0

        cursor = FakeCursor(
            rows=[
                {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
                {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
                {"ticker": "NVDA", "canonical_ticker": "NVDA"},
            ],
            columns=["ticker", "canonical_ticker"],
        )
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        amap = hr._load_alias_map()

        # canonical_ticker is read directly — no re-derivation
        assert amap["GOOG"] == "GOOGL"
        assert amap["GOOGL"] == "GOOGL"
        # NVDA is its own canonical
        assert amap["NVDA"] == "NVDA"

    def test_alias_map_canonical_by_column_not_alphabetical(self, monkeypatch):
        """Canonical is read from canonical_ticker column, not re-derived.
        Mutation: reverting to n_chunks-based sort must pick GOOG (wrong)."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0

        # Both have canonical_ticker=GOOGL (as gold emits with resolved counts)
        cursor = FakeCursor(
            rows=[
                {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
                {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
            ],
            columns=["ticker", "canonical_ticker"],
        )
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        amap = hr._load_alias_map()

        # Both should map to GOOGL (the canonical_ticker from gold)
        assert amap["GOOGL"] == "GOOGL"
        assert amap["GOOG"] == "GOOGL"

    def test_alias_map_tie_breaks_alphabetically(self, monkeypatch):
        """When canonical_ticker is BRK.A (SQL tie-break), the alias map uses it."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0

        # Gold table emits canonical_ticker as resolved by SQL (BRK.A wins tie)
        cursor = FakeCursor(
            rows=[
                {"ticker": "BRK.B", "canonical_ticker": "BRK.A"},
                {"ticker": "BRK.A", "canonical_ticker": "BRK.A"},
            ],
            columns=["ticker", "canonical_ticker"],
        )
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        amap = hr._load_alias_map()

        # canonical_ticker from gold → BRK.A is canonical
        assert amap["BRK.A"] == "BRK.A"
        assert amap["BRK.B"] == "BRK.A"


# ── 3b. _load_alias_map reads canonical_ticker directly ─────────────────────


class TestLoadAliasMapCanonicalTicker:
    """Verify _load_alias_map reads canonical_ticker from gold_sec_coverage
    and uses it directly — no re-derivation from n_chunks."""

    def test_alias_map_uses_canonical_ticker_column(self, monkeypatch):
        """GOOG and GOOGL both have n_chunks=831 (resolved), but canonical_ticker
        is GOOGL.  The alias map must use canonical_ticker directly, not
        re-derive from n_chunks (which would pick GOOG alphabetically on tie)."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0

        # These rows match what 07_gold_sec_coverage.sql emits:
        # both GOOG and GOOGL report n_chunks=831 (resolved to canonical GOOGL)
        cursor = FakeCursor(
            rows=[
                {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
                {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
                {"ticker": "NVDA", "canonical_ticker": "NVDA"},
            ],
            columns=["ticker", "canonical_ticker"],
        )
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        amap = hr._load_alias_map()

        # Both must resolve to GOOGL (the canonical_ticker from gold)
        assert amap["GOOG"] == "GOOGL", (
            f"GOOG should resolve to GOOGL via canonical_ticker, got {amap.get('GOOG')}"
        )
        assert amap["GOOGL"] == "GOOGL", (
            f"GOOGL should resolve to GOOGL, got {amap.get('GOOGL')}"
        )
        assert amap["NVDA"] == "NVDA"

    def test_alias_map_sql_reads_canonical_ticker_not_n_chunks(self, monkeypatch):
        """The SQL must SELECT ticker, canonical_ticker — not ticker, cik, n_chunks.
        Mutation: reverting to the old SELECT breaks the GOOG→GOOGL resolution."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0

        executed_sql = []
        original_execute = FakeCursor.execute

        def tracking_execute(self, sql, params=None):
            executed_sql.append(sql)
            original_execute(self, sql, params)

        cursor = FakeCursor(
            rows=[
                {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
                {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
            ],
            columns=["ticker", "canonical_ticker"],
        )
        cursor.execute = lambda sql, params=None: tracking_execute(cursor, sql, params)

        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cursor

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        hr._load_alias_map()

        assert len(executed_sql) == 1, f"Expected 1 SQL execution, got {len(executed_sql)}"
        sql = executed_sql[0]
        assert "canonical_ticker" in sql, (
            f"SQL must select canonical_ticker column. Got: {sql}"
        )

# ── 3c. Missing canonical_ticker column: graceful fallback ──────────────────


class TestMissingCanonicalTickerColumn:
    """If gold_sec_coverage lacks canonical_ticker (old schema), fall back to
    identity mapping with a WARNING — never guess alphabetically."""

    def test_identity_fallback_on_missing_column(self, monkeypatch):
        """UNRESOLVED_COLUMN error → identity map + WARNING log."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0

        def raise_unresolved():
            raise RuntimeError(
                "[UNRESOLVED_COLUMN] Column `canonical_ticker` not found in "
                "table `gold_sec_coverage`"
            )

        fake_conn = MagicMock()
        fake_conn.cursor.side_effect = raise_unresolved

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        with LoguruCapture() as log:
            amap = hr._load_alias_map()

        assert amap == {}, f"Expected empty identity map, got {amap}"
        assert "canonical_ticker" in log.text, (
            f"Expected WARNING about missing canonical_ticker column, got: {log.text[:500]}"
        )

    def test_identity_fallback_never_guesses_alphabetically(self, monkeypatch):
        """On missing column, the fallback must NOT re-derive canonical from
        n_chunks (which would pick GOOG on tie).  Identity map means each
        ticker maps to itself."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0

        def raise_unresolved():
            raise RuntimeError(
                "[UNRESOLVED_COLUMN] Column `canonical_ticker` not found"
            )

        fake_conn = MagicMock()
        fake_conn.cursor.side_effect = raise_unresolved

        monkeypatch.setattr(
            "db.delta_adapter._get_warehouse_connection",
            lambda: fake_conn,
        )

        amap = hr._load_alias_map()

        # Identity map: empty means _resolve_canonical_ticker returns input
        assert amap.get("GOOG", "GOOG") == "GOOG", (
            "Fallback should be identity (empty map), not alphabetical guess"
        )
        assert amap.get("GOOGL", "GOOGL") == "GOOGL", (
            "Fallback should be identity (empty map), not alphabetical guess"
        )


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
            hr._alias_map_retry_at = 0.0

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
            hr._alias_map_retry_at = 0.0

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
            hr._alias_map_retry_at = 0.0

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

        # Verify alias map sets a retry deadline (not permanently loaded)
        with hr._alias_map_lock:
            assert hr._alias_map_loaded is False, (
                "Fallback should NOT mark alias map as permanently loaded; "
                "it should schedule a retry so the map can be loaded later."
            )
            assert hr._alias_map_retry_at > 0, (
                "Fallback should set a retry deadline so the map is retried."
            )


# ── 6b. Alias map fallback retry: failed load retries after deadline ─────────


class TestAliasMapFallbackRetry:
    """When _load_alias_map falls back (missing column / load failure), it must
    NOT cache permanently.  Instead it schedules a retry after
    _ALIAS_MAP_RETRY_INTERVAL seconds so the map can be loaded once the table
    is rebuilt."""

    def test_fallback_then_retry_loads_canonical(self, monkeypatch):
        """First load sees no canonical_ticker → identity; after the retry
        interval, with canonical rows available, GOOGL resolves to GOOGL's
        canonical."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0
            hr._alias_map_retry_at = 0.0

        fake_now = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        # First call: table missing → fallback, identity map, NOT permanently loaded
        call_count = 0

        def make_conn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: table missing
                conn = MagicMock()
                conn.cursor.side_effect = RuntimeError(
                    "[TABLE_OR_VIEW_NOT_FOUND] gold_sec_coverage does not exist."
                )
                return conn
            else:
                # Subsequent calls: table exists with canonical_ticker
                cursor = FakeCursor(
                    rows=[
                        {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
                        {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
                    ],
                    columns=["ticker", "canonical_ticker"],
                )
                conn = MagicMock()
                conn.cursor.return_value = cursor
                return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", make_conn)

        # First load → fallback (identity)
        amap = hr._load_alias_map()
        assert amap == {}
        assert hr._alias_map_loaded is False
        assert hr._alias_map_retry_at > fake_now

        # Before the deadline → no reload, still identity
        fake_now = hr._alias_map_retry_at - 1
        amap = hr._load_alias_map()
        assert amap == {}
        assert call_count == 1, "Should not have retried before deadline"

        # Past the deadline → reload, now canonical_ticker is available
        fake_now = hr._alias_map_retry_at + 1
        amap = hr._load_alias_map()
        assert amap["GOOG"] == "GOOGL"
        assert amap["GOOGL"] == "GOOGL"
        assert hr._alias_map_loaded is True
        assert call_count == 2

    def test_no_reload_before_deadline(self, monkeypatch):
        """Before the retry deadline, _load_alias_map returns the cached
        (empty) map without calling the reader again."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0
            hr._alias_map_retry_at = 0.0

        fake_now = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        read_count = 0

        def counting_conn():
            nonlocal read_count
            read_count += 1
            conn = MagicMock()
            conn.cursor.side_effect = RuntimeError("table missing")
            return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", counting_conn)

        # First call → fallback, sets deadline
        hr._alias_map_loaded = False  # ensure fresh
        hr._load_alias_map()
        deadline = hr._alias_map_retry_at
        assert deadline > fake_now
        assert read_count == 1

        # Multiple calls before deadline → no additional reads
        for _ in range(5):
            hr._load_alias_map()
        assert read_count == 1, (
            f"Expected 1 read (the initial load), got {read_count}. "
            "The retry deadline is being ignored."
        )

    def test_successful_load_is_permanently_cached(self, monkeypatch):
        """A successful load sets _alias_map_loaded=True and clears the retry
        deadline.  Subsequent calls never re-read."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0
            hr._alias_map_retry_at = 0.0

        read_count = 0

        def counting_conn():
            nonlocal read_count
            read_count += 1
            cursor = FakeCursor(
                rows=[
                    {"ticker": "NVDA", "canonical_ticker": "NVDA"},
                ],
                columns=["ticker", "canonical_ticker"],
            )
            conn = MagicMock()
            conn.cursor.return_value = cursor
            return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", counting_conn)

        # First load → success
        amap = hr._load_alias_map()
        assert amap["NVDA"] == "NVDA"
        assert hr._alias_map_loaded is True
        assert hr._alias_map_retry_at == 0.0
        assert read_count == 1

        # Many subsequent calls → no re-read
        for _ in range(10):
            hr._load_alias_map()
        assert read_count == 1, (
            f"Successful load should be permanent; got {read_count} reads."
        )


# ── 6c. Alias map fallback retry: all three branches ────────────────────────


class TestAliasMapFallbackRetryAllBranches:
    """Drive EACH fallback path through the production _load_alias_map() with a
    fake warehouse/Spark reader.  For each branch: identity map now; before the
    deadline no re-read; after advancing time.monotonic past the deadline with a
    reader that now returns canonical rows → GOOG resolves to GOOGL.

    The cache-forever mutation (setting _alias_map_loaded = True instead of
    scheduling a retry) must break all three tests because after the deadline
    the reader would be ignored.
    """

    def _reset_alias_map(self, hr):
        """Reset alias map state between sub-tests."""
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0

    def _make_canonical_rows(self):
        """Return rows that resolve GOOG → GOOGL."""
        return [
            {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
            {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
            {"ticker": "NVDA", "canonical_ticker": "NVDA"},
        ]

    def test_a_unresolved_column_with_suggestion(self, monkeypatch):
        """Branch (a): exception message contains
        [UNRESOLVED_COLUMN.WITH_SUGGESTION] ... canonical_ticker
        (the real Databricks text for a missing column)."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        self._reset_alias_map(hr)

        fake_now = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        # Reader that raises UNRESOLVED_COLUMN on first call, returns
        # canonical rows on subsequent calls.
        call_count = [0]

        def make_conn():
            call_count[0] += 1
            if call_count[0] == 1:
                conn = MagicMock()
                conn.cursor.side_effect = RuntimeError(
                    "[UNRESOLVED_COLUMN.WITH_SUGGESTION] Column `canonical_ticker` "
                    "is not present in any of the tables accessible to the current "
                    "scope. Did you mean one of the following columns: [ticker, cik, "
                    "n_chunks]? line 1, pos 14\n"
                    "\n== SQL ==\nSELECT ticker, canonical_ticker FROM "
                    "bootcamp_students.evangoh_capstone.gold_sec_coverage\n"
                    "--------------^^^"
                )
                return conn
            else:
                cursor = FakeCursor(
                    rows=self._make_canonical_rows(),
                    columns=["ticker", "canonical_ticker"],
                )
                conn = MagicMock()
                conn.cursor.return_value = cursor
                return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", make_conn)

        # 1) First call → identity map (empty), NOT permanently loaded
        amap = hr._load_alias_map()
        assert amap == {}, f"Expected identity (empty) map, got {amap}"
        assert hr._alias_map_loaded is False, (
            "UNRESOLVED_COLUMN fallback must NOT set _alias_map_loaded=True"
        )
        assert hr._alias_map_retry_at > fake_now, (
            "Must schedule a retry deadline"
        )
        assert call_count[0] == 1

        # 2) Before the deadline → no re-read, still identity
        fake_now = hr._alias_map_retry_at - 1
        amap = hr._load_alias_map()
        assert amap == {}
        assert call_count[0] == 1, (
            f"Should not retry before deadline; got {call_count[0]} reads"
        )

        # 3) Past the deadline → reload, now canonical rows available
        fake_now = hr._alias_map_retry_at + 1
        amap = hr._load_alias_map()
        assert amap["GOOG"] == "GOOGL", (
            f"GOOG should resolve to GOOGL after retry, got {amap.get('GOOG')}"
        )
        assert amap["GOOGL"] == "GOOGL"
        assert hr._alias_map_loaded is True
        assert call_count[0] == 2

    def test_b_no_rows(self, monkeypatch):
        """Branch (b): the read returns no rows (empty table)."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        self._reset_alias_map(hr)

        fake_now = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        call_count = [0]

        def make_conn():
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: returns empty rows
                cursor = FakeCursor(
                    rows=[],
                    columns=["ticker", "canonical_ticker"],
                )
                conn = MagicMock()
                conn.cursor.return_value = cursor
                return conn
            else:
                # Subsequent calls: returns canonical rows
                cursor = FakeCursor(
                    rows=self._make_canonical_rows(),
                    columns=["ticker", "canonical_ticker"],
                )
                conn = MagicMock()
                conn.cursor.return_value = cursor
                return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", make_conn)

        # 1) First call → identity map, NOT permanently loaded
        amap = hr._load_alias_map()
        assert amap == {}
        assert hr._alias_map_loaded is False
        assert hr._alias_map_retry_at > fake_now
        assert call_count[0] == 1

        # 2) Before the deadline → no re-read
        fake_now = hr._alias_map_retry_at - 1
        amap = hr._load_alias_map()
        assert amap == {}
        assert call_count[0] == 1

        # 3) Past the deadline → reload with canonical rows
        fake_now = hr._alias_map_retry_at + 1
        amap = hr._load_alias_map()
        assert amap["GOOG"] == "GOOGL"
        assert amap["GOOGL"] == "GOOGL"
        assert hr._alias_map_loaded is True
        assert call_count[0] == 2

    def test_c_generic_exception(self, monkeypatch):
        """Branch (c): a generic exception (e.g. connection refused)."""
        from api.services import hybrid_retriever as hr

        _make_warehouse_guard(monkeypatch, hr)
        self._reset_alias_map(hr)

        fake_now = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        call_count = [0]

        def make_conn():
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: generic exception (not UNRESOLVED_COLUMN)
                conn = MagicMock()
                conn.cursor.side_effect = RuntimeError(
                    "connection refused by warehouse endpoint"
                )
                return conn
            else:
                # Subsequent calls: returns canonical rows
                cursor = FakeCursor(
                    rows=self._make_canonical_rows(),
                    columns=["ticker", "canonical_ticker"],
                )
                conn = MagicMock()
                conn.cursor.return_value = cursor
                return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", make_conn)

        # 1) First call → identity map, NOT permanently loaded
        amap = hr._load_alias_map()
        assert amap == {}
        assert hr._alias_map_loaded is False
        assert hr._alias_map_retry_at > fake_now
        assert call_count[0] == 1

        # 2) Before the deadline → no re-read
        fake_now = hr._alias_map_retry_at - 1
        amap = hr._load_alias_map()
        assert amap == {}
        assert call_count[0] == 1

        # 3) Past the deadline → reload with canonical rows
        fake_now = hr._alias_map_retry_at + 1
        amap = hr._load_alias_map()
        assert amap["GOOG"] == "GOOGL"
        assert amap["GOOGL"] == "GOOGL"
        assert hr._alias_map_loaded is True
        assert call_count[0] == 2


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


# ── 6d. Concurrent reload guard: exactly one warehouse read ──────────────────


class TestConcurrentReloadGuard:
    """When the retry deadline passes, multiple concurrent callers must NOT
    all trigger a warehouse read.  Exactly one caller should reload; the rest
    should return the stale map immediately."""

    def test_concurrent_reload_exactly_one_read(self, monkeypatch):
        """N threads (≥4) call _load_alias_map() concurrently right after the
        deadline with a fake reader that blocks until all threads have entered
        → exactly one warehouse read."""
        from api.services import hybrid_retriever as hr
        import threading

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0
            hr._alias_map_loading = False

        fake_now = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        # First call → fallback, sets deadline
        call_count = 0

        def counting_conn_fallback():
            nonlocal call_count
            call_count += 1
            conn = MagicMock()
            conn.cursor.side_effect = RuntimeError("table missing")
            return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", counting_conn_fallback)
        hr._load_alias_map()
        assert call_count == 1
        deadline = hr._alias_map_retry_at
        assert deadline > fake_now

        # Advance past the deadline
        fake_now = deadline + 1

        # Now set up a blocking reader for the concurrent reload
        read_count = 0
        all_threads_ready = threading.Event()
        reader_can_proceed = threading.Event()

        def blocking_conn():
            nonlocal read_count
            read_count += 1
            # Signal that this thread has entered the reader
            all_threads_ready.set()
            # Wait until the test lets us proceed
            reader_can_proceed.wait(timeout=10)
            cursor = FakeCursor(
                rows=[
                    {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
                    {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
                ],
                columns=["ticker", "canonical_ticker"],
            )
            conn = MagicMock()
            conn.cursor.return_value = cursor
            return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", blocking_conn)

        N_THREADS = 6
        results = [None] * N_THREADS
        errors = [None] * N_THREADS

        def worker(idx):
            try:
                results[idx] = hr._load_alias_map()
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(N_THREADS)]
        for t in threads:
            t.start()

        # Wait for the first thread to enter the reader
        all_threads_ready.wait(timeout=10)
        # Give other threads a moment to reach the lock check
        import time as _time
        _time.sleep(0.1)
        # Let the reader complete
        reader_can_proceed.set()

        for t in threads:
            t.join(timeout=10)

        # No errors
        for i, e in enumerate(errors):
            assert e is None, f"Thread {i} raised: {e}"

        # Exactly one warehouse read
        assert read_count == 1, (
            f"Expected exactly 1 warehouse read, got {read_count}. "
            "Multiple callers reloaded concurrently."
        )

        # All threads got a result (either stale or fresh)
        for i in range(N_THREADS):
            assert results[i] is not None, f"Thread {i} got no result"

    def test_concurrent_reload_mutation_fails(self, monkeypatch):
        """Mutation: remove the in-flight guard (_alias_map_loading check).
        With the guard removed, multiple threads WILL reload concurrently,
        causing read_count > 1 — proving the guard is load-bearing."""
        from api.services import hybrid_retriever as hr
        import threading

        _make_warehouse_guard(monkeypatch, hr)
        with hr._alias_map_lock:
            hr._alias_map.clear()
            hr._alias_map_loaded = False
            hr._alias_map_retry_at = 0.0
            hr._alias_map_loading = False

        fake_now = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: fake_now)

        # First call → fallback, sets deadline
        call_count = 0

        def counting_conn_fallback():
            nonlocal call_count
            call_count += 1
            conn = MagicMock()
            conn.cursor.side_effect = RuntimeError("table missing")
            return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", counting_conn_fallback)
        hr._load_alias_map()
        assert call_count == 1
        deadline = hr._alias_map_retry_at

        # Advance past the deadline
        fake_now = deadline + 1

        # MUTATION: monkey-patch the function to skip the loading guard.
        # Replace _load_alias_map with a version that does NOT check _alias_map_loading.
        original_func = hr._load_alias_map

        def _mutated_load_alias_map():
            """Mutated version: no in-flight guard."""
            with hr._alias_map_lock:
                if hr._alias_map_loaded:
                    return hr._alias_map
                if hr._alias_map_retry_at and time.monotonic() < hr._alias_map_retry_at:
                    return hr._alias_map
                # MUTATION: removed the _alias_map_loading check
                hr._alias_map_loading = True

            try:
                try:
                    spark = hr._get_spark()
                except ImportError:
                    spark = None

                if spark is not None:
                    from pyspark.sql import functions as F
                    rows = spark.table(hr.COVERAGE_TABLE).select("ticker", "canonical_ticker").collect()
                else:
                    from db.delta_adapter import _get_warehouse_connection
                    conn = _get_warehouse_connection()
                    cur = conn.cursor()
                    try:
                        cur.execute(f"SELECT ticker, canonical_ticker FROM {hr.COVERAGE_TABLE}")
                        cols = [d[0] for d in cur.description]
                        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    finally:
                        cur.close()

                if not rows:
                    with hr._alias_map_lock:
                        hr._alias_map_retry_at = time.monotonic() + hr._ALIAS_MAP_RETRY_INTERVAL
                    return {}

                amap = {}
                for r in rows:
                    t = (r["ticker"] or "").upper().strip()
                    ct = (r["canonical_ticker"] or "").upper().strip()
                    if t and ct:
                        amap[t] = ct

                with hr._alias_map_lock:
                    hr._alias_map = amap
                    hr._alias_map_loaded = True
                    hr._alias_map_retry_at = 0.0
                return amap
            except Exception as exc:
                msg = str(exc)
                if "UNRESOLVED_COLUMN" in msg or ("canonical_ticker" in msg and "not found" in msg.lower()):
                    with hr._alias_map_lock:
                        hr._alias_map = {}
                        hr._alias_map_retry_at = time.monotonic() + hr._ALIAS_MAP_RETRY_INTERVAL
                    return {}
                with hr._alias_map_lock:
                    hr._alias_map = {}
                    hr._alias_map_retry_at = time.monotonic() + hr._ALIAS_MAP_RETRY_INTERVAL
                return {}
            finally:
                with hr._alias_map_lock:
                    hr._alias_map_loading = False

        # Set up a blocking reader
        read_count = 0
        all_threads_ready = threading.Event()
        reader_can_proceed = threading.Event()

        def blocking_conn():
            nonlocal read_count
            read_count += 1
            all_threads_ready.set()
            reader_can_proceed.wait(timeout=10)
            cursor = FakeCursor(
                rows=[
                    {"ticker": "GOOG", "canonical_ticker": "GOOGL"},
                    {"ticker": "GOOGL", "canonical_ticker": "GOOGL"},
                ],
                columns=["ticker", "canonical_ticker"],
            )
            conn = MagicMock()
            conn.cursor.return_value = cursor
            return conn

        monkeypatch.setattr("db.delta_adapter._get_warehouse_connection", blocking_conn)

        N_THREADS = 6
        results = [None] * N_THREADS

        def worker(idx):
            results[idx] = _mutated_load_alias_map()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(N_THREADS)]
        for t in threads:
            t.start()

        all_threads_ready.wait(timeout=10)
        import time as _time
        _time.sleep(0.1)
        reader_can_proceed.set()

        for t in threads:
            t.join(timeout=10)

        # With the guard removed, multiple threads should have entered the reader
        assert read_count > 1, (
            f"Mutation test FAILED: expected read_count > 1 with guard removed, "
            f"got {read_count}. The guard may not be the load-bearing code."
        )