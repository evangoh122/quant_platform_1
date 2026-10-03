"""
hybrid_retriever.py — BM25 + Vector hybrid retrieval with RRF fusion.

Combines semantic (vector cosine similarity) and lexical (BM25) search on the
same corpus, then fuses rankings via Reciprocal Rank Fusion (RRF) before
handing off to the cross-encoder reranker.

Pipeline:  Chunk -> [BM25 + Vector] -> RRF -> Rerank -> LLM

Corpus source: Delta tables via databricks-connect (serverless).
  - Chunk text:  bootcamp_students.evangoh_capstone.silver_sec_sections
  - Embeddings:  bootcamp_students.evangoh_capstone.gold_sec_chunk_embeddings

Per-ticker lazy loading with bounded LRU cache. Each ticker's corpus is loaded
independently and cached. A process-wide OrderedDict acts as an LRU with
configurable max size (RAG_TICKER_CACHE_MAX, default 32).

Point-in-time: every retrieval takes ``as_of`` (default now) and may only
return chunks with ``accepted_ts <= as_of``.  The filter is applied BEFORE
scoring, not after reranking.  Missing/null accepted_ts chunks are EXCLUDED.
"""
from __future__ import annotations

import collections
import hashlib
import os
import re
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
from langchain_core.documents import Document
from loguru import logger
from rank_bm25 import BM25Okapi

from api.services.embeddings import get_embeddings
from api.services.exceptions import CorpusUnavailableError, EmbeddingConfigError


# ── Custom exceptions ─────────────────────────────────────────────────────────

class TickerRequiredError(Exception):
    """Raised when no ticker could be resolved for a query."""


class NoCoverageError(Exception):
    """Raised when a ticker has no SEC coverage (zero chunks)."""


# ── Config ────────────────────────────────────────────────────────────────────

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")

CHUNKS_TABLE = f"{CATALOG}.{SCHEMA}.silver_sec_sections"
EMBEDDINGS_TABLE = f"{CATALOG}.{SCHEMA}.gold_sec_chunk_embeddings"
COVERAGE_TABLE = f"{CATALOG}.{SCHEMA}.gold_sec_coverage"

# LRU cache size for per-ticker corpora
_RAG_TICKER_CACHE_MAX_RAW = os.getenv("RAG_TICKER_CACHE_MAX", "32")
try:
    _RAG_TICKER_CACHE_MAX = int(_RAG_TICKER_CACHE_MAX_RAW)
    if _RAG_TICKER_CACHE_MAX <= 0:
        raise ValueError
except ValueError:
    raise ValueError(
        f"RAG_TICKER_CACHE_MAX must be a positive integer, got '{_RAG_TICKER_CACHE_MAX_RAW}'"
    )

# Soft per-ticker memory budget in bytes (~12 MB)
_TICHER_CORPUS_SOFT_BUDGET = 12 * 1024 * 1024


# ── TickerCorpus dataclass ────────────────────────────────────────────────────

@dataclass
class TickerCorpus:
    """Immutable per-ticker corpus holding docs, BM25 index, and embeddings."""
    ticker: str
    docs: List[Document]
    tokenised: List[List[str]]
    bm25_index: Optional[BM25Okapi]
    embeddings_map: Dict[str, np.ndarray]
    stored_model: Optional[str]
    stored_dim: Optional[int]
    load_ts: float
    approx_bytes: int


# ── Per-ticker LRU cache ──────────────────────────────────────────────────────

# OrderedDict for LRU: move_to_end on access, popitem(last=False) for LRU eviction
_ticker_cache: collections.OrderedDict[str, TickerCorpus] = collections.OrderedDict()
_ticker_cache_lock = threading.RLock()

# In-flight load futures for coalescing concurrent requests
_inflight: Dict[str, Future] = {}
_inflight_lock = threading.Lock()


