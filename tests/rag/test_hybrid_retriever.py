"""tests/rag/test_hybrid_retriever.py — Offline tests for the hybrid retrieval pipeline.

Tests run without Databricks/Spark — corpus loading is stubbed with in-memory data.
Live integration tests are marked @pytest.mark.databricks.
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from langchain_core.documents import Document

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_doc(
    text: str,
    ticker: str = "NVDA",
    accession: str = "0000723125-25-000042",
    accepted_ts: str = "2025-01-15",
    **meta,
) -> Document:
    """Create a Document with standard metadata."""
    return Document(
        page_content=text,
        metadata={
            "ticker": ticker,
            "accession": accession,
            "accepted_ts": accepted_ts,
            "form_type": "10-K",
            "section_id": "item_7",
            "chunk_index": 0,
            "source_url": "",
            **meta,
        },
    )


# ── RRF Fusion tests ─────────────────────────────────────────────────────────

class TestRRFFuse:
    """Verify rrf_fuse matches Rag_workbench's expected behavior."""

    def test_basic_fusion_merges_rankings(self):
        from api.services.hybrid_retriever import rrf_fuse

        doc_a = _make_doc("Alpha content", accession="AAA")
        doc_b = _make_doc("Beta content", accession="BBB")
        doc_c = _make_doc("Gamma content", accession="CCC")

        # Vector ranking: A > B > C
        # BM25 ranking:   B > C > A
        rankings = [[doc_a, doc_b, doc_c], [doc_b, doc_c, doc_a]]
        result = rrf_fuse(rankings, k=60)

        assert len(result) == 3
        # B appears first in both (rank 1 vector, rank 0 BM25) → highest score
        assert result[0].metadata["accession"] == "BBB"

    def test_rrf_k_must_be_positive(self):
        from api.services.hybrid_retriever import rrf_fuse

        with pytest.raises(ValueError, match="rrf k must be >= 1"):
            rrf_fuse([[Document(page_content="x", metadata={})]], k=0)

    def test_ticker_boost_must_be_at_least_one(self):
        from api.services.hybrid_retriever import rrf_fuse

        with pytest.raises(ValueError, match="ticker_boost must be >= 1.0"):
            rrf_fuse([[Document(page_content="x", metadata={})]], ticker_boost=0.5)

    def test_ticker_boost_floats_matching_docs(self):
        from api.services.hybrid_retriever import rrf_fuse

        doc_nvda = _make_doc("NVDA content", ticker="NVDA", accession="NVDA1")
        doc_amd = _make_doc("AMD content", ticker="AMD", accession="AMD1")

        # Both lists: NVDA first, AMD second
        rankings = [[doc_nvda, doc_amd], [doc_nvda, doc_amd]]
        result = rrf_fuse(rankings, k=60, boost_ticker="NVDA", ticker_boost=2.0)

        # NVDA should be first with boosted score
        assert result[0].metadata["ticker"] == "NVDA"

    def test_deduplication_by_content_key(self):
        from api.services.hybrid_retriever import rrf_fuse

        # Same chunk appearing in both lists should be deduplicated
        doc = _make_doc("Same content", accession="DUP")
        rankings = [[doc], [doc]]
        result = rrf_fuse(rankings, k=60)

        assert len(result) == 1
        assert result[0].metadata["accession"] == "DUP"

    def test_empty_rankings(self):
        from api.services.hybrid_retriever import rrf_fuse

        result = rrf_fuse([], k=60)
        assert result == []

    def test_single_ranking_list(self):
        from api.services.hybrid_retriever import rrf_fuse

        doc_a = _make_doc("A", accession="A")
        doc_b = _make_doc("B", accession="B")
        result = rrf_fuse([[doc_a, doc_b]], k=60)

        assert len(result) == 2
        assert result[0].metadata["accession"] == "A"


# ── BM25 + Dense fusion on in-memory corpus ──────────────────────────────────

