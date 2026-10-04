"""tests/rag/test_merge_metrics.py — Tests for MERGE metrics None-safety.

Round 11: verify that missing history, missing metrics key, and exceptions
return None + WARNING (not silently 0).  Verify that aggregate propagates
None when any batch is unknown.

Mutation proof:
- Re-initialising inserted to 0 in _get_merge_inserted or _embed_and_write_batch
  → empty_history_returns_none, missing_key_returns_none, etc. FAIL.
- Adding `or 0` coercion in build aggregate → aggregate_none_propagation FAILS.
"""
from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: pyspark stubs (same approach as conftest fake_pyspark)
# ---------------------------------------------------------------------------

class _ColExpr:
    def __le__(self, other): return self
    def __lt__(self, other): return self
    def __ge__(self, other): return self
    def __gt__(self, other): return self
    def __eq__(self, other): return self
    def __ne__(self, other): return self
    def __and__(self, other): return self
    def __or__(self, other): return self
    def __invert__(self): return self
    def __getattr__(self, name): return self
    def __call__(self, *a, **kw): return self


@pytest.fixture(autouse=True)
def _install_pyspark_stubs(monkeypatch):
    """Install pyspark stubs so imports work.

    Imports real pyspark.sql.types BEFORE installing stubs so that
    StructType/StructField/etc. are available (needed by
    SparkDataWriter._ensure_schema).
    """
    # Import real types BEFORE stubbing the module
    real_types = {}
    try:
        from pyspark.sql.types import (
            BooleanType, IntegerType, StringType, StructField,
            StructType, TimestampType,
        )
        real_types = {
            "BooleanType": BooleanType,
            "IntegerType": IntegerType,
            "StringType": StringType,
            "StructField": StructField,
            "StructType": StructType,
            "TimestampType": TimestampType,
        }
    except ImportError:
        pass

    pyspark = ModuleType("pyspark")
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql_functions = ModuleType("pyspark.sql.functions")
    pyspark_sql_types = ModuleType("pyspark.sql.types")

    pyspark.sql = pyspark_sql
    pyspark_sql.functions = pyspark_sql_functions
    pyspark_sql.types = pyspark_sql_types

    # Attach real types to the stub
    for name, obj in real_types.items():
        setattr(pyspark_sql_types, name, obj)

    for name, obj in [
        ("pyspark", pyspark),
        ("pyspark.sql", pyspark_sql),
        ("pyspark.sql.functions", pyspark_sql_functions),
        ("pyspark.sql.types", pyspark_sql_types),
    ]:
        monkeypatch.setitem(sys.modules, name, obj)

    pyspark_sql_functions.col = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.lit = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.lower = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.unix_timestamp = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.desc = lambda *a, **kw: _ColExpr()

    pyspark_sql.SparkSession = MagicMock(name="SparkSession")
    pyspark_sql.DataFrame = MagicMock(name="DataFrame")


# ---------------------------------------------------------------------------
# Helpers: build mock Spark for _embed_and_write_batch
# ---------------------------------------------------------------------------

def _make_spark_for_embed(describe_result=None, describe_raises=None):
    """Return a mock Spark session configured for _embed_and_write_batch."""
    mock_spark = MagicMock()

    def sql_side_effect(query):
        if "DESCRIBE HISTORY" in query:
            if describe_raises:
                raise describe_raises
            mock_result = MagicMock()
            mock_result.collect.return_value = describe_result or []
            return mock_result
        return MagicMock()

    mock_spark.sql.side_effect = sql_side_effect
    mock_spark.createDataFrame.return_value = MagicMock()
    mock_spark.catalog = MagicMock()
    return mock_spark


def _make_spark_for_ingest(describe_result=None, describe_raises=None):
    """Return a mock Spark session configured for SparkDataWriter.append_bronze_rows."""
    mock_spark = MagicMock()

    def sql_side_effect(query):
        if "DESCRIBE HISTORY" in query:
            if describe_raises:
                raise describe_raises
            mock_result = MagicMock()
            mock_result.collect.return_value = describe_result or []
            return mock_result
        return MagicMock()

    mock_spark.sql.side_effect = sql_side_effect
    mock_spark.createDataFrame.return_value = MagicMock()
    mock_spark.catalog = MagicMock()
    return mock_spark