def _approx_corpus_bytes(
    docs: List[Document],
    embeddings_map: Dict[str, np.ndarray],
) -> int:
    """Estimate memory footprint of a ticker corpus."""
    text_bytes = sum(len(d.page_content.encode("utf-8")) for d in docs)
    vec_bytes = sum(v.nbytes for v in embeddings_map.values())
    # Rough overhead for Python objects, dicts, BM25 arrays
    overhead = len(docs) * 200 + len(embeddings_map) * 100
    return text_bytes + vec_bytes + overhead


def _get_spark():
    """Get a Spark session."""
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    else:
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()


def _load_ticker_corpus(ticker: str) -> TickerCorpus:
    """Load corpus for a single ticker from Delta tables.

    Pushes ticker predicate into both Spark reads before collect().
    """
    t0 = time.monotonic()
    spark = _get_spark()

    from pyspark.sql import functions as F

    # Load chunks for this ticker only
    chunks_df = (
        spark.table(CHUNKS_TABLE)
        .filter(F.col("ticker") == ticker)
        .select(
            "chunk_id", "ticker", "chunk_text", "accession_number",
            F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch"),
            "form_type", "filing_section", "chunk_index",
            "source_url",
        )
    )
    chunks_rows = chunks_df.collect()

    # Load embeddings for this ticker and configured model
    embed_df = (
        spark.table(EMBEDDINGS_TABLE)
        .filter(
            (F.col("ticker") == ticker)
            & (F.col("embedding_model") == _get_embedding_model())
        )
        .select("chunk_id", "embedding", "embedding_model")
    )
    embed_rows = embed_df.collect()

    # Build embedding map
    embeddings_map: Dict[str, np.ndarray] = {}
    seen_dims: set = set()
    seen_models: set = set()

    for row in embed_rows:
        cid = row["chunk_id"]
        vec = row["embedding"]
        if vec is not None:
            arr = np.array(vec, dtype=np.float32)
            embeddings_map[cid] = arr
            seen_dims.add(len(arr))
        model_name = row["embedding_model"]
        if model_name:
            seen_models.add(model_name)

    # Validate stored dimensions are uniform
    stored_dim: Optional[int] = None
    if seen_dims and len(seen_dims) > 1:
        raise CorpusUnavailableError(
            f"Embedding dimension mismatch for {ticker}: found {sorted(seen_dims)}. "
            f"The index is corrupted — rebuild embeddings."
        )
    stored_dim = next(iter(seen_dims), None) if seen_dims else None

    stored_model: Optional[str] = None
    if len(seen_models) > 1:
        raise CorpusUnavailableError(
            f"Multiple embedding models for {ticker}: {sorted(seen_models)}. "
            f"Rebuild embeddings with a single model."
        )
    stored_model = next(iter(seen_models), None) if seen_models else None

    # Build docs and BM25 index
    docs: List[Document] = []
    tokenised: List[List[str]] = []

    for row in chunks_rows:
        cid = row["chunk_id"]
        text = row["chunk_text"] or ""
        ticker_val = row["ticker"] or ""
        accession = row["accession_number"] or ""
        accepted_epoch = row["accepted_epoch"]
        if accepted_epoch is not None:
            accepted_ts = datetime.fromtimestamp(
                int(accepted_epoch), tz=timezone.utc
            ).isoformat()
        else:
            accepted_ts = ""
        form_type = row["form_type"] or ""
        section_id = row["filing_section"] or ""
        chunk_index = row["chunk_index"] or 0
        source_url = row["source_url"] or _accession_to_sec_url(accession)

        doc = Document(
            page_content=text,
            metadata={
                "chunk_id": cid,
                "ticker": ticker_val,
                "accession": accession,
                "accepted_ts": accepted_ts,
                "form_type": form_type,
                "section_id": section_id,
                "chunk_index": chunk_index,
                "source_url": source_url,
            },
        )
        docs.append(doc)
        tokenised.append(tokenize(text))

    bm25_index = BM25Okapi(tokenised) if tokenised else None

    approx_bytes = _approx_corpus_bytes(docs, embeddings_map)
    load_ts = time.monotonic()
    elapsed = load_ts - t0

    logger.info(
        "Ticker corpus loaded: {} chunks, {} embeddings, {:.1f} MB, {:.1f}s",
        len(chunks_rows), len(embeddings_map),
        approx_bytes / (1024 * 1024), elapsed,
    )

    return TickerCorpus(
        ticker=ticker,
        docs=docs,
        tokenised=tokenised,
        bm25_index=bm25_index,
        embeddings_map=embeddings_map,
        stored_model=stored_model,
        stored_dim=stored_dim,
        load_ts=load_ts,
        approx_bytes=approx_bytes,
    )


