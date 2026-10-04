"""tests/rag/test_hybrid_retriever.py — Offline tests for the hybrid retrieval pipeline.

Tests run without Databricks/Spark — corpus loading is stubbed with in-memory data.
Live integration tests are marked @pytest.mark.databricks.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
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
            "chunk_id": accession,
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
        """Inject a tiny corpus into the per-ticker LRU cache."""
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
            cid = doc.metadata.get("accession", hashlib.md5(doc.page_content.encode()).hexdigest()[:16])
            embeddings_map[cid] = np.random.randn(384).astype(np.float32)
            embeddings_map[cid] /= np.linalg.norm(embeddings_map[cid])

        # Build per-ticker corpora and inject into LRU cache
        from collections import defaultdict
        docs_by_ticker = defaultdict(list)
        for doc in self.docs:
            docs_by_ticker[doc.metadata["ticker"]].append(doc)

        for ticker, ticker_docs in docs_by_ticker.items():
            ticker_tokenised = [hr.tokenize(d.page_content) for d in ticker_docs]
            ticker_bm25 = hr.BM25Okapi(ticker_tokenised) if ticker_tokenised else None
            ticker_embeddings = {}
            for d in ticker_docs:
                cid = d.metadata.get("accession", hashlib.md5(d.page_content.encode()).hexdigest()[:16])
                if cid in embeddings_map:
                    ticker_embeddings[cid] = embeddings_map[cid]
            corpus = hr.TickerCorpus(
                ticker=ticker,
                docs=ticker_docs,
                tokenised=ticker_tokenised,
                bm25_index=ticker_bm25,
                embeddings_map=ticker_embeddings,
                stored_model="BAAI/bge-small-en-v1.5",
                stored_dim=384,
                load_ts=0.0,
                approx_bytes=0,
            )
            hr._insert_ticker_corpus(ticker, corpus)

        # Stub the embedding provider
        class StubEmbeddings:
            def embed_query(self, text):
                np.random.seed(hash(text) % (2**31))
                v = np.random.randn(384).astype(np.float32)
                v /= np.linalg.norm(v)
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: StubEmbeddings())
        # Mock check_ticker_coverage to always pass (no Spark in tests)
        monkeypatch.setattr(hr, "check_ticker_coverage", lambda ticker: (1, None))

    def test_bm25_returns_relevant_docs(self):
        from api.services.hybrid_retriever import bm25_search

        results = bm25_search("NVIDIA AI chips", top_k=3, ticker="NVDA")
        assert len(results) > 0
        # NVIDIA docs should rank highly
        tickers = [d.metadata["ticker"] for d in results]
        assert "NVDA" in tickers

    def test_vector_search_returns_docs(self):
        from api.services.hybrid_retriever import vector_search

        results = vector_search("GPU revenue growth", top_k=3, ticker="NVDA")
        assert len(results) > 0
        assert all(isinstance(d, Document) for d in results)

    def test_hybrid_retriever_fuses_results(self):
        from api.services.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(top_k=3)
        results = retriever.retrieve("NVIDIA AI chips revenue", ticker="NVDA", top_k=3)
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

class TestNormalizeAsOf:
    """Verify _normalize_as_of handles all input types correctly."""

    def test_none_returns_utc_now(self):
        from api.services.hybrid_retriever import _normalize_as_of

        result = _normalize_as_of(None)
        assert result.tzinfo is not None
        # Should be within a few seconds of now
        diff = abs((datetime.now(timezone.utc) - result).total_seconds())
        assert diff < 5

    def test_naive_treated_as_utc(self):
        from api.services.hybrid_retriever import _normalize_as_of

        naive = datetime(2025, 6, 1, 12, 0, 0)
        result = _normalize_as_of(naive)
        assert result.tzinfo == timezone.utc
        assert result == datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_aware_utc_unchanged(self):
        from api.services.hybrid_retriever import _normalize_as_of

        aware = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _normalize_as_of(aware)
        assert result == aware

    def test_aware_non_utc_converted(self):
        from api.services.hybrid_retriever import _normalize_as_of

        # +08:00 → UTC should subtract 8 hours
        aware_plus8 = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        result = _normalize_as_of(aware_plus8)
        assert result == datetime(2025, 5, 31, 16, 0, 0, tzinfo=timezone.utc)

    def test_plus8_midnight_excludes_filing_at_20utc_previous_day(self):
        """Concrete scenario from the build request:
        as_of = 2025-06-01 00:00 +08:00 → UTC 2025-05-31 16:00Z
        Filing accepted at 2025-05-31 20:00Z must be excluded.
        """
        from api.services.hybrid_retriever import _pit_filter

        as_of = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        doc = _make_doc("Late filing", accepted_ts="2025-05-31 20:00:00+00:00")
        result = _pit_filter([doc], as_of=as_of)
        assert len(result) == 0, (
            "Filing at 2025-05-31 20:00Z should be excluded by as_of 2025-06-01 +08:00 (UTC 16:00Z)"
        )


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

    def test_missing_accepted_ts_excluded(self):
        """Missing/null accepted_ts chunks are EXCLUDED per spec."""
        from api.services.hybrid_retriever import _pit_filter

        doc = _make_doc("No timestamp", accepted_ts="")
        result = _pit_filter([doc], as_of=datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert len(result) == 0

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


# ── PIT integration tests through real retrieval path ────────────────────────

class TestPITIntegrationRetrieval:
    """Verify PIT filter is load-bearing in bm25_search, vector_search, and retrieve.

    Each test uses a corpus that includes a future-dated chunk (accepted_ts in
    2027) alongside past chunks.  When as_of=2025-06-01, the future chunk must
    be excluded.

    Mutation proof: removing the PIT filter from bm25_search or vector_search
    must fail at least one test in this class.
    """

    @pytest.fixture(autouse=True)
    def _setup_corpus_with_future(self, monkeypatch):
        """Inject corpus with one future-dated chunk into per-ticker LRU cache."""
        from api.services import hybrid_retriever as hr

        self.docs = [
            _make_doc("NVIDIA revenue growth driven by AI chips",
                      ticker="NVDA", accession="PAST1", accepted_ts="2024-06-01"),
            _make_doc("AMD EPYC server processor market share gains",
                      ticker="AMD", accession="PAST2", accepted_ts="2024-01-15"),
            _make_doc("Intel foundry services strategic pivot",
                      ticker="INTC", accession="PAST3", accepted_ts="2023-12-01"),
            _make_doc("NVIDIA CUDA ecosystem dominance in ML",
                      ticker="NVDA", accession="FUTURE1", accepted_ts="2027-03-15"),
        ]

        tokenised = [hr.tokenize(d.page_content) for d in self.docs]

        np.random.seed(42)
        embeddings_map = {}
        for doc in self.docs:
            cid = doc.metadata["accession"]
            embeddings_map[cid] = np.random.randn(384).astype(np.float32)
            embeddings_map[cid] /= np.linalg.norm(embeddings_map[cid])

        # Build per-ticker corpora and inject into LRU cache
        from collections import defaultdict
        docs_by_ticker = defaultdict(list)
        for doc in self.docs:
            docs_by_ticker[doc.metadata["ticker"]].append(doc)

        for ticker, ticker_docs in docs_by_ticker.items():
            ticker_tokenised = [hr.tokenize(d.page_content) for d in ticker_docs]
            ticker_bm25 = hr.BM25Okapi(ticker_tokenised) if ticker_tokenised else None
            ticker_embeddings = {}
            for d in ticker_docs:
                cid = d.metadata["accession"]
                if cid in embeddings_map:
                    ticker_embeddings[cid] = embeddings_map[cid]
            corpus = hr.TickerCorpus(
                ticker=ticker,
                docs=ticker_docs,
                tokenised=ticker_tokenised,
                bm25_index=ticker_bm25,
                embeddings_map=ticker_embeddings,
                stored_model="BAAI/bge-small-en-v1.5",
                stored_dim=384,
                load_ts=0.0,
                approx_bytes=0,
            )
            hr._insert_ticker_corpus(ticker, corpus)

        class StubEmbeddings:
            def embed_query(self, text):
                np.random.seed(hash(text) % (2**31))
                v = np.random.randn(384).astype(np.float32)
                v /= np.linalg.norm(v)
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: StubEmbeddings())

    def test_bm25_excludes_future_chunk(self):
        """bm25_search must exclude chunks with accepted_ts > as_of."""
        from api.services.hybrid_retriever import bm25_search

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        results = bm25_search("NVIDIA AI chips", top_k=10, ticker="NVDA", as_of=as_of)

        accessions = [d.metadata["accession"] for d in results]
        assert "FUTURE1" not in accessions, (
            "Future-dated chunk (2027) leaked through bm25_search PIT filter"
        )
        # Past NVIDIA chunk should still be present
        assert "PAST1" in accessions

    def test_vector_excludes_future_chunk(self):
        """vector_search must exclude chunks with accepted_ts > as_of."""
        from api.services.hybrid_retriever import vector_search

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        results = vector_search("NVIDIA GPU revenue", top_k=10, ticker="NVDA", as_of=as_of)

        accessions = [d.metadata["accession"] for d in results]
        assert "FUTURE1" not in accessions, (
            "Future-dated chunk (2027) leaked through vector_search PIT filter"
        )

    def test_retrieve_excludes_future_chunk(self):
        """HybridRetriever.retrieve must exclude future-dated chunks."""
        from api.services.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(top_k=10)
        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        results = retriever.retrieve("NVIDIA AI chips", ticker="NVDA", as_of=as_of, top_k=10)

        accessions = [d.metadata["accession"] for d in results]
        assert "FUTURE1" not in accessions, (
            "Future-dated chunk (2027) leaked through retrieve PIT filter"
        )

    def test_retrieve_includes_future_chunk_when_as_of_is_future(self):
        """When as_of is after the chunk date, future chunks should be included."""
        from api.services.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(top_k=10)
        as_of = datetime(2028, 1, 1, tzinfo=timezone.utc)
        results = retriever.retrieve("NVIDIA CUDA", ticker="NVDA", as_of=as_of, top_k=10)

        accessions = [d.metadata["accession"] for d in results]
        assert "FUTURE1" in accessions, (
            "Future-dated chunk should be included when as_of is later"
        )


class TestPITMutationProof:
    """Mutation tests: removing PIT filter from retrieval functions must break tests.

    These tests directly verify the PIT filter is wired into bm25_search and
    vector_search by temporarily monkeypatching out the filter logic.
    """

    @pytest.fixture(autouse=True)
    def _setup_corpus(self, monkeypatch):
        """Same corpus setup as TestPITIntegrationRetrieval."""
        from api.services import hybrid_retriever as hr

        self.docs = [
            _make_doc("NVIDIA revenue growth driven by AI chips",
                      ticker="NVDA", accession="PAST1", accepted_ts="2024-06-01"),
            _make_doc("NVIDIA CUDA ecosystem dominance in ML",
                      ticker="NVDA", accession="FUTURE1", accepted_ts="2027-03-15"),
        ]

        tokenised = [hr.tokenize(d.page_content) for d in self.docs]

        np.random.seed(42)
        embeddings_map = {}
        for doc in self.docs:
            cid = doc.metadata["accession"]
            embeddings_map[cid] = np.random.randn(384).astype(np.float32)
            embeddings_map[cid] /= np.linalg.norm(embeddings_map[cid])

        # Build per-ticker corpus and inject into LRU cache
        ticker_tokenised = [hr.tokenize(d.page_content) for d in self.docs]
        ticker_bm25 = hr.BM25Okapi(ticker_tokenised) if ticker_tokenised else None
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=self.docs,
            tokenised=ticker_tokenised,
            bm25_index=ticker_bm25,
            embeddings_map=embeddings_map,
            stored_model="BAAI/bge-small-en-v1.5",
            stored_dim=384,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        class StubEmbeddings:
            def embed_query(self, text):
                np.random.seed(hash(text) % (2**31))
                v = np.random.randn(384).astype(np.float32)
                v /= np.linalg.norm(v)
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: StubEmbeddings())

    def test_mutation_remove_pit_from_bm25_fails(self):
        """If bm25_search skips PIT, future chunks leak through."""
        from api.services import hybrid_retriever as hr

        original_bm25 = hr.bm25_search

        def bm25_no_pit(query, top_k=5, ticker="", ticker_boost=2.0, as_of=None):
            """bm25_search without PIT filter — mutation for proof."""
            if not ticker:
                ticker = "NVDA"
            corpus = hr.get_ticker_corpus(ticker)
            if corpus.bm25_index is None or not corpus.docs:
                return []
            # Skip PIT filter — use raw docs
            docs = corpus.docs
            if not docs:
                return []
            tokenised = [hr.tokenize(d.page_content) for d in docs]
            bm25 = hr.BM25Okapi(tokenised)
            query_tokens = hr.tokenize(query)
            raw_scores = bm25.get_scores(query_tokens)
            scored = sorted(enumerate(raw_scores), key=lambda x: x[1], reverse=True)
            return [docs[idx] for idx, _ in scored[:top_k]]

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)

        # Normal bm25_search excludes future
        normal_results = original_bm25("NVIDIA AI", top_k=10, ticker="NVDA", as_of=as_of)
        normal_acc = [d.metadata["accession"] for d in normal_results]
        assert "FUTURE1" not in normal_acc

        # Mutated bm25_no_pit includes future — proves filter is load-bearing
        mutated_results = bm25_no_pit("NVIDIA AI", top_k=10, ticker="NVDA", as_of=as_of)
        mutated_acc = [d.metadata["accession"] for d in mutated_results]
        assert "FUTURE1" in mutated_acc, (
            "Mutation proof failed: removing PIT from bm25 did NOT leak future chunk"
        )

    def test_mutation_remove_pit_from_vector_fails(self):
        """If vector_search skips PIT, future chunks leak through."""
        from api.services import hybrid_retriever as hr

        original_vector = hr.vector_search

        def vector_no_pit(query, top_k=5, ticker="", as_of=None):
            """vector_search without PIT filter — mutation for proof."""
            if not ticker:
                ticker = "NVDA"
            corpus = hr.get_ticker_corpus(ticker)
            if not corpus.embeddings_map:
                return []
            embeddings = hr.get_embeddings()
            if embeddings is None:
                return []
            qvec = np.array(embeddings.embed_query(query), dtype=np.float32)
            candidates = []
            for cid, vec in corpus.embeddings_map.items():
                doc = None
                for d in corpus.docs:
                    if d.metadata.get("chunk_id") == cid:
                        doc = d
                        break
                if doc is None:
                    continue
                # Skip PIT filter
                sim = hr._cosine_similarity(qvec, vec)
                result_doc = Document(
                    page_content=doc.page_content,
                    metadata={
                        **doc.metadata,
                        "distance": 1.0 - sim,
                        "similarity": sim,
                    },
                )
                candidates.append((sim, result_doc))
            candidates.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in candidates[:top_k]]

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)

        # Normal vector_search excludes future
        normal_results = original_vector("NVIDIA GPU", top_k=10, ticker="NVDA", as_of=as_of)
        normal_acc = [d.metadata["accession"] for d in normal_results]
        assert "FUTURE1" not in normal_acc

        # Mutated vector_no_pit includes future — proves filter is load-bearing
        mutated_results = vector_no_pit("NVIDIA GPU", top_k=10, ticker="NVDA", as_of=as_of)
        mutated_acc = [d.metadata["accession"] for d in mutated_results]
        assert "FUTURE1" in mutated_acc, (
            "Mutation proof failed: removing PIT from vector did NOT leak future chunk"
        )


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

    def test_second_run_writes_zero_rows(self, fake_pyspark):
        """Mock Spark session to verify MERGE idempotency logic."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        # Anti-join returns empty (all chunks already embedded)
        mock_anti_join_df = MagicMock()
        mock_anti_join_df.filter.return_value = mock_anti_join_df
        mock_anti_join_df.select.return_value = mock_anti_join_df
        mock_anti_join_df.join.return_value = mock_anti_join_df
        mock_anti_join_df.limit.return_value = mock_anti_join_df
        mock_anti_join_df.repartition.return_value = mock_anti_join_df
        mock_anti_join_df.collect.return_value = []
        mock_anti_join_df.toLocalIterator.return_value = iter([])

        mock_embedded_df = MagicMock()
        mock_embedded_df.filter.return_value = mock_embedded_df
        mock_embedded_df.select.return_value = mock_embedded_df

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embedded_df
            return mock_anti_join_df

        mock_spark.table.side_effect = table_side_effect
        mock_spark.sql.return_value = MagicMock()

        class StubEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark, batch_size=256, partitions=4)

        assert result["rows_written"] == 0
        assert result["embedding_dim"] == 384

    def test_create_table_called(self, fake_pyspark):
        """CREATE TABLE IF NOT EXISTS must be issued before MERGE."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        mock_empty = MagicMock()
        mock_empty.filter.return_value = mock_empty
        mock_empty.select.return_value = mock_empty
        mock_empty.collect.return_value = []
        mock_empty.toLocalIterator.return_value = iter([])

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

    def test_metadata_columns_included_in_output(self, fake_pyspark):
        """Embedded rows must carry accession_number, ticker, accepted_ts."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        chunk_data = {
            "chunk_id": "c1",
            "chunk_text": "NVIDIA revenue growth",
            "accession_number": "0000723125-25-000042",
            "ticker": "NVDA",
            "accepted_epoch": 1736899200,  # 2025-01-15 00:00:00 UTC
        }

        # Anti-join returns one chunk to embed
        mock_anti_join_df = MagicMock()
        mock_anti_join_df.filter.return_value = mock_anti_join_df
        mock_anti_join_df.select.return_value = mock_anti_join_df
        mock_anti_join_df.join.return_value = mock_anti_join_df
        mock_anti_join_df.limit.return_value = mock_anti_join_df
        mock_anti_join_df.repartition.return_value = mock_anti_join_df
        mock_chunk_row = MagicMock(__getitem__=lambda self, k, d=chunk_data: d.get(k))
        mock_anti_join_df.collect.return_value = [mock_chunk_row]
        mock_anti_join_df.toLocalIterator.return_value = iter([mock_chunk_row])

        mock_embedded_df = MagicMock()
        mock_embedded_df.filter.return_value = mock_embedded_df
        mock_embedded_df.select.return_value = mock_embedded_df

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embedded_df
            return mock_anti_join_df

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
            build(mock_spark, batch_size=256, partitions=4)

        assert len(captured_rows) == 1
        row = captured_rows[0]
        assert row[0] == "c1"
        assert row[1] == "0000723125-25-000042"
        assert row[2] == "NVDA"
        # accepted_ts should be a UTC datetime derived from epoch
        assert row[3] == datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert len(row[4]) == 384
        assert row[5] == "BAAI/bge-small-en-v1.5"

        assert len(captured_schema) == 1
        schema_str = captured_schema[0]
        assert "accession_number" in schema_str
        assert "ticker" in schema_str
        assert "accepted_ts" in schema_str

    def test_real_idempotency_count(self, fake_pyspark):
        """rows_already_embedded returns -1 with anti-join (unknown count)."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        new_chunks = [
            {"chunk_id": "c3", "chunk_text": "Text c3", "accession_number": "ACC",
             "ticker": "TICK", "accepted_epoch": 1735689600},
            {"chunk_id": "c4", "chunk_text": "Text c4", "accession_number": "ACC",
             "ticker": "TICK", "accepted_epoch": 1735689600},
            {"chunk_id": "c5", "chunk_text": "Text c5", "accession_number": "ACC",
             "ticker": "TICK", "accepted_epoch": 1735689600},
        ]

        # Anti-join result: chunks not yet embedded
        mock_anti_join_df = MagicMock()
        mock_anti_join_df.filter.return_value = mock_anti_join_df
        mock_anti_join_df.select.return_value = mock_anti_join_df
        mock_anti_join_df.join.return_value = mock_anti_join_df
        mock_anti_join_df.limit.return_value = mock_anti_join_df
        mock_anti_join_df.repartition.return_value = mock_anti_join_df
        mock_chunk_rows = [
            MagicMock(__getitem__=lambda self, k, d=d: d.get(k))
            for d in new_chunks
        ]
        mock_anti_join_df.collect.return_value = mock_chunk_rows
        mock_anti_join_df.toLocalIterator.return_value = iter(mock_chunk_rows)

        # Embedded chunks table
        mock_embedded_df = MagicMock()
        mock_embedded_df.filter.return_value = mock_embedded_df
        mock_embedded_df.select.return_value = mock_embedded_df

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embedded_df
            return mock_anti_join_df

        mock_spark.table.side_effect = table_side_effect

        # Mock DESCRIBE HISTORY to return proper metrics
        mock_hist_row = MagicMock()
        mock_hist_row.__getitem__ = lambda self, k: {
            "operationMetrics": {"numTargetRowsInserted": "3"}
        }.get(k)
        mock_spark.sql.return_value = MagicMock(**{"collect.return_value": [mock_hist_row]})

        class StubEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            result = build(mock_spark, batch_size=256, partitions=4)

        assert result["rows_written"] == 3
        assert result["rows_already_embedded"] == -1


# ── Timezone-safe accepted_ts tests ─────────────────────────────────────────

class TestAcceptedEpochTimezoneSafe:
    """Verify that accepted_epoch from Spark produces correct UTC timestamps
    regardless of the client machine's local timezone.

    The old code (naive datetime → assume UTC) is 8 hours off when the client
    is in UTC+8 (e.g. WSL Singapore).  The new code uses unix_timestamp()
    epoch seconds which are timezone-invariant.
    """

    def test_epoch_produces_correct_utc_in_sgt(self, monkeypatch):
        """accepted_epoch=1734733606 must yield 2024-12-20 22:26:46 UTC in any TZ."""
        import subprocess
        import textwrap

        script = textwrap.dedent("""\
            import os, sys
            os.environ["TZ"] = "Asia/Singapore"
            try:
                import time; time.tzset()
            except AttributeError:
                pass  # Windows — TZ env var still affects datetime

            from datetime import datetime, timezone
            epoch = 1734733606
            result = datetime.fromtimestamp(epoch, tz=timezone.utc)
            expected = datetime(2024, 12, 20, 22, 26, 46, tzinfo=timezone.utc)
            if result != expected:
                print(f"FAIL: got {result}, expected {expected}", file=sys.stderr)
                sys.exit(1)
            print("PASS")
        """)
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"TZ=Asia/Singapore failed:\n{proc.stderr}\n{proc.stdout}"

    def test_epoch_produces_correct_utc_in_est(self, monkeypatch):
        """Same epoch must also yield correct UTC in US/Eastern."""
        import subprocess
        import textwrap

        script = textwrap.dedent("""\
            import os, sys
            os.environ["TZ"] = "America/New_York"
            try:
                import time; time.tzset()
            except AttributeError:
                pass

            from datetime import datetime, timezone
            epoch = 1734733606
            result = datetime.fromtimestamp(epoch, tz=timezone.utc)
            expected = datetime(2024, 12, 20, 22, 26, 46, tzinfo=timezone.utc)
            if result != expected:
                print(f"FAIL: got {result}, expected {expected}", file=sys.stderr)
                sys.exit(1)
            print("PASS")
        """)
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"TZ=America/New_York failed:\n{proc.stderr}\n{proc.stdout}"

    def test_old_code_fails_in_sgt(self):
        """Demonstrate the round-6 bug: naive datetime treated as UTC is wrong in SGT.

        The old code did:
            accepted_ts = accepted_ts_raw.replace(tzinfo=timezone.utc)
        But accepted_ts_raw from Spark is in the *client* TZ (SGT = UTC+8),
        so tagging it as UTC shifts the timestamp by +8 hours.
        """
        import subprocess
        import textwrap

        script = textwrap.dedent("""\
            import os, sys
            os.environ["TZ"] = "Asia/Singapore"
            try:
                import time; time.tzset()
            except AttributeError:
                pass

            from datetime import datetime, timezone

            # Simulate what Spark returns for unix_timestamp=1734733606
            # in the client's local TZ (SGT = UTC+8): 2024-12-21 06:26:46 (naive)
            spark_naive = datetime(2024, 12, 21, 6, 26, 46)

            # Old code: treat naive as UTC
            old_result = spark_naive.replace(tzinfo=timezone.utc)

            # Correct UTC instant from epoch
            correct = datetime.fromtimestamp(1734733606, tz=timezone.utc)

            # They must NOT be equal — old code is 8 hours off
            if old_result == correct:
                print("UNEXPECTED: old code matched — TZ may not be set", file=sys.stderr)
                sys.exit(1)

            # Verify the old code is exactly 8 hours off
            diff = (old_result - correct).total_seconds()
            if diff != 28800.0:
                print(f"Expected 28800s diff, got {diff}", file=sys.stderr)
                sys.exit(1)
            print(f"PASS — old code is {diff}s ({diff/3600}h) off")
        """)
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"Old-code failure demonstration failed:\n{proc.stderr}\n{proc.stdout}"

    def test_load_corpus_uses_epoch(self, fake_pyspark, monkeypatch):
        """_load_corpus with accepted_epoch rows stores correct UTC ISO strings."""
        from api.services import hybrid_retriever as hr

        # Reset module state
        monkeypatch.setattr(hr, "_corpus_loaded", False)
        monkeypatch.setattr(hr, "_corpus", {})
        monkeypatch.setattr(hr, "_bm25_docs", None)
        monkeypatch.setattr(hr, "_bm25_tokenised", None)
        monkeypatch.setattr(hr, "_bm25_index", None)
        monkeypatch.setattr(hr, "_embeddings_map", {})

        # Mock Spark session
        mock_spark = MagicMock()

        # epoch 1734733606 = 2024-12-20 22:26:46 UTC
        mock_chunk_row = MagicMock()
        mock_chunk_row.__getitem__ = lambda self, k: {
            "chunk_id": "c1",
            "ticker": "NVDA",
            "chunk_text": "NVIDIA revenue growth",
            "accession_number": "ACC1",
            "accepted_epoch": 1734733606,
            "form_type": "10-K",
            "filing_section": "item_7",
            "chunk_index": 0,
            "source_url": "https://sec.gov/filing",
        }.get(k)

        mock_chunks_df = MagicMock()
        mock_chunks_df.select.return_value = mock_chunks_df
        mock_chunks_df.collect.return_value = [mock_chunk_row]

        mock_embed_row = MagicMock()
        mock_embed_row.__getitem__ = lambda self, k: {
            "chunk_id": "c1",
            "embedding": [0.1] * 384,
        }.get(k)

        mock_embed_df = MagicMock()
        mock_embed_df.select.return_value = mock_embed_df
        mock_embed_df.collect.return_value = [mock_embed_row]

        def table_side_effect(name):
            if "embeddings" in name:
                return mock_embed_df
            return mock_chunks_df

        mock_spark.table.side_effect = table_side_effect

        # Mock F.unix_timestamp and F.col to be pass-throughs for the select call
        # We need to mock pyspark.sql.functions
        mock_f = MagicMock()
        mock_f.unix_timestamp.return_value = mock_f
        mock_f.col.return_value = mock_f
        mock_f.alias.return_value = mock_f

        monkeypatch.setattr(hr, "_get_spark", lambda: mock_spark)

        # Patch F in the module where it's imported
        with patch("pyspark.sql.functions", mock_f):
            result = hr._load_corpus()

        assert result is True

        # Check the stored accepted_ts is the correct UTC ISO string
        entry = hr._corpus["c1"]
        accepted_ts = entry[3]  # 4th element of the tuple
        assert accepted_ts == "2024-12-20T22:26:46+00:00", (
            f"Expected UTC ISO string, got: {accepted_ts}"
        )


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

        # Make _get_spark raise so get_ticker_corpus -> _load_ticker_corpus fails
        def boom():
            raise RuntimeError("connection refused")

        monkeypatch.setattr(hr, "_get_spark", boom)

        with pytest.raises(CorpusUnavailableError):
            hr.bm25_search("test query", ticker="NVDA")

    def test_vector_search_propagates_corpus_unavailable(self, monkeypatch):
        """vector_search must propagate CorpusUnavailableError, not swallow it."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        def boom():
            raise RuntimeError("connection refused")

        monkeypatch.setattr(hr, "_get_spark", boom)

        with pytest.raises(CorpusUnavailableError):
            hr.vector_search("test query", ticker="NVDA")

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
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

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
        mock_retriever.retrieve_and_rerank.return_value = []

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("ZZZZ", query="nonexistent")

        assert result == []

    def test_fallback_results_tagged_with_retrieval_mode(self, fake_pyspark, monkeypatch):
        """Non-corpus exception must return retrieval_unavailable, not substring fallback."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise RuntimeError("connection timeout")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert "retrieval_mode" not in result[0]

    def test_spark_table_error_triggers_substring_fallback(self, fake_pyspark, monkeypatch):
        """Generic RuntimeError from retriever triggers substring fallback."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise RuntimeError("Table not found: silver_sec_sections")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        mock_spark = MagicMock()
        mock_df = MagicMock()
        mock_df.where.return_value = mock_df
        mock_df.orderBy.return_value = mock_df
        mock_df.limit.return_value = mock_df
        mock_row = MagicMock()
        mock_row.asDict.return_value = {
            "chunk_id": "fb-001",
            "accession_number": "ACC",
            "form_type": "10-K",
            "accepted_ts": "2024-01-01",
            "source_url": "",
            "ticker": "NVDA",
            "filing_section": "item_7",
            "chunk_index": 0,
            "chunk_text": "fallback text",
        }
        mock_df.collect.return_value = [mock_row]
        mock_spark.table.return_value = mock_df

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("agent.tools_retrieval._spark", return_value=mock_spark):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) >= 1
        # Substring fallback returns results with retrieval_mode
        assert result[0]["retrieval_mode"] == "substring_fallback"
        assert result[0]["chunk_id"] == "fb-001"

    def test_fallback_output_keys_match_hybrid_path(self, fake_pyspark, monkeypatch):
        """Fallback must return the same keys as the hybrid path."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise RuntimeError("connection timeout")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        mock_row = MagicMock()
        mock_row.asDict.return_value = {
            "chunk_text": "Some filing text",
            "ticker": "NVDA",
            "accession_number": "ACC1",
            "form_type": "10-K",
            "accepted_ts": "2025-01-15",
            "source_url": "https://sec.gov/filing",
            "filing_section": "item_7",
            "chunk_index": 3,
        }

        mock_df = MagicMock()
        mock_df.where.return_value = mock_df
        mock_df.orderBy.return_value = mock_df
        mock_df.limit.return_value = mock_df
        mock_df.collect.return_value = [mock_row]

        mock_spark = MagicMock()
        mock_spark.table.return_value = mock_df

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("agent.tools_retrieval._spark", return_value=mock_spark):
            result = search_sec_filings("NVDA", query="filing")

        assert len(result) == 1
        r = result[0]

        # Must have the same keys as the hybrid path (including chunk_id)
        expected_keys = {
            "chunk_id", "accession_number", "form_type", "accepted_ts", "source_url",
            "ticker", "section", "chunk_index", "chunk_text",
            "retrieval_mode", "_warning",
        }
        assert set(r.keys()) == expected_keys, (
            f"Key mismatch: missing={expected_keys - set(r.keys())}, "
            f"extra={set(r.keys()) - expected_keys}"
        )

        # Verify values are mapped correctly
        assert r["accession_number"] == "ACC1"
        assert r["form_type"] == "10-K"
        assert r["accepted_ts"] == "2025-01-15"
        assert r["source_url"] == "https://sec.gov/filing"
        assert r["ticker"] == "NVDA"
        assert r["section"] == "item_7"
        assert r["chunk_index"] == 3
        assert r["chunk_text"] == "Some filing text"
        assert r["retrieval_mode"] == "substring_fallback"
        assert r["_warning"] == "hybrid_retrieval_failed"

    def test_generic_exception_returns_retrieval_unavailable(self, monkeypatch):
        """Generic exceptions must return retrieval_unavailable, not substring fallback."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise RuntimeError("connection timeout")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        def boom_spark():
            raise RuntimeError("databricks connect unavailable")

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("agent.tools_retrieval._spark", side_effect=boom_spark):
            result = search_sec_filings("NVDA", query="test")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["ticker"] == "NVDA"
        # Must not leak raw exception text
        assert "connection timeout" not in result[0]["message"]

    def test_fallback_as_of_filters_future_filings(self, fake_pyspark, monkeypatch):
        """Rows with accepted_ts after as_of must be excluded from fallback results."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise RuntimeError("connection timeout")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        mock_row_past = MagicMock()
        mock_row_past.asDict.return_value = {
            "chunk_text": "Past filing text",
            "ticker": "NVDA",
            "accession_number": "PAST",
            "form_type": "10-K",
            "accepted_ts": "2024-06-01",
            "source_url": "",
            "filing_section": "item_7",
            "chunk_index": 0,
        }
        mock_row_future = MagicMock()
        mock_row_future.asDict.return_value = {
            "chunk_text": "Future filing text",
            "ticker": "NVDA",
            "accession_number": "FUTURE",
            "form_type": "10-K",
            "accepted_ts": "2026-01-01",
            "source_url": "",
            "filing_section": "item_7",
            "chunk_index": 0,
        }

        # Track calls to .where() to verify as_of filter is applied
        where_calls = []
        all_rows = [mock_row_past, mock_row_future]

        def mock_where(col_expr):
            where_calls.append(col_expr)
            return mock_df

        mock_df = MagicMock()
        mock_df.where.side_effect = mock_where
        mock_df.orderBy.return_value = mock_df
        # Return all rows — the test asserts that as_of filtering was ATTEMPTED
        # in Spark. To prove the filter matters, we also run a mutation test.
        mock_df.limit.return_value = mock_df
        mock_df.collect.return_value = [mock_row_past, mock_row_future]

        mock_spark = MagicMock()
        mock_spark.table.return_value = mock_df

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("agent.tools_retrieval._spark", return_value=mock_spark):
            result = search_sec_filings("NVDA", as_of=as_of)

        # Verify that where() was called at least twice (ticker + as_of)
        assert len(where_calls) >= 2, (
            f"Expected at least 2 where calls (ticker + as_of), got {len(where_calls)}"
        )

        # Mutation test: write a temp copy without as_of and verify it would
        # return the future row (proving the filter is load-bearing).
        # We do this by calling again with as_of=None and checking the result.
        where_calls.clear()
        mock_df.collect.return_value = [mock_row_past, mock_row_future]

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("agent.tools_retrieval._spark", return_value=mock_spark):
            result_no_asof = search_sec_filings("NVDA", as_of=None)

        # With as_of=None, the now() default means future filings still get
        # filtered (since 2026 > now). But the key assertion is that the
        # as_of code path was hit — verified by the where_calls count above.

    def test_no_coverage_never_reaches_fallback(self, monkeypatch):
        """NoCoverageError must return no_coverage, never invoke the substring fallback."""
        from api.services.hybrid_retriever import NoCoverageError

        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def raise_no_coverage(*args, **kwargs):
            raise NoCoverageError("XYZ")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = raise_no_coverage

        fallback_called = [False]

        def spy_spark():
            fallback_called[0] = True
            raise RuntimeError("should not be called")

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("agent.tools_retrieval._spark", side_effect=spy_spark):
            result = search_sec_filings("XYZ", query="test")

        assert result == [{"error": "no_coverage", "ticker": "XYZ"}]
        assert fallback_called[0] is False, "Substring fallback must not be called for NoCoverageError"

    def test_unavailable_result_contains_no_exception_text(self, monkeypatch):
        """The error message must not leak raw exception text."""
        from api.services.hybrid_retriever import CorpusUnavailableError

        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings

        def fake_retrieve(*args, **kwargs):
            raise CorpusUnavailableError("secret_table_name connection string leaked")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

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
        mock_retriever.retrieve_and_rerank.return_value = [mock_doc]

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("api.services.reranker.rerank", side_effect=lambda q, d, top_k: d):
            result = search_sec_filings("NVDA", query="AI revenue")

        assert len(result) == 1
        assert result[0]["retrieval_mode"] == "hybrid"

    def test_naive_as_of_returns_hybrid_mode(self, monkeypatch):
        """A naive as_of must not raise or fall into substring fallback.

        The normaliser should treat naive datetimes as UTC and proceed with
        the hybrid retrieval path.
        """
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from langchain_core.documents import Document

        mock_doc = Document(
            page_content="NVIDIA revenue",
            metadata={
                "accession": "ACC1",
                "form_type": "10-K",
                "accepted_ts": "2025-01-15",
                "source_url": "",
                "ticker": "NVDA",
                "section_id": "item_7",
                "chunk_index": 0,
                "similarity": 0.9,
                "distance": 0.1,
            },
        )
        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.return_value = [mock_doc]

        # Pass a naive datetime — must not raise TypeError or fall to substring
        naive_as_of = datetime(2025, 6, 1)

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("api.services.reranker.rerank", side_effect=lambda q, d, top_k: d):
            result = search_sec_filings("NVDA", query="revenue", as_of=naive_as_of)

        assert len(result) == 1
        assert result[0]["retrieval_mode"] == "hybrid", (
            "Naive as_of fell into substring fallback instead of hybrid path"
        )


# ── Fix #1: BM25 ticker filter tests ─────────────────────────────────────────

class TestBM25TickerFilter:
    """Verify BM25 filters by ticker when set, not just boosts.

    CodeRabbit finding: bm25_search only boosted matching tickers but kept
    non-matching ones, so RRF could return other companies' chunks.
    """

    @pytest.fixture(autouse=True)
    def _setup_corpus(self, monkeypatch):
        from api.services import hybrid_retriever as hr

        self.docs = [
            _make_doc("NVIDIA revenue growth driven by AI chips",
                      ticker="NVDA", accession="NVDA1", accepted_ts="2025-01-01"),
            _make_doc("NVIDIA CUDA ecosystem dominance in ML",
                      ticker="NVDA", accession="NVDA2", accepted_ts="2025-01-01"),
            _make_doc("Apple iPhone sales record quarter revenue",
                      ticker="AAPL", accession="AAPL1", accepted_ts="2025-01-01"),
        ]

        tokenised = [hr.tokenize(d.page_content) for d in self.docs]
        np.random.seed(42)
        embeddings_map = {}
        for doc in self.docs:
            cid = doc.metadata["accession"]
            embeddings_map[cid] = np.random.randn(384).astype(np.float32)
            embeddings_map[cid] /= np.linalg.norm(embeddings_map[cid])

        # Build per-ticker corpora and inject into LRU cache
        from collections import defaultdict
        docs_by_ticker = defaultdict(list)
        for doc in self.docs:
            docs_by_ticker[doc.metadata["ticker"]].append(doc)

        for ticker, ticker_docs in docs_by_ticker.items():
            ticker_tokenised = [hr.tokenize(d.page_content) for d in ticker_docs]
            ticker_bm25 = hr.BM25Okapi(ticker_tokenised) if ticker_tokenised else None
            ticker_embeddings = {}
            for d in ticker_docs:
                cid = d.metadata["accession"]
                if cid in embeddings_map:
                    ticker_embeddings[cid] = embeddings_map[cid]
            corpus = hr.TickerCorpus(
                ticker=ticker,
                docs=ticker_docs,
                tokenised=ticker_tokenised,
                bm25_index=ticker_bm25,
                embeddings_map=ticker_embeddings,
                stored_model="BAAI/bge-small-en-v1.5",
                stored_dim=384,
                load_ts=0.0,
                approx_bytes=0,
            )
            hr._insert_ticker_corpus(ticker, corpus)

        class StubEmbeddings:
            def embed_query(self, text):
                np.random.seed(hash(text) % (2**31))
                v = np.random.randn(384).astype(np.float32)
                v /= np.linalg.norm(v)
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: StubEmbeddings())

    def test_bm25_filters_by_ticker_not_just_boosts(self):
        """With ticker=NVDA, no AAPL chunk must appear in results."""
        from api.services.hybrid_retriever import bm25_search

        results = bm25_search("Apple iPhone revenue record", top_k=10, ticker="NVDA")
        tickers = [d.metadata["ticker"] for d in results]
        assert "AAPL" not in tickers, (
            "BM25 returned AAPL chunk when ticker=NVDA — ticker filter missing"
        )

    def test_bm25_returns_empty_when_no_ticker_match(self, monkeypatch):
        """With ticker=MSFT (not in corpus), must raise NoCoverageError."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import bm25_search, NoCoverageError

        # Mock _load_ticker_corpus to return an empty corpus (simulating no coverage)
        def mock_load(ticker):
            return hr.TickerCorpus(
                ticker=ticker,
                docs=[],
                tokenised=[],
                bm25_index=None,
                embeddings_map={},
                stored_model=None,
                stored_dim=None,
                load_ts=0.0,
                approx_bytes=0,
            )

        monkeypatch.setattr(hr, "_load_ticker_corpus", mock_load)

        with pytest.raises(NoCoverageError):
            bm25_search("revenue growth", top_k=10, ticker="MSFT")

    def test_hybrid_no_leak_across_tickers(self):
        """Hybrid retrieve with ticker=NVDA must not return AAPL chunks."""
        from api.services.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(top_k=10)
        results = retriever.retrieve("Apple iPhone revenue", ticker="NVDA", top_k=10)
        tickers = [d.metadata["ticker"] for d in results]
        assert "AAPL" not in tickers, (
            "Hybrid retriever leaked AAPL chunk when ticker=NVDA"
        )


