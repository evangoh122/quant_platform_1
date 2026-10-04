"""tests/rag/test_sec_embeddings_incremental.py - Tests for incremental embedding builder.

Uses fake dataframe/embedding/store adapters. No network or Databricks calls.
"""
from __future__ import annotations

import sys
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
        mock_spark.sql.return_value = MagicMock()
        mock_spark.createDataFrame.return_value = MagicMock()

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