def _get_embedding_model() -> str:
    """Get the configured embedding model name."""
    return os.getenv("ST_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


def _accession_to_sec_url(accession: str) -> str:
    """Convert accession number to SEC EDGAR URL."""
    clean = accession.replace("-", "")
    return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&accession={clean}"


def get_ticker_corpus(ticker: str) -> TickerCorpus:
    """Get or load the corpus for a ticker, with LRU caching and coalesced loads.

    Thread-safe. Concurrent requests for the same ticker coalesce to one load.
    """
    ticker = ticker.upper().strip()

    # Fast path: check cache
    with _ticker_cache_lock:
        if ticker in _ticker_cache:
            _ticker_cache.move_to_end(ticker)
            return _ticker_cache[ticker]

    # Check if a load is already in-flight
    with _inflight_lock:
        if ticker in _inflight:
            future = _inflight[ticker]
        else:
            future = Future()
            _inflight[ticker] = future

            # We are the loader
            try:
                corpus = _load_ticker_corpus(ticker)
                _insert_ticker_corpus(ticker, corpus)
                future.set_result(corpus)
            except Exception as e:
                future.set_exception(e)
                # Remove in-flight marker so later requests can retry
                with _inflight_lock:
                    _inflight.pop(ticker, None)
                raise

    return future.result()


def _insert_ticker_corpus(ticker: str, corpus: TickerCorpus) -> None:
    """Insert corpus into LRU cache, evicting LRU entries if needed."""
    with _ticker_cache_lock:
        _ticker_cache[ticker] = corpus
        _ticker_cache.move_to_end(ticker)

        # Evict LRU entries until we're within bounds
        while len(_ticker_cache) > _RAG_TICKER_CACHE_MAX:
            evicted_ticker, _ = _ticker_cache.popitem(last=False)
            logger.debug("Evicted ticker corpus: {}", evicted_ticker)

    # Clean up in-flight marker
    with _inflight_lock:
        _inflight.pop(ticker, None)


def reload_corpus(ticker: Optional[str] = None) -> None:
    """Invalidate one ticker or all tickers under lock without eager reload."""
    with _ticker_cache_lock:
        if ticker:
            _ticker_cache.pop(ticker.upper().strip(), None)
        else:
            _ticker_cache.clear()


# ── Normalize as_of ──────────────────────────────────────────────────────────

def _normalize_as_of(as_of: Optional[datetime] = None) -> datetime:
    """Normalise *as_of* to a tz-aware UTC datetime."""
    if as_of is None:
        return datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        return as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(timezone.utc)


# ── Tokenizer ────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenisation for BM25."""
    return text.lower().split()


# ── RRF fusion ───────────────────────────────────────────────────────────────

def rrf_fuse(
    ranked_lists: list[list[Document]],
    k: int = 60,
    boost_ticker: str = "",
    ticker_boost: float = 2.0,
) -> list[Document]:
    """Reciprocal Rank Fusion over multiple ranked lists.

    Optionally boosts documents matching ``boost_ticker`` by ``ticker_boost``.
    De-duplicates by (ticker, accession, md5[:16]) of content.
    """
    scores: dict[tuple, float] = {}
    docs_by_key: dict[tuple, Document] = {}

    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked):
            key = (
                doc.metadata.get("ticker", ""),
                doc.metadata.get("accession", ""),
                hashlib.md5(doc.page_content[:500].encode()).hexdigest()[:16],
            )
            score = 1.0 / (k + rank + 1)
            if boost_ticker and doc.metadata.get("ticker") == boost_ticker:
                score *= ticker_boost
            scores[key] = scores.get(key, 0.0) + score
            if key not in docs_by_key:
                docs_by_key[key] = doc

    sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
    results = []
    for key in sorted_keys:
        doc = docs_by_key[key]
        doc.metadata["rrf_score"] = scores[key]
        results.append(doc)
    return results


