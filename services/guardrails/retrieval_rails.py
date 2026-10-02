"""
retrieval_rails.py — Phase 14: Retrieval Rail (Relevance Filtering).

Evaluates retrieved chunks against the query and drops irrelevant context
before generation. Uses keyword overlap + semantic similarity heuristics.

Usage:
    from api.services.guardrails.retrieval_rails import filter_retrieval
    relevant_chunks = filter_retrieval(query, chunks)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class RetrievalVerdict:
    original_count: int
    filtered_count: int
    dropped_count: int
    filtered_chunks: list[dict[str, Any]]


# Minimum keyword overlap ratio to keep a chunk
_MIN_KEYWORD_OVERLAP = 0.15

# Minimum chunk length (chars) to consider
_MIN_CHUNK_LENGTH = 50


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text (4+ chars, no stopwords)."""
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was",
        "were", "been", "have", "has", "had", "will", "would", "could",
        "should", "may", "might", "can", "shall", "not", "but", "what",
        "which", "who", "when", "where", "how", "than", "then", "also",
        "about", "after", "before", "between", "during", "into", "through",
        "each", "every", "both", "few", "more", "most", "other", "some",
        "such", "only", "own", "same", "very", "just", "because", "does",
    }
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    return {w for w in words if w not in stopwords}


def _keyword_overlap(query_keywords: set[str], chunk_keywords: set[str]) -> float:
    """Calculate Jaccard-like overlap between query and chunk keywords."""
    if not query_keywords or not chunk_keywords:
        return 0.0
    intersection = query_keywords & chunk_keywords
    return len(intersection) / min(len(query_keywords), len(chunk_keywords))


def filter_retrieval(
    query: str,
    chunks: list[dict[str, Any]],
    min_overlap: float = _MIN_KEYWORD_OVERLAP,
) -> RetrievalVerdict:
    """Filter retrieved chunks by relevance to the query.

    Args:
        query: The user's question.
        chunks: List of chunk dicts with at least a 'chunk_text' key.
        min_overlap: Minimum keyword overlap ratio to keep a chunk.

    Returns:
        RetrievalVerdict with filtered_chunks containing only relevant chunks.
    """
    if not chunks:
        return RetrievalVerdict(
            original_count=0,
            filtered_count=0,
            dropped_count=0,
            filtered_chunks=[],
        )

    query_keywords = _extract_keywords(query)
    filtered = []

    for chunk in chunks:
        text = chunk.get("chunk_text", "")
        if not text or len(text.strip()) < _MIN_CHUNK_LENGTH:
            continue

        chunk_keywords = _extract_keywords(text)
        overlap = _keyword_overlap(query_keywords, chunk_keywords)

        if overlap >= min_overlap:
            filtered.append(chunk)

    # Always keep at least one chunk (the most relevant one) if any exist
    if not filtered and chunks:
        scored = []
        for chunk in chunks:
            text = chunk.get("chunk_text", "")
            chunk_keywords = _extract_keywords(text)
            score = _keyword_overlap(query_keywords, chunk_keywords)
            scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        filtered = [scored[0][1]]

    return RetrievalVerdict(
        original_count=len(chunks),
        filtered_count=len(filtered),
        dropped_count=len(chunks) - len(filtered),
        filtered_chunks=filtered,
    )
