"""sec_kg/enrichment.py — optional LLM enrichment for Segment/Product/Customer.

Disabled by default. Zero client calls when disabled or budget=0.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class ExtractionClient(Protocol):
    """Injected client interface for LLM extraction."""
    def extract(self, text: str, types: List[str]) -> List[Dict[str, Any]]: ...


class FakeExtractionClient:
    """Bomb client that raises if called — used in CI/tests."""
    def extract(self, text: str, types: List[str]) -> List[Dict[str, Any]]:
        raise AssertionError("LLM extraction client should not be called in CI")


def extract_enrichments(
    chunks: List[Dict[str, Any]],
    corpus: Dict[str, Dict[str, Any]],
    *,
    client: Optional[Any] = None,
    enabled: bool = False,
    budget: int = 0,
    max_chunks: int = 1000,
    max_records: int = 5000,
) -> List[Dict[str, Any]]:
    """Extract Segment/Product/Customer entities from filing chunks.

    Args:
        chunks: list of chunk metadata dicts
        corpus: chunk_id -> chunk data
        client: extraction client (must implement .extract())
        enabled: whether extraction is enabled
        budget: maximum number of LLM calls (0 = no calls)
        max_chunks: maximum chunks to process
        max_records: maximum extracted records

    Returns:
        List of extracted entity dicts ready for build_graph consumption.
    """
    if not enabled or budget <= 0:
        return []

    if client is None:
        client = FakeExtractionClient()

    allowed_types = ["Segment", "Product", "Customer"]
    results = []
    calls_made = 0

    for i, chunk in enumerate(chunks[:max_chunks]):
        if calls_made >= budget:
            break
        if len(results) >= max_records:
            break

        chunk_text = chunk.get("chunk_text", "")
        if not chunk_text or not chunk_text.strip():
            continue

        chunk_id = chunk.get("chunk_id", "")
        accession = chunk.get("accession_number", "")
        ticker = chunk.get("ticker", "")
        cik = chunk.get("cik", "")
        accepted_epoch = chunk.get("accepted_epoch")

        try:
            raw_results = client.extract(chunk_text, allowed_types)
            calls_made += 1
        except Exception:
            continue

        for item in raw_results:
            if len(results) >= max_records:
                break

            entity_type = item.get("type", "")
            if entity_type not in allowed_types:
                continue

            label = item.get("label", "")
            if not label or len(label) > 500:
                continue

            confidence = item.get("confidence", 0.0)
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
                continue

            results.append({
                "cik": cik,
                "ticker": ticker,
                "accession_number": accession,
                "form_type": chunk.get("form_type", ""),
                "accepted_epoch": accepted_epoch,
                "entity_type": entity_type.lower(),
                "entity_key": label,
                "entity_value": label,
                "entity_unit": "",
                "period_start": "",
                "period_end": "",
                "confidence": confidence,
                "source_chunk_id": chunk_id,
                "_enrichment_meta": {
                    "model_version": getattr(client, "model_version", "unknown"),
                    "provider": getattr(client, "provider", "unknown"),
                    "prompt_version": getattr(client, "prompt_version", "unknown"),
                },
            })

    return results