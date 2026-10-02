"""
hybrid_retriever.py — BM25 + Vector hybrid retrieval with RRF fusion.

Combines semantic (vector cosine similarity) and lexical (BM25) search on the
same corpus, then fuses rankings via Reciprocal Rank Fusion (RRF) before
handing off to the cross-encoder reranker.

Pipeline:  Chunk → [BM25 + Vector] → RRF → Rerank → LLM

Corpus source: Delta tables via databricks-connect (serverless).
  - Chunk text:  bootcamp_students.evangoh_capstone.silver_sec_sections
  - Embeddings:  bootcamp_students.evangoh_capstone.gold_sec_chunk_embeddings

The corpus (~10 720 chunks, ~16 MB at 384-d float32) is loaded once and
cached in-process.  BM25 index is built lazily on first query.

Point-in-time: every retrieval takes ``as_of`` (default now) and may only
return chunks with ``accepted_ts <= as_of``.  The filter is applied BEFORE
scoring, not after reranking.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
from langchain_core.documents import Document
from loguru import logger
from rank_bm25 import BM25Okapi

from api.services.embeddings import EMBEDDING_DIM, get_embeddings


def _normalize_as_of(as_of: Optional[datetime] = None) -> datetime:
    """Normalise *as_of* to a tz-aware UTC datetime.

    Rules:
      * ``None`` → ``datetime.now(timezone.utc)``
      * naive (no tzinfo) → treated as UTC and tagged accordingly
      * aware → converted to UTC via ``.astimezone(timezone.utc)``
    """
    if as_of is None:
        return datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        # Naive datetime — treat as UTC per contract (documented in module docstring)
        return as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(timezone.utc)


class CorpusUnavailableError(Exception):
    """Raised when the retrieval corpus cannot be loaded from Delta tables.

    Callers must surface this as a structured "retrieval unavailable" result
    so the agent can report the failure — never silently return an empty list.
    """

# ── Catalog / schema ─────────────────────────────────────────────────────────

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")

CHUNKS_TABLE = f"{CATALOG}.{SCHEMA}.silver_sec_sections"
EMBEDDINGS_TABLE = f"{CATALOG}.{SCHEMA}.gold_sec_chunk_embeddings"


# ── Tokenizer ────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenisation for BM25."""
    return text.lower().split()


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


# ── RRF Fusion ───────────────────────────────────────────────────────────────

def rrf_fuse(
    rankings: list[list[Document]],
    k: int = 60,
    boost_ticker: str = "",
    ticker_boost: float = 2.0,
) -> list[Document]:
    """Reciprocal Rank Fusion over multiple ranked lists.

    RRF_score(d) = Σ 1 / (k + rank_i(d))

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


# ── Company name → ticker resolver ───────────────────────────────────────────

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


# ── Corpus cache ─────────────────────────────────────────────────────────────

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


def _get_spark():
    """Get a Spark session, using DatabricksSession outside a Databricks runtime.

    Inside a Databricks runtime (DATABRICKS_RUNTIME_VERSION set), the ambient
    session is used.  Outside, DatabricksSession (databricks-connect) is required.
    """
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    else:
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()


def _load_corpus() -> bool:
    """Load chunk text + embeddings from Delta tables into process memory.

    Returns True if the corpus was loaded successfully.
    Raises CorpusUnavailableError on any load failure so callers can surface
    a structured error instead of silently returning empty results.
    """
    global _corpus_loaded, _bm25_docs, _bm25_tokenised, _bm25_index, _embeddings_map

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

            # Load chunk text
            chunks_df = spark.table(CHUNKS_TABLE).select(
                "chunk_id", "ticker", "chunk_text", "accession_number",
                "accepted_ts", "form_type", "filing_section", "chunk_index",
                "source_url",
            )
            chunks_rows = chunks_df.collect()

            # Load embeddings
            embed_df = spark.table(EMBEDDINGS_TABLE).select(
                "chunk_id", "embedding",
            )
            embed_rows = embed_df.collect()

            # Build embedding map
            for row in embed_rows:
                cid = row["chunk_id"]
                vec = row["embedding"]
                if vec is not None:
                    _embeddings_map[cid] = np.array(vec, dtype=np.float32)

            # Build corpus map + BM25 lists
            docs: List[Document] = []
            tokenised: List[List[str]] = []

            for row in chunks_rows:
                cid = row["chunk_id"]
                text = row["chunk_text"] or ""
                ticker = row["ticker"] or ""
                accession = row["accession_number"] or ""
                accepted_ts_raw = row["accepted_ts"]
                if accepted_ts_raw is not None:
                    # Ensure we always store UTC ISO format regardless of Spark session tz
                    if isinstance(accepted_ts_raw, datetime):
                        if accepted_ts_raw.tzinfo is None:
                            accepted_ts_raw = accepted_ts_raw.replace(tzinfo=timezone.utc)
                        accepted_ts = accepted_ts_raw.astimezone(timezone.utc).isoformat()
                    else:
                        accepted_ts = str(accepted_ts_raw)
                else:
                    accepted_ts = ""
                form_type = row["form_type"] or ""
                section_id = row["filing_section"] or ""
                chunk_index = row["chunk_index"] or 0
                source_url = row["source_url"] or _accession_to_sec_url(accession)

                _corpus[cid] = (text, ticker, accession, accepted_ts, form_type, section_id, chunk_index, source_url)

                # Only include chunks that have embeddings for dense search
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
            raise
        except Exception as e:
            logger.error("Failed to load corpus: {}", e)
            _corpus_loaded = True
            raise CorpusUnavailableError(f"Failed to load corpus: {e}") from e


def reload_corpus() -> bool:
    """Force a reload of the corpus (e.g. after new embeddings are built).

    Raises CorpusUnavailableError if the reload fails.
    """
    global _corpus_loaded, _corpus, _bm25_docs, _bm25_tokenised, _bm25_index, _embeddings_map
    with _corpus_lock:
        _corpus_loaded = False
        _corpus = {}
        _bm25_docs = None
        _bm25_tokenised = None
        _bm25_index = None
        _embeddings_map = {}
    return _load_corpus()


# ── Point-in-time filter ─────────────────────────────────────────────────────

def _parse_ts(ts_str: str) -> Optional[datetime]:
    """Parse a timestamp string to UTC datetime."""
    if not ts_str or ts_str == "None":
        return None
    try:
        # Handle both '2024-09-11' and '2024-09-11 00:00:00' and ISO formats
        ts_str = ts_str.replace("T", " ").replace("Z", "+00:00")
        if "+" not in ts_str and ts_str.endswith(":00"):
            pass  # already has offset
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
    """
    as_of = _normalize_as_of(as_of)

    filtered = []
    for doc in docs:
        accepted_ts_str = doc.metadata.get("accepted_ts", "")
        accepted_dt = _parse_ts(accepted_ts_str)
        if accepted_dt is not None and accepted_dt <= as_of:
            filtered.append(doc)
        elif accepted_dt is None:
            # If no timestamp, include it (defensive)
            filtered.append(doc)
    return filtered