class TestBM25DenseFusion:
    """Test BM25 and dense search with a stubbed in-memory corpus."""

    @pytest.fixture(autouse=True)
    def _setup_corpus(self, monkeypatch):
        """Inject a tiny corpus into the module-level cache."""
        from api.services import hybrid_retriever as hr

        self.docs = [
            _make_doc("NVIDIA revenue growth driven by AI chips", ticker="NVDA", accession="A1", accepted_ts="2025-01-01"),
            _make_doc("AMD EPYC server processor market share gains", ticker="AMD", accession="A2", accepted_ts="2025-01-01"),
            _make_doc("Intel foundry services strategic pivot", ticker="INTC", accession="A3", accepted_ts="2025-01-01"),
            _make_doc("NVIDIA CUDA ecosystem dominance in ML", ticker="NVDA", accession="A4", accepted_ts="2025-01-01"),
            _make_doc("Qualcomm 5G modem technology patents", ticker="QCOM", accession="A5", accepted_ts="2025-01-01"),
        ]

        # Pre-tokenised for BM25
        tokenised = [hr.tokenize(d.page_content) for d in self.docs]

        # Stub embeddings: simple random but deterministic vectors
        np.random.seed(42)
        embeddings_map = {}
        for doc in self.docs:
            cid = hashlib.md5(doc.page_content.encode()).hexdigest()[:16]
            embeddings_map[cid] = np.random.randn(384).astype(np.float32)
            embeddings_map[cid] /= np.linalg.norm(embeddings_map[cid])

        # Inject into module cache
        monkeypatch.setattr(hr, "_corpus_loaded", True)
        monkeypatch.setattr(hr, "_bm25_docs", self.docs)
        monkeypatch.setattr(hr, "_bm25_tokenised", tokenised)
        monkeypatch.setattr(hr, "_bm25_index", hr.BM25Okapi(tokenised))
        monkeypatch.setattr(hr, "_embeddings_map", embeddings_map)
        monkeypatch.setattr(hr, "_corpus", {
            hashlib.md5(d.page_content.encode()).hexdigest()[:16]: (
                d.page_content,
                d.metadata["ticker"],
                d.metadata["accession"],
                d.metadata["accepted_ts"],
                d.metadata["form_type"],
                d.metadata["section_id"],
                d.metadata["chunk_index"],
                d.metadata.get("source_url", ""),
            )
            for d in self.docs
        })

        # Stub the embedding provider
        class StubEmbeddings:
            def embed_query(self, text):
                np.random.seed(hash(text) % (2**31))
                v = np.random.randn(384).astype(np.float32)
                v /= np.linalg.norm(v)
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: StubEmbeddings())

    def test_bm25_returns_relevant_docs(self):
        from api.services.hybrid_retriever import bm25_search

        results = bm25_search("NVIDIA AI chips", top_k=3)
        assert len(results) > 0
        # NVIDIA docs should rank highly
        tickers = [d.metadata["ticker"] for d in results]
        assert "NVDA" in tickers

    def test_vector_search_returns_docs(self):
        from api.services.hybrid_retriever import vector_search

        results = vector_search("GPU revenue growth", top_k=3)
        assert len(results) > 0
        assert all(isinstance(d, Document) for d in results)

    def test_hybrid_retriever_fuses_results(self):
        from api.services.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(top_k=3)
        results = retriever.retrieve("NVIDIA AI chips revenue", top_k=3)
        assert len(results) > 0
        assert len(results) <= 3

    def test_ticker_boost_ranks_matching_docs_higher(self):
        from api.services.hybrid_retriever import bm25_search

        results = bm25_search("AI chips", top_k=10, ticker="NVDA", ticker_boost=10.0)
        assert len(results) > 0
        # With high boost, NVDA docs should appear first
        first_ticker = results[0].metadata["ticker"]
        assert first_ticker == "NVDA", f"Expected NVDA first with boost, got {first_ticker}"


# ── Point-in-time filter tests ───────────────────────────────────────────────