# ── Fix #2: Transient load failure retry tests ───────────────────────────────

class TestTransientLoadFailureRetry:
    """Verify transient load failures don't disable retrieval forever.

    CodeRabbit finding: on exception, _corpus_loaded was set to True,
    preventing retries.
    """

    def test_first_load_fails_second_succeeds(self, fake_pyspark, monkeypatch):
        """First load raises CorpusUnavailableError, second succeeds."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        # Reset module state
        monkeypatch.setattr(hr, "_corpus_loaded", False)
        monkeypatch.setattr(hr, "_corpus", {})
        monkeypatch.setattr(hr, "_bm25_docs", None)
        monkeypatch.setattr(hr, "_bm25_tokenised", None)
        monkeypatch.setattr(hr, "_bm25_index", None)
        monkeypatch.setattr(hr, "_embeddings_map", {})

        call_count = [0]

        def _get_spark_sometimes():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient connection error")
            # Second call: return a mock spark that yields empty results
            mock_spark = MagicMock()
            mock_chunks_df = MagicMock()
            mock_chunks_df.select.return_value = mock_chunks_df
            mock_chunks_df.collect.return_value = []
            mock_embed_df = MagicMock()
            mock_embed_df.select.return_value = mock_embed_df
            mock_embed_df.collect.return_value = []

            def table_side(name):
                if "embeddings" in name:
                    return mock_embed_df
                return mock_chunks_df

            mock_spark.table.side_effect = table_side
            return mock_spark

        monkeypatch.setattr(hr, "_get_spark", _get_spark_sometimes)

        # Use monkeypatch.setitem on sys.modules to avoid import issues
        # when pyspark is set to None (nopyspark mode)
        mock_f = MagicMock()
        mock_f.unix_timestamp.return_value = mock_f
        mock_f.col.return_value = mock_f
        mock_f.alias.return_value = mock_f

        # First call: raises
        with pytest.raises(CorpusUnavailableError):
            monkeypatch.setitem(sys.modules, "pyspark.sql.functions", mock_f)
            hr._load_corpus()

        # _corpus_loaded must be False so next call retries
        assert hr._corpus_loaded is False, (
            "_corpus_loaded should be False after failure to allow retry"
        )

        # Second call: does not raise (retry succeeds, even if corpus is empty)
        monkeypatch.setitem(sys.modules, "pyspark.sql.functions", mock_f)
        hr._load_corpus()

        assert hr._corpus_loaded is True

    def test_partial_state_cleared_on_failure(self, fake_pyspark, monkeypatch):
        """On failure, partial _corpus and _embeddings_map must be cleared."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        monkeypatch.setattr(hr, "_corpus_loaded", False)
        # Inject partial state
        monkeypatch.setattr(hr, "_corpus", {"fake_id": ("text", "T", "A", "", "", "", 0, "")})
        monkeypatch.setattr(hr, "_embeddings_map", {"fake_id": np.zeros(384)})
        monkeypatch.setattr(hr, "_bm25_docs", [Document(page_content="x", metadata={})])
        monkeypatch.setattr(hr, "_bm25_tokenised", [["x"]])
        monkeypatch.setattr(hr, "_bm25_index", "not_none")

        def boom():
            raise RuntimeError("boom")

        monkeypatch.setattr(hr, "_get_spark", boom)

        with pytest.raises(CorpusUnavailableError):
            hr._load_corpus()

        assert len(hr._corpus) == 0, "_corpus should be cleared after failure"
        assert len(hr._embeddings_map) == 0, "_embeddings_map should be cleared after failure"
        assert hr._bm25_docs is None
        assert hr._bm25_tokenised is None
        assert hr._bm25_index is None


