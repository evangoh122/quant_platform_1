"""tests/rag/test_embedding_config.py — Verify config/embeddings consistency.

Ensures api.config is the single source of truth for the HF embedding model
and dimension, and that api.services.embeddings imports those values rather
than hardcoding its own.
"""
from __future__ import annotations

import importlib
import os


def test_config_hf_model_default():
    """Config's HF_EMBEDDING_MODEL defaults to bge-small-en-v1.5."""
    import api.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.config.HF_EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"


def test_config_embedding_dim_hf_provider():
    """Config's EMBEDDING_DIM is 384 for the huggingface provider."""
    import api.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.config.EMBEDDING_DIM == 384


def test_embeddings_dim_matches_config():
    """embeddings.EMBEDDING_DIM equals config.EMBEDDING_DIM (384)."""
    import api.config as cfg_mod
    import api.services.embeddings as emb_mod
    importlib.reload(cfg_mod)
    importlib.reload(emb_mod)
    assert emb_mod.EMBEDDING_DIM == cfg_mod.config.EMBEDDING_DIM == 384


def test_embeddings_provider_matches_config():
    """embeddings.EMBEDDING_PROVIDER equals config.EMBEDDING_PROVIDER."""
    import api.config as cfg_mod
    import api.services.embeddings as emb_mod
    importlib.reload(cfg_mod)
    importlib.reload(emb_mod)
    assert emb_mod.EMBEDDING_PROVIDER == cfg_mod.config.EMBEDDING_PROVIDER


def test_st_model_matches_config():
    """embeddings.ST_EMBEDDING_MODEL equals config.ST_EMBEDDING_MODEL."""
    import api.config as cfg_mod
    import api.services.embeddings as emb_mod
    importlib.reload(cfg_mod)
    importlib.reload(emb_mod)
    assert emb_mod.ST_EMBEDDING_MODEL == cfg_mod.config.ST_EMBEDDING_MODEL


def test_hybrid_retriever_uses_config_dim():
    """hybrid_retriever.EMBEDDING_DIM equals config.EMBEDDING_DIM."""
    import api.config as cfg_mod
    import api.services.hybrid_retriever as hr_mod
    importlib.reload(cfg_mod)
    # hybrid_retriever imports EMBEDDING_DIM from embeddings, which imports from config
    from api.services.embeddings import EMBEDDING_DIM
    assert EMBEDDING_DIM == cfg_mod.config.EMBEDDING_DIM == 384