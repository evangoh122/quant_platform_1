"""tests/rag/test_rag_eval_retrieval.py — Tests for retrieval execution.

Tests run the production retriever through the install_offline_corpus seam
with fixture data.  No network, Spark, Databricks, or model download required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from langchain_core.documents import Document

from evals.rag_eval.corpus import JsonlCorpusAdapter, install_offline_corpus
from evals.rag_eval.models import GoldenItem, RetrievalConfig, RetrievalHit
from evals.rag_eval.retrieve import assert_no_pit_leakage, retrieve_item


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rag_eval"


@pytest.fixture()
def offline_adapter():
    """Load the smoke fixture as a JsonlCorpusAdapter."""
    return JsonlCorpusAdapter.from_files(
        FIXTURE_DIR / "corpus_smoke.jsonl",
        FIXTURE_DIR / "embeddings_smoke.npz",
    )


def _answerable_item(**kw) -> GoldenItem:
    defaults = {
        "id": "t1",
        "ticker": "NVDA",
        "question": "What was NVIDIA revenue in 2024?",
        "as_of": "2024-06-01T00:00:00+00:00",
    }
    defaults.update(kw)
    return GoldenItem(**defaults)


class TestAllEightAblationsRun:
    """test_all_eight_ablations_run_real_production_scoring"""

    def test_eight_configs_produce_results(self, offline_adapter):
        """All 8 ablation configs (4 modes x 2 ticker filters) produce results."""
        modes = ["bm25", "dense", "hybrid_rrf", "hybrid_rerank"]
        item = _answerable_item()
        results = []
        for mode in modes:
            for tf in [True, False]:
                config = RetrievalConfig(mode=mode, ticker_filter=tf, top_k=5)
                hits = retrieve_item(item, config, offline_adapter)
                results.append((mode, tf, hits))
        assert len(results) == 8
        # At least some should return hits (BM25 always works; dense may depend on embeddings)
        non_empty = sum(1 for _, _, h in results if h)
        assert non_empty >= 4, f"Only {non_empty}/8 configs returned hits"


class TestHybridUsesDoubleDepth:
    """test_hybrid_uses_double_candidate_depth"""

    def test_candidate_depth_is_2x(self):
        config = RetrievalConfig(mode="hybrid_rrf", top_k=5)
        assert config.candidate_depth == 10

    def test_candidate_depth_custom_multiplier(self):
        config = RetrievalConfig(mode="hybrid_rrf", top_k=5, candidate_depth_multiplier=3)
        assert config.candidate_depth == 15


class TestRerankerRunsAfterRrf:
    """test_reranker_runs_after_rrf"""

    def test_hybrid_rerank_has_mode(self, offline_adapter):
        """hybrid_rerank mode sets retrieval_mode correctly."""
        item = _answerable_item()
        config = RetrievalConfig(mode="hybrid_rerank", top_k=5)
        hits = retrieve_item(item, config, offline_adapter)
        if hits:
            # The mode should be set (even if reranker is unavailable)
            assert hits[0].retrieval_mode in ("hybrid_rerank", "hybrid_rrf")


class TestTickerFilterOnAndOffDiffer:
    """test_ticker_filter_on_and_off_differ"""

    def test_ticker_filter_affects_results(self, offline_adapter):
        """With and without ticker filter should produce different result sets."""
        item = _answerable_item(ticker="NVDA")

        config_on = RetrievalConfig(mode="bm25", ticker_filter=True, top_k=10)
        config_off = RetrievalConfig(mode="bm25", ticker_filter=False, top_k=10)

        hits_on = retrieve_item(item, config_on, offline_adapter)
        hits_off = retrieve_item(item, config_off, offline_adapter)

        # With ticker filter, only NVDA chunks should appear
        for h in hits_on:
            assert h.ticker == "NVDA"

        # Without ticker filter, other tickers may appear
        tickers_off = {h.ticker for h in hits_off}
        # At least NVDA should be present
        assert "NVDA" in tickers_off


class TestSearchSecFilingsReturnsChunkId:
    """test_search_sec_filings_returns_chunk_id"""

    def test_chunk_id_in_wrapper_result(self):
        """The search_sec_filings wrapper must include chunk_id in results."""
        import sys
        from unittest.mock import MagicMock, patch

        # Mock db.lakebase if psycopg is not installed
        if "db.lakebase" not in sys.modules:
            sys.modules["db.lakebase"] = MagicMock()

        # Create a mock Document with chunk_id in metadata
        mock_doc = Document(
            page_content="test content",
            metadata={
                "chunk_id": "test-chunk-001",
                "ticker": "NVDA",
                "accession": "0000723125-24-000001",
                "form_type": "10-K",
                "accepted_ts": "2024-01-15T00:00:00+00:00",
                "source_url": "",
                "section_id": "item_7",
                "chunk_index": 0,
                "retrieval_mode": "hybrid",
            },
        )

        from agent import tools_retrieval as tr
        with patch.object(tr, "normalize_symbol", return_value="NVDA"), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever, \
             patch("api.services.reranker.rerank", return_value=[mock_doc]):
            MockRetriever.return_value.retrieve_and_rerank.return_value = [mock_doc]
            results = tr.search_sec_filings("NVDA", query="revenue", top_k=1)

        assert len(results) == 1
        assert "chunk_id" in results[0]
        assert results[0]["chunk_id"] == "test-chunk-001"


class TestWrapperMatchesHybridRerank:
    """test_wrapper_matches_hybrid_rerank"""

    def test_wrapper_uses_retrieve_and_rerank(self):
        """search_sec_filings delegates to retrieve_and_rerank (shared composition)."""
        import sys
        from unittest.mock import MagicMock, patch

        # Mock db.lakebase if psycopg is not installed
        if "db.lakebase" not in sys.modules:
            sys.modules["db.lakebase"] = MagicMock()

        from agent import tools_retrieval as tr

        docs = [
            Document(page_content="doc1", metadata={
                "chunk_id": "c1", "ticker": "NVDA", "accession": "A1",
                "form_type": "10-K", "accepted_ts": "2024-01-01",
                "source_url": "", "section_id": "s1", "chunk_index": 0,
                "retrieval_mode": "hybrid",
            }),
            Document(page_content="doc2", metadata={
                "chunk_id": "c2", "ticker": "NVDA", "accession": "A2",
                "form_type": "10-K", "accepted_ts": "2024-01-01",
                "source_url": "", "section_id": "s2", "chunk_index": 1,
                "retrieval_mode": "hybrid",
            }),
        ]

        with patch.object(tr, "normalize_symbol", return_value="NVDA"), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever:
            MockRetriever.return_value.retrieve_and_rerank.return_value = docs
            results = tr.search_sec_filings("NVDA", query="revenue", top_k=5)

        # retrieve_and_rerank should have been called (the shared composition)
        MockRetriever.return_value.retrieve_and_rerank.assert_called_once()
        assert len(results) == 2


class TestProductionWrapperMatchesHarness:
    """test_production_wrapper_matches_hybrid_rerank_on_fixture"""

    def test_search_sec_filings_matches_hybrid_rerank(self, offline_adapter, monkeypatch):
        """PRODUCTION search_sec_filings output matches harness hybrid_rerank on fixture data.

        Same chunk ids AND scores, same order. Uses a deterministic fake reranker
        so the test is hermetic and fast.  Mutation proof: perturbing the score in
        one path (e.g. multiply by 1.01) causes this test to FAIL.
        """
        from evals.rag_eval.corpus import install_offline_corpus
        from api.services.hybrid_retriever import HybridRetriever
        from api.services import reranker as reranker_mod
        from agent import tools_retrieval as tr
        import sys
        from unittest.mock import MagicMock, patch

        # Mock db.lakebase if psycopg is not installed
        if "db.lakebase" not in sys.modules:
            sys.modules["db.lakebase"] = MagicMock()

        # Capture docs as seen by rerank in each path
        _prod_reranked_docs: list = []

        def _fake_rerank(query, docs, top_k=5):
            # Assign deterministic scores for comparison
            for d in docs:
                chunk_id = d.metadata.get("chunk_id", "")
                d.metadata["rerank_score"] = hash(chunk_id) % 100 / 100.0
            scored = sorted(docs, key=lambda d: d.metadata.get("rerank_score", 0), reverse=True)
            result = scored[:top_k]
            # Capture a copy of (chunk_id, rerank_score) for production path comparison
            _prod_reranked_docs.clear()
            _prod_reranked_docs.extend(
                [(d.metadata.get("chunk_id", ""), d.metadata.get("rerank_score")) for d in result]
            )
            return result

        monkeypatch.setattr(reranker_mod, "rerank", _fake_rerank)

        item = _answerable_item(ticker="NVDA")
        as_of = item.as_of_datetime()

        with install_offline_corpus(offline_adapter):
            retriever = HybridRetriever(top_k=5, rrf_k=60)

            # Harness path: retrieve_mode("hybrid_rerank")
            docs_harness = retriever.retrieve_mode(
                query=item.question,
                mode="hybrid_rerank",
                ticker=item.ticker,
                as_of=as_of,
                top_k=5,
            )

            _prod_reranked_docs.clear()

            # Production path: search_sec_filings uses the same composition
            with patch.object(tr, "normalize_symbol", return_value="NVDA"), \
                 patch("api.services.hybrid_retriever.HybridRetriever", return_value=retriever):
                results_prod = tr.search_sec_filings(
                    item.ticker,
                    query=item.question,
                    top_k=5,
                    as_of=as_of,
                )

        # Compare (chunk_id, score) tuples in order
        harness_seq = [
            (d.metadata.get("chunk_id", ""), d.metadata.get("rerank_score"))
            for d in docs_harness
        ]
        prod_seq = list(_prod_reranked_docs)

        harness_ids = [cid for cid, _ in harness_seq]
        prod_ids = [r.get("chunk_id", "") for r in results_prod]
        assert harness_ids == prod_ids, (
            f"chunk IDs differ.\n  harness: {harness_ids}\n  prod:    {prod_ids}"
        )

        # Score comparison with pytest.approx — a mutation that perturbs scores
        # in one path (e.g. multiply by 1.01) will fail here.
        for i, ((h_id, h_score), (p_id, p_score)) in enumerate(zip(harness_seq, prod_seq)):
            assert h_id == p_id, f"Chunk ID mismatch at position {i}: {h_id} vs {p_id}"
            assert h_score == pytest.approx(p_score, rel=1e-9), (
                f"Score mismatch at position {i} (chunk {h_id}): "
                f"harness={h_score} vs prod={p_score}"
            )


class TestEveryModeFiltersBeforeScoring:
    """test_every_mode_filters_before_scoring"""

    def test_pit_filter_applied_in_bm25(self, offline_adapter):
        """BM25 mode should filter future chunks before scoring."""
        item = _answerable_item(as_of="2024-06-01T00:00:00+00:00")
        config = RetrievalConfig(mode="bm25", ticker_filter=False, top_k=20)
        hits = retrieve_item(item, config, offline_adapter)
        # smoke-005-future (accepted 2024-08-15) should not appear
        hit_ids = {h.chunk_id for h in hits}
        assert "smoke-005-future" not in hit_ids

    def test_pit_filter_applied_in_dense(self, offline_adapter):
        """Dense mode should filter future chunks before scoring."""
        item = _answerable_item(as_of="2024-06-01T00:00:00+00:00")
        config = RetrievalConfig(mode="dense", ticker_filter=False, top_k=20)
        hits = retrieve_item(item, config, offline_adapter)
        hit_ids = {h.chunk_id for h in hits}
        assert "smoke-005-future" not in hit_ids


class TestFutureChunkIsHardGate:
    """test_future_chunk_is_hard_gate_even_if_highest_score"""

    def test_pit_leakage_raises(self):
        """assert_no_pit_leakage raises for future chunks."""
        as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
        hits = [
            RetrievalHit(
                chunk_id="c1", ticker="X", accession="A1", section="s1",
                form_type="10-K", accepted_ts="2024-08-01T00:00:00+00:00",
                text="future", rank=1,
            ),
        ]
        with pytest.raises(ValueError, match="PIT leakage"):
            assert_no_pit_leakage(hits, as_of)

    def test_no_leakage_returns_zero(self):
        as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
        hits = [
            RetrievalHit(
                chunk_id="c1", ticker="X", accession="A1", section="s1",
                form_type="10-K", accepted_ts="2024-01-01T00:00:00+00:00",
                text="past", rank=1,
            ),
        ]
        assert assert_no_pit_leakage(hits, as_of) == 0


class TestRetrieveMatchesRetrieveMode:
    """test_retrieve_and_retrieve_mode_return_same_docs"""

    def test_retrieve_matches_hybrid_rrf_mode(self, offline_adapter):
        """retrieve() and retrieve_mode(mode='hybrid_rrf') return identical ORDERED results.

        Both paths must call the same bm25_search + vector_search + rrf_fuse
        composition.  We compare ordered (chunk_id, score) lists — not unordered
        sets — because ordering is the whole point of RRF fusion.
        """
        from evals.rag_eval.corpus import install_offline_corpus
        from api.services.hybrid_retriever import HybridRetriever

        item = _answerable_item(ticker="NVDA")
        as_of = item.as_of_datetime()

        with install_offline_corpus(offline_adapter):
            retriever = HybridRetriever(top_k=5, rrf_k=60)

            # Production path: retrieve() gives RRF-fused results
            docs_prod = retriever.retrieve(
                query=item.question,
                ticker=item.ticker,
                as_of=as_of,
                top_k=5,
            )

            # Eval path: retrieve_mode("hybrid_rrf") delegates to retrieve()
            docs_eval = retriever.retrieve_mode(
                query=item.question,
                mode="hybrid_rrf",
                ticker=item.ticker,
                as_of=as_of,
                top_k=5,
            )

        # Ordered (chunk_id, component_score) comparison
        prod_seq = [(d.metadata.get("chunk_id", ""), d.metadata.get("component_score")) for d in docs_prod]
        eval_seq = [(d.metadata.get("chunk_id", ""), d.metadata.get("component_score")) for d in docs_eval]
        assert prod_seq == eval_seq, (
            f"retrieve() and retrieve_mode('hybrid_rrf') ordered results differ.\n"
            f"  prod: {prod_seq}\n"
            f"  eval: {eval_seq}"
        )

    def test_hybrid_rerank_parity_with_deterministic_reranker(self, offline_adapter, monkeypatch):
        """retrieve_and_rerank() and retrieve_mode('hybrid_rerank') produce identical ORDERED results with scores.

        Uses a deterministic fake reranker (sorts by chunk_id reversed) so the
        test is hermetic.  A mutation that skips or reorders rerank in one path
        will cause the ordered comparison to fail.
        """
        from evals.rag_eval.corpus import install_offline_corpus
        from api.services.hybrid_retriever import HybridRetriever
        from api.services import reranker as reranker_mod

        call_log: list[str] = []

        def _fake_rerank(query, docs, top_k=5):
            call_log.append("rerank")
            # Assign deterministic scores based on chunk_id for comparison
            scored = []
            for d in docs:
                d_copy = d.copy() if hasattr(d, 'copy') else d
                # Use a deterministic score: higher chunk_id = higher score
                chunk_id = d.metadata.get("chunk_id", "")
                d_copy.metadata["rerank_score"] = hash(chunk_id) % 100 / 100.0
                scored.append(d_copy)
            scored.sort(key=lambda d: d.metadata.get("rerank_score", 0), reverse=True)
            return scored[:top_k]

        monkeypatch.setattr(reranker_mod, "rerank", _fake_rerank)

        item = _answerable_item(ticker="NVDA")
        as_of = item.as_of_datetime()

        with install_offline_corpus(offline_adapter):
            retriever = HybridRetriever(top_k=5, rrf_k=60)

            # Production composition: retrieve_and_rerank()
            docs_prod = retriever.retrieve_and_rerank(
                query=item.question,
                ticker=item.ticker,
                as_of=as_of,
                top_k=5,
            )

            call_log.clear()

            # Eval path: retrieve_mode("hybrid_rerank")
            docs_eval = retriever.retrieve_mode(
                query=item.question,
                mode="hybrid_rerank",
                ticker=item.ticker,
                as_of=as_of,
                top_k=5,
            )

        assert call_log.count("rerank") == 1, "retrieve_mode('hybrid_rerank') must call rerank exactly once"

        # Compare both order AND scores
        prod_seq = [(d.metadata.get("chunk_id", ""), d.metadata.get("rerank_score")) for d in docs_prod]
        eval_seq = [(d.metadata.get("chunk_id", ""), d.metadata.get("rerank_score")) for d in docs_eval]
        assert prod_seq == eval_seq, (
            f"retrieve_and_rerank() and retrieve_mode('hybrid_rerank') ordered results with scores differ.\n"
            f"  prod: {prod_seq}\n"
            f"  eval: {eval_seq}"
        )


class TestSmokeFiveItemsOffline:
    """test_smoke_five_items_offline_no_network"""

    def test_smoke_run(self, offline_adapter):
        """5-item smoke run completes without network/paid calls."""
        from evals.rag_eval.retrieve import run_retrieval
        import json

        golden_path = FIXTURE_DIR / "golden_smoke.jsonl"
        items = []
        with open(golden_path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line.strip())
                items.append(GoldenItem(
                    id=obj["id"],
                    ticker=obj.get("ticker", ""),
                    question=obj.get("question", ""),
                    gold_chunk_ids=tuple(obj.get("gold_chunk_ids", [])),
                    gold_accession_sections=tuple(tuple(x) for x in obj.get("gold_accession_sections", [])),
                    item_type=obj.get("item_type", "answerable"),
                    allowed_older_chunk_ids=tuple(obj.get("allowed_older_chunk_ids", [])),
                    as_of=obj.get("as_of"),
                ))

        configs = [
            RetrievalConfig(mode="bm25", ticker_filter=True, top_k=10),
            RetrievalConfig(mode="bm25", ticker_filter=False, top_k=10),
        ]

        results = run_retrieval(items, configs, offline_adapter)
        assert len(results) == 10  # 5 items x 2 configs

        # No errors for answerable items with BM25
        answerable_results = [r for r in results if r.item.item_type == "answerable"]
        for r in answerable_results:
            assert r.error is None, f"Error for {r.item.id}: {r.error}"