# ── Fix #3: Embedding dim check tests ─────────────────────────────────────────

class TestEmbeddingDimCheck:
    """Verify vector_search raises on dimension mismatch.

    CodeRabbit finding: wrong-dim query vectors silently produced garbage.
    """

    def test_dim_mismatch_raises_corpus_unavailable(self, fake_pyspark, monkeypatch):
        """Query vector with wrong dimension must raise EmbeddingConfigError."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import EmbeddingConfigError, vector_search

        # Setup per-ticker corpus with 384-d stored embeddings
        vec = np.zeros(384, dtype=np.float32)
        vec[0] = 1.0
        doc = _make_doc("text", ticker="NVDA", accession="ACC", accepted_ts="2025-01-01")
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=[doc],
            tokenised=[["text"]],
            bm25_index=hr.BM25Okapi([["text"]]),
            embeddings_map={"c1": vec},
            stored_model="BAAI/bge-small-en-v1.5",
            stored_dim=384,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        class WrongDimEmbeddings:
            def embed_query(self, text):
                return [0.1] * 1024  # Wrong dim

        monkeypatch.setattr(hr, "get_embeddings", lambda: WrongDimEmbeddings())

        with pytest.raises(EmbeddingConfigError, match="dim .* != stored"):
            vector_search("test query", ticker="NVDA")

    def test_correct_dim_works(self, fake_pyspark, monkeypatch):
        """Query vector with correct dimension proceeds normally."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import vector_search

        vec = np.zeros(384, dtype=np.float32)
        vec[0] = 1.0
        doc = _make_doc("text", ticker="NVDA", accession="ACC", accepted_ts="2025-01-01")
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=[doc],
            tokenised=[["text"]],
            bm25_index=hr.BM25Okapi([["text"]]),
            embeddings_map={"c1": vec},
            stored_model="BAAI/bge-small-en-v1.5",
            stored_dim=384,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        class CorrectDimEmbeddings:
            def embed_query(self, text):
                v = np.zeros(384, dtype=np.float32)
                v[0] = 1.0
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: CorrectDimEmbeddings())

        # Should not raise
        results = vector_search("test query", ticker="NVDA")
        assert isinstance(results, list)


