"""tests/rag/test_rag_eval_metrics.py — Tests for retrieval metrics."""
from __future__ import annotations

import random

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


# ── Deduplication + zero-gold exclusion ──────────────────────────────────────


def _ref_recall_at_k(ranked_ids: list[str], gold_ids: list[str], k: int) -> float:
    """Independent reference: deduplicate ranking, then compute recall@k."""
    if not gold_ids:
        return 0.0
    seen: set[str] = set()
    deduped: list[str] = []
    for rid in ranked_ids:
        if rid not in seen:
            seen.add(rid)
            deduped.append(rid)
    top_k = set(deduped[:k])
    gold = set(gold_ids)
    return len(top_k & gold) / len(gold)


def _ref_mrr_at_k(ranked_ids: list[str], gold_ids: list[str], k: int = 10) -> float:
    """Independent reference: deduplicate ranking, then compute MRR@k."""
    if not gold_ids:
        return 0.0
    seen: set[str] = set()
    deduped: list[str] = []
    for rid in ranked_ids:
        if rid not in seen:
            seen.add(rid)
            deduped.append(rid)
    gold = set(gold_ids)
    for i, rid in enumerate(deduped[:k]):
        if rid in gold:
            return 1.0 / (i + 1)
    return 0.0


def _ref_ndcg_at_k(ranked_ids: list[str], gold_ids: list[str], k: int = 10) -> float:
    """Independent reference: deduplicate ranking, then compute nDCG@k."""
    import math as _math
    if not gold_ids:
        return 0.0
    seen: set[str] = set()
    deduped: list[str] = []
    for rid in ranked_ids:
        if rid not in seen:
            seen.add(rid)
            deduped.append(rid)
    gold = set(gold_ids)
    dcg = 0.0
    for i, rid in enumerate(deduped[:k]):
        if rid in gold:
            dcg += 1.0 / _math.log2(i + 2)
    ideal_count = min(len(gold), k)
    idcg = sum(1.0 / _math.log2(i + 2) for i in range(ideal_count))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


class TestDeduplicationExplicitCases:
    """test_deduplication_explicit_cases"""

    def test_duplicate_relevant_ids_ndcg_one(self):
        """["g","g"] vs ["g"] → nDCG 1.0 (deduped ranking is ["g"], gold={"g"})."""
        assert ndcg_at_k(["g", "g"], ["g"], 10) == pytest.approx(1.0)

    def test_duplicate_relevant_ids_recall(self):
        """["g","g"] vs ["g"] → recall 1.0."""
        assert recall_at_k(["g", "g"], ["g"], 2) == pytest.approx(1.0)

    def test_duplicate_relevant_ids_mrr(self):
        """["g","g"] vs ["g"] → MRR 1.0."""
        assert reciprocal_rank_at_k(["g", "g"], ["g"], 10) == pytest.approx(1.0)

    def test_duplicate_non_relevant_ids(self):
        """["x","x","g"] vs ["g"] → after dedup ["x","g"], recall@3 1.0, MRR 1/2."""
        assert recall_at_k(["x", "x", "g"], ["g"], 3) == pytest.approx(1.0)
        assert reciprocal_rank_at_k(["x", "x", "g"], ["g"], 3) == pytest.approx(1 / 2)

    def test_ndcg_bounded_zero_one(self):
        """nDCG must always be in [0, 1]."""
        cases = [
            (["g", "g"], ["g"], 2),
            (["a", "b", "c"], ["a", "b", "c"], 3),
            (["x", "y", "z"], ["a"], 3),
            ([], ["a"], 5),
            (["a"], [], 5),
        ]
        for ranked, gold, k in cases:
            val = ndcg_at_k(ranked, gold, k)
            assert 0.0 <= val <= 1.0, f"nDCG {val} out of [0,1] for {ranked},{gold},{k}"

    def test_perfect_plus_zero_gold_aggregate(self):
        """Perfect row + zero-gold row → recall@5 1.0 with 1 excluded."""
        from evals.rag_eval.models import ItemResult, RetrievalConfig

        perfect_item = _item("answerable", gold_chunk_ids=("c1", "c2"))
        perfect_ir = ItemResult(
            item=perfect_item,
            config=RetrievalConfig(mode="bm25", ticker_filter=True, top_k=5),
        )
        perfect_ir.metrics = {
            "recall_at_1": 1.0, "recall_at_5": 1.0, "recall_at_10": 1.0,
            "mrr_at_10": 1.0, "ndcg_at_10": 1.0,
        }

        zero_gold_item = _item("answerable", gold_chunk_ids=())
        zero_gold_ir = ItemResult(
            item=zero_gold_item,
            config=RetrievalConfig(mode="bm25", ticker_filter=True, top_k=5),
        )
        zero_gold_ir.metrics = {
            "recall_at_1": 0.0, "recall_at_5": 0.0, "recall_at_10": 0.0,
            "mrr_at_10": 0.0, "ndcg_at_10": 0.0,
        }

        result = aggregate_results([perfect_ir, zero_gold_ir])
        # Zero-gold row excluded → overall recall@5 = 1.0 (only perfect row counted)
        assert result["overall"]["recall_at_5"] == pytest.approx(1.0)
        assert result["zero_gold_excluded"] == 1