# ── Company aliases ──────────────────────────────────────────────────────────

_COMPANY_ALIASES: dict[str, str] = {
    "analog devices": "ADI",
    "advanced micro devices": "AMD",
    "apple": "AAPL",
    "applied materials": "AMAT",
    "arm holdings": "ARM",
    "asml holding": "ASML",
    "asml": "ASML",
    "broadcom": "AVGO",
    "cadence design": "CDNS",
    "intel": "INTC",
    "kla": "KLAC",
    "lam research": "LRCX",
    "marvell": "MRVL",
    "microchip": "MCHP",
    "micron": "MU",
    "mpwr": "MPWR",
    "monolithic power": "MPWR",
    "nvidia": "NVDA",
    "nxp": "NXPI",
    "nxp semiconductors": "NXPI",
    "on semiconductor": "ON",
    "qualcomm": "QCOM",
    "skyworks": "SWKS",
    "stmicroelectronics": "STM",
    "synopsys": "SNPS",
    "taiwan semiconductor": "TSM",
    "teradyne": "TER",
    "texas instruments": "TXN",
    "tsmc": "TSM",
}

_ALIAS_PATTERNS = sorted(
    [(re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE), v)
     for k, v in _COMPANY_ALIASES.items()],
    key=lambda x: len(x[0].pattern),
    reverse=True,
)


def resolve_ticker_from_query(
    query: str,
    ticker: Optional[str] = None,
) -> str:
    """Resolve a ticker from explicit parameter or query text.

    Returns the ticker string, or empty string if not resolved.
    """
    if ticker:
        return ticker.upper().strip()

    for pattern, t in _ALIAS_PATTERNS:
        if pattern.search(query):
            return t
    return ""


# ── Coverage lookup ──────────────────────────────────────────────────────────

def check_ticker_coverage(ticker: str) -> Tuple[int, Optional[str]]:
    """Check coverage for a ticker. Returns (n_chunks, cik).

    Raises NoCoverageError if the ticker has zero chunks.
    """
    ticker = ticker.upper().strip()
    try:
        spark = _get_spark()
        from pyspark.sql import functions as F

        row = (
            spark.table(COVERAGE_TABLE)
            .filter(F.col("ticker") == ticker)
            .select("n_chunks", "cik")
            .collect()
        )
        if not row:
            raise NoCoverageError(ticker)

        n_chunks = row[0]["n_chunks"] or 0
        cik = row[0]["cik"]
        if n_chunks == 0:
            raise NoCoverageError(ticker)

        return n_chunks, cik
    except NoCoverageError:
        raise
    except Exception as e:
        logger.warning("Coverage lookup failed for {}: {}", ticker, e)
        # Don't mask NoCoverageError - let the caller handle lookup failures
        raise


# ── Point-in-time filter ─────────────────────────────────────────────────────