# ── BM25 search ──────────────────────────────────────────────────────────────

def bm25_search(
    query: str,
    top_k: int = 5,
    ticker: str = "",
    ticker_boost: float = 2.0,
    as_of: Optional[datetime] = None,
) -> list[Document]:
    """Run BM25 keyword search over the corpus.

    When ticker is provided, raw BM25 scores for matching docs are multiplied
    by ticker_boost before ranking.

    Raises CorpusUnavailableError if the corpus cannot be loaded.
    """
    _load_corpus()
    as_of = _normalize_as_of(as_of)
    if _bm25_index is None or _bm25_docs is None:
        return []

    # Apply PIT filter to the doc list before scoring
    docs = _pit_filter(_bm25_docs, as_of)
    if not docs:
        return []

    # Rebuild a temporary BM25 index over the filtered docs for correctness
    # (PIT filter changes which documents are eligible)
    tokenised = [tokenize(d.page_content) for d in docs]
    bm25 = BM25Okapi(tokenised)

    query_tokens = tokenize(query)
    raw_scores = bm25.get_scores(query_tokens)

    if ticker:
        boosted = [
            (idx, s * ticker_boost if docs[idx].metadata.get("ticker") == ticker else s)
            for idx, s in enumerate(raw_scores)
        ]
    else:
        boosted = list(enumerate(raw_scores))

    scored = sorted(boosted, key=lambda x: x[1], reverse=True)
    return [docs[idx] for idx, _ in scored[:top_k]]


# ── Dense vector search ─────────────────────────────────────────────────────

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors.  Both must be normalised."""
    return float(np.dot(a, b))


def vector_search(
    query: str,
    top_k: int = 5,
    ticker: str = "",
    as_of: Optional[datetime] = None,
) -> list[Document]:
    """Run brute-force cosine similarity search over the embeddings corpus.

    Loads the query embedding via the configured provider, then scores against
    all cached embeddings.  Returns top_k documents sorted by similarity.

    Raises CorpusUnavailableError if the corpus cannot be loaded.
    """
    _load_corpus()
    as_of = _normalize_as_of(as_of)
    if not _embeddings_map:
        return []

    embeddings = get_embeddings()
    if embeddings is None:
        logger.warning("Embeddings not available — vector search skipped")
        return []

    qvec = np.array(embeddings.embed_query(query), dtype=np.float32)

    # Build candidate docs from corpus entries that have embeddings
    candidates: List[Tuple[float, Document]] = []
    for cid, vec in _embeddings_map.items():
        entry = _corpus.get(cid)
        if entry is None:
            continue
        text, ticker_val, accession, accepted_ts, form_type, section_id, chunk_index, source_url = entry

        # Apply PIT filter per-document
        accepted_dt = _parse_ts(accepted_ts)
        if accepted_dt is not None and accepted_dt > as_of:
            continue

        # Apply ticker filter
        if ticker and ticker_val != ticker:
            continue

        sim = _cosine_similarity(qvec, vec)
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
                "distance": 1.0 - sim,
                "similarity": sim,
            },
        )
        candidates.append((sim, doc))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in candidates[:top_k]]


# ── Hybrid Retriever ─────────────────────────────────────────────────────────

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
        """
        as_of = _normalize_as_of(as_of)
        effective_top_k = top_k or self.top_k
        effective_ticker = resolve_ticker_from_query(query, ticker)

        bm25_docs = bm25_search(
            query,
            top_k=effective_top_k * 2,
            ticker=effective_ticker,
            ticker_boost=self.ticker_boost,
            as_of=as_of,
        )
        vec_docs = vector_search(
            query,
            top_k=effective_top_k * 2,
            ticker=effective_ticker,
            as_of=as_of,
        )

        if not bm25_docs and not vec_docs:
            return []
        if not bm25_docs:
            return vec_docs[:effective_top_k]
        if not vec_docs:
            return bm25_docs[:effective_top_k]

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
        return fused[:effective_top_k]