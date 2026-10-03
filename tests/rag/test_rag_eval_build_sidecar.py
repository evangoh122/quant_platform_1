"""tests/rag/test_rag_eval_build_sidecar.py — Tests for the build_sidecar CLI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from evals.rag_eval.build_sidecar import build_sidecar


class TestBuildSidecar:
    """test_build_sidecar"""

    def test_build_sidecar_from_npy(self, tmp_path):
        """Build sidecar from .npy embeddings and .txt IDs."""
        # Create corpus
        lines = [
            json.dumps({"chunk_id": "c1", "ticker": "X", "chunk_text": "hello"}),
            json.dumps({"chunk_id": "c2", "ticker": "Y", "chunk_text": "world"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Create embeddings
        vecs = np.random.RandomState(42).randn(2, 384).astype(np.float32)
        npy_path = tmp_path / "embeddings.npy"
        np.save(str(npy_path), vecs)

        # Create IDs
        ids_path = tmp_path / "ids.txt"
        ids_path.write_text("c1\nc2\n", encoding="utf-8")

        out_path = tmp_path / "sidecar.npz"

        build_sidecar(npy_path, ids_path, corpus_path, out_path, model_name="test-model")

        # Verify the sidecar
        data = np.load(str(out_path), allow_pickle=False)
        assert "embeddings" in data
        assert "chunk_ids" in data
        assert data["embedding_model"] == "test-model"
        assert data["dimension"] == 384
        assert len(data["embeddings"]) == 2
        assert len(data["chunk_ids"]) == 2

        # Verify corpus hash matches
        corpus_content = "\n".join(lines)
        expected_sha = hashlib.sha256(corpus_content.encode()).hexdigest()
        assert str(data["corpus_sha256"]) == expected_sha

    def test_build_sidecar_validates_count_mismatch(self, tmp_path):
        """Mismatched embedding/ID count raises ValueError."""
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text('{"chunk_id": "c1", "chunk_text": "x"}\n', encoding="utf-8")

        vecs = np.random.RandomState(42).randn(3, 384).astype(np.float32)
        npy_path = tmp_path / "embeddings.npy"
        np.save(str(npy_path), vecs)

        ids_path = tmp_path / "ids.txt"
        ids_path.write_text("c1\nc2\n", encoding="utf-8")

        out_path = tmp_path / "sidecar.npz"

        with pytest.raises(ValueError, match="does not match"):
            build_sidecar(npy_path, ids_path, corpus_path, out_path)

    def test_build_sidecar_from_npy_ids(self, tmp_path):
        """Build sidecar from .npy embeddings and .npy IDs."""
        lines = [
            json.dumps({"chunk_id": "c1", "ticker": "X", "chunk_text": "hello"}),
            json.dumps({"chunk_id": "c2", "ticker": "Y", "chunk_text": "world"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        vecs = np.random.RandomState(42).randn(2, 384).astype(np.float32)
        npy_path = tmp_path / "embeddings.npy"
        np.save(str(npy_path), vecs)

        ids = np.array(["c1", "c2"])
        ids_path = tmp_path / "ids.npy"
        np.save(str(ids_path), ids)

        out_path = tmp_path / "sidecar.npz"

        build_sidecar(npy_path, ids_path, corpus_path, out_path)

        data = np.load(str(out_path), allow_pickle=False)
        assert len(data["embeddings"]) == 2
        assert list(data["chunk_ids"]) == ["c1", "c2"]

    def test_sidecar_loads_in_adapter(self, tmp_path):
        """Sidecar built by build_sidecar loads correctly in JsonlCorpusAdapter."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        lines = [
            json.dumps({"chunk_id": "c1", "ticker": "X", "chunk_text": "hello",
                        "accepted_ts": "2024-01-01T00:00:00+00:00"}),
            json.dumps({"chunk_id": "c2", "ticker": "Y", "chunk_text": "world",
                        "accepted_ts": "2024-02-01T00:00:00+00:00"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        vecs = np.random.RandomState(42).randn(2, 384).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        npy_path = tmp_path / "embeddings.npy"
        np.save(str(npy_path), vecs)

        ids_path = tmp_path / "ids.txt"
        ids_path.write_text("c1\nc2\n", encoding="utf-8")

        out_path = tmp_path / "sidecar.npz"

        build_sidecar(npy_path, ids_path, corpus_path, out_path, normalized=True)

        # Load with adapter
        adapter = JsonlCorpusAdapter.from_files(corpus_path, out_path)
        assert len(adapter.records()) == 2
        assert adapter.has_embeddings
        assert adapter.embedding_dimension == 384