def _parse_ts(ts_str: str) -> Optional[datetime]:
    """Parse a timestamp string to UTC datetime."""
    if not ts_str or ts_str == "None":
        return None
    try:
        ts_str = ts_str.replace("T", " ").replace("Z", "+00:00")
        if "+" not in ts_str and ts_str.endswith(":00"):
            pass
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _pit_filter(
    docs: List[Document],
    as_of: Optional[datetime] = None,
) -> List[Document]:
    """Filter documents to only include those with accepted_ts <= as_of.

    Applied BEFORE scoring so future filings never influence ranking.
    Missing/null accepted_ts chunks are EXCLUDED (not defensively included).
    """
    as_of = _normalize_as_of(as_of)

    filtered = []
    for doc in docs:
        accepted_ts_str = doc.metadata.get("accepted_ts", "")
        accepted_dt = _parse_ts(accepted_ts_str)
        if accepted_dt is not None and accepted_dt <= as_of:
            filtered.append(doc)
        # Missing/null accepted_ts: EXCLUDED (all newly published chunks require
        # authoritative acceptance time)
    return filtered


# ── BM25 search ──────────────────────────────────────────────────────────────

def bm25_search(
    query: str,
    top_k: int = 5,
    ticker: str = "",
    ticker_boost: float = 2.0,
    as_of: Optional[datetime] = None,
) -> list[Document]:
    """Run BM25 keyword search over the per-ticker corpus.

    When ticker is provided, raw BM25 scores for matching docs are multiplied
    by ticker_boost before ranking.

    Raises CorpusUnavailableError if the corpus cannot be loaded.
    Raises TickerRequiredError if no ticker is resolved.
    """
    if not ticker:
        raise TickerRequiredError("A ticker is required for retrieval")

    as_of = _normalize_as_of(as_of)

    try:
        corpus = get_ticker_corpus(ticker)
    except Exception as e:
        raise CorpusUnavailableError(f"Failed to load corpus for {ticker}: {e}") from e

    if corpus.bm25_index is None or not corpus.docs:
        return []

    # Apply PIT filter before scoring
    docs = _pit_filter(corpus.docs, as_of)
    if not docs:
        return []

    # Build temporary BM25 index for the PIT subset
    tokenised = [tokenize(d.page_content) for d in docs]
    bm25 = BM25Okapi(tokenised)

    query_tokens = tokenize(query)
    raw_scores = bm25.get_scores(query_tokens)

    scored = sorted(enumerate(raw_scores), key=lambda x: x[1], reverse=True)
    return [docs[idx] for idx, _ in scored[:top_k]]