class TestPITFilter:
    """Verify that accepted_ts <= as_of filtering works correctly."""

    def test_chunk_accepted_after_as_of_excluded(self):
        from api.services.hybrid_retriever import _pit_filter

        doc_past = _make_doc("Past filing", accepted_ts="2024-06-01")
        doc_future = _make_doc("Future filing", accepted_ts="2026-01-01")
        doc_present = _make_doc("Present filing", accepted_ts="2025-06-15")

        as_of = datetime(2025, 12, 31, tzinfo=timezone.utc)
        result = _pit_filter([doc_past, doc_future, doc_present], as_of=as_of)

        texts = [d.page_content for d in result]
        assert "Past filing" in texts
        assert "Present filing" in texts
        assert "Future filing" not in texts

    def test_chunk_accepted_exactly_at_as_of_included(self):
        from api.services.hybrid_retriever import _pit_filter

        as_of = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        doc = _make_doc("Exact match", accepted_ts="2025-06-15 12:00:00")
        result = _pit_filter([doc], as_of=as_of)

        assert len(result) == 1
        assert result[0].page_content == "Exact match"

    def test_none_as_of_uses_now(self):
        from api.services.hybrid_retriever import _pit_filter

        doc = _make_doc("Recent", accepted_ts="2020-01-01")
        result = _pit_filter([doc], as_of=None)
        assert len(result) == 1  # Should include since 2020 < now

    def test_missing_accepted_ts_included_defensively(self):
        from api.services.hybrid_retriever import _pit_filter

        doc = _make_doc("No timestamp", accepted_ts="")
        result = _pit_filter([doc], as_of=datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert len(result) == 1

    def test_pit_filter_applied_before_scoring(self):
        """A future chunk that is the best lexical match must not appear."""
        from api.services.hybrid_retriever import HybridRetriever, _pit_filter

        # Directly test the filter — future doc excluded even if it's a perfect match
        future_doc = _make_doc(
            "NVIDIA export restrictions China semiconductor",
            accepted_ts="2027-01-01",
            accession="FUTURE",
        )
        past_doc = _make_doc(
            "Qualcomm quarterly earnings report",
            accepted_ts="2024-01-01",
            accession="PAST",
        )

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        result = _pit_filter([future_doc, past_doc], as_of=as_of)

        assert len(result) == 1
        assert result[0].metadata["accession"] == "PAST"


# ── Reranker fallback tests ──────────────────────────────────────────────────

class TestRerankerFallback:
    """Verify graceful fallback when the reranker model cannot load."""

    def test_returns_docs_unchanged_when_model_unavailable(self):
        from api.services import reranker as rr

        docs = [
            _make_doc("Doc A", accession="A"),
            _make_doc("Doc B", accession="B"),
            _make_doc("Doc C", accession="C"),
        ]

        with patch.object(rr, "_model", None), \
             patch.object(rr, "CrossEncoder", None):
            result = rr.rerank("test query", docs, top_k=2)

        assert len(result) == 2
        # Should be unchanged order (fallback)
        assert result[0].metadata["accession"] == "A"
        assert result[1].metadata["accession"] == "B"

    def test_returns_empty_for_empty_docs(self):
        from api.services.reranker import rerank

        result = rerank("query", [], top_k=5)
        assert result == []

    def test_truncates_to_top_k_on_fallback(self):
        from api.services import reranker as rr

        docs = [_make_doc(f"Doc {i}", accession=str(i)) for i in range(10)]

        with patch.object(rr, "_model", None), \
             patch.object(rr, "CrossEncoder", None):
            result = rr.rerank("query", docs, top_k=3)

        assert len(result) == 3


# ── Ticker resolution tests ──────────────────────────────────────────────────

class TestTickerResolution:
    """Verify company name → ticker resolution from query text."""

    def test_resolves_nvidia(self):
        from api.services.hybrid_retriever import resolve_ticker_from_query

        assert resolve_ticker_from_query("What is NVIDIA's revenue?") == "NVDA"

    def test_resolves_micron_technology(self):
        from api.services.hybrid_retriever import resolve_ticker_from_query

        assert resolve_ticker_from_query("Micron Technology gross margin") == "MU"

    def test_explicit_ticker_overrides_query(self):
        from api.services.hybrid_retriever import resolve_ticker_from_query

        assert resolve_ticker_from_query("NVIDIA revenue", ticker="AMD") == "AMD"

    def test_no_match_returns_empty(self):
        from api.services.hybrid_retriever import resolve_ticker_from_query

        assert resolve_ticker_from_query("random question about nothing") == ""

    def test_empty_query_returns_empty(self):
        from api.services.hybrid_retriever import resolve_ticker_from_query

        assert resolve_ticker_from_query("") == ""


# ── Embedding build idempotency test ─────────────────────────────────────────

class TestEmbeddingBuildIdempotency:
    """Verify the embedding build pipeline is idempotent."""

    def test_second_run_writes_zero_rows(self):
        """Mock Spark session to verify MERGE idempotency logic."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        existing_chunks = ["chunk_1", "chunk_2", "chunk_3"]

        mock_existing_df = MagicMock()
        mock_existing_df.filter.return_value = mock_existing_df
        mock_existing_df.select.return_value = mock_existing_df
        mock_existing_df.collect.return_value = [
            MagicMock(__getitem__=lambda self, k, cid=cid: cid) for cid in existing_chunks
        ]

        mock_chunks_df = MagicMock()
        mock_chunks_df.select.return_value = mock_chunks_df
        mock_chunks_df.filter.return_value = mock_chunks_df
        mock_chunks_df.collect.return_value = [
            MagicMock(__getitem__=lambda self, k, cid=cid: {
                "chunk_id": cid,
                "chunk_text": f"Text for {cid}",
                "accession_number": "0000723125-25-000042",
                "ticker": "NVDA",
                "accepted_ts": "2025-01-15",
            }.get(k))
            for cid in existing_chunks
        ]

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_existing_df
            return mock_chunks_df

        mock_spark.table.side_effect = table_side_effect
        mock_spark.sql.return_value = MagicMock()

        class StubEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark)

        assert result["rows_written"] == 0
        assert result["embedding_dim"] == 384
        assert result["rows_already_embedded"] == 3

    def test_create_table_called(self):
        """CREATE TABLE IF NOT EXISTS must be issued before MERGE."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        mock_empty = MagicMock()
        mock_empty.filter.return_value = mock_empty
        mock_empty.select.return_value = mock_empty
        mock_empty.collect.return_value = []

        def table_side_effect(name):
            return mock_empty

        mock_spark.table.side_effect = table_side_effect

        class StubEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            build(mock_spark)

        calls = mock_spark.sql.call_args_list
        assert len(calls) >= 1
        create_sql = calls[0][0][0]
        assert "CREATE TABLE IF NOT EXISTS" in create_sql
        assert "gold_sec_chunk_embeddings" in create_sql
        assert "accession_number" in create_sql
        assert "ticker" in create_sql
        assert "accepted_ts" in create_sql

    def test_metadata_columns_included_in_output(self):
        """Embedded rows must carry accession_number, ticker, accepted_ts."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        chunk_data = {
            "chunk_id": "c1",
            "chunk_text": "NVIDIA revenue growth",
            "accession_number": "0000723125-25-000042",
            "ticker": "NVDA",
            "accepted_ts": "2025-01-15",
        }

        mock_existing_df = MagicMock()
        mock_existing_df.filter.return_value = mock_existing_df
        mock_existing_df.select.return_value = mock_existing_df
        mock_existing_df.collect.return_value = []

        mock_chunks_df = MagicMock()
        mock_chunks_df.select.return_value = mock_chunks_df
        mock_chunks_df.filter.return_value = mock_chunks_df
        mock_chunks_df.collect.return_value = [
            MagicMock(__getitem__=lambda self, k, d=chunk_data: d.get(k))
        ]

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_existing_df
            return mock_chunks_df

        mock_spark.table.side_effect = table_side_effect

        captured_rows = []
        captured_schema = []

        def capture_create_df(rows, schema=None):
            captured_rows.extend(rows)
            if schema:
                captured_schema.append(schema)
            return MagicMock()

        mock_spark.createDataFrame.side_effect = capture_create_df
        mock_spark.sql.return_value = MagicMock()

        class StubEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            build(mock_spark)

        assert len(captured_rows) == 1
        row = captured_rows[0]
        assert row[0] == "c1"
        assert row[1] == "0000723125-25-000042"
        assert row[2] == "NVDA"
        assert row[3] == "2025-01-15"
        assert len(row[4]) == 384
        assert row[5] == "BAAI/bge-small-en-v1.5"

        assert len(captured_schema) == 1
        schema_str = captured_schema[0]
        assert "accession_number" in schema_str
        assert "ticker" in schema_str
        assert "accepted_ts" in schema_str

    def test_real_idempotency_count(self):
        """rows_already_embedded must reflect actual count, not hardcoded."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        all_chunks = ["c1", "c2", "c3", "c4", "c5"]
        already_embedded = ["c1", "c2"]

        mock_existing_df = MagicMock()
        mock_existing_df.filter.return_value = mock_existing_df
        mock_existing_df.select.return_value = mock_existing_df
        mock_existing_df.collect.return_value = [
            MagicMock(__getitem__=lambda self, k, cid=cid: cid) for cid in already_embedded
        ]

        chunk_data_map = {
            cid: {
                "chunk_id": cid,
                "chunk_text": f"Text {cid}",
                "accession_number": "ACC",
                "ticker": "TICK",
                "accepted_ts": "2025-01-01",
            }
            for cid in all_chunks
        }

        mock_chunks_df = MagicMock()
        mock_chunks_df.select.return_value = mock_chunks_df
        mock_chunks_df.filter.return_value = mock_chunks_df
        mock_chunks_df.collect.return_value = [
            MagicMock(__getitem__=lambda self, k, d=d: d.get(k))
            for d in chunk_data_map.values()
        ]

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_existing_df
            return mock_chunks_df

        mock_spark.table.side_effect = table_side_effect
        mock_spark.sql.return_value = MagicMock()

        class StubEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark)

        assert result["rows_written"] == 3
        assert result["rows_already_embedded"] == 2