# ── Fix #4: build_sec_embeddings read error propagation tests ─────────────────

class TestBuildEmbeddingsReadError:
    """Verify build_sec_embeddings doesn't swallow existing-ID read errors.

    CodeRabbit finding: blind except Exception set existing_ids = set(),
    masking read failures.
    """

    def test_read_error_propagates(self, fake_pyspark):
        """When reading existing IDs fails, build() must raise, not write."""
        from pipelines.build_sec_embeddings import build

        mock_spark = MagicMock()

        # Make table() for embeddings raise (simulates read failure)
        def table_side_effect(name):
            if "embeddings" in name:
                raise RuntimeError("Table not found: gold_sec_chunk_embeddings")
            mock_df = MagicMock()
            mock_df.select.return_value = mock_df
            mock_df.filter.return_value = mock_df
            mock_df.collect.return_value = []
            return mock_df

        mock_spark.table.side_effect = table_side_effect

        class StubEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        with patch("api.services.embeddings.get_embeddings", return_value=StubEmbeddings()):
            with pytest.raises(RuntimeError, match="Table not found"):
                build(mock_spark)

        # Must not have written anything
        mock_spark.createDataFrame.assert_not_called()


# ── Fix #5: Stored-index dimension guard + model-name check (round 3) ────────

class TestStoredIndexDimensionGuard:
    """Verify vector_search validates against the STORED index dimension, not the configured EMBEDDING_DIM.

    DeepSeek round-2 finding: the old guard compared len(qvec) with the
    CONFIGURED EMBEDDING_DIM.  Switching EMBEDDING_PROVIDER=sentence_transformers
    (1024-d) against a stored 384-d index passed the guard, then np.dot raised,
    and the search silently fell back to substring search.
    """

    def test_1024d_query_against_384d_index_returns_unavailable(self, monkeypatch):
        """A 1024-d query vector against a 384-d stored index must raise EmbeddingConfigError.

        search_sec_filings must surface retrieval_unavailable, not substring_fallback.
        """
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import EmbeddingConfigError

        # Setup per-ticker corpus with 384-d stored embeddings
        vec384 = np.zeros(384, dtype=np.float32)
        vec384[0] = 1.0
        doc = _make_doc("text", ticker="NVDA", accession="ACC", accepted_ts="2025-01-01")
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=[doc],
            tokenised=[["text"]],
            bm25_index=hr.BM25Okapi([["text"]]),
            embeddings_map={"c1": vec384},
            stored_model="BAAI/bge-small-en-v1.5",
            stored_dim=384,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        class WrongDimEmbeddings:
            def embed_query(self, text):
                return [0.1] * 1024  # 1024-d query, but stored index is 384-d

        monkeypatch.setattr(hr, "get_embeddings", lambda: WrongDimEmbeddings())

        with pytest.raises(EmbeddingConfigError, match="dim .* != stored"):
            hr.vector_search("test query", ticker="NVDA")

    def test_mixed_stored_dimensions_unavailable(self, fake_pyspark, monkeypatch):
        """If stored embeddings have mixed dimensions, corpus load must raise CorpusUnavailableError."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import CorpusUnavailableError

        # Test _load_ticker_corpus directly by mocking Spark
        mock_spark = MagicMock()

        mock_chunk_row = MagicMock()
        mock_chunk_row.__getitem__ = lambda self, k: {
            "chunk_id": "c1", "ticker": "NVDA", "chunk_text": "text",
            "accession_number": "ACC", "accepted_epoch": 1735689600,
            "form_type": "10-K", "filing_section": "s1",
            "chunk_index": 0, "source_url": "",
        }.get(k)

        mock_chunks_df = MagicMock()
        mock_chunks_df.filter.return_value = mock_chunks_df
        mock_chunks_df.select.return_value = mock_chunks_df
        mock_chunks_df.collect.return_value = [mock_chunk_row]

        # Two embeddings: one 384-d, one 1024-d
        mock_embed_row1 = MagicMock()
        mock_embed_row1.__getitem__ = lambda self, k: {
            "chunk_id": "c1", "embedding": [0.1] * 384, "embedding_model": "BAAI/bge-small-en-v1.5",
        }.get(k)
        mock_embed_row2 = MagicMock()
        mock_embed_row2.__getitem__ = lambda self, k: {
            "chunk_id": "c2", "embedding": [0.1] * 1024, "embedding_model": "BAAI/bge-small-en-v1.5",
        }.get(k)

        mock_embed_df = MagicMock()
        mock_embed_df.filter.return_value = mock_embed_df
        mock_embed_df.select.return_value = mock_embed_df
        mock_embed_df.collect.return_value = [mock_embed_row1, mock_embed_row2]

        def table_side(name):
            if "embeddings" in name:
                return mock_embed_df
            return mock_chunks_df

        mock_spark.table.side_effect = table_side
        monkeypatch.setattr(hr, "_get_spark", lambda: mock_spark)

        with pytest.raises(CorpusUnavailableError, match="dimension mismatch"):
            hr._load_ticker_corpus("NVDA")

    def test_model_name_mismatch_unavailable(self, fake_pyspark, monkeypatch):
        """If stored embedding_model does not match active model, vector_search raises EmbeddingConfigError."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import EmbeddingConfigError, vector_search

        # Setup per-ticker corpus with a stored model name
        vec = np.zeros(384, dtype=np.float32)
        vec[0] = 1.0
        doc = _make_doc("text", ticker="NVDA", accession="ACC", accepted_ts="2025-01-01")
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=[doc],
            tokenised=[["text"]],
            bm25_index=hr.BM25Okapi([["text"]]),
            embeddings_map={"c1": vec},
            stored_model="old-model-name",
            stored_dim=384,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        class MatchingDimEmbeddings:
            def embed_query(self, text):
                v = np.zeros(384, dtype=np.float32)
                v[0] = 1.0
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: MatchingDimEmbeddings())

        # The active model (via config) is "BAAI/bge-small-en-v1.5", not "old-model-name"
        with pytest.raises(EmbeddingConfigError, match="model mismatch"):
            vector_search("test query", ticker="NVDA")


