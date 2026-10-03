"""evals/rag_eval/metrics.py — Pure functions for retrieval metrics.

All functions are deterministic and make no LLM calls.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from typing import Any, Optional, Sequence

from evals.rag_eval.models import CorpusRecord, GoldenItem, ItemResult, RetrievalHit


# ── Core metric functions ─────────────────────────────────────────────────────

def recall_at_k(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """Fraction of gold IDs found in top-k ranked results.

    Returns 0.0 when gold_ids is empty (excluded from aggregation by caller).
    """
    if not gold_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    gold = set(gold_ids)
    return len(top_k & gold) / len(gold)


def reciprocal_rank_at_k(
    ranked_ids: Sequence[str],
    gold_ids: Sequence[str],
    k: int = 10,
) -> float:
    """1 / rank of first relevant item in top-k.

    Returns 0.0 when gold_ids is empty or no gold appears in top-k.
    """
    if not gold_ids:
        return 0.0
    gold = set(gold_ids)
    for i, rid in enumerate(ranked_ids[:k]):
        if rid in gold:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(
    ranked_ids: Sequence[str],
    gold_ids: Sequence[str],
    k: int = 10,
) -> float:
    """Normalized Discounted Cumulative Gain at k with binary relevance.

    Returns 0.0 when gold_ids is empty.
    """
    if not gold_ids:
        return 0.0
    gold = set(gold_ids)

    # DCG
    dcg = 0.0
    for i, rid in enumerate(ranked_ids[:k]):
        if rid in gold:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because rank is 1-indexed

    # Ideal DCG
    ideal_count = min(len(gold), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


# ── Secondary metrics (accession, section level) ──────────────────────────────

def section_keys(hits: Sequence[RetrievalHit]) -> list[tuple[str, str]]:
    """Extract unique (accession, section) keys from hits, in rank order."""
    seen: set[tuple[str, str]] = set()
    keys: list[tuple[str, str]] = []
    for h in hits:
        k = (h.accession, h.section)
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def _gold_section_keys(
    item: GoldenItem,
    corpus_map: dict[str, CorpusRecord],
) -> set[tuple[str, str]]:
    """Derive gold (accession, section) keys from gold_chunk_ids + corpus."""
    keys: set[tuple[str, str]] = set()
    for cid in item.gold_chunk_ids:
        rec = corpus_map.get(cid)
        if rec:
            keys.add((rec.accession, rec.section))
    # Also include explicitly declared gold accession-section pairs
    keys.update(item.gold_accession_sections)
    return keys


def score_item(
    item: GoldenItem,
    hits: Sequence[RetrievalHit],
    corpus_map: Optional[dict[str, CorpusRecord]] = None,
) -> dict[str, Any]:
    """Score a single item's retrieval hits against gold standards.

    Returns a dict of metric values.
    """
    ranked_ids = [h.chunk_id for h in hits]
    gold_ids = list(item.gold_chunk_ids)

    metrics: dict[str, Any] = {}

    # Primary chunk-level metrics
    metrics["recall_at_1"] = recall_at_k(ranked_ids, gold_ids, 1)
    metrics["recall_at_5"] = recall_at_k(ranked_ids, gold_ids, 5)
    metrics["recall_at_10"] = recall_at_k(ranked_ids, gold_ids, 10)
    metrics["mrr_at_10"] = reciprocal_rank_at_k(ranked_ids, gold_ids, 10)
    metrics["ndcg_at_10"] = ndcg_at_k(ranked_ids, gold_ids, 10)

    # Secondary accession+section metrics
    if corpus_map:
        gold_sec = _gold_section_keys(item, corpus_map)
        hit_sec = section_keys(hits)
        ranked_sec_ids = [f"{a}::{s}" for a, s in hit_sec]
        gold_sec_ids = [f"{a}::{s}" for a, s in gold_sec]
        metrics["recall_at_1_section"] = recall_at_k(ranked_sec_ids, gold_sec_ids, 1)
        metrics["recall_at_5_section"] = recall_at_k(ranked_sec_ids, gold_sec_ids, 5)
        metrics["recall_at_10_section"] = recall_at_k(ranked_sec_ids, gold_sec_ids, 10)
        metrics["mrr_at_10_section"] = reciprocal_rank_at_k(ranked_sec_ids, gold_sec_ids, 10)
        metrics["ndcg_at_10_section"] = ndcg_at_k(ranked_sec_ids, gold_sec_ids, 10)
    else:
        for m in ["recall_at_1_section", "recall_at_5_section", "recall_at_10_section",
                   "mrr_at_10_section", "ndcg_at_10_section"]:
            metrics[m] = 0.0

    return metrics


def score_abstention(
    item: GoldenItem,
    hits: Sequence[RetrievalHit],
) -> dict[str, Any]:
    """Score abstention/trap items separately from answerable items.

    Returns a dict with:
    - allowed_top_hit: True iff top-1 is temporally allowed and (for older-answer
      traps) belongs to allowed older gold evidence.
    - abstention_label: heuristic label for unanswerable items.
    """
    result: dict[str, Any] = {
        "allowed_top_hit": None,
        "abstention_label": None,
    }

    as_of = item.as_of_datetime()

    if item.item_type == "unanswerable":
        # True unanswerable: no gold evidence exists
        if not hits:
            result["abstention_label"] = "no_gold_retrieved"
        else:
            # Check if any future evidence leaked through
            future_hits = [
                h for h in hits
                if _parse_ts(h.accepted_ts) and _parse_ts(h.accepted_ts) > as_of
            ]
            if future_hits:
                result["abstention_label"] = "future_leakage"
            else:
                result["abstention_label"] = "top_hit_present"
        result["allowed_top_hit"] = False

    elif item.item_type == "point_in_time_trap":
        if not hits:
            result["allowed_top_hit"] = False
            result["abstention_label"] = "no_gold_retrieved"
            return result

        top = hits[0]
        top_dt = _parse_ts(top.accepted_ts)

        # Check: no future evidence
        future_hits = [
            h for h in hits
            if _parse_ts(h.accepted_ts) and _parse_ts(h.accepted_ts) > as_of
        ]
        if future_hits:
            result["allowed_top_hit"] = False
            result["abstention_label"] = "future_leakage"
            return result

        # For older-answer traps, top-1 must be in allowed older gold
        if item.allowed_older_chunk_ids:
            allowed = set(item.allowed_older_chunk_ids)
            result["allowed_top_hit"] = top.chunk_id in allowed
        else:
            # Simple PIT trap: top hit must be temporally allowed
            result["allowed_top_hit"] = top_dt is not None and top_dt <= as_of

    return result


# ── PIT leakage ───────────────────────────────────────────────────────────────

def _parse_ts(ts_str: str) -> Optional[Any]:
    """Parse a timestamp string to datetime."""
    from datetime import datetime, timezone
    if not ts_str or ts_str == "None":
        return None
    try:
        ts_str = ts_str.replace("T", " ").replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# ── Bootstrap CI ──────────────────────────────────────────────────────────────

def bootstrap_ci(
    values: Sequence[float],
    *,
    seed: int = 1729,
    samples: int = 10_000,
    confidence: float = 0.95,
) -> dict[str, float]:
    """Bootstrap confidence interval for the mean.

    Returns dict with mean, lower, upper, n, and warning for tiny strata.
    """
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "lower": 0.0, "upper": 0.0, "n": 0, "warning": "empty"}

    if n < 2:
        return {
            "mean": float(values[0]),
            "lower": float(values[0]),
            "upper": float(values[0]),
            "n": n,
            "warning": "n<2, CI is degenerate",
        }

    rng = random.Random(seed)
    means: list[float] = []
    vals = list(values)

    for _ in range(samples):
        sample = [vals[rng.randint(0, n - 1)] for _ in range(n)]
        means.append(sum(sample) / n)

    means.sort()
    alpha = 1.0 - confidence
    lower_idx = int((alpha / 2) * samples)
    upper_idx = int((1 - alpha / 2) * samples)
    lower_idx = max(0, min(lower_idx, samples - 1))
    upper_idx = max(0, min(upper_idx, samples - 1))

    result: dict[str, float] = {
        "mean": sum(values) / n,
        "lower": means[lower_idx],
        "upper": means[upper_idx],
        "n": n,
    }
    if n < 10:
        result["warning"] = f"tiny stratum (n={n})"
    return result


# ── Aggregate results ─────────────────────────────────────────────────────────

def aggregate_results(
    item_results: list[ItemResult],
    corpus_map: Optional[dict[str, CorpusRecord]] = None,
) -> dict[str, Any]:
    """Aggregate item-level results into overall, per-type, and per-ticker metrics.

    Returns dict with keys: overall, per_type, per_ticker, secondary, bootstrap,
    abstention, leakage.
    """
    # Separate answerable and non-answerable
    answerable = [ir for ir in item_results if ir.item.item_type == "answerable"]
    non_answerable = [ir for ir in item_results if ir.item.item_type != "answerable"]

    # Aggregate answerable metrics
    metric_names = [
        "recall_at_1", "recall_at_5", "recall_at_10",
        "mrr_at_10", "ndcg_at_10",
        "recall_at_1_section", "recall_at_5_section", "recall_at_10_section",
        "mrr_at_10_section", "ndcg_at_10_section",
    ]

    def _avg_metrics(items: list[ItemResult], names: list[str]) -> dict[str, float]:
        if not items:
            return {n: 0.0 for n in names}
        result: dict[str, float] = {}
        for name in names:
            vals = [ir.metrics.get(name, 0.0) for ir in items]
            result[name] = sum(vals) / len(vals) if vals else 0.0
        return result

    overall = _avg_metrics(answerable, metric_names)

    # Per-type
    per_type: dict[str, dict[str, float]] = {}
    for item_type in ("answerable", "unanswerable", "point_in_time_trap"):
        type_items = [ir for ir in item_results if ir.item.item_type == item_type]
        if type_items:
            per_type[item_type] = _avg_metrics(type_items, metric_names)

    # Per-ticker
    per_ticker: dict[str, dict[str, float]] = {}
    tickers = set(ir.item.ticker for ir in item_results)
    for ticker in sorted(tickers):
        ticker_items = [ir for ir in answerable if ir.item.ticker == ticker]
        if ticker_items:
            per_ticker[ticker] = _avg_metrics(ticker_items, metric_names)

    # Bootstrap CIs on recall@5 and MRR for answerable items
    bootstrap: dict[str, Any] = {}
    if answerable:
        r5_vals = [ir.metrics.get("recall_at_5", 0.0) for ir in answerable]
        mrr_vals = [ir.metrics.get("mrr_at_10", 0.0) for ir in answerable]
        bootstrap["recall_at_5"] = bootstrap_ci(r5_vals)
        bootstrap["mrr_at_10"] = bootstrap_ci(mrr_vals)

        # Per-type bootstrap
        bootstrap["per_type"] = {}
        for item_type in per_type:
            type_answerable = [ir for ir in answerable if ir.item.item_type == item_type]
            if len(type_answerable) >= 2:
                bootstrap["per_type"][item_type] = {
                    "recall_at_5": bootstrap_ci(
                        [ir.metrics.get("recall_at_5", 0.0) for ir in type_answerable]
                    ),
                    "mrr_at_10": bootstrap_ci(
                        [ir.metrics.get("mrr_at_10", 0.0) for ir in type_answerable]
                    ),
                }

        # Per-ticker bootstrap
        bootstrap["per_ticker"] = {}
        for ticker in per_ticker:
            ticker_answerable = [ir for ir in answerable if ir.item.ticker == ticker]
            if len(ticker_answerable) >= 2:
                bootstrap["per_ticker"][ticker] = {
                    "recall_at_5": bootstrap_ci(
                        [ir.metrics.get("recall_at_5", 0.0) for ir in ticker_answerable]
                    ),
                    "mrr_at_10": bootstrap_ci(
                        [ir.metrics.get("mrr_at_10", 0.0) for ir in ticker_answerable]
                    ),
                }

    # Abstention/trap results
    abstention: dict[str, Any] = {}
    for ir in non_answerable:
        key = f"{ir.item.id}__{ir.config.label()}"
        abstention[key] = {
            "item_id": ir.item.id,
            "item_type": ir.item.item_type,
            "config": ir.config.label(),
            "allowed_top_hit": ir.allowed_top_hit,
            "abstention_label": ir.abstention_label,
        }

    # Leakage
    leakage_total = sum(ir.leakage_count for ir in item_results)
    leakage_by_config: dict[str, int] = {}
    for ir in item_results:
        cfg_label = ir.config.label()
        leakage_by_config[cfg_label] = leakage_by_config.get(cfg_label, 0) + ir.leakage_count

    return {
        "overall": overall,
        "per_type": per_type,
        "per_ticker": per_ticker,
        "secondary": _avg_metrics(answerable, [n for n in metric_names if "_section" in n]),
        "bootstrap": bootstrap,
        "abstention": abstention,
        "leakage_total": leakage_total,
        "leakage_by_config": leakage_by_config,
    }