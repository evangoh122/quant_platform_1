"""
reranker.py — Cross-encoder post-retrieval reranker.

Uses cross-encoder/ms-marco-MiniLM-L-6-v2 to score (query, document) pairs
and rerank retrieved chunks by relevance before they reach the LLM.

The model is lazy-loaded on first use to avoid startup latency.
Falls back silently (returns docs unchanged) if sentence-transformers is
unavailable or the model fails to load.
"""
from __future__ import annotations

import threading
from typing import List, Optional

from langchain_core.documents import Document
from loguru import logger

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_lock = threading.Lock()
_model = None
_model_name: Optional[str] = None


def _get_model(model_name: str = _DEFAULT_MODEL):
    """Return the singleton CrossEncoder, loading it on first call."""
    global _model, _model_name
    if _model is not None and _model_name == model_name:
        return _model
    if CrossEncoder is None:
        logger.warning("sentence-transformers not installed — reranker disabled")
        return None
    with _lock:
        if _model is not None and _model_name == model_name:
            return _model
        try:
            logger.info("Loading cross-encoder reranker: {}", model_name)
            _model = CrossEncoder(model_name)
            _model_name = model_name
        except Exception as e:
            logger.error("Failed to load reranker model {}: {}", model_name, e)
            _model = None
    return _model


def rerank(
    query: str,
    docs: List[Document],
    top_k: int = 5,
    model_name: str = _DEFAULT_MODEL,
) -> List[Document]:
    """Rerank documents by cross-encoder relevance score.

    Returns the top_k most relevant documents, sorted by score descending.
    Returns docs unchanged (truncated to top_k) if the model is unavailable.
    """
    if not docs:
        return []

    model = _get_model(model_name)
    if model is None:
        return docs[:top_k]

    pairs = [(query, d.page_content) for d in docs]
    try:
        scores = model.predict(pairs)
    except Exception as e:
        logger.error("Reranker prediction failed: {}", e)
        return docs[:top_k]

    scored = list(zip(scores, docs))
    scored.sort(key=lambda x: x[0], reverse=True)

    reranked = [doc for _, doc in scored[:top_k]]

    if scored:
        logger.debug(
            "Reranked {} -> {} docs (scores: {:.3f} .. {:.3f})",
            len(docs), len(reranked), scored[0][0], scored[-1][0],
        )
    return reranked