def _hist_row(metrics_dict):
    """Build a fake DESCRIBE HISTORY row with the given operationMetrics."""
    row = MagicMock()
    row.__getitem__ = lambda self, k: {"operationMetrics": metrics_dict}.get(k)
    return row


# ===========================================================================
# _embed_and_write_batch (build_sec_embeddings.py)
# ===========================================================================

class TestEmbedWriteBatchMetrics:
    """Tests for _embed_and_write_batch merge metrics reporting."""

    def _call(self, spark, merge_lock=None):
        from pipelines.build_sec_embeddings import _embed_and_write_batch
        lock = merge_lock or threading.Lock()
        embeddings = MagicMock()
        embeddings.embed_documents.return_value = [[0.1] * 384]
        batch = [{
            "chunk_id": "c1",
            "chunk_text": "hello",
            "accession_number": "ACC1",
            "ticker": "NVDA",
            "accepted_epoch": 1736899200,
        }]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return _embed_and_write_batch(spark, embeddings, batch, now, lock)

    def test_empty_history_returns_none(self, caplog):
        """Empty DESCRIBE HISTORY → None + WARNING."""
        spark = _make_spark_for_embed(describe_result=[])
        with caplog.at_level(logging.WARNING, logger="pipelines.build_sec_embeddings"):
            result = self._call(spark)
        assert result is None, (
            f"Expected None when history is empty, got {result}. "
            "Mutation: initialising inserted to 0 silently returns 0."
        )
        assert any("unknown" in r.message.lower() for r in caplog.records), (
            "Expected WARNING log when history is empty"
        )

    def test_missing_key_returns_none(self, caplog):
        """Metrics map without numTargetRowsInserted → None + WARNING."""
        spark = _make_spark_for_embed(describe_result=[_hist_row({"otherKey": "5"})])
        with caplog.at_level(logging.WARNING, logger="pipelines.build_sec_embeddings"):
            result = self._call(spark)
        assert result is None, (
            f"Expected None when key is missing, got {result}. "
            "Mutation: missing key path falls through to return initial 0."
        )
        assert any("unknown" in r.message.lower() for r in caplog.records)

    def test_exception_returns_none(self, caplog):
        """Exception reading history → None + WARNING."""
        spark = _make_spark_for_embed(describe_raises=RuntimeError("boom"))
        with caplog.at_level(logging.WARNING, logger="pipelines.build_sec_embeddings"):
            result = self._call(spark)
        assert result is None, (
            f"Expected None on exception, got {result}. "
            "Mutation: exception handler not reached because initial value is 0."
        )
        assert any("unknown" in r.message.lower() for r in caplog.records)

    def test_metrics_with_zero_returns_zero(self):
        """Metrics reporting '0' → integer 0, not None."""
        spark = _make_spark_for_embed(describe_result=[_hist_row({"numTargetRowsInserted": "0"})])
        result = self._call(spark)
        assert result == 0, f"Expected 0, got {result}"

    def test_metrics_with_seven_returns_seven(self):
        """Metrics reporting '7' → integer 7."""
        spark = _make_spark_for_embed(describe_result=[_hist_row({"numTargetRowsInserted": "7"})])
        result = self._call(spark)
        assert result == 7, f"Expected 7, got {result}"


# ===========================================================================
# SparkDataWriter.append_bronze_rows (sec_rag_ingest.py)
# ===========================================================================

