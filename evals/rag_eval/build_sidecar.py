"""evals/rag_eval/build_sidecar.py — Build .npz embedding sidecar from pre-computed arrays.

Usage:
    python -m evals.rag_eval.build_sidecar --npy embeddings.npy --ids chunk_ids.npy --corpus corpus.jsonl --out sidecar.npz

Or with raw float32 binary:
    python -m evals.rag_eval.build_sidecar --npy embeddings.f32 --ids chunk_ids.txt --corpus corpus.jsonl --out sidecar.npz --dim 384

Writes the .npz with the manifest the loader expects, corpus hash included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def _compute_corpus_sha(corpus_path: Path) -> str:
    """Compute SHA-256 of the corpus JSONL (stripped lines joined by \\n)."""
    lines: list[str] = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)
    content = "\n".join(lines)
    return hashlib.sha256(content.encode()).hexdigest()


def _load_ids(ids_path: Path) -> np.ndarray:
    """Load chunk IDs from .npy or .txt file."""
    if ids_path.suffix == ".npy":
        return np.load(str(ids_path), allow_pickle=False)
    elif ids_path.suffix == ".txt":
        with open(ids_path, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
        return np.array(ids)
    else:
        raise ValueError(f"Unsupported ID file format: {ids_path.suffix}. Use .npy or .txt.")


def _load_embeddings(npy_path: Path, dim: int | None = None) -> np.ndarray:
    """Load embeddings from .npy or raw .f32 file."""
    if npy_path.suffix == ".npy":
        arr = np.load(str(npy_path), allow_pickle=False)
    elif npy_path.suffix == ".f32":
        if dim is None:
            raise ValueError("--dim is required for raw .f32 files")
        arr = np.fromfile(str(npy_path), dtype=np.float32)
        if len(arr) % dim != 0:
            raise ValueError(
                f"File size ({len(arr)} floats) is not divisible by dim ({dim})"
            )
        arr = arr.reshape(-1, dim)
    else:
        raise ValueError(f"Unsupported embedding file format: {npy_path.suffix}. Use .npy or .f32.")

    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)

    if arr.ndim != 2:
        raise ValueError(f"Expected 2D embeddings array, got {arr.ndim}D")

    return arr


def build_sidecar(
    npy_path: Path,
    ids_path: Path,
    corpus_path: Path,
    out_path: Path,
    model_name: str = "",
    dim: int | None = None,
    normalized: bool = False,
) -> None:
    """Build .npz embedding sidecar from pre-computed arrays.

    Args:
        npy_path: Path to embeddings (.npy or raw .f32).
        ids_path: Path to chunk IDs (.npy or .txt).
        corpus_path: Path to corpus JSONL (for hash validation).
        out_path: Output .npz path.
        model_name: Embedding model name (required metadata for stored-model check).
        dim: Embedding dimension (required for raw .f32 files).
        normalized: Whether embeddings are L2-normalized.
    """
    if not model_name:
        raise ValueError(
            "model_name is required. The embedding model name must be recorded "
            "in the sidecar for the stored-model check in vector_search to work. "
            "Example: --model BAAI/bge-small-en-v1.5"
        )

    embeddings = _load_embeddings(npy_path, dim)
    chunk_ids = _load_ids(ids_path)
    corpus_sha = _compute_corpus_sha(corpus_path)

    if len(embeddings) != len(chunk_ids):
        raise ValueError(
            f"Embedding count ({len(embeddings)}) does not match ID count ({len(chunk_ids)})."
        )

    actual_dim = embeddings.shape[1]

    # Validate normalization if claimed
    if normalized:
        norms = np.linalg.norm(embeddings, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-3):
            print("WARNING: --normalized claimed but norms deviate from 1.0", file=sys.stderr)

    np.savez(
        str(out_path),
        embeddings=embeddings,
        chunk_ids=chunk_ids,
        embedding_model=model_name,
        dimension=actual_dim,
        normalized=normalized,
        corpus_sha256=corpus_sha,
    )

    print(f"Wrote sidecar to {out_path}")
    print(f"  Embeddings: {embeddings.shape[0]} x {actual_dim}")
    print(f"  Model: {model_name or '(unspecified)'}")
    print(f"  Normalized: {normalized}")
    print(f"  Corpus SHA: {corpus_sha[:16]}...")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build .npz embedding sidecar from pre-computed arrays",
        prog="python -m evals.rag_eval.build_sidecar",
    )
    parser.add_argument(
        "--npy", type=Path, required=True,
        help="Path to embeddings file (.npy or raw .f32)",
    )
    parser.add_argument(
        "--ids", type=Path, required=True,
        help="Path to chunk IDs file (.npy or .txt, one ID per line)",
    )
    parser.add_argument(
        "--corpus", type=Path, required=True,
        help="Path to corpus JSONL (for hash validation)",
    )
    parser.add_argument(
        "--out", type=Path, required=True,
        help="Output .npz path",
    )
    parser.add_argument(
        "--model", type=str, default="",
        help="Embedding model name (metadata)",
    )
    parser.add_argument(
        "--dim", type=int, default=None,
        help="Embedding dimension (required for raw .f32 files)",
    )
    parser.add_argument(
        "--normalized", action="store_true",
        help="Claim that embeddings are L2-normalized",
    )

    args = parser.parse_args(argv)

    if not args.npy.exists():
        print(f"ERROR: Embeddings file not found: {args.npy}", file=sys.stderr)
        return 1
    if not args.ids.exists():
        print(f"ERROR: IDs file not found: {args.ids}", file=sys.stderr)
        return 1
    if not args.corpus.exists():
        print(f"ERROR: Corpus file not found: {args.corpus}", file=sys.stderr)
        return 1

    try:
        build_sidecar(
            npy_path=args.npy,
            ids_path=args.ids,
            corpus_path=args.corpus,
            out_path=args.out,
            model_name=args.model,
            dim=args.dim,
            normalized=args.normalized,
        )
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())