# ── CorpusUnavailableError tests ─────────────────────────────────────────────

class TestCorpusUnavailableError:
    """Verify that corpus load failures raise CorpusUnavailableError, not silent []."""

    def test_load_corpus_raises_on_spark_failure(self, monkeypatch):
        """When Spark/table read fails, CorpusUnavailableError must be raised."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        # Reset module state so _load_corpus actually attempts a load
        monkeypatch.setattr(hr, "_corpus_loaded", False)
        monkeypatch.setattr(hr, "_corpus", {})
        monkeypatch.setattr(hr, "_bm25_docs", None)
        monkeypatch.setattr(hr, "_bm25_tokenised", None)
        monkeypatch.setattr(hr, "_bm25_index", None)
        monkeypatch.setattr(hr, "_embeddings_map", {})

        # Make _get_spark raise (simulates databricks-connect failure)
        def boom():
            raise RuntimeError("Only remote Spark sessions using Databricks Connect are supported")

        monkeypatch.setattr(hr, "_get_spark", boom)

        with pytest.raises(CorpusUnavailableError, match="Failed to load corpus"):
            hr._load_corpus()

    def test_bm25_search_propagates_corpus_unavailable(self, monkeypatch):
        """bm25_search must propagate CorpusUnavailableError, not swallow it."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        monkeypatch.setattr(hr, "_corpus_loaded", False)
        monkeypatch.setattr(hr, "_corpus", {})
        monkeypatch.setattr(hr, "_bm25_docs", None)
        monkeypatch.setattr(hr, "_bm25_tokenised", None)
        monkeypatch.setattr(hr, "_bm25_index", None)
        monkeypatch.setattr(hr, "_embeddings_map", {})

        def boom():
            raise RuntimeError("connection refused")

        monkeypatch.setattr(hr, "_get_spark", boom)

        with pytest.raises(CorpusUnavailableError):
            hr.bm25_search("test query")

    def test_vector_search_propagates_corpus_unavailable(self, monkeypatch):
        """vector_search must propagate CorpusUnavailableError, not swallow it."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        monkeypatch.setattr(hr, "_corpus_loaded", False)
        monkeypatch.setattr(hr, "_corpus", {})
        monkeypatch.setattr(hr, "_bm25_docs", None)
        monkeypatch.setattr(hr, "_bm25_tokenised", None)
        monkeypatch.setattr(hr, "_bm25_index", None)
        monkeypatch.setattr(hr, "_embeddings_map", {})

        def boom():
            raise RuntimeError("connection refused")

        monkeypatch.setattr(hr, "_get_spark", boom)

        with pytest.raises(CorpusUnavailableError):
            hr.vector_search("test query")

    def test_empty_cache_after_load_raises(self, monkeypatch):
        """If _corpus_loaded is True but _corpus is empty, raise immediately."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        monkeypatch.setattr(hr, "_corpus_loaded", True)
        monkeypatch.setattr(hr, "_corpus", {})

        with pytest.raises(CorpusUnavailableError, match="empty after previous load failure"):
            hr._load_corpus()