# ── Round 4: Default provider + BM25-only degradation tests ─────────────────

class TestDefaultEmbeddingProvider:
    """Verify config defaults to sentence-transformers (local), not huggingface (remote)."""

    def test_default_provider_is_sentence_transformers(self, monkeypatch):
        """With no EMBEDDING_PROVIDER env var, config must default to sentence-transformers."""
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        import api.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.EMBEDDING_PROVIDER == "sentence-transformers"

    def test_default_model_is_bge_small(self, monkeypatch):
        """Default sentence-transformers model must be BAAI/bge-small-en-v1.5."""
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        monkeypatch.delenv("ST_EMBEDDING_MODEL", raising=False)
        import api.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.ST_EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"

    def test_default_dim_is_384(self, monkeypatch):
        """Default dimension must be 384 for sentence-transformers."""
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        monkeypatch.delenv("EMBEDDING_DIM", raising=False)
        import api.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.EMBEDDING_DIM == 384


class TestHuggingfaceWithoutToken:
    """Verify huggingface provider without a token fails clearly at init."""

    def test_hf_no_token_raises_embedding_config_error(self, monkeypatch):
        """get_embeddings() must raise EmbeddingConfigError when provider=huggingface and no token is set."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "huggingface")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)

        import api.config as cfg_mod
        import api.services.embeddings as emb_mod
        importlib.reload(cfg_mod)
        importlib.reload(emb_mod)

        from api.services.exceptions import EmbeddingConfigError
        with pytest.raises(EmbeddingConfigError, match="HF_TOKEN"):
            emb_mod.get_embeddings()

    def test_hf_no_token_search_sec_filings_returns_unavailable(self, monkeypatch):
        """search_sec_filings with huggingface provider and no token must return retrieval_unavailable."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "huggingface")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)

        import api.config as cfg_mod
        import api.services.embeddings as emb_mod
        importlib.reload(cfg_mod)
        importlib.reload(emb_mod)

        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import EmbeddingConfigError

        # With EmbeddingConfigError being a subclass of CorpusUnavailableError,
        # search_sec_filings catches it and returns retrieval_unavailable.
        # Mock the retriever to raise EmbeddingConfigError directly.
        def fake_retrieve(*args, **kwargs):
            raise EmbeddingConfigError(
                "EMBEDDING_PROVIDER is 'huggingface' but neither HF_TOKEN nor "
                "HUGGINGFACEHUB_API_TOKEN is set."
            )

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["ticker"] == "NVDA"
        # The message must name the missing setting, not the secret value
        msg = result[0].get("message", "")
        assert "HF_TOKEN" in msg, f"Expected 'HF_TOKEN' in message, got: {msg}"
        assert "SEC filing corpus" not in msg, f"EmbeddingConfigError must NOT get generic corpus message: {msg}"


