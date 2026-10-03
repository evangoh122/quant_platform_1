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


# -- Custom exceptions --

class TickerRequiredError(Exception):
    """Raised when no ticker could be resolved for a query."""


class NoCoverageError(Exception):
    """Raised when a ticker has no SEC coverage (zero chunks)."""


# -- Config --

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
_TICKER_CORPUS_SOFT_BUDGET = 12 * 1024 * 1024


# -- TickerCorpus dataclass --

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


# -- Per-ticker LRU cache --

# OrderedDict for LRU: move_to_end on access, popitem(last=False) for LRU eviction
_ticker_cache: collections.OrderedDict[str, TickerCorpus] = collections.OrderedDict()
_ticker_cache_lock = threading.RLock()

# In-flight load futures for coalescing concurrent requests
_inflight: Dict[str, Future] = {}
_inflight_lock = threading.RLock()


# -- Global corpus state (backward compatibility for existing tests) --

_corpus_lock = threading.Lock()
_corpus_loaded = False

# chunk_id -> (text, ticker, accession, accepted_ts, form_type, section_id, chunk_index, source_url)
_corpus: Dict[str, Tuple[str, str, str, str, str, str, int, str]] = {}

# For BM25: parallel lists indexed by ordinal
_bm25_docs: Optional[List[Document]] = None
_bm25_tokenised: Optional[List[List[str]]] = None
_bm25_index: Optional[BM25Okapi] = None

# For dense: chunk_id -> embedding vector (numpy float32)
_embeddings_map: Dict[str, np.ndarray] = {}

# Stored index metadata (recorded at corpus load time)
_stored_index_dim: Optional[int] = None
_stored_embedding_model: Optional[str] = None


# -- Normalize as_of --

def _normalize_as_of(as_of: Optional[datetime] = None) -> datetime:
    """Normalise *as_of* to a tz-aware UTC datetime."""
    if as_of is None:
        return datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        return as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(timezone.utc)


# -- Tokenizer --

def tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenisation for BM25."""
    return text.lower().split()


# -- Accession URL --

def _accession_to_sec_url(accession: str) -> str:
    """Convert an accession number to the direct SEC EDGAR filing index URL."""
    if not accession:
        return ""
    clean = accession.replace("-", "")
    if len(clean) < 18:
        return ""
    cik = clean[:10].lstrip("0")
    dashed = f"{clean[:10]}-{clean[10:12]}-{clean[12:]}"
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{clean}/{dashed}-index.htm"


# -- Approximate corpus size --

def _approx_corpus_bytes(
    docs: List[Document],
    embeddings_map: Dict[str, np.ndarray],
) -> int:
    """Estimate memory footprint of a ticker corpus."""
    text_bytes = sum(len(d.page_content.encode("utf-8")) for d in docs)
    vec_bytes = sum(v.nbytes for v in embeddings_map.values())
    overhead = len(docs) * 200 + len(embeddings_map) * 100
    return text_bytes + vec_bytes + overhead


# -- Spark session --

def _get_spark():
    """Get a Spark session."""
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    else:
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()


# -- Per-ticker corpus loading --

def _get_embedding_model() -> str:
    """Get the configured embedding model name."""
    return os.getenv("ST_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


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
            f"The index is corrupted -- rebuild embeddings."
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


def get_ticker_corpus(ticker: str) -> TickerCorpus:
    """Get or load the corpus for a ticker, with LRU caching and coalesced loads.

    Thread-safe. Concurrent requests for the same ticker coalesce to one load.
    No all-corpus fallback — raises NoCoverageError if ticker has no data.

    Raises NoCoverageError if the ticker has no chunks.
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
                if not corpus.docs:
                    raise NoCoverageError(ticker)
                _insert_ticker_corpus(ticker, corpus)
                future.set_result(corpus)
            except NoCoverageError:
                future.set_exception(NoCoverageError(ticker))
                with _inflight_lock:
                    _inflight.pop(ticker, None)
                raise
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


# -- Coverage lookup --

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
        raise


# -- Global corpus loading (backward compatibility) --