class TestSparkDataWriterMetrics:
    """Tests for SparkDataWriter.append_bronze_rows merge metrics reporting."""

    def _call(self, spark, merge_lock=None):
        """Call append_bronze_rows on a SparkDataWriter with a mock spark."""
        from pipelines.sec_rag_ingest import SparkDataWriter
        lock = merge_lock or threading.Lock()
        writer = SparkDataWriter(spark_factory=lambda: spark)
        # Patch the class-level lock for this test
        original_lock = SparkDataWriter._merge_lock
        SparkDataWriter._merge_lock = lock
        try:
            rows = [{
                "record_key": "rk1",
                "ticker": "NVDA",
                "cik": "0001045810",
                "company_name": "NVIDIA",
                "form_type": "10-K",
                "filing_date": "2025-01-01",
                "accepted_ts": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "accession_number": "ACC1",
                "primary_doc": "f.htm",
                "filing_url": "http://example.com",
                "chunk_id": 1,
                "filing_section": "item1_business",
                "chunk_text": "hello",
                "chunk_char_count": 5,
                "source": "sec_edgar",
                "ingest_ts": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "raw_payload": "{}",
            }]
            return writer.append_bronze_rows("test", "test", rows)
        finally:
            SparkDataWriter._merge_lock = original_lock

    def test_empty_history_returns_none(self, caplog):
        """Empty DESCRIBE HISTORY → None + WARNING."""
        spark = _make_spark_for_ingest(describe_result=[])
        with caplog.at_level(logging.WARNING, logger="pipelines.sec_rag_ingest"):
            result = self._call(spark)
        assert result is None, (
            f"Expected None when history is empty, got {result}. "
            "Mutation: initialising inserted to 0 silently returns 0."
        )
        assert any("unknown" in r.message.lower() for r in caplog.records)

    def test_missing_key_returns_none(self, caplog):
        """Metrics map without numTargetRowsInserted → None + WARNING."""
        spark = _make_spark_for_ingest(describe_result=[_hist_row({"otherKey": "5"})])
        with caplog.at_level(logging.WARNING, logger="pipelines.sec_rag_ingest"):
            result = self._call(spark)
        assert result is None, (
            f"Expected None when key is missing, got {result}. "
            "Mutation: missing key path falls through to return initial 0."
        )
        assert any("unknown" in r.message.lower() for r in caplog.records)

    def test_exception_returns_none(self, caplog):
        """Exception reading history → None + WARNING."""
        spark = _make_spark_for_ingest(describe_raises=RuntimeError("boom"))
        with caplog.at_level(logging.WARNING, logger="pipelines.sec_rag_ingest"):
            result = self._call(spark)
        assert result is None, (
            f"Expected None on exception, got {result}. "
            "Mutation: exception handler not reached because initial value is 0."
        )
        assert any("unknown" in r.message.lower() for r in caplog.records)

    def test_metrics_with_zero_returns_zero(self):
        """Metrics reporting '0' → integer 0, not None."""
        spark = _make_spark_for_ingest(describe_result=[_hist_row({"numTargetRowsInserted": "0"})])
        result = self._call(spark)
        assert result == 0, f"Expected 0, got {result}"

    def test_metrics_with_seven_returns_seven(self):
        """Metrics reporting '7' → integer 7."""
        spark = _make_spark_for_ingest(describe_result=[_hist_row({"numTargetRowsInserted": "7"})])
        result = self._call(spark)
        assert result == 7, f"Expected 7, got {result}"


# ===========================================================================
# Aggregate: None propagation through batch sums
# ===========================================================================