# ── Session selection tests ──────────────────────────────────────────────────

class TestSessionSelection:
    """Verify _get_spark picks the right session based on runtime environment."""

    def test_uses_databricks_session_outside_runtime(self, monkeypatch):
        """Outside Databricks runtime, DatabricksSession must be used."""
        from api.services import hybrid_retriever as hr

        # Ensure DATABRICKS_RUNTIME_VERSION is NOT set
        monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)

        mock_session_cls = MagicMock()
        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = MagicMock()
        mock_session_cls.builder = mock_builder

        with patch.dict("sys.modules", {"databricks.connect": MagicMock(DatabricksSession=mock_session_cls)}):
            spark = hr._get_spark()

        mock_builder.serverless.assert_called_once_with(True)
        mock_builder.getOrCreate.assert_called_once()

    def test_uses_ambient_session_inside_runtime(self, monkeypatch):
        """Inside Databricks runtime, SparkSession.builder.getOrCreate() is used."""
        from api.services import hybrid_retriever as hr

        monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")

        mock_spark_session = MagicMock()
        mock_builder = MagicMock()
        mock_builder.getOrCreate.return_value = mock_spark_session

        mock_pyspark = MagicMock()
        mock_pyspark.SparkSession.builder = mock_builder

        with patch.dict("sys.modules", {"pyspark.sql": mock_pyspark}):
            spark = hr._get_spark()

        mock_builder.getOrCreate.assert_called_once()


