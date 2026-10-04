"""evals/rag_eval/corpus.py — Corpus adapter protocol and implementations.

Provides JsonlCorpusAdapter for offline eval and DeltaCorpusAdapter for live
eval.  Also provides install_offline_corpus() to populate the production cache
for offline testing.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Protocol, Sequence

import numpy as np

from evals.rag_eval.models import CorpusRecord


# ── Timestamp resolution ─────────────────────────────────────────────────────

def _resolve_accepted_ts(obj: dict[str, Any]) -> str:
    """Resolve accepted_ts from a JSONL record dict.

    Priority:
      1. accepted_epoch (int, seconds UTC) → ISO UTC string
      2. accepted_ts (str) → pass through if non-empty
      3. Neither present → raise ValueError at load time
    """
    from datetime import datetime, timezone

    epoch = obj.get("accepted_epoch")
    ts_str = obj.get("accepted_ts", "")

    if epoch is not None:
        try:
            dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
            return dt.isoformat()
        except (ValueError, OSError) as exc:
            raise ValueError(
                f"Invalid accepted_epoch {epoch!r}: {exc}"
            ) from exc

    if ts_str:
        return ts_str

    raise ValueError(
        f"Record {obj.get('chunk_id', '?')!r} has neither accepted_epoch nor accepted_ts. "
        f"Every record must have a timestamp."
    )


# ── Adapter protocol ──────────────────────────────────────────────────────────

class CorpusAdapter(Protocol):
    """Protocol for corpus adapters."""

    def records(self) -> Sequence[CorpusRecord]:
        """Return all corpus records."""
        ...

    def embedding_map(self) -> Dict[str, np.ndarray]:
        """Return chunk_id -> embedding vector mapping.

        Raises FileNotFoundError if dense embeddings are not available.
        """
        ...


# ── JSONL corpus adapter ──────────────────────────────────────────────────────

class JsonlCorpusAdapter:
    """Offline corpus adapter loading from JSONL + optional .npz sidecar."""

    def __init__(
        self,
        records_list: list[CorpusRecord],
        embeddings: Optional[Dict[str, np.ndarray]] = None,
        embedding_model: str = "",
        embedding_dimension: int = 0,
        normalized: bool = False,
        corpus_sha256: str = "",
    ):
        self._records = records_list
        self._embeddings = embeddings
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._normalized = normalized
        self._corpus_sha256 = corpus_sha256

    @classmethod
    def from_files(
        cls,
        corpus_path: Path,
        embeddings_path: Optional[Path] = None,
    ) -> JsonlCorpusAdapter:
        """Load corpus from JSONL and optional .npz embedding sidecar."""
        records_list: list[CorpusRecord] = []
        corpus_lines: list[str] = []

        with open(corpus_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                corpus_lines.append(line)
                obj = json.loads(line)
                records_list.append(CorpusRecord(
                    chunk_id=obj["chunk_id"],
                    ticker=obj.get("ticker", ""),
                    accession=obj.get("accession_number", obj.get("accession", "")),
                    section=obj.get("filing_section", obj.get("section", "")),
                    form_type=obj.get("form_type", ""),
                    accepted_ts=_resolve_accepted_ts(obj),
                    text=obj.get("chunk_text", obj.get("text", "")),
                    chunk_index=obj.get("chunk_index", 0),
                    source_url=obj.get("source_url", ""),
                ))

        corpus_content = "\n".join(corpus_lines)
        corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()

        embeddings: Optional[Dict[str, np.ndarray]] = None
        embedding_model = ""
        embedding_dim = 0
        normalized = False

        if embeddings_path is not None:
            if not embeddings_path.exists():
                raise FileNotFoundError(
                    f"Embedding sidecar not found: {embeddings_path}. "
                    f"Dense modes require an embedding sidecar."
                )
            embeddings, embedding_model, embedding_dim, normalized = _load_npz_sidecar(
                embeddings_path, records_list, corpus_sha
            )

        return cls(
            records_list=records_list,
            embeddings=embeddings,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dim,
            normalized=normalized,
            corpus_sha256=corpus_sha,
        )

    def records(self) -> Sequence[CorpusRecord]:
        return self._records

    def embedding_map(self) -> Dict[str, np.ndarray]:
        if self._embeddings is None:
            raise FileNotFoundError(
                "No embedding sidecar loaded. Dense modes require an .npz sidecar. "
                "Use --embeddings to provide the path."
            )
        return self._embeddings

    @property
    def embedding_model_name(self) -> str:
        return self._embedding_model

    @property
    def embedding_dimension(self) -> int:
        return self._embedding_dimension

    @property
    def corpus_sha256(self) -> str:
        return self._corpus_sha256

    @property
    def has_embeddings(self) -> bool:
        return self._embeddings is not None


def _load_npz_sidecar(
    path: Path,
    records: list[CorpusRecord],
    corpus_sha: str,
) -> tuple[Dict[str, np.ndarray], str, int, bool]:
    """Load and validate .npz embedding sidecar."""
    data = np.load(str(path), allow_pickle=False)

    # Extract manifest from npz metadata
    manifest_model = str(data.get("embedding_model", ""))
    manifest_dim = int(data.get("dimension", 0))
    manifest_normalized = bool(data.get("normalized", False))
    manifest_corpus_hash = str(data.get("corpus_sha256", ""))

    # Get the embeddings array and IDs
    if "embeddings" not in data or "chunk_ids" not in data:
        raise ValueError(
            "Invalid .npz sidecar: must contain 'embeddings' and 'chunk_ids' arrays."
        )

    embeddings_arr = data["embeddings"]
    chunk_ids = data["chunk_ids"]

    if embeddings_arr.dtype != np.float32:
        raise ValueError(f"Expected float32 embeddings, got {embeddings_arr.dtype}")

    if len(embeddings_arr) != len(chunk_ids):
        raise ValueError(
            f"Embedding/ID count mismatch: {len(embeddings_arr)} embeddings vs "
            f"{len(chunk_ids)} chunk IDs."
        )

    if len(embeddings_arr) != len(records):
        raise ValueError(
            f"Embedding count ({len(embeddings_arr)}) does not match corpus record "
            f"count ({len(records)}). Sidecar must have exactly one embedding per chunk."
        )

    # Validate dimensions are uniform
    if embeddings_arr.ndim != 2:
        raise ValueError(f"Expected 2D embeddings array, got {embeddings_arr.ndim}D")

    dim = embeddings_arr.shape[1]
    if manifest_dim and dim != manifest_dim:
        raise ValueError(
            f"Dimension mismatch: manifest says {manifest_dim}, got {dim}."
        )

    # Validate all values are finite
    if not np.all(np.isfinite(embeddings_arr)):
        raise ValueError("Embeddings contain non-finite values (NaN or Inf).")

    # Validate normalization
    if manifest_normalized:
        norms = np.linalg.norm(embeddings_arr, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-3):
            raise ValueError("Manifest claims normalized but norms deviate from 1.0.")

    # Validate corpus hash
    if manifest_corpus_hash and manifest_corpus_hash != corpus_sha:
        raise ValueError(
            f"Corpus hash mismatch: sidecar was built for corpus "
            f"{manifest_corpus_hash[:12]}..., current corpus is {corpus_sha[:12]}...."
        )

    # Validate model name is present — required for the stored-model check
    # in vector_search to work correctly.
    if not manifest_model:
        raise ValueError(
            "Embedding sidecar is missing 'embedding_model' metadata. "
            "Rebuild the sidecar with --model set to the embedding model name."
        )

    # Build mapping
    emb_map: Dict[str, np.ndarray] = {}
    for i, cid in enumerate(chunk_ids):
        emb_map[str(cid)] = embeddings_arr[i]

    return emb_map, manifest_model, dim, manifest_normalized


# ── Delta corpus adapter (live) ───────────────────────────────────────────────

class DeltaCorpusAdapter:
    """Live corpus adapter loading from Delta tables."""

    def __init__(self) -> None:
        self._records_list: Optional[list[CorpusRecord]] = None
        self._embeddings_map: Optional[Dict[str, np.ndarray]] = None

    @classmethod
    def load(cls) -> DeltaCorpusAdapter:
        """Load corpus from Delta tables.

        All Databricks/Spark imports are inside this method.
        """
        adapter = cls()
        adapter._load_delta()
        return adapter

    def _load_delta(self) -> None:
        """Load from silver_sec_sections and gold_sec_chunk_embeddings."""
        from datetime import datetime, timezone

        import numpy as np
        from pyspark.sql import functions as F

        from api.services.hybrid_retriever import _get_spark, CHUNKS_TABLE, EMBEDDINGS_TABLE

        spark = _get_spark()

        # Load chunks
        chunks_df = spark.table(CHUNKS_TABLE).select(
            "chunk_id", "ticker", "chunk_text", "accession_number",
            F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch"),
            "form_type", "filing_section", "chunk_index", "source_url",
        )
        chunks_rows = chunks_df.collect()

        # Load embeddings
        embed_df = spark.table(EMBEDDINGS_TABLE).select(
            "chunk_id", "embedding", "embedding_model",
        )
        embed_rows = embed_df.collect()

        # Build embeddings map
        self._embeddings_map = {}
        for row in embed_rows:
            cid = row["chunk_id"]
            vec = row["embedding"]
            if vec is not None:
                self._embeddings_map[cid] = np.array(vec, dtype=np.float32)

        # Build records
        self._records_list = []
        for row in chunks_rows:
            cid = row["chunk_id"]
            accepted_epoch = row["accepted_epoch"]
            if accepted_epoch is not None:
                accepted_ts = datetime.fromtimestamp(
                    int(accepted_epoch), tz=timezone.utc
                ).isoformat()
            else:
                accepted_ts = ""
            self._records_list.append(CorpusRecord(
                chunk_id=cid,
                ticker=row["ticker"] or "",
                accession=row["accession_number"] or "",
                section=row["filing_section"] or "",
                form_type=row["form_type"] or "",
                accepted_ts=accepted_ts,
                text=row["chunk_text"] or "",
                chunk_index=row["chunk_index"] or 0,
                source_url=row["source_url"] or "",
            ))

    def records(self) -> Sequence[CorpusRecord]:
        if self._records_list is None:
            raise RuntimeError("DeltaCorpusAdapter not loaded. Call .load() first.")
        return self._records_list

    def embedding_map(self) -> Dict[str, np.ndarray]:
        if self._embeddings_map is None:
            raise RuntimeError("DeltaCorpusAdapter not loaded. Call .load() first.")
        return self._embeddings_map


# ── Offline corpus installation (test seam) ───────────────────────────────────

_install_lock = threading.Lock()


@contextlib.contextmanager
def install_offline_corpus(adapter: JsonlCorpusAdapter) -> Iterator[None]:
    """Populate the production hybrid_retriever cache with offline data.

    This is an explicit test/eval seam around production scoring — not a forked
    retriever implementation.  Restores prior globals even after errors and
    serializes concurrent use.
    """
    import api.services.hybrid_retriever as hr

    with _install_lock:
        # Save originals
        orig_corpus = dict(hr._corpus)
        orig_bm25_docs = hr._bm25_docs
        orig_bm25_tokenised = hr._bm25_tokenised
        orig_bm25_index = hr._bm25_index
        orig_embeddings_map = dict(hr._embeddings_map)
        orig_loaded = hr._corpus_loaded
        orig_dim = hr._stored_index_dim
        orig_model = hr._stored_embedding_model

        # Save per-ticker LRU cache
        with hr._ticker_cache_lock:
            orig_ticker_cache = dict(hr._ticker_cache)

        try:
            # Clear and repopulate
            hr._corpus.clear()
            hr._embeddings_map.clear()
            hr._bm25_docs = None
            hr._bm25_tokenised = None
            hr._bm25_index = None
            hr._corpus_loaded = False
            hr._stored_index_dim = None
            hr._stored_embedding_model = None

            # Install corpus records
            from collections import defaultdict
            from langchain_core.documents import Document
            from rank_bm25 import BM25Okapi
            from api.services.hybrid_retriever import tokenize, TickerCorpus

            docs: list[Document] = []
            tokenised: list[list[str]] = []

            # Group by ticker for per-ticker cache
            ticker_docs: dict[str, list[Document]] = defaultdict(list)
            ticker_tokenised: dict[str, list[list[str]]] = defaultdict(list)

            for rec in adapter.records():
                hr._corpus[rec.chunk_id] = (
                    rec.text, rec.ticker, rec.accession, rec.accepted_ts,
                    rec.form_type, rec.section, rec.chunk_index, rec.source_url,
                )
                doc = Document(
                    page_content=rec.text,
                    metadata={
                        "chunk_id": rec.chunk_id,
                        "ticker": rec.ticker,
                        "accession": rec.accession,
                        "accepted_ts": rec.accepted_ts,
                        "form_type": rec.form_type,
                        "section_id": rec.section,
                        "chunk_index": rec.chunk_index,
                        "source_url": rec.source_url,
                    },
                )
                docs.append(doc)
                tok = tokenize(rec.text)
                tokenised.append(tok)

                if rec.ticker:
                    ticker_docs[rec.ticker].append(doc)
                    ticker_tokenised[rec.ticker].append(tok)

            if tokenised:
                hr._bm25_index = BM25Okapi(tokenised)
            hr._bm25_docs = docs
            hr._bm25_tokenised = tokenised

            # Install embeddings if available
            if adapter.has_embeddings:
                emb_map = adapter.embedding_map()
                hr._embeddings_map.update(emb_map)
                hr._stored_index_dim = adapter.embedding_dimension
                hr._stored_embedding_model = adapter.embedding_model_name

            # Build and install per-ticker TickerCorpus objects
            with hr._ticker_cache_lock:
                hr._ticker_cache.clear()

            for ticker, tdocs in ticker_docs.items():
                ttok = ticker_tokenised[ticker]
                bm25 = BM25Okapi(ttok) if ttok else None
                # Build per-ticker embeddings map
                ticker_emb: dict[str, np.ndarray] = {}
                for d in tdocs:
                    cid = d.metadata.get("chunk_id", "")
                    if cid in hr._embeddings_map:
                        ticker_emb[cid] = hr._embeddings_map[cid]

                corpus = TickerCorpus(
                    ticker=ticker,
                    docs=tdocs,
                    tokenised=ttok,
                    bm25_index=bm25,
                    embeddings_map=ticker_emb,
                    stored_model=adapter.embedding_model_name or None,
                    stored_dim=adapter.embedding_dimension or None,
                    load_ts=0.0,
                    approx_bytes=0,
                )
                hr._insert_ticker_corpus(ticker, corpus)

            hr._corpus_loaded = True
            yield

        finally:
            # Restore originals
            hr._corpus.clear()
            hr._corpus.update(orig_corpus)
            hr._bm25_docs = orig_bm25_docs
            hr._bm25_tokenised = orig_bm25_tokenised
            hr._bm25_index = orig_bm25_index
            hr._embeddings_map.clear()
            hr._embeddings_map.update(orig_embeddings_map)
            hr._corpus_loaded = orig_loaded
            hr._stored_index_dim = orig_dim
            hr._stored_embedding_model = orig_model

            # Restore per-ticker LRU cache
            with hr._ticker_cache_lock:
                hr._ticker_cache.clear()
                hr._ticker_cache.update(orig_ticker_cache)


# ── Export utilities ──────────────────────────────────────────────────────────

def export_delta_embeddings(output_path: Path) -> None:
    """Export embeddings from Delta tables to .npz sidecar for offline use.

    This is a one-time live export command.  Requires Databricks connectivity.
    """
    from datetime import datetime, timezone

    import numpy as np
    from pyspark.sql import functions as F

    from api.services.hybrid_retriever import _get_spark, CHUNKS_TABLE, EMBEDDINGS_TABLE

    spark = _get_spark()

    # Load corpus for SHA
    chunks_df = spark.table(CHUNKS_TABLE).select("chunk_id")
    chunk_ids = [row["chunk_id"] for row in chunks_df.collect()]

    # Load embeddings
    embed_df = spark.table(EMBEDDINGS_TABLE).select(
        "chunk_id", "embedding", "embedding_model",
    )
    embed_rows = embed_df.collect()

    # Build arrays
    ids_list: list[str] = []
    vecs_list: list[np.ndarray] = []
    model_name = ""
    for row in embed_rows:
        cid = row["chunk_id"]
        vec = row["embedding"]
        if vec is not None:
            ids_list.append(cid)
            vecs_list.append(np.array(vec, dtype=np.float32))
            if not model_name and row["embedding_model"]:
                model_name = row["embedding_model"]

    if not vecs_list:
        raise ValueError("No embeddings found in Delta table.")

    embeddings_arr = np.stack(vecs_list)
    dim = embeddings_arr.shape[1]

    # Normalize
    norms = np.linalg.norm(embeddings_arr, axis=1, keepdims=True)
    embeddings_arr = embeddings_arr / norms

    # Compute corpus SHA from sorted chunk IDs
    corpus_content = "\n".join(sorted(chunk_ids))
    corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()

    np.savez(
        str(output_path),
        embeddings=embeddings_arr,
        chunk_ids=np.array(ids_list),
        embedding_model=model_name,
        dimension=dim,
        normalized=True,
        corpus_sha256=corpus_sha,
    )


def build_local_embeddings(
    corpus_path: Path,
    output_path: Path,
    model_name: str = "BAAI/bge-small-en-v1.5",
    revision: str = "main",
) -> None:
    """Build embeddings locally using sentence-transformers.

    Records exact model/revision and corpus hash.  Not for CI use.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer

    # Load corpus
    records_list: list[CorpusRecord] = []
    corpus_lines: list[str] = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            corpus_lines.append(line)
            obj = json.loads(line)
            records_list.append(CorpusRecord(
                chunk_id=obj["chunk_id"],
                ticker=obj.get("ticker", ""),
                accession=obj.get("accession_number", obj.get("accession", "")),
                section=obj.get("filing_section", obj.get("section", "")),
                form_type=obj.get("form_type", ""),
                accepted_ts=_resolve_accepted_ts(obj),
                text=obj.get("chunk_text", obj.get("text", "")),
                chunk_index=obj.get("chunk_index", 0),
                source_url=obj.get("source_url", ""),
            ))

    corpus_content = "\n".join(corpus_lines)
    corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()

    # Load model
    model = SentenceTransformer(model_name, revision=revision)
    dim = model.get_sentence_embedding_dimension()

    # Encode
    texts = [r.text for r in records_list]
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)

    chunk_ids = [r.chunk_id for r in records_list]

    np.savez(
        str(output_path),
        embeddings=embeddings,
        chunk_ids=np.array(chunk_ids),
        embedding_model=model_name,
        dimension=dim,
        normalized=True,
        corpus_sha256=corpus_sha,
    )