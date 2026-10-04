"""evals/rag_eval/retrieve.py — Retrieval execution for the eval harness.

Runs golden items through production retrieval via the corpus adapter seam.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from langchain_core.documents import Document

from evals.rag_eval.corpus import CorpusAdapter, install_offline_corpus
from evals.rag_eval.models import (
    CorpusRecord,
    GoldenItem,
    ItemResult,
    RetrievalConfig,
    RetrievalHit,
)


def retrieve_item(
    item: GoldenItem,
    config: RetrievalConfig,
    adapter: CorpusAdapter,
) -> list[RetrievalHit]:
    """Retrieve hits for one golden item under one configuration.

    Uses the production HybridRetriever and search_sec_filings wrapper via the
    install_offline_corpus seam.
    """
    as_of = item.as_of_datetime()
    ticker = item.ticker if config.ticker_filter else ""

    # For offline adapters, install the corpus into production cache
    from evals.rag_eval.corpus import JsonlCorpusAdapter
    if isinstance(adapter, JsonlCorpusAdapter):
        with install_offline_corpus(adapter):
            return _retrieve_via_production(
                query=item.question,
                ticker=ticker,
                as_of=as_of,
                config=config,
            )
    else:
        # Live adapter — corpus is already in production cache
        return _retrieve_via_production(
            query=item.question,
            ticker=ticker,
            as_of=as_of,
            config=config,
        )


def _retrieve_via_production(
    query: str,
    ticker: str,
    as_of: datetime,
    config: RetrievalConfig,
) -> list[RetrievalHit]:
    """Run retrieval through the production retriever seam."""
    from api.services.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever(
        top_k=config.top_k,
        rrf_k=config.rrf_k,
    )

    # Use the retrieve_mode seam
    docs = retriever.retrieve_mode(
        query=query,
        mode=config.mode,
        ticker=ticker,
        as_of=as_of,
        top_k=config.top_k,
        rerank=(config.mode == "hybrid_rerank"),
    )

    # Convert Documents to RetrievalHits
    hits: list[RetrievalHit] = []
    for rank, doc in enumerate(docs):
        hits.append(RetrievalHit(
            chunk_id=doc.metadata.get("chunk_id", ""),
            ticker=doc.metadata.get("ticker", ""),
            accession=doc.metadata.get("accession", ""),
            section=doc.metadata.get("section_id", ""),
            form_type=doc.metadata.get("form_type", ""),
            accepted_ts=doc.metadata.get("accepted_ts", ""),
            text=doc.page_content,
            rank=rank + 1,
            retrieval_mode=doc.metadata.get("retrieval_mode", config.mode),
            component_score=doc.metadata.get("component_score"),
            rerank_score=doc.metadata.get("rerank_score"),
            similarity=doc.metadata.get("similarity"),
            distance=doc.metadata.get("distance"),
        ))

    return hits


def count_pit_leakage(
    hits: Sequence[RetrievalHit],
    as_of: datetime,
) -> tuple[int, list[str]]:
    """Count chunks with accepted_ts > as_of.

    Returns (count, leaked_chunk_ids).  Does NOT raise.
    Missing or unparseable timestamps are treated as violations (fail-closed).
    """
    leak_count = 0
    leaked_ids: list[str] = []
    for h in hits:
        if not h.accepted_ts:
            leak_count += 1
            leaked_ids.append(h.chunk_id)
            continue
        try:
            ts_str = h.accepted_ts.replace("T", " ").replace("Z", "+00:00")
            accepted_dt = datetime.fromisoformat(ts_str)
            if accepted_dt.tzinfo is None:
                accepted_dt = accepted_dt.replace(tzinfo=timezone.utc)
            if accepted_dt > as_of:
                leak_count += 1
                leaked_ids.append(h.chunk_id)
        except (ValueError, TypeError):
            leak_count += 1
            leaked_ids.append(h.chunk_id)
    return leak_count, leaked_ids


def assert_no_pit_leakage(
    hits: Sequence[RetrievalHit],
    as_of: datetime,
) -> int:
    """Check that no returned chunk has accepted_ts > as_of.

    Returns the count of leaked chunks.  Raises ValueError if any leak found.
    Missing or unparseable timestamps are treated as violations (fail-closed).
    The ValueError carries ``leak_count`` and ``leaked_chunk_ids`` attributes.
    """
    leak_count, leaked_ids = count_pit_leakage(hits, as_of)

    if leak_count > 0:
        err = ValueError(
            f"PIT leakage: {leak_count} chunk(s) have accepted_ts > as_of ({as_of.isoformat()})"
        )
        err.leak_count = leak_count
        err.leaked_chunk_ids = leaked_ids
        raise err
    return leak_count


def run_retrieval(
    items: Sequence[GoldenItem],
    configs: Sequence[RetrievalConfig],
    adapter: CorpusAdapter,
) -> list[ItemResult]:
    """Run retrieval for all items across all configs.

    Returns a list of ItemResults with hits and PIT leakage checks.
    """
    results: list[ItemResult] = []

    for item in items:
        for config in configs:
            ir = ItemResult(item=item, config=config)
            try:
                hits = retrieve_item(item, config, adapter)
                ir.hits = hits

                # PIT leakage check — hard gate
                as_of = item.as_of_datetime()
                ir.leakage_count = assert_no_pit_leakage(hits, as_of)

                # Score the item
                from evals.rag_eval.metrics import score_item, score_abstention

                corpus_map = _build_corpus_map(adapter)
                ir.metrics = score_item(item, hits, corpus_map)

                # Abstention/trap scoring
                abs_result = score_abstention(item, hits)
                ir.allowed_top_hit = abs_result.get("allowed_top_hit")
                ir.abstention_label = abs_result.get("abstention_label")

            except ValueError as e:
                if "PIT leakage" in str(e):
                    ir.error = str(e)
                    ir.leakage_count = getattr(e, "leak_count", 0)
                    ir.leaked_chunk_ids = getattr(e, "leaked_chunk_ids", [])
                else:
                    ir.error = str(e)
            except Exception as e:
                ir.error = f"{type(e).__name__}: {e}"

            results.append(ir)

    return results


def _build_corpus_map(adapter: CorpusAdapter) -> dict[str, CorpusRecord]:
    """Build chunk_id -> CorpusRecord mapping."""
    return {rec.chunk_id: rec for rec in adapter.records()}