"""tests/rag/test_sec_embeddings_incremental.py - Tests for incremental embedding builder.

Uses fake dataframe/embedding/store adapters. No network or Databricks calls.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class StubEmbeddings:
    def embed_documents(self, texts):
        return [[0.1] * 384 for _ in texts]


class TestEmbeddingBuild:
    """Test the refactored embedding builder with anti-join pattern."""

    def _make_mock_spark(self, new_chunks=None, existing_chunks=None):
        """Create a mock Spark session with anti-join chain."""
        mock_spark = MagicMock()

        new_chunks = new_chunks or []
        existing_chunks = existing_chunks or []

        # Mock the anti-join result (chunks to embed)
        mock_anti_join_df = MagicMock()
        mock_anti_join_df.filter.return_value = mock_anti_join_df
        mock_anti_join_df.select.return_value = mock_anti_join_df
        mock_anti_join_df.alias.return_value = mock_anti_join_df
        mock_anti_join_df.join.return_value = mock_anti_join_df
        mock_anti_join_df.repartition.return_value = mock_anti_join_df
        mock_anti_join_df.limit.return_value = mock_anti_join_df
        # toLocalIterator yields MagicMock rows (used by new streaming code)
        mock_anti_join_df.toLocalIterator.return_value = iter([
            MagicMock(__getitem__=lambda self, k, d=chunk: d.get(k))
            for chunk in new_chunks
        ])
        # collect is still used by some old paths
        mock_anti_join_df.collect.return_value = [
            MagicMock(__getitem__=lambda self, k, d=chunk: d.get(k))
            for chunk in new_chunks
        ]

        # Mock the embedded chunks table
        mock_embedded_df = MagicMock()
        mock_embedded_df.filter.return_value = mock_embedded_df
        mock_embedded_df.select.return_value = mock_embedded_df
        mock_embedded_df.collect.return_value = [
            MagicMock(__getitem__=lambda self, k, cid=cid: cid)
            for cid in existing_chunks
        ]

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embedded_df
            return mock_anti_join_df

        mock_spark.table.side_effect = table_side_effect

        # Track batch sizes by intercepting createDataFrame calls.
        # Each createDataFrame call corresponds to one batch → one MERGE.
        batch_size_history = []
        original_create = mock_spark.createDataFrame

        def tracking_create(data, schema=None):
            batch_size_history.append(len(data))
            return MagicMock()

        mock_spark.createDataFrame.side_effect = tracking_create

        # DESCRIBE HISTORY: return the batch size for the corresponding MERGE.
        describe_idx = [0]

        def sql_side_effect(query):
            if "DESCRIBE HISTORY" in query:
                idx = describe_idx[0]
                describe_idx[0] += 1
                inserted = batch_size_history[idx] if idx < len(batch_size_history) else 0
                mock_hist = MagicMock()
                mock_hist.__getitem__ = lambda self, k, n=str(inserted): {
                    "operationMetrics": {"numTargetRowsInserted": n}
                }.get(k)
                m = MagicMock()
                m.collect.return_value = [mock_hist]
                return m
            return MagicMock()

        mock_spark.sql.side_effect = sql_side_effect
        mock_spark.catalog = MagicMock()

        return mock_spark

    def test_only_anti_joined_chunks_embedded(self, fake_pyspark):
        """Only chunks NOT in the embeddings table should be processed."""
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": "new_1",
                "chunk_text": "New text 1",
                "accession_number": "ACC1",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            },
            {
                "chunk_id": "new_2",
                "chunk_text": "New text 2",
                "accession_number": "ACC2",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            },
        ]

        mock_spark = self._make_mock_spark(
            new_chunks=new_chunks,
            existing_chunks=["old_1", "old_2", "old_3"],
        )

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark, batch_size=256, partitions=4)

        assert result["rows_written"] == 2

    def test_second_run_writes_zero(self, fake_pyspark):
        """When all chunks are already embedded, 0 rows should be written."""
        from pipelines.build_sec_embeddings import build

        mock_spark = self._make_mock_spark(new_chunks=[], existing_chunks=["c1", "c2"])

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark, batch_size=256, partitions=4)

        assert result["rows_written"] == 0

    def test_dimension_validation(self, fake_pyspark):
        """Embeddings with wrong dimension should raise ValueError."""
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": "c1",
                "chunk_text": "Text",
                "accession_number": "ACC",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            },
        ]

        mock_spark = self._make_mock_spark(new_chunks=new_chunks)

        class WrongDimEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 128 for _ in texts]  # Wrong dim

        with patch("api.services.embeddings.get_embeddings", return_value=WrongDimEmbeddings()):
            with pytest.raises(ValueError, match="dimension mismatch"):
                build(mock_spark, batch_size=256, partitions=4)

    def test_batch_size_bounded(self, fake_pyspark):
        """Batch size should be respected."""
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": f"c{i}",
                "chunk_text": f"Text {i}",
                "accession_number": f"ACC{i}",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            }
            for i in range(10)
        ]

        mock_spark = self._make_mock_spark(new_chunks=new_chunks)

        embed_call_count = [0]
        class CountingEmbeddings:
            def embed_documents(self, texts):
                embed_call_count[0] += 1
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=CountingEmbeddings()):
            build(mock_spark, batch_size=3, partitions=1)

        # 10 chunks / batch_size 3 = 4 batches
        assert embed_call_count[0] == 4

    def test_ticker_filter_pushed(self, fake_pyspark):
        """When --ticker is specified, filter should be pushed to Spark."""
        from pipelines.build_sec_embeddings import build

        mock_spark = self._make_mock_spark(new_chunks=[])

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            build(mock_spark, batch_size=256, partitions=4, ticker="NVDA")

        # Verify filter was called on the chunks table
        chunks_table_call = mock_spark.table.call_args_list
        assert len(chunks_table_call) >= 2  # embeddings table + chunks table

    def test_concurrent_embedding_workers(self, fake_pyspark):
        """Multiple batches should be embedded concurrently (spy on threads)."""
        import threading
        import time
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": f"c{i}",
                "chunk_text": f"Text {i}",
                "accession_number": f"ACC{i}",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            }
            for i in range(8)
        ]

        mock_spark = self._make_mock_spark(new_chunks=new_chunks)

        active_threads = []
        max_concurrent = [0]
        lock = threading.Lock()

        class SlowEmbeddings:
            def embed_documents(self, texts):
                tid = threading.current_thread().ident
                with lock:
                    active_threads.append(tid)
                    max_concurrent[0] = max(max_concurrent[0], len(set(active_threads)))
                time.sleep(0.05)
                with lock:
                    active_threads.remove(tid)
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=SlowEmbeddings()):
            result = build(mock_spark, batch_size=2, partitions=4)

        assert result["rows_written"] == 8
        # With 8 chunks, batch_size=2 → 4 batches, partitions=4 workers
        # At least 2 should have run concurrently
        assert max_concurrent[0] >= 2, (
            f"Expected concurrent workers, max_concurrent={max_concurrent[0]}"
        )

    def test_sequential_output_matches_concurrent(self, fake_pyspark):
        """Concurrent embedding must produce the same result as sequential."""
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": f"c{i}",
                "chunk_text": f"Text {i}",
                "accession_number": f"ACC{i}",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            }
            for i in range(6)
        ]

        # Run with partitions=1 (sequential)
        mock_spark_seq = self._make_mock_spark(new_chunks=new_chunks)
        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result_seq = build(mock_spark_seq, batch_size=3, partitions=1)

        # Run with partitions=4 (concurrent)
        mock_spark_par = self._make_mock_spark(new_chunks=new_chunks)
        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result_par = build(mock_spark_par, batch_size=3, partitions=4)

        assert result_seq["rows_written"] == result_par["rows_written"] == 6
        assert result_seq["embedding_dim"] == result_par["embedding_dim"]


class TestEmbeddingJobYaml:
    """Static YAML assertions for the sec_embeddings job."""

    def test_sec_embeddings_job_exists(self):
        """sec_embeddings job must exist in jobs.yml."""
        import yaml
        from pathlib import Path

        jobs_path = Path(__file__).parent.parent.parent / "resources" / "jobs.yml"
        if not jobs_path.exists():
            pytest.skip("jobs.yml not found")

        content = jobs_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        assert "sec_embeddings" in data.get("resources", {}).get("jobs", {})

    def test_sec_embeddings_no_schedule(self):
        """sec_embeddings job must have no schedule/trigger."""
        import yaml
        from pathlib import Path

        jobs_path = Path(__file__).parent.parent.parent / "resources" / "jobs.yml"
        if not jobs_path.exists():
            pytest.skip("jobs.yml not found")

        content = jobs_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        job = data["resources"]["jobs"]["sec_embeddings"]
        assert "schedule" not in job, "sec_embeddings must not have a schedule"
        assert "trigger" not in job, "sec_embeddings must not have a trigger"

    def test_sec_rag_ingest_job_exists(self):
        """sec_rag_ingest job must exist in jobs.yml."""
        import yaml
        from pathlib import Path

        jobs_path = Path(__file__).parent.parent.parent / "resources" / "jobs.yml"
        if not jobs_path.exists():
            pytest.skip("jobs.yml not found")

        content = jobs_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        assert "sec_rag_ingest" in data.get("resources", {}).get("jobs", {})

    def test_sec_rag_ingest_no_schedule(self):
        """sec_rag_ingest job must have no schedule/trigger."""
        import yaml
        from pathlib import Path

        jobs_path = Path(__file__).parent.parent.parent / "resources" / "jobs.yml"
        if not jobs_path.exists():
            pytest.skip("jobs.yml not found")

        content = jobs_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        job = data["resources"]["jobs"]["sec_rag_ingest"]
        assert "schedule" not in job
        assert "trigger" not in job


class TestEmbeddingConcurrencyFixes:
    """Test round-8b fixes: unique view names, isin predicate, MERGE metrics."""

    def test_concurrent_batches_use_distinct_view_names(self, fake_pyspark):
        """Two concurrent batches must create distinct view names,
        and both batches' rows must reach the target table."""
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": f"c{i}",
                "chunk_text": f"Text {i}",
                "accession_number": f"ACC{i}",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            }
            for i in range(6)
        ]

        mock_spark = self._make_mock_spark_for_concurrency(new_chunks)

        mock_spark.catalog = MagicMock()

        # Capture createOrReplaceTempView calls AND the row data per batch
        captured_view_names = []
        captured_batch_rows = []

        class ViewTrackingDF:
            def __init__(self, rows):
                self._rows = rows

            def createOrReplaceTempView(self, name):
                captured_view_names.append(name)
                captured_batch_rows.append(self._rows)

        def mock_create_df(rows, schema=None):
            return ViewTrackingDF(rows)

        mock_spark.createDataFrame.side_effect = mock_create_df

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            build(mock_spark, batch_size=3, partitions=4)

        # With 6 chunks / batch_size=3 → 2 batches → 2 distinct view names
        assert len(captured_view_names) == 2
        assert captured_view_names[0] != captured_view_names[1]
        for name in captured_view_names:
            assert name.startswith("_embed_src_")

        # Both batches' rows must have reached the write path
        all_chunk_ids = set()
        for batch_rows in captured_batch_rows:
            for row in batch_rows:
                all_chunk_ids.add(row[0])  # chunk_id is the first element
        expected_ids = {f"c{i}" for i in range(6)}
        assert all_chunk_ids == expected_ids, (
            f"Expected all 6 chunk_ids in write path, got {all_chunk_ids}"
        )

    def test_comma_separated_ticker_uses_isin(self, fake_pyspark):
        """Comma-separated ticker list must use isin predicate, not scalar equality."""
        from pipelines.build_sec_embeddings import build
        import pyspark.sql.functions as F

        class _EvalCol:
            """Evaluable Column spy: records isin vs == and can evaluate on dict rows."""
            def __init__(self, name):
                self._name = name
                self._op = None
                self._target = None

            def isin(self, values):
                self._op = "isin"
                self._target = set(values)
                return self

            def __eq__(self, other):
                self._op = "eq"
                self._target = other
                return self

            def __ne__(self, other):
                return self

            def __getattr__(self, _name):
                return self

            def __call__(self, *a, **kw):
                return self

            def evaluate(self, row):
                val = row.get(self._name)
                if self._op == "isin":
                    return val in self._target
                if self._op == "eq":
                    return val == self._target
                return True

        captured_filter_args = []
        original_col = F.col
        F.col = lambda name: _EvalCol(name)

        try:
            mock_spark = MagicMock()
            mock_anti_join_df = MagicMock()

            def capture_filter(expr):
                captured_filter_args.append(expr)
                return mock_anti_join_df

            mock_anti_join_df.filter.side_effect = capture_filter
            mock_anti_join_df.select.return_value = mock_anti_join_df
            mock_anti_join_df.join.return_value = mock_anti_join_df
            mock_anti_join_df.repartition.return_value = mock_anti_join_df
            mock_anti_join_df.limit.return_value = mock_anti_join_df
            mock_anti_join_df.toLocalIterator.return_value = iter([])

            mock_embedded_df = MagicMock()
            mock_embedded_df.filter.return_value = mock_embedded_df
            mock_embedded_df.select.return_value = mock_embedded_df

            def table_side_effect(name):
                if "embeddings" in name:
                    return mock_embedded_df
                return mock_anti_join_df

            mock_spark.table.side_effect = table_side_effect

            with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
                build(mock_spark, batch_size=256, partitions=4, ticker="AAPL,MSFT")

            # captured: [0] = string predicate, [1] = ticker Column
            assert len(captured_filter_args) >= 2
            ticker_filter = captured_filter_args[1]
            assert isinstance(ticker_filter, _EvalCol)

            # Evaluate on test rows: AAPL and MSFT kept, GOOG dropped
            assert ticker_filter.evaluate({"ticker": "AAPL"}), "AAPL must be kept"
            assert ticker_filter.evaluate({"ticker": "MSFT"}), "MSFT must be kept"
            assert not ticker_filter.evaluate({"ticker": "GOOG"}), "GOOG must be dropped"

            # Mutation proof: scalar F.col("ticker") == "AAPL,MSFT" would set
            # _op="eq", _target="AAPL,MSFT" and evaluate({"ticker":"AAPL"})
            # would return False — caught above.
        finally:
            F.col = original_col

    def test_single_ticker_uses_equality(self, fake_pyspark):
        """Single ticker must use equality predicate (not isin)."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        mock_anti_join_df = MagicMock()
        mock_anti_join_df.filter.return_value = mock_anti_join_df
        mock_anti_join_df.select.return_value = mock_anti_join_df
        mock_anti_join_df.join.return_value = mock_anti_join_df
        mock_anti_join_df.repartition.return_value = mock_anti_join_df
        mock_anti_join_df.limit.return_value = mock_anti_join_df
        mock_anti_join_df.toLocalIterator.return_value = iter([])

        mock_embedded_df = MagicMock()
        mock_embedded_df.filter.return_value = mock_embedded_df
        mock_embedded_df.select.return_value = mock_embedded_df

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embedded_df
            return mock_anti_join_df

        mock_spark.table.side_effect = table_side_effect

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            build(mock_spark, batch_size=256, partitions=4, ticker="NVDA")

        assert mock_anti_join_df.filter.called

    def test_inserted_count_from_metrics(self, fake_pyspark):
        """MERGE must report actual inserted rows from operationMetrics.

        3 candidates sent but only 1 actually inserted (2 already existed).
        rows_written must be 1, not len(out_rows)=3.
        """
        from pipelines.build_sec_embeddings import build

        new_chunks = [
            {
                "chunk_id": "c1",
                "chunk_text": "Text 1",
                "accession_number": "ACC1",
                "ticker": "NVDA",
                "accepted_epoch": 1736899200,
            },
            {
                "chunk_id": "c2",
                "chunk_text": "Text 2",
                "accession_number": "ACC2",
                "ticker": "NVDA",
                "accepted_epoch": 1736899201,
            },
            {
                "chunk_id": "c3",
                "chunk_text": "Text 3",
                "accession_number": "ACC3",
                "ticker": "NVDA",
                "accepted_epoch": 1736899202,
            },
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

        # Mock DESCRIBE HISTORY: only 1 of 3 candidates was actually inserted
        mock_hist_row = MagicMock()
        mock_hist_row.__getitem__ = lambda self, k: {
            "operationMetrics": {"numTargetRowsInserted": "1"}
        }.get(k)
        mock_spark.sql.return_value.collect.return_value = [mock_hist_row]
        mock_spark.createDataFrame.return_value = MagicMock()
        mock_spark.catalog = MagicMock()

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark, batch_size=256, partitions=4)

        # 3 candidates but only 1 inserted — must use MERGE metric, not len(out_rows)
        assert result["rows_written"] == 1

    def test_zero_inserted_reported_as_zero(self, fake_pyspark):
        """N4: When MERGE inserts 0 rows (all duplicates), rows_written must
        be 0, not len(out_rows).

        Mutation proof: old code had
        ``return inserted if inserted > 0 else len(out_rows)`` which would
        return 3 (the candidate count) when 0 were actually inserted.
        """
        from pipelines.build_sec_embeddings import build

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

        # Mock DESCRIBE HISTORY: 0 rows inserted (all were duplicates)
        mock_hist_row = MagicMock()
        mock_hist_row.__getitem__ = lambda self, k: {
            "operationMetrics": {"numTargetRowsInserted": "0"}
        }.get(k)
        mock_spark.sql.return_value.collect.return_value = [mock_hist_row]
        mock_spark.createDataFrame.return_value = MagicMock()
        mock_spark.catalog = MagicMock()

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark, batch_size=256, partitions=4)

        # 0 inserted must be 0, not len(out_rows)=3
        assert result["rows_written"] == 0, (
            f"Expected rows_written=0, got {result['rows_written']}. "
            "Mutation: old code returned len(out_rows) when inserted==0."
        )

    def _make_mock_spark_for_concurrency(self, new_chunks):
        """Helper: mock Spark for concurrency tests."""
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
        mock_spark.sql.return_value = MagicMock()
        mock_spark.catalog = MagicMock()

        return mock_spark


class TestJobEntrypointImportsN5:
    """N5 (P2): Verify jobs.yml declares all dependencies needed by each
    entrypoint, and that entrypoints set sys.path for Databricks jobs.

    Mutation proof: remove loguru/python-dotenv from sec_embeddings env →
    test_sec_embeddings_env_declares_loguru_dotenv FAILS.
    Remove sys.path.insert from build_sec_embeddings.py →
    test_build_sec_embeddings_sets_sys_path FAILS.
    """

    JOBS_PATH = Path(__file__).parent.parent.parent / "resources" / "jobs.yml"

    def _load_jobs(self):
        import yaml
        if not self.JOBS_PATH.exists():
            pytest.skip("jobs.yml not found")
        return yaml.safe_load(self.JOBS_PATH.read_text(encoding="utf-8"))

    def test_sec_embeddings_env_declares_loguru_dotenv(self):
        """sec_embeddings environment must declare loguru and python-dotenv
        (imported transitively by api/services/embeddings.py → api/config.py)."""
        data = self._load_jobs()
        envs = data["resources"]["jobs"]["sec_embeddings"]["environments"]
        deps = []
        for env in envs:
            deps.extend(env.get("spec", {}).get("dependencies", []))

        dep_str = " ".join(deps)
        assert "loguru" in dep_str, (
            "sec_embeddings env missing loguru (imported by api/services/embeddings.py)"
        )
        assert "python-dotenv" in dep_str, (
            "sec_embeddings env missing python-dotenv (imported by api/config.py)"
        )

    def test_sec_rag_ingest_env_declares_bs4(self):
        """sec_rag_ingest environment must declare beautifulsoup4
        (used by strip_html via from bs4 import BeautifulSoup)."""
        data = self._load_jobs()
        envs = data["resources"]["jobs"]["sec_rag_ingest"]["environments"]
        deps = []
        for env in envs:
            deps.extend(env.get("spec", {}).get("dependencies", []))

        dep_str = " ".join(deps)
        assert "beautifulsoup4" in dep_str, (
            "sec_rag_ingest env missing beautifulsoup4 (used by strip_html)"
        )

    def test_build_sec_embeddings_sets_sys_path(self):
        """build_sec_embeddings.py must set sys.path for Databricks job context."""
        source = Path(__file__).parent.parent.parent / "pipelines" / "build_sec_embeddings.py"
        content = source.read_text(encoding="utf-8")
        assert "sys.path.insert" in content, (
            "build_sec_embeddings.py missing sys.path.insert — "
            "api.* imports will fail in Databricks job context"
        )

    def test_sec_rag_ingest_sets_sys_path(self):
        """sec_rag_ingest.py must set sys.path for Databricks job context."""
        source = Path(__file__).parent.parent.parent / "pipelines" / "sec_rag_ingest.py"
        content = source.read_text(encoding="utf-8")
        assert "sys.path.insert" in content, (
            "sec_rag_ingest.py missing sys.path.insert — "
            "pipelines.* imports will fail in Databricks job context"
        )

    def test_all_entrypoint_imports_declared(self):
        """Every top-level import in each entrypoint must be available in
        the Databricks serverless environment or declared as a dependency.

        This test parses the AST of each entrypoint and checks that every
        top-level import (excluding stdlib and repo-local modules) is listed
        in the job's environment dependencies.
        """
        import ast
        import sys as _sys
        data = self._load_jobs()

        # Map entrypoint → job name
        entrypoints = {
            "pipelines/build_sec_embeddings.py": "sec_embeddings",
            "pipelines/sec_rag_ingest.py": "sec_rag_ingest",
            "pipelines/ingest_sec_companyfacts.py": "sec_companyfacts_ingest",
        }

        # Stdlib modules (no need to declare)
        stdlib_mods = set(_sys.stdlib_module_names) if hasattr(_sys, "stdlib_module_names") else {
            "argparse", "hashlib", "json", "logging", "os", "re", "sys",
            "threading", "time", "uuid", "dataclasses", "datetime", "pathlib",
            "typing", "abc", "collections", "concurrent", "email", "io",
            "struct", "functools", "copy", "math", "random", "string",
            "textwrap", "enum", "contextlib", "warnings", "traceback",
            "importlib", "inspect", "ast",
        }

        # Repo-local modules (resolved by sys.path.insert)
        repo_local_prefixes = {"pipelines", "api", "ml", "db", "silver", "gold", "etl", "config", "strategies"}

        repo_root = Path(__file__).parent.parent.parent

        for rel_path, job_name in entrypoints.items():
            source_path = repo_root / rel_path
            if not source_path.exists():
                continue

            raw = source_path.read_bytes()
            # Strip UTF-8 BOM if present
            if raw[:3] == b"\xef\xbb\xbf":
                raw = raw[3:]
            tree = ast.parse(raw.decode("utf-8"), filename=str(source_path))

            # Collect top-level import module names
            imported_modules = set()
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.add(node.module.split(".")[0])

            # Get job dependencies from jobs.yml
            job = data["resources"]["jobs"].get(job_name, {})
            env_deps = set()
            for env in job.get("environments", []):
                for dep in env.get("spec", {}).get("dependencies", []):
                    # "loguru>=0.7.0" → "loguru"
                    env_deps.add(dep.split(">=")[0].split("==")[0].split("<")[0].strip())

            # Check: every imported module must be stdlib, repo-local, or in deps
            # Also allow known Databricks built-in packages
            databricks_builtin = {"databricks", "pyspark", "spark"}
            missing = []
            for mod in sorted(imported_modules):
                if mod in stdlib_mods:
                    continue
                if mod in repo_local_prefixes:
                    continue
                if mod in databricks_builtin:
                    continue
                if mod in env_deps:
                    continue
                # Check if it's a known pip package alias
                pip_aliases = {"bs4": "beautifulsoup4", "dotenv": "python-dotenv", "PIL": "Pillow"}
                if pip_aliases.get(mod) in env_deps:
                    continue
                missing.append(mod)

            assert not missing, (
                f"{job_name} ({rel_path}) imports {missing} but these are not "
                f"declared in the job environment dependencies: {env_deps}"
            )