def _load_corpus() -> bool:
    """Load chunk text + embeddings from Delta tables into process memory.

    Returns True if the corpus was loaded successfully.
    Raises CorpusUnavailableError on any load failure so callers can surface
    a structured error instead of silently returning empty results.
    """
    global _corpus_loaded, _bm25_docs, _bm25_tokenised, _bm25_index, _embeddings_map
    global _stored_index_dim, _stored_embedding_model

    if _corpus_loaded:
        if not _corpus:
            raise CorpusUnavailableError("Corpus cache is empty after previous load failure")
        return True

    with _corpus_lock:
        if _corpus_loaded:
            if not _corpus:
                raise CorpusUnavailableError("Corpus cache is empty after previous load failure")
            return True

        t0 = time.monotonic()
        try:
            spark = _get_spark()

            from pyspark.sql import functions as F

            chunks_df = spark.table(CHUNKS_TABLE).select(
                "chunk_id", "ticker", "chunk_text", "accession_number",
                F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch"),
                "form_type", "filing_section", "chunk_index",
                "source_url",
            )
            chunks_rows = chunks_df.collect()

            embed_df = spark.table(EMBEDDINGS_TABLE).select(
                "chunk_id", "embedding", "embedding_model",
            )
            embed_rows = embed_df.collect()

            seen_dims: set[int] = set()
            seen_models: set[str] = set()
            for row in embed_rows:
                cid = row["chunk_id"]
                vec = row["embedding"]
                if vec is not None:
                    arr = np.array(vec, dtype=np.float32)
                    _embeddings_map[cid] = arr
                    seen_dims.add(len(arr))
                model_name = row["embedding_model"]
                if model_name:
                    seen_models.add(model_name)

            if seen_dims and len(seen_dims) > 1:
                raise CorpusUnavailableError(
                    f"Embedding dimension mismatch in stored index: found {sorted(seen_dims)}. "
                    f"The index is corrupted -- rebuild embeddings."
                )
            _stored_index_dim = next(iter(seen_dims), None)

            if len(seen_models) > 1:
                raise CorpusUnavailableError(
                    f"Multiple embedding models in stored index: {sorted(seen_models)}. "
                    f"Rebuild embeddings with a single model."
                )
            _stored_embedding_model = next(iter(seen_models), None)

            docs: List[Document] = []
            tokenised: List[List[str]] = []

            for row in chunks_rows:
                cid = row["chunk_id"]
                text = row["chunk_text"] or ""
                ticker = row["ticker"] or ""
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

                _corpus[cid] = (text, ticker, accession, accepted_ts, form_type, section_id, chunk_index, source_url)

                doc = Document(
                    page_content=text,
                    metadata={
                        "chunk_id": cid,
                        "ticker": ticker,
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

            if tokenised:
                _bm25_index = BM25Okapi(tokenised)
            _bm25_docs = docs
            _bm25_tokenised = tokenised

            elapsed = time.monotonic() - t0
            logger.info(
                "Corpus loaded: {} chunks, {} embeddings, {:.1f}s",
                len(chunks_rows), len(_embeddings_map), elapsed,
            )
            _corpus_loaded = True
            return bool(_corpus)

        except CorpusUnavailableError:
            _corpus_loaded = False
            _corpus.clear()
            _embeddings_map.clear()
            _bm25_docs = None
            _bm25_tokenised = None
            _bm25_index = None
            _stored_index_dim = None
            _stored_embedding_model = None
            raise
        except Exception as e:
            logger.error("Failed to load corpus: {}", e)
            _corpus_loaded = False
            _corpus.clear()
            _embeddings_map.clear()
            _bm25_docs = None
            _bm25_tokenised = None
            _bm25_index = None
            _stored_index_dim = None
            _stored_embedding_model = None
            raise CorpusUnavailableError(f"Failed to load corpus: {e}") from e


def reload_corpus(ticker: Optional[str] = None) -> bool:
    """Invalidate one ticker or all tickers.

    When ticker is None, clears the global corpus and LRU cache.
    When ticker is set, only removes that ticker from the LRU cache.
    """
    global _corpus_loaded, _corpus, _bm25_docs, _bm25_tokenised, _bm25_index, _embeddings_map
    global _stored_index_dim, _stored_embedding_model

    if ticker:
        # Per-ticker invalidation
        with _ticker_cache_lock:
            _ticker_cache.pop(ticker.upper().strip(), None)
        return True

    # Full invalidation
    with _corpus_lock:
        _corpus_loaded = False
        _corpus = {}
        _bm25_docs = None
        _bm25_tokenised = None
        _bm25_index = None
        _embeddings_map = {}
        _stored_index_dim = None
        _stored_embedding_model = None

    with _ticker_cache_lock:
        _ticker_cache.clear()

    return _load_corpus()


# -- Point-in-time filter --

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
    Missing/null accepted_ts chunks are EXCLUDED (all newly published chunks
    require authoritative acceptance time).
    """
    as_of = _normalize_as_of(as_of)

    filtered = []
    for doc in docs:
        accepted_ts_str = doc.metadata.get("accepted_ts", "")
        accepted_dt = _parse_ts(accepted_ts_str)
        if accepted_dt is not None and accepted_dt <= as_of:
            filtered.append(doc)
        # Missing/null accepted_ts: EXCLUDED
    return filtered


# -- RRF Fusion --

def rrf_fuse(
    rankings: list[list[Document]],
    k: int = 60,
    boost_ticker: str = "",
    ticker_boost: float = 2.0,
) -> list[Document]:
    """Reciprocal Rank Fusion over multiple ranked lists.

    RRF_score(d) = Sum 1 / (k + rank_i(d))

    If boost_ticker is set, docs whose ticker matches get their contribution
    multiplied by ticker_boost at fusion time.

    Uses (ticker, accession, content_hash) as a stable content key so the same
    chunk appearing in both BM25 and vector results is correctly deduplicated.
    """
    if k < 1:
        raise ValueError(f"rrf k must be >= 1, got {k}")
    if ticker_boost < 1.0:
        raise ValueError(f"ticker_boost must be >= 1.0, got {ticker_boost}")

    scores: dict[tuple, float] = {}
    doc_map: dict[tuple, Document] = {}

    for ranked_list in rankings:
        for rank, doc in enumerate(ranked_list):
            key = (
                doc.metadata.get("ticker", ""),
                doc.metadata.get("accession", ""),
                hashlib.md5(doc.page_content.encode()).hexdigest()[:16],
            )
            doc_map[key] = doc
            base = 1.0 / (k + rank + 1)
            if boost_ticker and doc.metadata.get("ticker") == boost_ticker:
                base *= ticker_boost
            scores[key] = scores.get(key, 0.0) + base

    sorted_keys = sorted(scores, key=lambda k_: scores[k_], reverse=True)
    return [doc_map[k_] for k_ in sorted_keys]


# -- Company name -> ticker resolver --

_COMPANY_ALIASES: dict[str, str] = {
    "analog devices": "ADI",
    "advanced micro devices": "AMD",
    "taiwan semiconductor": "TSM",
    "nxp semiconductors": "NXPI",
    "microchip technology": "MCHP",
    "monolithic power": "MPWR",
    "on semiconductor": "ON",
    "applied materials": "AMAT",
    "lam research": "LRCX",
    "kla corporation": "KLAC",
    "onto innovation": "ONTO",
    "kulicke & soffa": "KLIC",
    "ichor holdings": "ICHR",
    "aehr test systems": "AEHR",
    "texas instruments": "TXN",
    "micron technology": "MU",
    "space exploration technologies": "SPCX",
    "space exploration": "SPCX",
    "space x": "SPCX",
    "rocket lab": "RKLB",
    "rocket labs": "RKLB",
    "rocketlab": "RKLB",
    "spacex": "SPCX",
    "broadcom": "AVGO",
    "intel": "INTC",
    "micron": "MU",
    "nvidia": "NVDA",
    "qualcomm": "QCOM",
    "tsmc": "TSM",
    "marvell": "MRVL",
    "microchip": "MCHP",
    "skyworks": "SWKS",
    "qorvo": "QRVO",
    "onsemi": "ON",
    "teradyne": "TER",
    "entegris": "ENTG",
    "formfactor": "FORM",
    "photronics": "PLAB",
    "kulicke": "KLIC",
    "ichor": "ICHR",
    "veeco": "VECO",
    "axcelis": "ACLS",
    "amkor": "AMKR",
    "cohu": "COHU",
    "aehr": "AEHR",
    "rklb": "RKLB",
    "mu": "MU",
}

_ALIAS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE), ticker)
    for alias, ticker in sorted(_COMPANY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
]


def resolve_ticker_from_query(query: str, ticker: str = "") -> str:
    """Return the ticker to use for retrieval.

    If ticker is already set, return it unchanged.  Otherwise scan the query
    for a known company name (whole-word match, longest alias wins).
    """
    if ticker:
        return ticker
    if not query:
        return ""
    for pattern, resolved in _ALIAS_PATTERNS:
        if pattern.search(query):
            logger.info("Auto-resolved ticker {!r} from query text", resolved)
            return resolved
    return ""


# -- BM25 search --

def bm25_search(
    query: str,
    top_k: int = 5,
    ticker: str = "",
    ticker_boost: float = 2.0,
    as_of: Optional[datetime] = None,
) -> list[Document]:
    """Run BM25 keyword search over the corpus.

    Requires a ticker. Raises TickerRequiredError if ticker is empty.
    No all-corpus fallback — per-ticker LRU only.

    Raises CorpusUnavailableError if the corpus cannot be loaded.
    Raises TickerRequiredError if ticker is empty.
    """
    as_of = _normalize_as_of(as_of)

    if not ticker:
        raise TickerRequiredError("BM25 search requires a ticker")

    try:
        corpus = get_ticker_corpus(ticker)
    except NoCoverageError:
        raise
    except Exception as e:
        raise CorpusUnavailableError(f"Failed to load corpus for {ticker}: {e}") from e

    if corpus.bm25_index is None or not corpus.docs:
        return []

    docs = _pit_filter(corpus.docs, as_of)
    if not docs:
        return []

    tokenised = [tokenize(d.page_content) for d in docs]
    bm25 = BM25Okapi(tokenised)
    query_tokens = tokenize(query)
    raw_scores = bm25.get_scores(query_tokens)
    scored = sorted(enumerate(raw_scores), key=lambda x: x[1], reverse=True)
    return [docs[idx] for idx, _ in scored[:top_k]]


# -- Dense vector search --

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Both must be normalised."""
    return float(np.dot(a, b))


def vector_search(
    query: str,
    top_k: int = 5,
    ticker: str = "",
    as_of: Optional[datetime] = None,
) -> list[Document]:
    """Run brute-force cosine similarity search over the embeddings corpus.

    Requires a ticker. Raises TickerRequiredError if ticker is empty.
    No all-corpus fallback — per-ticker LRU only.

    Raises CorpusUnavailableError if the corpus cannot be loaded.
    Raises TickerRequiredError if ticker is empty.
    """
    as_of = _normalize_as_of(as_of)

    if not ticker:
        raise TickerRequiredError("Vector search requires a ticker")

    try:
        corpus = get_ticker_corpus(ticker)
    except NoCoverageError:
        raise
    except Exception as e:
        raise CorpusUnavailableError(f"Failed to load corpus for {ticker}: {e}") from e

    if not corpus.embeddings_map:
        return []

    embeddings = get_embeddings()
    qvec = np.array(embeddings.embed_query(query), dtype=np.float32)

    if corpus.stored_dim is not None and len(qvec) != corpus.stored_dim:
        raise EmbeddingConfigError(
            f"query embedding dim {len(qvec)} != stored index dim {corpus.stored_dim}; "
            f"check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL / EMBEDDING_DIM",
            user_safe=True,
        )

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

    candidates: List[Tuple[float, Document]] = []
    for cid, vec in corpus.embeddings_map.items():
        doc = None
        for d in corpus.docs:
            if d.metadata.get("chunk_id") == cid:
                doc = d
                break
        if doc is None:
            continue

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


# -- Hybrid Retriever --

class HybridRetriever:
    """BM25 + Vector hybrid retriever with RRF fusion.

    Runs both retrieval methods, fuses via Reciprocal Rank Fusion, and returns
    the merged list.  Falls back gracefully to whichever method is available.

    Supports point-in-time filtering via ``as_of``.
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
            ticker: Optional ticker filter.
            as_of: Point-in-time cutoff (default: now).
            top_k: Override for number of results.

        Returns:
            Fused and optionally reranked list of Documents.
            If the dense embedder fails at runtime, falls back to BM25-only
            with _warning="dense_unavailable" metadata on each result.

        Raises:
            TickerRequiredError: If no ticker could be resolved.
            NoCoverageError: If the ticker has zero SEC chunks.
        """
        as_of = _normalize_as_of(as_of)
        effective_top_k = top_k or self.top_k
        effective_ticker = resolve_ticker_from_query(query, ticker)

        if not effective_ticker:
            raise TickerRequiredError("No ticker could be resolved from query or argument")

        check_ticker_coverage(effective_ticker)

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
            # Dimension/model mismatch -- configuration error, propagate
            raise
        except Exception as e:
            # Transient embedder failure (network, auth, runtime) -- degrade to BM25-only
            logger.warning("Dense embedding failed ({}: {}), falling back to BM25-only", type(e).__name__, e)
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