# ── Dense vector search ─────────────────────────────────────────────────────

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Both must be normalised."""
    return float(np.dot(a, b))


def vector_search(
    query: str,
    top_k: int = 5,
    ticker: str = "",
    as_of: Optional[datetime] = None,
) -> list[Document]:
    """Run brute-force cosine similarity search over the per-ticker embeddings.

    Raises CorpusUnavailableError if the corpus cannot be loaded.
    Raises TickerRequiredError if no ticker is resolved.
    """
    if not ticker:
        raise TickerRequiredError("A ticker is required for retrieval")

    as_of = _normalize_as_of(as_of)

    try:
        corpus = get_ticker_corpus(ticker)
    except Exception as e:
        raise CorpusUnavailableError(f"Failed to load corpus for {ticker}: {e}") from e

    if not corpus.embeddings_map:
        return []

    embeddings = get_embeddings()
    qvec = np.array(embeddings.embed_query(query), dtype=np.float32)

    # Verify query vector dimension matches stored index dimension
    if corpus.stored_dim is not None and len(qvec) != corpus.stored_dim:
        raise EmbeddingConfigError(
            f"query embedding dim {len(qvec)} != stored index dim {corpus.stored_dim}; "
            f"check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL / EMBEDDING_DIM",
            user_safe=True,
        )

    # Verify active embedding model matches stored model
    if corpus.stored_model is not None:
        from api.config import config as _cfg
        provider = _cfg.EMBEDDING_PROVIDER
        if provider in ("sentence-transformers", "sentence_transformers", "local", "st"):
            active_model = _cfg.ST_EMBEDDING_MODEL
        else:
            active_model = _cfg.HF_EMBEDDING_MODEL
        if active_model and active_model != corpus.stored_model:
            raise EmbeddingConfigError(
                f"embedding model mismatch: active '{active_model}' != stored '{corpus.stored_model}'; "
                f"check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL",
                user_safe=True,
            )

    # Build candidates with PIT and ticker filter applied before scoring
    candidates: List[Tuple[float, Document]] = []
    for cid, vec in corpus.embeddings_map.items():
        # Find the doc for this chunk
        doc = None
        for d in corpus.docs:
            if d.metadata.get("chunk_id") == cid:
                doc = d
                break
        if doc is None:
            continue

        # Apply PIT filter
        accepted_dt = _parse_ts(doc.metadata.get("accepted_ts", ""))
        if accepted_dt is not None and accepted_dt > as_of:
            continue

        sim = _cosine_similarity(qvec, vec)
        result_doc = Document(
            page_content=doc.page_content,
            metadata={
                **doc.metadata,
                "distance": 1.0 - sim,
                "similarity": sim,
            },
        )
        candidates.append((sim, result_doc))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in candidates[:top_k]]


# ── Hybrid Retriever ─────────────────────────────────────────────────────────

class HybridRetriever:
    """BM25 + Vector hybrid retriever with RRF fusion.

    Requires a ticker. Uses per-ticker lazy loading with bounded LRU cache.
    """

    def __init__(
        self,
        top_k: int = 5,
        rrf_k: int = 60,
        ticker_boost: float = 2.0,
    ):
        self.top_k = top_k
        self.rrf_k = rrf_k
        self.ticker_boost = ticker_boost

    def retrieve(
        self,
        query: str,
        ticker: str = "",
        as_of: Optional[datetime] = None,
        top_k: Optional[int] = None,
    ) -> List[Document]:
        """Run hybrid retrieval with RRF fusion.

        Args:
            query: The search query.
            ticker: Required ticker filter.
            as_of: Point-in-time cutoff (default: now).
            top_k: Override for number of results.

        Returns:
            Fused and optionally reranked list of Documents.

        Raises:
            TickerRequiredError: If no ticker could be resolved.
            NoCoverageError: If the ticker has no SEC coverage.
            CorpusUnavailableError: If the corpus cannot be loaded.
        """
        as_of = _normalize_as_of(as_of)
        effective_top_k = top_k or self.top_k
        effective_ticker = resolve_ticker_from_query(query, ticker)

        if not effective_ticker:
            raise TickerRequiredError(
                "No ticker could be resolved from query or explicit parameter"
            )

        bm25_docs = bm25_search(
            query,
            top_k=effective_top_k * 2,
            ticker=effective_ticker,
            ticker_boost=self.ticker_boost,
            as_of=as_of,
        )

        try:
            vec_docs = vector_search(
                query,
                top_k=effective_top_k * 2,
                ticker=effective_ticker,
                as_of=as_of,
            )
        except CorpusUnavailableError:
            raise
        except Exception as e:
            logger.warning("Dense embedding failed ({}: {}), falling back to BM25-only",
                           type(e).__name__, e)
            vec_docs = []

        bm25_only = not vec_docs

        if not bm25_docs and not vec_docs:
            return []
        if not bm25_docs:
            return vec_docs[:effective_top_k]
        if not vec_docs:
            results = bm25_docs[:effective_top_k]
        else:
            fused = rrf_fuse(
                [vec_docs, bm25_docs],
                k=self.rrf_k,
                boost_ticker=effective_ticker,
                ticker_boost=self.ticker_boost,
            )
            logger.debug(
                "Hybrid RRF: {} vector + {} BM25 -> {} fused (top_k={}, ticker={}, boost={}x)",
                len(vec_docs), len(bm25_docs), len(fused),
                effective_top_k, effective_ticker, self.ticker_boost,
            )
            results = fused[:effective_top_k]

        if bm25_only:
            for doc in results:
                doc.metadata["retrieval_mode"] = "bm25_only"
                doc.metadata["_warning"] = "dense_unavailable"

        return results