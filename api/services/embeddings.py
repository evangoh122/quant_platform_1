"""
embeddings.py — Embedding provider abstraction for SEC chunk retrieval.

Supports two backends:
  - sentence-transformers / local — in-process ST model (BAAI/bge-small-en-v1.5, 384-d).
    Lazy-loaded on first use.  No network inference call.
  - huggingface — HF Inference API (direct HTTP fallback).

Provider is selected via EMBEDDING_PROVIDER env var.
"""
from __future__ import annotations

import os
import threading
from typing import List, Optional

import numpy as np
from loguru import logger

from api.config import config
from api.services.exceptions import EmbeddingConfigError

# ── Config (single source of truth: api.config) ──────────────────────────────

EMBEDDING_PROVIDER = config.EMBEDDING_PROVIDER
ST_EMBEDDING_MODEL = config.ST_EMBEDDING_MODEL
EMBEDDING_DIM = config.EMBEDDING_DIM
EMBEDDING_QUERY_PREFIX = config.EMBEDDING_QUERY_PREFIX
EMBEDDING_MAX_SEQ_LEN = int(os.getenv("EMBEDDING_MAX_SEQ_LEN", "512"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "4"))


# ── Local sentence-transformers backend ──────────────────────────────────────

class LocalSTEmbeddings:
    """Embeddings via a local sentence-transformers model (in-process, no network).

    The model is lazy-loaded on first use so import stays cheap.
    BAAI/bge-small-en-v1.5 produces 384-d normalised vectors.
    """

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        logger.info("LocalSTEmbeddings ready — model={} (lazy-load)", model_name)

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer
                    logger.info("Loading local embedding model: {}", self._model_name)
                    self._model = SentenceTransformer(self._model_name)
                    try:
                        self._model.max_seq_length = EMBEDDING_MAX_SEQ_LEN
                    except Exception:
                        pass
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        vecs = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            batch_size=EMBEDDING_BATCH_SIZE,
        )
        return [v.tolist() for v in vecs]

    def embed_query(self, text: str) -> List[float]:
        prefix = EMBEDDING_QUERY_PREFIX
        if prefix:
            text = f"{prefix}{text}"
        model = self._get_model()
        vec = model.encode(
            [text], normalize_embeddings=True, convert_to_numpy=True, batch_size=1,
        )[0]
        return vec.tolist()


# ── HuggingFace Inference API backend ────────────────────────────────────────

class HFInferenceEmbeddings:
    """Embeddings via HuggingFace InferenceClient (feature_extraction).

    Falls back to direct HTTP on routing errors.
    """

    def __init__(self, model_name: str):
        self._model = model_name
        self._api_key = os.getenv("HF_TOKEN", "")
        self._url = f"https://api-inference.huggingface.co/models/{model_name}"
        self._client = None
        self._use_http_fallback = False
        logger.info("HFInferenceEmbeddings ready — model={}", model_name)

    def _get_client(self):
        if self._client is None and not self._use_http_fallback:
            try:
                from huggingface_hub import InferenceClient
                self._client = InferenceClient(token=self._api_key)
            except ImportError:
                self._use_http_fallback = True
        return self._client

    def _embed(self, text: str) -> List[float]:
        client = self._get_client()
        if client is not None:
            try:
                result = client.feature_extraction(text, model=self._model)
            except Exception as e:
                logger.warning(
                    "InferenceClient failed ({}: {}) — falling back to direct HTTP",
                    type(e).__name__, e,
                )
                self._client = None
                self._use_http_fallback = True
                client = None
        if client is None:
            import requests
            resp = requests.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"inputs": text},
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
        arr = np.array(result)
        if arr.ndim == 2:
            arr = arr.mean(axis=0)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        prefix = EMBEDDING_QUERY_PREFIX
        if prefix:
            text = f"{prefix}{text}"
        return self._embed(text)


# ── Singleton factory ────────────────────────────────────────────────────────

_embeddings = None
_embeddings_lock = threading.Lock()


def get_embeddings():
    """Return the configured embeddings instance (singleton).

    EMBEDDING_PROVIDER selects the backend:
      - sentence-transformers / local / st — in-process ST model
      - huggingface — HF Inference API
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    with _embeddings_lock:
        if _embeddings is not None:
            return _embeddings

        if EMBEDDING_PROVIDER in ("sentence-transformers", "sentence_transformers", "local", "st"):
            try:
                _embeddings = LocalSTEmbeddings(ST_EMBEDDING_MODEL)
                return _embeddings
            except Exception as e:
                raise EmbeddingConfigError(
                    f"Failed to load embedding model '{ST_EMBEDDING_MODEL}': {e}"
                ) from e

        if EMBEDDING_PROVIDER == "huggingface":
            model_name = config.HF_EMBEDDING_MODEL
            hf_token = os.getenv("HF_TOKEN", "") or os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
            if not hf_token:
                raise EmbeddingConfigError(
                    "EMBEDDING_PROVIDER is 'huggingface' but neither HF_TOKEN nor "
                    "HUGGINGFACEHUB_API_TOKEN is set. Switch to 'sentence-transformers' "
                    "or provide a HuggingFace API token."
                )
            try:
                _embeddings = HFInferenceEmbeddings(model_name)
                return _embeddings
            except Exception as e:
                raise EmbeddingConfigError(
                    f"Failed to init HuggingFace embeddings model '{model_name}': {e}"
                ) from e

        raise EmbeddingConfigError(
            f"Unsupported EMBEDDING_PROVIDER '{EMBEDDING_PROVIDER}'. "
            f"Use 'sentence-transformers' or 'huggingface'."
        )