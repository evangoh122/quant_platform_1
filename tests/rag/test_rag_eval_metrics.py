"""tests/rag/test_rag_eval_metrics.py — Tests for retrieval metrics."""
from __future__ import annotations

import pytest

from evals.rag_eval.models import CorpusRecord, GoldenItem, ItemResult, RetrievalConfig, RetrievalHit
from evals.rag_eval.metrics import (
    aggregate_results,
    bootstrap_ci,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
    score_abstention,
    score_item,
    section_keys,
)


def _hit(cid: str, accession: str = "A1", section: str = "s1", **kw) -> RetrievalHit:
    defaults = dict(
        chunk_id=cid, ticker="X", accession=accession, section=section,
        form_type="10-K", accepted_ts="2024-01-01T00:00:00+00:00",
        text=f"text of {cid}", rank=0,
    )
    defaults.update(kw)
    return RetrievalHit(**defaults)


def _item(item_type="answerable", **kw) -> GoldenItem:
    return GoldenItem(id="t1", ticker="X", question="q", item_type=item_type, **kw)


class TestExactChunkMetrics:
    """test_exact_chunk_metrics"""

    def test_recall_at_1_exact_match(self):
        assert recall_at_k(["a", "b", "c"], ["a"], 1) == 1.0

    def test_recall_at_1_miss(self):
        assert recall_at_k(["a", "b", "c"], ["d"], 1) == 0.0

    def test_recall_at_5_partial(self):
        assert recall_at_k(["a", "b", "c", "d", "e"], ["a", "c", "f"], 5) == pytest.approx(2 / 3)

    def test_recall_at_10_all_found(self):
        ids = [f"c{i}" for i in range(10)]
        gold = [f"c{i}" for i in range(5)]
        assert recall_at_k(ids, gold, 10) == 1.0

    def test_mrr_first_at_rank_1(self):
        assert reciprocal_rank_at_k(["a", "b"], ["a"], 10) == 1.0

    def test_mrr_first_at_rank_3(self):
        assert reciprocal_rank_at_k(["x", "y", "a", "b"], ["a"], 10) == pytest.approx(1 / 3)

    def test_mrr_no_match(self):
        assert reciprocal_rank_at_k(["x", "y"], ["a"], 10) == 0.0

    def test_ndcg_perfect_ranking(self):
        assert ndcg_at_k(["a", "b", "c"], ["a", "b", "c"], 3) == pytest.approx(1.0)

    def test_ndcg_worst_ranking(self):
        # Gold is at the end
        assert ndcg_at_k(["x", "y", "a"], ["a"], 3) < 1.0

    def test_ndcg_no_gold_returns_zero(self):
        assert ndcg_at_k(["a", "b"], [], 10) == 0.0


class TestSecondaryAccessionSectionMetrics:
    """test_secondary_accession_section_metrics"""

    def test_section_keys_deduped(self):
        hits = [_hit("c1", "A1", "s1"), _hit("c2", "A1", "s1"), _hit("c3", "A2", "s2")]
        keys = section_keys(hits)
        assert keys == [("A1", "s1"), ("A2", "s2")]

    def test_score_item_secondary_metrics(self):
        corpus_map = {
            "c1": CorpusRecord("c1", "X", "A1", "s1", "10-K", "2024-01-01T00:00:00+00:00", "t"),
            "c2": CorpusRecord("c2", "X", "A1", "s1", "10-K", "2024-01-01T00:00:00+00:00", "t"),
        }
        item = GoldenItem(
            id="t1", ticker="X", question="q",
            gold_chunk_ids=("c1",),
            gold_accession_sections=(("A1", "s1"),),
        )
        hits = [_hit("c1", "A1", "s1")]
        metrics = score_item(item, hits, corpus_map)
        assert metrics["recall_at_1_section"] == 1.0


class TestZeroGoldExcluded:
    """test_zero_gold_excluded"""

    def test_zero_gold_recall_excluded(self):
        """Items with no gold chunks should return 0.0 (excluded from aggregation)."""
        assert recall_at_k(["a"], [], 1) == 0.0

    def test_zero_gold_mrr_excluded(self):
        assert reciprocal_rank_at_k(["a"], [], 10) == 0.0

    def test_zero_gold_ndcg_excluded(self):
        assert ndcg_at_k(["a"], [], 10) == 0.0


class TestBootstrapIsDeterministic:
    """test_bootstrap_is_deterministic"""

    def test_same_seed_same_result(self):
        values = [0.5, 0.6, 0.7, 0.8, 0.9]
        ci1 = bootstrap_ci(values, seed=1729, samples=1000)
        ci2 = bootstrap_ci(values, seed=1729, samples=1000)
        assert ci1["lower"] == ci2["lower"]
        assert ci1["upper"] == ci2["upper"]

    def test_different_seed_differs(self):
        values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        ci1 = bootstrap_ci(values, seed=1729, samples=5000)
        ci2 = bootstrap_ci(values, seed=42, samples=5000)
        # Very unlikely to be exactly equal
        assert ci1["lower"] != ci2["lower"] or ci1["upper"] != ci2["upper"]

    def test_tiny_stratum_warning(self):
        values = [0.5]
        ci = bootstrap_ci(values, seed=1729)
        assert ci["n"] == 1
        assert "warning" in ci


class TestAbstentionAndTrapScoring:
    """test_abstention_and_trap_scoring"""

    def test_unanswerable_no_hits(self):
        item = _item("unanswerable")
        result = score_abstention(item, [])
        assert result["allowed_top_hit"] is False
        assert result["abstention_label"] == "no_gold_retrieved"

    def test_unanswerable_with_hits(self):
        item = _item("unanswerable")
        hits = [_hit("c1")]
        result = score_abstention(item, hits)
        assert result["allowed_top_hit"] is False
        assert result["abstention_label"] == "top_hit_present"

    def test_pit_trap_future_leakage(self):
        item = _item(
            "point_in_time_trap",
            as_of="2024-06-01T00:00:00+00:00",
        )
        # Future hit
        hits = [_hit("c1", accepted_ts="2024-08-01T00:00:00+00:00")]
        result = score_abstention(item, hits)
        assert result["allowed_top_hit"] is False
        assert result["abstention_label"] == "future_leakage"

    def test_pit_trap_allowed_older(self):
        item = _item(
            "point_in_time_trap",
            as_of="2024-06-01T00:00:00+00:00",
            allowed_older_chunk_ids=("c-old",),
        )
        hits = [_hit("c-old", accepted_ts="2023-01-01T00:00:00+00:00")]
        result = score_abstention(item, hits)
        assert result["allowed_top_hit"] is True

    def test_pit_trap_disallowed_older(self):
        item = _item(
            "point_in_time_trap",
            as_of="2024-06-01T00:00:00+00:00",
            allowed_older_chunk_ids=("c-old",),
        )
        hits = [_hit("c-other", accepted_ts="2023-01-01T00:00:00+00:00")]
        result = score_abstention(item, hits)
        assert result["allowed_top_hit"] is False