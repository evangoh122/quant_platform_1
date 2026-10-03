"""tests/rag/test_rag_eval_corpus.py — Tests for the corpus adapter module."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rag_eval"


class TestJsonlAdapterValidatesManifest:
    """test_jsonl_adapter_validates_manifest"""

    def test_valid_manifest_loads(self, tmp_path):
        """Valid .npz with matching corpus hash loads successfully."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        corpus_line = '{"chunk_id": "c1", "ticker": "X", "chunk_text": "hello", "accepted_ts": "2024-01-01T00:00:00+00:00"}'
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(corpus_line + "\n", encoding="utf-8")
        # Hash must match how from_files computes it: stripped lines joined by \n
        corpus_sha = hashlib.sha256(corpus_line.encode()).hexdigest()

        emb_path = tmp_path / "emb.npz"
        vecs = np.random.RandomState(42).randn(1, 384).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        np.savez(
            str(emb_path),
            embeddings=vecs,
            chunk_ids=np.array(["c1"]),
            embedding_model="BAAI/bge-small-en-v1.5",
            dimension=384,
            normalized=True,
            corpus_sha256=corpus_sha,
        )

        adapter = JsonlCorpusAdapter.from_files(corpus_path, emb_path)
        assert len(adapter.records()) == 1
        assert adapter.has_embeddings
        assert adapter.embedding_dimension == 384

    def test_corpus_hash_mismatch_fails(self, tmp_path):
        """Mismatched corpus SHA raises ValueError."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text('{"chunk_id": "c1", "chunk_text": "x", "accepted_ts": "2024-01-01T00:00:00+00:00"}\n', encoding="utf-8")

        emb_path = tmp_path / "emb.npz"
        vecs = np.random.RandomState(42).randn(1, 384).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        np.savez(
            str(emb_path),
            embeddings=vecs,
            chunk_ids=np.array(["c1"]),
            embedding_model="test",
            dimension=384,
            normalized=True,
            corpus_sha256="deadbeef" * 8,
        )

        with pytest.raises(ValueError, match="Corpus hash mismatch"):
            JsonlCorpusAdapter.from_files(corpus_path, emb_path)

    def test_dimension_mismatch_fails(self, tmp_path):
        """Non-uniform embedding dimensions raise ValueError."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        corpus_content = '{"chunk_id": "c1", "chunk_text": "x", "accepted_ts": "2024-01-01T00:00:00+00:00"}\n{"chunk_id": "c2", "chunk_text": "y", "accepted_ts": "2024-01-01T00:00:00+00:00"}\n'
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(corpus_content, encoding="utf-8")
        corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()

        emb_path = tmp_path / "emb.npz"
        # Different dimensions — can't stack, so create manually
        np.savez(
            str(emb_path),
            embeddings=np.array([[1.0] * 100, [2.0] * 100], dtype=np.float32),
            chunk_ids=np.array(["c1", "c2"]),
            embedding_model="test",
            dimension=200,  # doesn't match actual dim of 100
            normalized=False,
            corpus_sha256=corpus_sha,
        )

        with pytest.raises(ValueError, match="Dimension mismatch"):
            JsonlCorpusAdapter.from_files(corpus_path, emb_path)


class TestDenseRequiresEmbeddings:
    """test_dense_requires_embeddings"""

    def test_embedding_map_raises_without_sidecar(self, tmp_path):
        """Dense mode without sidecar raises FileNotFoundError."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text('{"chunk_id": "c1", "chunk_text": "x", "accepted_ts": "2024-01-01T00:00:00+00:00"}\n', encoding="utf-8")

        adapter = JsonlCorpusAdapter.from_files(corpus_path, None)
        assert not adapter.has_embeddings
        with pytest.raises(FileNotFoundError, match="No embedding sidecar"):
            adapter.embedding_map()


class TestOfflineInstallRestoresCache:
    """test_offline_install_restores_production_cache"""

    def test_install_and_restore(self, tmp_path):
        """install_offline_corpus populates and restores the production cache."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter, install_offline_corpus
        import api.services.hybrid_retriever as hr

        corpus_path = FIXTURE_DIR / "corpus_smoke.jsonl"
        emb_path = FIXTURE_DIR / "embeddings_smoke.npz"
        adapter = JsonlCorpusAdapter.from_files(corpus_path, emb_path)

        # Save original state
        orig_loaded = hr._corpus_loaded
        orig_corpus_len = len(hr._corpus)

        with install_offline_corpus(adapter):
            # Inside context: corpus should be populated
            assert hr._corpus_loaded is True
            assert len(hr._corpus) == 10
            assert "smoke-001" in hr._corpus
            assert hr._bm25_index is not None
            assert len(hr._embeddings_map) == 10

        # After context: original state restored
        assert hr._corpus_loaded == orig_loaded
        assert len(hr._corpus) == orig_corpus_len

    def test_install_restores_on_exception(self, tmp_path):
        """install_offline_corpus restores state even when exception occurs."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter, install_offline_corpus
        import api.services.hybrid_retriever as hr

        corpus_path = FIXTURE_DIR / "corpus_smoke.jsonl"
        emb_path = FIXTURE_DIR / "embeddings_smoke.npz"
        adapter = JsonlCorpusAdapter.from_files(corpus_path, emb_path)

        orig_loaded = hr._corpus_loaded

        with pytest.raises(RuntimeError):
            with install_offline_corpus(adapter):
                assert hr._corpus_loaded is True
                raise RuntimeError("test error")

        assert hr._corpus_loaded == orig_loaded


class TestDeltaImportIsLazy:
    """test_delta_import_is_lazy"""

    def test_delta_adapter_not_loaded_until_explicit(self):
        """DeltaCorpusAdapter doesn't load until .load() is called."""
        from evals.rag_eval.corpus import DeltaCorpusAdapter

        adapter = DeltaCorpusAdapter()
        with pytest.raises(RuntimeError, match="not loaded"):
            adapter.records()
        with pytest.raises(RuntimeError, match="not loaded"):
            adapter.embedding_map()