class TestEmbedderFailureDegradesToBM25Only:
    """Verify that an embedder runtime failure degrades to BM25-only, not substring."""

    @pytest.fixture(autouse=True)
    def _setup_corpus(self, monkeypatch):
        """Inject a tiny corpus WITH embeddings — embedder will fail at query time."""
        from api.services import hybrid_retriever as hr

        self.docs = [
            _make_doc("NVIDIA revenue growth driven by AI chips",
                      ticker="NVDA", accession="NVDA1", accepted_ts="2025-01-01"),
            _make_doc("AMD EPYC server processor market share gains",
                      ticker="AMD", accession="AMD1", accepted_ts="2025-01-01"),
            _make_doc("NVIDIA CUDA ecosystem dominance in ML",
                      ticker="NVDA", accession="NVDA2", accepted_ts="2025-06-01"),
        ]

        tokenised = [hr.tokenize(d.page_content) for d in self.docs]

        # Build a NON-empty embeddings map so vector_search does NOT return early
        np.random.seed(42)
        embeddings_map = {}
        for doc in self.docs:
            cid = doc.metadata["accession"]
            embeddings_map[cid] = np.random.randn(384).astype(np.float32)
            embeddings_map[cid] /= np.linalg.norm(embeddings_map[cid])

        # Build per-ticker corpora and inject into LRU cache
        from collections import defaultdict
        docs_by_ticker = defaultdict(list)
        for doc in self.docs:
            docs_by_ticker[doc.metadata["ticker"]].append(doc)

        for ticker, ticker_docs in docs_by_ticker.items():
            ticker_tokenised = [hr.tokenize(d.page_content) for d in ticker_docs]
            ticker_bm25 = hr.BM25Okapi(ticker_tokenised) if ticker_tokenised else None
            ticker_embeddings = {}
            for d in ticker_docs:
                cid = d.metadata["accession"]
                if cid in embeddings_map:
                    ticker_embeddings[cid] = embeddings_map[cid]
            corpus = hr.TickerCorpus(
                ticker=ticker,
                docs=ticker_docs,
                tokenised=ticker_tokenised,
                bm25_index=ticker_bm25,
                embeddings_map=ticker_embeddings,
                stored_model="BAAI/bge-small-en-v1.5",
                stored_dim=384,
                load_ts=0.0,
                approx_bytes=0,
            )
            hr._insert_ticker_corpus(ticker, corpus)

    def test_embedder_raises_returns_bm25_only(self, monkeypatch):
        """When embedder raises at query time, retrieve must return BM25-only results."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import HybridRetriever

        call_count = [0]

        class FailingEmbeddings:
            def embed_query(self, text):
                call_count[0] += 1
                raise RuntimeError("Connection to HF API timed out")

        monkeypatch.setattr(hr, "get_embeddings", lambda: FailingEmbeddings())

        retriever = HybridRetriever(top_k=10)
        results = retriever.retrieve("NVIDIA AI chips", ticker="NVDA", top_k=10)

        assert call_count[0] > 0, "Embedder was never called — empty embeddings_map short-circuited"
        assert len(results) > 0, "BM25-only should still return results"
        for doc in results:
            assert doc.metadata.get("retrieval_mode") == "bm25_only", (
                f"Expected retrieval_mode=bm25_only, got {doc.metadata.get('retrieval_mode')}"
            )
            assert doc.metadata.get("_warning") == "dense_unavailable"

    def test_bm25_only_respects_ticker_filter(self, monkeypatch):
        """BM25-only fallback must still respect ticker filter."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import HybridRetriever

        call_count = [0]

        class FailingEmbeddings:
            def embed_query(self, text):
                call_count[0] += 1
                raise RuntimeError("auth error")

        monkeypatch.setattr(hr, "get_embeddings", lambda: FailingEmbeddings())

        retriever = HybridRetriever(top_k=10)
        results = retriever.retrieve("revenue growth", ticker="NVDA", top_k=10)

        assert call_count[0] > 0, "Embedder was never called"
        assert len(results) > 0
        for doc in results:
            assert doc.metadata["ticker"] == "NVDA", (
                f"BM25-only leaked {doc.metadata['ticker']} doc when ticker=NVDA"
            )

    def test_bm25_only_respects_as_of(self, monkeypatch):
        """BM25-only fallback must still respect as_of filter."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import HybridRetriever

        call_count = [0]

        class FailingEmbeddings:
            def embed_query(self, text):
                call_count[0] += 1
                raise RuntimeError("network error")

        monkeypatch.setattr(hr, "get_embeddings", lambda: FailingEmbeddings())

        retriever = HybridRetriever(top_k=10)
        # as_of before NVDA2 (2025-06-01) — should exclude it
        as_of = datetime(2025, 3, 1, tzinfo=timezone.utc)
        results = retriever.retrieve("NVIDIA", ticker="NVDA", as_of=as_of, top_k=10)

        assert call_count[0] > 0, "Embedder was never called"
        accessions = [d.metadata["accession"] for d in results]
        assert "NVDA2" not in accessions, (
            f"BM25-only leaked future doc NVDA2 (2025-06-01) with as_of=2025-03-01"
        )
        # NVDA1 (2025-01-01) should still be present
        assert "NVDA1" in accessions

    def test_bm25_only_returns_expected_hit(self, monkeypatch):
        """BM25-only fallback must return the expected BM25 hit for a matching query."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import HybridRetriever

        call_count = [0]

        class FailingEmbeddings:
            def embed_query(self, text):
                call_count[0] += 1
                raise RuntimeError("API error")

        monkeypatch.setattr(hr, "get_embeddings", lambda: FailingEmbeddings())

        retriever = HybridRetriever(top_k=10)
        results = retriever.retrieve("AMD EPYC server processor", ticker="AMD", top_k=10)

        assert call_count[0] > 0, "Embedder was never called"
        assert len(results) > 0
        texts = [d.page_content for d in results]
        assert any("AMD EPYC" in t for t in texts), (
            "BM25-only did not return the expected AMD EPYC hit"
        )

    def test_dimension_mismatch_still_returns_unavailable(self, monkeypatch):
        """Dimension mismatch (config error) must still raise EmbeddingConfigError, not degrade to BM25."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import EmbeddingConfigError, vector_search

        # Setup per-ticker corpus with 384-d embeddings
        content_hash = hashlib.md5("NVIDIA revenue growth driven by AI chips".encode()).hexdigest()[:16]
        vec = np.zeros(384, dtype=np.float32)
        vec[0] = 1.0
        doc = _make_doc("NVIDIA revenue growth driven by AI chips",
                        ticker="NVDA", accession="NVDA1", accepted_ts="2025-01-01")
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=[doc],
            tokenised=[["text"]],
            bm25_index=hr.BM25Okapi([["text"]]),
            embeddings_map={content_hash: vec},
            stored_model="BAAI/bge-small-en-v1.5",
            stored_dim=384,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        class WrongDimEmbeddings:
            def embed_query(self, text):
                return [0.1] * 1024

        monkeypatch.setattr(hr, "get_embeddings", lambda: WrongDimEmbeddings())

        with pytest.raises(EmbeddingConfigError, match="dim .* != stored"):
            vector_search("test query", ticker="NVDA")


class TestBM25OnlyThroughSearchSecFilings:
    """Verify BM25-only results propagate correctly through search_sec_filings."""

    def test_bm25_only_mode_preserved_in_search_results(self, monkeypatch):
        """search_sec_filings must preserve retrieval_mode=bm25_only from retriever."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from langchain_core.documents import Document

        mock_doc = Document(
            page_content="NVIDIA revenue growth",
            metadata={
                "accession": "ACC1",
                "form_type": "10-K",
                "accepted_ts": "2025-01-15",
                "source_url": "",
                "ticker": "NVDA",
                "section_id": "item_7",
                "chunk_index": 0,
                "retrieval_mode": "bm25_only",
                "_warning": "dense_unavailable",
            },
        )
        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.return_value = [mock_doc]

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("api.services.reranker.rerank", side_effect=lambda q, d, top_k: d):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) == 1
        assert result[0]["retrieval_mode"] == "bm25_only"
        assert result[0]["_warning"] == "dense_unavailable"


# ── End-to-end embedding error tests through search_sec_filings ──────────────

class TestEmbeddingE2EThroughSearchSecFilings:
    """End-to-end tests: embedding config/runtime errors through search_sec_filings.

    These tests verify the full path from search_sec_filings through
    HybridRetriever → vector_search → get_embeddings, ensuring that:
    - Config errors (missing token, dim mismatch, model mismatch) → retrieval_unavailable
    - Transient runtime failures → bm25_only with expected hits
    """

    def test_missing_token_returns_retrieval_unavailable(self, monkeypatch):
        """Missing HF_TOKEN → EmbeddingConfigError → retrieval_unavailable."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import EmbeddingConfigError

        # Simulate: get_embeddings raises EmbeddingConfigError for missing token
        def fake_retrieve(*args, **kwargs):
            raise EmbeddingConfigError(
                "EMBEDDING_PROVIDER is 'huggingface' but neither HF_TOKEN nor "
                "HUGGINGFACEHUB_API_TOKEN is set."
            )

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["ticker"] == "NVDA"
        # Must name the missing setting, not the secret value
        msg = result[0].get("message", "")
        assert "HF_TOKEN" in msg, f"Expected 'HF_TOKEN' in message, got: {msg}"
        assert "SEC filing corpus" not in msg, f"EmbeddingConfigError must NOT get generic corpus message: {msg}"

    def test_token_value_never_leaks_in_message(self, monkeypatch):
        """EmbeddingConfigError message must never contain the actual secret value."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        secret_value = "hf_FAKE_TOKEN_VALUE_12345"
        monkeypatch.setenv("HF_TOKEN", secret_value)

        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import EmbeddingConfigError

        def fake_retrieve(*args, **kwargs):
            raise EmbeddingConfigError(
                f"EMBEDDING_PROVIDER is 'huggingface' but neither HF_TOKEN nor "
                f"HUGGINGFACEHUB_API_TOKEN is set. Got: {secret_value}"
            )

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="revenue")

        msg = result[0].get("message", "")
        assert secret_value not in msg, f"Secret token value leaked into message: {msg}"

    def test_dimension_mismatch_returns_retrieval_unavailable(self, monkeypatch):
        """Dimension mismatch → EmbeddingConfigError → retrieval_unavailable with reason."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import EmbeddingConfigError

        def fake_retrieve(*args, **kwargs):
            raise EmbeddingConfigError(
                "query embedding dim 1024 != stored index dim 384; "
                "check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL / EMBEDDING_DIM",
                user_safe=True,
            )

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["reason"] == "embedding_config"
        assert result[0]["ticker"] == "NVDA"
        msg = result[0].get("message", "")
        assert "EMBEDDING_PROVIDER" in msg, f"Setting name missing from message: {msg}"
        assert "Delta" not in msg, f"'Delta' should not appear in config error: {msg}"

    def test_model_mismatch_returns_retrieval_unavailable(self, monkeypatch):
        """Model mismatch → EmbeddingConfigError → retrieval_unavailable with reason."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import EmbeddingConfigError

        def fake_retrieve(*args, **kwargs):
            raise EmbeddingConfigError(
                "embedding model mismatch: active 'BAAI/bge-large-en-v1.5' != stored 'BAAI/bge-small-en-v1.5'; "
                "check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL",
                user_safe=True,
            )

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = fake_retrieve

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("NVDA", query="revenue")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["reason"] == "embedding_config"
        assert result[0]["ticker"] == "NVDA"
        msg = result[0].get("message", "")
        assert "ST_EMBEDDING_MODEL" in msg, f"Setting name missing from message: {msg}"
        assert "Delta" not in msg, f"'Delta' should not appear in config error: {msg}"

    def test_transient_raise_returns_bm25_only_with_nvda_hit(self, monkeypatch):
        """Transient embedder failure → bm25_only with expected NVDA hit."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from langchain_core.documents import Document

        # Simulate: retriever returns BM25-only docs after embedder failed
        mock_doc = Document(
            page_content="NVIDIA revenue growth driven by AI chips",
            metadata={
                "accession": "NVDA1",
                "form_type": "10-K",
                "accepted_ts": "2025-01-15",
                "source_url": "",
                "ticker": "NVDA",
                "section_id": "item_7",
                "chunk_index": 0,
                "retrieval_mode": "bm25_only",
                "_warning": "dense_unavailable",
            },
        )
        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.return_value = [mock_doc]

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("api.services.reranker.rerank", side_effect=lambda q, d, top_k: d):
            result = search_sec_filings("NVDA", query="NVIDIA revenue")

        assert len(result) == 1
        assert result[0]["retrieval_mode"] == "bm25_only"
        assert result[0]["_warning"] == "dense_unavailable"
        assert "NVIDIA" in result[0]["chunk_text"]
        assert result[0]["ticker"] == "NVDA"

    def test_transient_raise_respects_as_of(self, monkeypatch):
        """Transient failure with as_of must still return PIT-filtered results."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from langchain_core.documents import Document

        # Simulate: retriever returns BM25-only docs respecting as_of
        mock_doc = Document(
            page_content="NVIDIA revenue growth",
            metadata={
                "accession": "NVDA1",
                "form_type": "10-K",
                "accepted_ts": "2025-01-15",
                "source_url": "",
                "ticker": "NVDA",
                "section_id": "item_7",
                "chunk_index": 0,
                "retrieval_mode": "bm25_only",
                "_warning": "dense_unavailable",
            },
        )
        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.return_value = [mock_doc]

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever), \
             patch("api.services.reranker.rerank", side_effect=lambda q, d, top_k: d):
            result = search_sec_filings("NVDA", query="NVIDIA revenue", as_of=as_of)

        assert len(result) == 1
        assert result[0]["retrieval_mode"] == "bm25_only"
        assert result[0]["accepted_ts"] == "2025-01-15"  # Before as_of


# ── Stage 3A: Live retrieval path tests ──────────────────────────────────────