class TestAggregateNonePropagation:
    """Verify that the build-level aggregate propagates None correctly.

    If any batch returns None (unknown), the total rows_written must be None,
    not a partial sum and not 0.
    """

    def test_mixed_with_none_returns_none(self):
        """[3, None, 2] → None (unknown propagates)."""
        from pipelines.build_sec_embeddings import build

        # 3 chunks → 1 batch. We need 3 batches to test aggregation.
        # Use batch_size=1 so each chunk is its own batch.
        new_chunks = [
            {
                "chunk_id": f"c{i}",
                "chunk_text": f"Text {i}",
                "accession_number": f"ACC{i}",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            }
            for i in range(3)
        ]

        mock_spark = MagicMock()
        mock_anti_join_df = MagicMock()
        mock_anti_join_df.filter.return_value = mock_anti_join_df
        mock_anti_join_df.select.return_value = mock_anti_join_df
        mock_anti_join_df.join.return_value = mock_anti_join_df
        mock_anti_join_df.repartition.return_value = mock_anti_join_df
        mock_anti_join_df.limit.return_value = mock_anti_join_df
        mock_chunk_rows = [
            MagicMock(__getitem__=lambda self, k, d=d: d.get(k))
            for d in new_chunks
        ]
        mock_anti_join_df.toLocalIterator.return_value = iter(mock_chunk_rows)

        mock_embedded_df = MagicMock()
        mock_embedded_df.filter.return_value = mock_embedded_df
        mock_embedded_df.select.return_value = mock_embedded_df

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embedded_df
            return mock_anti_join_df

        mock_spark.table.side_effect = table_side_effect

        # DESCRIBE HISTORY returns: batch0=3, batch1=None(unknown), batch2=2
        call_idx = [0]
        results_per_call = [
            [_hist_row({"numTargetRowsInserted": "3"})],  # batch 0 → 3
            [],                                            # batch 1 → None (empty history)
            [_hist_row({"numTargetRowsInserted": "2"})],  # batch 2 → 2
        ]

        def sql_side_effect(query):
            if "DESCRIBE HISTORY" in query:
                idx = call_idx[0]
                call_idx[0] += 1
                mock_result = MagicMock()
                mock_result.collect.return_value = results_per_call[idx]
                return mock_result
            return MagicMock()

        mock_spark.sql.side_effect = sql_side_effect
        mock_spark.createDataFrame.return_value = MagicMock()
        mock_spark.catalog = MagicMock()

        with patch("api.services.embeddings.get_embeddings", return_value=MagicMock(
            embed_documents=MagicMock(return_value=[[0.1] * 384])
        )):
            result = build(mock_spark, batch_size=1, partitions=1)

        assert result["rows_written"] is None, (
            f"Expected rows_written=None when any batch is unknown, got {result['rows_written']}. "
            "Mutation: `or 0` coercion in aggregate or `rows_written = 0` initialisation."
        )

    def test_all_zero_returns_zero(self):
        """[0, 0] → 0 (real zeros stay zero)."""
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": f"c{i}",
                "chunk_text": f"Text {i}",
                "accession_number": f"ACC{i}",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            }
            for i in range(2)
        ]

        mock_spark = MagicMock()
        mock_anti_join_df = MagicMock()
        mock_anti_join_df.filter.return_value = mock_anti_join_df
        mock_anti_join_df.select.return_value = mock_anti_join_df
        mock_anti_join_df.join.return_value = mock_anti_join_df
        mock_anti_join_df.repartition.return_value = mock_anti_join_df
        mock_anti_join_df.limit.return_value = mock_anti_join_df
        mock_chunk_rows = [
            MagicMock(__getitem__=lambda self, k, d=d: d.get(k))
            for d in new_chunks
        ]
        mock_anti_join_df.toLocalIterator.return_value = iter(mock_chunk_rows)

        mock_embedded_df = MagicMock()
        mock_embedded_df.filter.return_value = mock_embedded_df
        mock_embedded_df.select.return_value = mock_embedded_df

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embedded_df
            return mock_anti_join_df

        mock_spark.table.side_effect = table_side_effect

        # Both batches return 0
        call_idx = [0]

        def sql_side_effect(query):
            if "DESCRIBE HISTORY" in query:
                idx = call_idx[0]
                call_idx[0] += 1
                mock_result = MagicMock()
                mock_result.collect.return_value = [
                    _hist_row({"numTargetRowsInserted": "0"})
                ]
                return mock_result
            return MagicMock()

        mock_spark.sql.side_effect = sql_side_effect
        mock_spark.createDataFrame.return_value = MagicMock()
        mock_spark.catalog = MagicMock()

        with patch("api.services.embeddings.get_embeddings", return_value=MagicMock(
            embed_documents=MagicMock(return_value=[[0.1] * 384])
        )):
            result = build(mock_spark, batch_size=1, partitions=1)

        assert result["rows_written"] == 0, (
            f"Expected rows_written=0 when all batches report 0, got {result['rows_written']}. "
            "Mutation: None propagation incorrectly overrides real 0."
        )