class TestDedupPropertyTest:
    """test_dedup_property — seeded randomized ≥ 500 cases."""

    def test_recall_matches_reference(self):
        rng = random.Random(1729)
        pool = [f"id{i}" for i in range(20)]
        for _ in range(500):
            ranked = [rng.choice(pool) for _ in range(rng.randint(0, 15))]
            gold = [rng.choice(pool) for _ in range(rng.randint(0, 8))]
            k = rng.randint(0, 20)
            assert recall_at_k(ranked, gold, k) == pytest.approx(
                _ref_recall_at_k(ranked, gold, k), abs=1e-12
            ), f"recall mismatch: {ranked}, {gold}, k={k}"

    def test_mrr_matches_reference(self):
        rng = random.Random(1730)
        pool = [f"id{i}" for i in range(20)]
        for _ in range(500):
            ranked = [rng.choice(pool) for _ in range(rng.randint(0, 15))]
            gold = [rng.choice(pool) for _ in range(rng.randint(0, 8))]
            k = rng.randint(0, 20)
            assert reciprocal_rank_at_k(ranked, gold, k) == pytest.approx(
                _ref_mrr_at_k(ranked, gold, k), abs=1e-12
            ), f"MRR mismatch: {ranked}, {gold}, k={k}"

    def test_ndcg_matches_reference(self):
        rng = random.Random(1731)
        pool = [f"id{i}" for i in range(20)]
        for _ in range(500):
            ranked = [rng.choice(pool) for _ in range(rng.randint(0, 15))]
            gold = [rng.choice(pool) for _ in range(rng.randint(0, 8))]
            k = rng.randint(0, 20)
            assert ndcg_at_k(ranked, gold, k) == pytest.approx(
                _ref_ndcg_at_k(ranked, gold, k), abs=1e-12
            ), f"nDCG mismatch: {ranked}, {gold}, k={k}"

    def test_ndcg_always_bounded(self):
        """nDCG in [0, 1] for all randomized inputs."""
        rng = random.Random(1732)
        pool = [f"id{i}" for i in range(30)]
        for _ in range(500):
            ranked = [rng.choice(pool) for _ in range(rng.randint(0, 20))]
            gold = [rng.choice(pool) for _ in range(rng.randint(0, 10))]
            k = rng.randint(0, 25)
            val = ndcg_at_k(ranked, gold, k)
            assert 0.0 <= val <= 1.0 + 1e-12, f"nDCG {val} out of bounds: {ranked},{gold},{k}"