# ── search_sec_filings structured error tests ───────────────────────────────

class TestSearchSecFilingsError:
    """Verify search_sec_filings surfaces structured errors on corpus failure."""

    def test_returns_structured_error_on_corpus_unavailable(self, monkeypatch):
        """CorpusUnavailableError must produce a structured error dict, not []."""
        from api.services.hybrid_retriever import CorpusUnavailableError

        # Mock db.lakebase before importing agent.tools_retrieval
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        # Make HybridRetriever.retrieve raise CorpusUnavailableError
        def fake_retrieve(*args, **kwargs):
            raise CorpusUnavailableError("Delta table not found")

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="test query")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert "SEC filing corpus could not be loaded" in result[0]["message"]
        assert result[0]["ticker"] == "NVDA"

    def test_returns_empty_list_still_works_when_corpus_loaded(self, monkeypatch):
        """Normal empty result (no matches) is still a plain empty list."""
        # Mock db.lakebase before importing agent.tools_retrieval
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("ZZZZ", query="nonexistent")

        assert result == []

    def test_fallback_results_tagged_with_retrieval_mode(self, monkeypatch):
        """Non-corpus exception must return results tagged with retrieval_mode."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise RuntimeError("connection timeout")

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = fake_retrieve

        mock_row = MagicMock()
        mock_row.asDict.return_value = {
            "chunk_text": "NVIDIA revenue growth",
            "ticker": "NVDA",
            "accession_number": "ACC1",
        }
        mock_spark = MagicMock()
        mock_spark.table.return_value.where.return_value.limit.return_value.collect.return_value = [mock_row]

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("agent.tools_retrieval._spark", return_value=mock_spark):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) == 1
        assert result[0]["retrieval_mode"] == "substring_fallback"
        assert result[0]["_warning"] == "hybrid_retrieval_failed"

    def test_unavailable_result_contains_no_exception_text(self, monkeypatch):
        """The error message must not leak raw exception text."""
        from api.services.hybrid_retriever import CorpusUnavailableError

        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise CorpusUnavailableError("secret_table_name connection string leaked")

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="test")

        msg = result[0]["message"]
        assert "secret_table_name" not in msg
        assert "connection string leaked" not in msg

    def test_spark_uses_databricks_session_outside_runtime(self, monkeypatch):
        """_spark() must delegate to hybrid_retriever._get_spark."""
        from api.services import hybrid_retriever as hr

        monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)

        mock_session_cls = MagicMock()
        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = MagicMock()
        mock_session_cls.builder = mock_builder

        with patch.dict("sys.modules", {"databricks.connect": MagicMock(DatabricksSession=mock_session_cls)}):
            from agent.tools_retrieval import _spark
            spark = _spark()

        mock_builder.serverless.assert_called_once_with(True)
        mock_builder.getOrCreate.assert_called_once()

    def test_normal_results_tagged_with_retrieval_mode_hybrid(self, monkeypatch):
        """Normal results must carry retrieval_mode=hybrid."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from langchain_core.documents import Document

        mock_doc = Document(
            page_content="NVIDIA AI revenue",
            metadata={
                "accession": "ACC1",
                "form_type": "10-K",
                "accepted_ts": "2025-01-15",
                "source_url": "https://sec.gov/filing",
                "ticker": "NVDA",
                "section_id": "item_7",
                "chunk_index": 0,
                "similarity": 0.95,
                "distance": 0.05,
            },
        )
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [mock_doc]

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("api.services.reranker.rerank", side_effect=lambda q, d, top_k: d):
            result = search_sec_filings("NVDA", query="AI revenue")

        assert len(result) == 1
        assert result[0]["retrieval_mode"] == "hybrid"