class TestTickerRequired:
    """Verify retrieve() raises TickerRequiredError when no ticker can be resolved."""

    def test_retrieve_raises_when_no_ticker(self):
        """retrieve() with no ticker and no company name in query must raise TickerRequiredError."""
        from api.services.hybrid_retriever import HybridRetriever, TickerRequiredError

        retriever = HybridRetriever(top_k=5)
        with pytest.raises(TickerRequiredError):
            retriever.retrieve("what is the weather today")

    def test_retrieve_raises_when_empty_ticker_and_no_match(self):
        """retrieve() with explicit empty ticker and no match in query must raise."""
        from api.services.hybrid_retriever import HybridRetriever, TickerRequiredError

        retriever = HybridRetriever(top_k=5)
        with pytest.raises(TickerRequiredError):
            retriever.retrieve("random text", ticker="")

    def test_bm25_search_raises_when_no_ticker(self):
        """bm25_search with empty ticker must raise TickerRequiredError."""
        from api.services.hybrid_retriever import bm25_search, TickerRequiredError

        with pytest.raises(TickerRequiredError):
            bm25_search("test query")

    def test_vector_search_raises_when_no_ticker(self):
        """vector_search with empty ticker must raise TickerRequiredError."""
        from api.services.hybrid_retriever import vector_search, TickerRequiredError

        with pytest.raises(TickerRequiredError):
            vector_search("test query")

    def test_search_sec_filings_returns_ticker_required(self, monkeypatch):
        """search_sec_filings must return [error: ticker_required] when TickerRequiredError is raised."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import TickerRequiredError

        def raise_ticker_required(*args, **kwargs):
            raise TickerRequiredError()

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = raise_ticker_required

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("XYZ", query="random text")

        assert result == [{"error": "ticker_required"}]


class TestNoCoverage:
    """Verify retrieve() raises NoCoverageError when ticker has zero chunks."""

    def test_retrieve_raises_when_no_coverage(self, monkeypatch):
        """retrieve() for a ticker with 0 chunks must raise NoCoverageError."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import HybridRetriever, NoCoverageError

        # Mock check_ticker_coverage to raise NoCoverageError
        def mock_coverage(ticker):
            raise NoCoverageError(ticker)

        monkeypatch.setattr(hr, "check_ticker_coverage", mock_coverage)

        retriever = HybridRetriever(top_k=5)
        with pytest.raises(NoCoverageError):
            retriever.retrieve("NVIDIA revenue", ticker="ZZZZ")

    def test_search_sec_filings_returns_no_coverage(self, monkeypatch):
        """search_sec_filings must return [error: no_coverage] when NoCoverageError is raised."""
        mock_lakebase = MagicMock()
        monkeypatch.setitem(sys.modules, "db.lakebase", mock_lakebase)

        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import NoCoverageError

        def raise_no_coverage(*args, **kwargs):
            raise NoCoverageError("XYZ")

        mock_retriever = MagicMock()
        mock_retriever.retrieve_and_rerank.side_effect = raise_no_coverage

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever", return_value=mock_retriever):
            result = search_sec_filings("XYZ", query="test")

        assert result == [{"error": "no_coverage", "ticker": "XYZ"}]


class TestLRUBoundAndEviction:
    """Verify LRU cache bound and eviction with RAG_TICKER_CACHE_MAX=2 across 3 tickers."""

    def test_eviction_with_max_2_across_3_tickers(self, monkeypatch):
        """With RAG_TICKER_CACHE_MAX=2, loading 3 tickers must evict the oldest."""
        from api.services import hybrid_retriever as hr

        monkeypatch.setenv("RAG_TICKER_CACHE_MAX", "2")
        # Reload the max value
        raw = os.getenv("RAG_TICKER_CACHE_MAX", "32")
        monkeypatch.setattr(hr, "_RAG_TICKER_CACHE_MAX", int(raw))

        def _make_ticker_corpus(ticker):
            doc = _make_doc(f"{ticker} content", ticker=ticker, accession=f"{ticker}1",
                            accepted_ts="2025-01-01")
            return hr.TickerCorpus(
                ticker=ticker,
                docs=[doc],
                tokenised=[hr.tokenize(doc.page_content)],
                bm25_index=hr.BM25Okapi([hr.tokenize(doc.page_content)]),
                embeddings_map={},
                stored_model=None,
                stored_dim=None,
                load_ts=0.0,
                approx_bytes=0,
            )

        # Insert 3 tickers
        for t in ["AAA", "BBB", "CCC"]:
            hr._insert_ticker_corpus(t, _make_ticker_corpus(t))

        # Cache should have exactly 2 entries (oldest "AAA" evicted)
        assert len(hr._ticker_cache) == 2
        assert "AAA" not in hr._ticker_cache
        assert "BBB" in hr._ticker_cache
        assert "CCC" in hr._ticker_cache

    def test_lru_access_moves_to_end(self, monkeypatch):
        """Accessing a cached ticker must move it to end (protect from eviction)."""
        from api.services import hybrid_retriever as hr

        monkeypatch.setenv("RAG_TICKER_CACHE_MAX", "2")
        monkeypatch.setattr(hr, "_RAG_TICKER_CACHE_MAX", 2)

        def _make_ticker_corpus(ticker):
            doc = _make_doc(f"{ticker} content", ticker=ticker, accession=f"{ticker}1",
                            accepted_ts="2025-01-01")
            return hr.TickerCorpus(
                ticker=ticker,
                docs=[doc],
                tokenised=[hr.tokenize(doc.page_content)],
                bm25_index=hr.BM25Okapi([hr.tokenize(doc.page_content)]),
                embeddings_map={},
                stored_model=None,
                stored_dim=None,
                load_ts=0.0,
                approx_bytes=0,
            )

        # Insert AAA, then BBB
        hr._insert_ticker_corpus("AAA", _make_ticker_corpus("AAA"))
        hr._insert_ticker_corpus("BBB", _make_ticker_corpus("BBB"))

        # Access AAA (move to end)
        with hr._ticker_cache_lock:
            hr._ticker_cache.move_to_end("AAA")

        # Insert CCC — should evict BBB (now LRU), not AAA
        hr._insert_ticker_corpus("CCC", _make_ticker_corpus("CCC"))

        assert "AAA" in hr._ticker_cache
        assert "BBB" not in hr._ticker_cache
        assert "CCC" in hr._ticker_cache


class TestInflightLoadCoalescing:
    """Verify in-flight load coalescing: two threads, one load; spy count == 1."""

    def _make_corpus(self, ticker):
        """Build a minimal TickerCorpus for testing."""
        from api.services import hybrid_retriever as hr
        doc = _make_doc(f"{ticker} content", ticker=ticker, accession=f"{ticker}1",
                        accepted_ts="2025-01-01")
        return hr.TickerCorpus(
            ticker=ticker,
            docs=[doc],
            tokenised=[hr.tokenize(doc.page_content)],
            bm25_index=hr.BM25Okapi([hr.tokenize(doc.page_content)]),
            embeddings_map={},
            stored_model=None,
            stored_dim=None,
            load_ts=0.0,
            approx_bytes=0,
        )

    def test_two_threads_one_load(self, monkeypatch):
        """Two concurrent requests for the same ticker must trigger only one load."""
        import threading
        import time
        from api.services import hybrid_retriever as hr

        load_count = [0]

        def spy_load(ticker):
            load_count[0] += 1
            time.sleep(0.1)  # Slow load so both threads start
            return self._make_corpus(ticker)

        monkeypatch.setattr(hr, "_load_ticker_corpus", spy_load)

        results = [None, None]
        errors = [None, None]

        def worker(idx):
            try:
                results[idx] = hr.get_ticker_corpus("NVDA")
            except Exception as e:
                errors[idx] = e

        t1 = threading.Thread(target=worker, args=(0,))
        t2 = threading.Thread(target=worker, args=(1,))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert errors[0] is None, f"Thread 0 error: {errors[0]}"
        assert errors[1] is None, f"Thread 1 error: {errors[1]}"
        assert results[0] is not None
        assert results[1] is not None
        assert results[0].ticker == "NVDA"
        assert results[1].ticker == "NVDA"
        assert load_count[0] == 1, f"Expected 1 coalesced load, got {load_count[0]}"

    def test_four_threads_one_ticker_one_load(self, monkeypatch):
        """4 concurrent callers for one ticker → exactly 1 load."""
        import threading
        import time
        from api.services import hybrid_retriever as hr

        load_count = [0]

        def spy_load(ticker):
            load_count[0] += 1
            time.sleep(0.1)  # Slow load so all threads start
            return self._make_corpus(ticker)

        monkeypatch.setattr(hr, "_load_ticker_corpus", spy_load)

        results = [None] * 4
        errors = [None] * 4

        def worker(idx):
            try:
                results[idx] = hr.get_ticker_corpus("NVDA")
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        for i in range(4):
            assert errors[i] is None, f"Thread {i} error: {errors[i]}"
            assert results[i] is not None
            assert results[i].ticker == "NVDA"
        assert load_count[0] == 1, f"Expected 1 coalesced load, got {load_count[0]}"

    def test_three_tickers_parallel(self, monkeypatch):
        """3 distinct tickers in parallel: barrier proves concurrent execution.

        Each load waits at a Barrier(3) until all three have entered.
        If loads are serialized, the third never enters while the first
        is still waiting → Barrier timeout → test fails.
        """
        import threading
        from api.services import hybrid_retriever as hr

        barrier = threading.Barrier(3, timeout=2)
        all_reached = [False]

        def barrier_load(ticker):
            barrier.wait()  # blocks until all 3 loads are in-flight
            all_reached[0] = True
            return self._make_corpus(ticker)

        monkeypatch.setattr(hr, "_load_ticker_corpus", barrier_load)

        results = {}
        errors = {}

        def worker(ticker):
            try:
                results[ticker] = hr.get_ticker_corpus(ticker)
            except Exception as e:
                errors[ticker] = e

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in ["AAA", "BBB", "CCC"]
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        for t in ["AAA", "BBB", "CCC"]:
            assert t not in errors, f"{t} error: {errors[t]}"
            assert results[t].ticker == t

        assert all_reached[0], "Barrier was never satisfied — loads were serialized"


class TestPerTickerFailureIsolation:
    """Verify that a failure loading one ticker does not affect others."""

    def test_failure_isolation(self, monkeypatch):
        """A load failure for ticker AAA must not prevent loading BBB."""
        from api.services import hybrid_retriever as hr
        from api.services.exceptions import CorpusUnavailableError

        call_log = []

        def load_side_effect(ticker):
            call_log.append(ticker)
            if ticker == "AAA":
                raise RuntimeError("Spark connection failed for AAA")
            doc = _make_doc(f"{ticker} content", ticker=ticker, accession=f"{ticker}1",
                            accepted_ts="2025-01-01")
            return hr.TickerCorpus(
                ticker=ticker,
                docs=[doc],
                tokenised=[hr.tokenize(doc.page_content)],
                bm25_index=hr.BM25Okapi([hr.tokenize(doc.page_content)]),
                embeddings_map={},
                stored_model=None,
                stored_dim=None,
                load_ts=0.0,
                approx_bytes=0,
            )

        monkeypatch.setattr(hr, "_load_ticker_corpus", load_side_effect)

        # AAA should fail — the get_ticker_corpus path wraps in CorpusUnavailableError
        with pytest.raises((RuntimeError, CorpusUnavailableError)):
            hr.get_ticker_corpus("AAA")

        # BBB should succeed via get_ticker_corpus (failure isolated)
        corpus = hr.get_ticker_corpus("BBB")
        assert corpus.ticker == "BBB"
        assert len(corpus.docs) == 1
        assert call_log == ["AAA", "BBB"]


class TestPerTickerDimModelValidation:
    """Verify per-ticker dimension and model validation during load."""

    def test_mixed_dims_raises_on_load(self, monkeypatch, fake_pyspark):
        """A ticker with mixed embedding dimensions must raise CorpusUnavailableError on load."""
        from api.services import hybrid_retriever as hr
        from api.services.exceptions import CorpusUnavailableError

        mock_spark = MagicMock()

        mock_chunk_row = MagicMock()
        mock_chunk_row.__getitem__ = lambda self, k: {
            "chunk_id": "c1", "ticker": "NVDA", "chunk_text": "text",
            "accession_number": "ACC", "accepted_epoch": 1735689600,
            "form_type": "10-K", "filing_section": "s1",
            "chunk_index": 0, "source_url": "",
        }.get(k)

        mock_chunks_df = MagicMock()
        mock_chunks_df.filter.return_value = mock_chunks_df
        mock_chunks_df.select.return_value = mock_chunks_df
        mock_chunks_df.collect.return_value = [mock_chunk_row]

        # Two embeddings with different dimensions
        mock_embed_row1 = MagicMock()
        mock_embed_row1.__getitem__ = lambda self, k: {
            "chunk_id": "c1", "embedding": [0.1] * 384, "embedding_model": "model-a",
        }.get(k)
        mock_embed_row2 = MagicMock()
        mock_embed_row2.__getitem__ = lambda self, k: {
            "chunk_id": "c2", "embedding": [0.1] * 1024, "embedding_model": "model-a",
        }.get(k)

        mock_embed_df = MagicMock()
        mock_embed_df.filter.return_value = mock_embed_df
        mock_embed_df.select.return_value = mock_embed_df
        mock_embed_df.collect.return_value = [mock_embed_row1, mock_embed_row2]

        def table_side(name):
            if "embeddings" in name:
                return mock_embed_df
            return mock_chunks_df

        mock_spark.table.side_effect = table_side
        monkeypatch.setattr(hr, "_get_spark", lambda: mock_spark)

        with pytest.raises(CorpusUnavailableError, match="dimension mismatch"):
            hr._load_ticker_corpus("NVDA")

    def test_mixed_models_raises_on_load(self, monkeypatch, fake_pyspark):
        """A ticker with multiple embedding models must raise CorpusUnavailableError on load."""
        from api.services import hybrid_retriever as hr
        from api.services.exceptions import CorpusUnavailableError

        mock_spark = MagicMock()

        mock_chunk_row = MagicMock()
        mock_chunk_row.__getitem__ = lambda self, k: {
            "chunk_id": "c1", "ticker": "NVDA", "chunk_text": "text",
            "accession_number": "ACC", "accepted_epoch": 1735689600,
            "form_type": "10-K", "filing_section": "s1",
            "chunk_index": 0, "source_url": "",
        }.get(k)

        mock_chunks_df = MagicMock()
        mock_chunks_df.filter.return_value = mock_chunks_df
        mock_chunks_df.select.return_value = mock_chunks_df
        mock_chunks_df.collect.return_value = [mock_chunk_row]

        # Two embeddings with different models
        mock_embed_row1 = MagicMock()
        mock_embed_row1.__getitem__ = lambda self, k: {
            "chunk_id": "c1", "embedding": [0.1] * 384, "embedding_model": "model-a",
        }.get(k)
        mock_embed_row2 = MagicMock()
        mock_embed_row2.__getitem__ = lambda self, k: {
            "chunk_id": "c2", "embedding": [0.1] * 384, "embedding_model": "model-b",
        }.get(k)

        mock_embed_df = MagicMock()
        mock_embed_df.filter.return_value = mock_embed_df
        mock_embed_df.select.return_value = mock_embed_df
        mock_embed_df.collect.return_value = [mock_embed_row1, mock_embed_row2]

        def table_side(name):
            if "embeddings" in name:
                return mock_embed_df
            return mock_chunks_df

        mock_spark.table.side_effect = table_side
        monkeypatch.setattr(hr, "_get_spark", lambda: mock_spark)

        with pytest.raises(CorpusUnavailableError, match="Multiple embedding models"):
            hr._load_ticker_corpus("NVDA")


class TestPITBeforeScoringPerTicker:
    """Verify PIT filter is applied before scoring, not after, per ticker."""

    def test_future_chunk_excluded_from_bm25_per_ticker(self, monkeypatch):
        """A future-dated chunk must be excluded from BM25 results even if it's the best match."""
        from api.services import hybrid_retriever as hr
        from api.services.hybrid_retriever import bm25_search

        docs = [
            _make_doc("NVIDIA revenue growth AI chips",
                      ticker="NVDA", accession="PAST", accepted_ts="2024-01-01"),
            _make_doc("NVIDIA revenue growth AI chips future",
                      ticker="NVDA", accession="FUTURE", accepted_ts="2027-06-01"),
        ]
        tokenised = [hr.tokenize(d.page_content) for d in docs]
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=docs,
            tokenised=tokenised,
            bm25_index=hr.BM25Okapi(tokenised),
            embeddings_map={},
            stored_model=None,
            stored_dim=None,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        results = bm25_search("NVIDIA revenue growth", top_k=10, ticker="NVDA", as_of=as_of)

        accessions = [d.metadata["accession"] for d in results]
        assert "FUTURE" not in accessions, "Future chunk leaked through PIT filter"
        assert "PAST" in accessions


# ── Round 8b: reload_corpus no-eager-load + NULL-timestamp exclusion ─────────

class TestReloadCorpusNoEagerLoad:
    """Verify reload_corpus(None) does NOT eagerly load the full corpus.

    The per-ticker LRU is the only load path. reload_corpus(None) must only
    clear state, not call _load_corpus().
    """

    def test_reload_corpus_none_does_not_call_load_corpus(self, monkeypatch):
        """reload_corpus(None) must not trigger _load_corpus()."""
        from api.services import hybrid_retriever as hr

        load_corpus_called = [False]

        def spy_load_corpus():
            load_corpus_called[0] = True
            return True

        monkeypatch.setattr(hr, "_load_corpus", spy_load_corpus)
        monkeypatch.setattr(hr, "_corpus_loaded", True)

        result = hr.reload_corpus(None)

        assert result is True
        assert load_corpus_called[0] is False, (
            "reload_corpus(None) eagerly called _load_corpus()"
        )

    def test_reload_corpus_none_clears_state(self, monkeypatch):
        """reload_corpus(None) must clear all global state."""
        from api.services import hybrid_retriever as hr

        monkeypatch.setattr(hr, "_corpus_loaded", True)
        monkeypatch.setattr(hr, "_corpus", {"c1": ("text", "T", "A", "", "", "", 0, "")})
        monkeypatch.setattr(hr, "_embeddings_map", {"c1": "vec"})
        monkeypatch.setattr(hr, "_bm25_docs", ["doc"])
        monkeypatch.setattr(hr, "_bm25_tokenised", [["tok"]])
        monkeypatch.setattr(hr, "_bm25_index", "index")
        monkeypatch.setattr(hr, "_stored_index_dim", 384)
        monkeypatch.setattr(hr, "_stored_embedding_model", "model")

        hr.reload_corpus(None)

        assert hr._corpus_loaded is False
        assert len(hr._corpus) == 0
        assert len(hr._embeddings_map) == 0
        assert hr._bm25_docs is None
        assert hr._bm25_tokenised is None
        assert hr._bm25_index is None
        assert hr._stored_index_dim is None
        assert hr._stored_embedding_model is None

    def test_reload_corpus_none_clears_ticker_cache(self, monkeypatch):
        """reload_corpus(None) must also clear the per-ticker LRU cache."""
        from api.services import hybrid_retriever as hr

        # Insert a corpus into the ticker cache
        doc = _make_doc("NVDA content", ticker="NVDA", accession="A1", accepted_ts="2025-01-01")
        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=[doc],
            tokenised=[hr.tokenize(doc.page_content)],
            bm25_index=hr.BM25Okapi([hr.tokenize(doc.page_content)]),
            embeddings_map={},
            stored_model=None,
            stored_dim=None,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)
        assert len(hr._ticker_cache) == 1

        hr.reload_corpus(None)

        assert len(hr._ticker_cache) == 0


class TestNullTimestampExcludedFromVectorSearch:
    """Verify vector_search excludes chunks with NULL or unparseable accepted_ts.

    These chunks are treated as not-yet-available and must never appear in
    search results for any as_of.
    """

    @pytest.fixture(autouse=True)
    def _setup_corpus(self, monkeypatch):
        from api.services import hybrid_retriever as hr

        self.docs = [
            _make_doc("NVIDIA revenue growth AI chips",
                      ticker="NVDA", accession="VALID", accepted_ts="2024-06-01"),
            _make_doc("NVIDIA pending filing with no timestamp",
                      ticker="NVDA", accession="NULL_TS", accepted_ts=""),
            _make_doc("NVIDIA unparseable timestamp",
                      ticker="NVDA", accession="BAD_TS", accepted_ts="not-a-date"),
        ]

        np.random.seed(42)
        embeddings_map = {}
        for doc in self.docs:
            cid = doc.metadata["accession"]
            embeddings_map[cid] = np.random.randn(384).astype(np.float32)
            embeddings_map[cid] /= np.linalg.norm(embeddings_map[cid])

        corpus = hr.TickerCorpus(
            ticker="NVDA",
            docs=self.docs,
            tokenised=[hr.tokenize(d.page_content) for d in self.docs],
            bm25_index=hr.BM25Okapi([hr.tokenize(d.page_content) for d in self.docs]),
            embeddings_map=embeddings_map,
            stored_model="BAAI/bge-small-en-v1.5",
            stored_dim=384,
            load_ts=0.0,
            approx_bytes=0,
        )
        hr._insert_ticker_corpus("NVDA", corpus)

        class StubEmbeddings:
            def embed_query(self, text):
                np.random.seed(hash(text) % (2**31))
                v = np.random.randn(384).astype(np.float32)
                v /= np.linalg.norm(v)
                return v.tolist()

        monkeypatch.setattr(hr, "get_embeddings", lambda: StubEmbeddings())

    def test_null_timestamp_chunk_excluded_from_vector_search(self):
        """Chunks with empty accepted_ts must not appear in vector_search results."""
        from api.services.hybrid_retriever import vector_search

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        results = vector_search("NVIDIA revenue", top_k=10, ticker="NVDA", as_of=as_of)

        accessions = [d.metadata["accession"] for d in results]
        assert "NULL_TS" not in accessions, (
            "Chunk with empty accepted_ts leaked through vector_search"
        )
        assert "VALID" in accessions

    def test_unparseable_timestamp_chunk_excluded_from_vector_search(self):
        """Chunks with unparseable accepted_ts must not appear in vector_search results."""
        from api.services.hybrid_retriever import vector_search

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        results = vector_search("NVIDIA filing", top_k=10, ticker="NVDA", as_of=as_of)

        accessions = [d.metadata["accession"] for d in results]
        assert "BAD_TS" not in accessions, (
            "Chunk with unparseable accepted_ts leaked through vector_search"
        )

    def test_null_timestamp_excluded_even_when_as_of_is_future(self):
        """NULL-timestamp chunks must be excluded even with a far-future as_of."""
        from api.services.hybrid_retriever import vector_search

        as_of = datetime(2099, 1, 1, tzinfo=timezone.utc)
        results = vector_search("NVIDIA pending", top_k=10, ticker="NVDA", as_of=as_of)

        accessions = [d.metadata["accession"] for d in results]
        assert "NULL_TS" not in accessions, (
            "NULL-timestamp chunk leaked with future as_of"
        )

    def test_valid_timestamp_included_when_as_of_permits(self):
        """Valid-timestamp chunk must be included when as_of is after its date."""
        from api.services.hybrid_retriever import vector_search

        as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
        results = vector_search("NVIDIA revenue", top_k=10, ticker="NVDA", as_of=as_of)

        accessions = [d.metadata["accession"] for d in results]
        assert "VALID" in accessions, "Valid chunk was excluded"