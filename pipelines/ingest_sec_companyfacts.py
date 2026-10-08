"""pipelines/ingest_sec_companyfacts.py — SEC Company Facts XBRL ingestion.

Fetches the SEC Company Facts JSON endpoint per CIK, flattens each payload
into one row per unit entry, and appends to the bronze_sec_xbrl_facts
Delta table.  Also writes a per-CIK manifest row to
sec_companyfacts_ingest_log.

Reuses RateLimiter, SecClient, CIK mapping, and User-Agent resolution from
sec_rag_ingest.py — no duplication.

Usage:
    python pipelines/ingest_sec_companyfacts.py --catalog bootcamp_students --schema evangoh_capstone
    python pipelines/ingest_sec_companyfacts.py --catalog C --schema S --tickers AAPL,MSFT --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure repo root is on sys.path so ``pipelines.*`` resolves when invoked
# via ``python_file`` in a Databricks job.
_p = globals().get("__file__") or sys.argv[0]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(_p))))

from pipelines._runtime import get_spark
from pipelines.sec_rag_ingest import (
    DEFAULT_REQUESTS_PER_SECOND,
    DEFAULT_SECRET_KEY,
    DEFAULT_SECRET_SCOPE,
    EDGAR_DATA_BASE,
    HttpClient,
    HttpResponse,
    RateLimiter,
    SecClient,
    SecClientConfig,
    SecClientError,
    SparkUniverseReader,
    TickerEntry,
    UniverseReader,
    _resolve_user_agent,
    _validate_user_agent,
    build_cik_map,
    get_global_limiter,
    load_cik_overrides,
    load_company_tickers,
    resolve_canonical_tickers,
    _SystemClock,
)

# Plain-Python column specs — no PySpark import required.
# The StructType is built on demand via _get_bronze_schema() / _get_manifest_schema().
from collections import namedtuple

_ColumnSpec = namedtuple("_ColumnSpec", ["name", "type_str", "nullable"])

BRONZE_COLUMNS = [
    _ColumnSpec("ingest_run_id", "string", False),
    _ColumnSpec("ingested_at", "timestamp", False),
    _ColumnSpec("source_url", "string", True),
    _ColumnSpec("payload_hash", "string", True),
    _ColumnSpec("cik", "string", True),
    _ColumnSpec("entity_name", "string", True),
    _ColumnSpec("ticker", "string", True),
    _ColumnSpec("taxonomy", "string", True),
    _ColumnSpec("concept", "string", True),
    _ColumnSpec("label", "string", True),
    _ColumnSpec("description", "string", True),
    _ColumnSpec("unit", "string", True),
    _ColumnSpec("value_raw", "string", True),
    _ColumnSpec("value_decimal", "double", True),
    _ColumnSpec("period_start", "string", True),
    _ColumnSpec("period_end", "string", True),
    _ColumnSpec("instant", "string", True),
    _ColumnSpec("fiscal_year", "int", True),
    _ColumnSpec("fiscal_period", "string", True),
    _ColumnSpec("form_type", "string", True),
    _ColumnSpec("accession_number", "string", True),
    _ColumnSpec("filed_date", "string", True),
    _ColumnSpec("frame", "string", True),
    _ColumnSpec("raw_fact_json", "string", True),
    _ColumnSpec("source_updated_at", "string", True),
]

MANIFEST_COLUMNS = [
    _ColumnSpec("ingest_run_id", "string", False),
    _ColumnSpec("cik", "string", False),
    _ColumnSpec("ticker", "string", False),
    _ColumnSpec("fetch_status", "string", False),
    _ColumnSpec("attempt_count", "int", True),
    _ColumnSpec("payload_hash", "string", True),
    _ColumnSpec("payload_bytes", "int", True),
    _ColumnSpec("fact_count", "int", True),
    _ColumnSpec("http_status", "int", True),
    _ColumnSpec("started_at", "timestamp", True),
    _ColumnSpec("completed_at", "timestamp", True),
    _ColumnSpec("error_category", "string", True),
    _ColumnSpec("error_message", "string", True),
    _ColumnSpec("logged_at", "timestamp", False),
]

# Spark type string to StructType builder (populated lazily)
_SPARK_TYPE_MAP = None


def _get_spark_type_map():
    """Build the Spark type map on first call (requires PySpark)."""
    global _SPARK_TYPE_MAP
    if _SPARK_TYPE_MAP is not None:
        return _SPARK_TYPE_MAP
    from pyspark.sql.types import (
        BooleanType,
        DoubleType,
        FloatType,
        IntegerType,
        LongType,
        StringType,
        TimestampType,
    )
    _SPARK_TYPE_MAP = {
        "string": StringType(),
        "int": IntegerType(),
        "bigint": LongType(),
        "double": DoubleType(),
        "float": FloatType(),
        "boolean": BooleanType(),
        "timestamp": TimestampType(),
    }
    return _SPARK_TYPE_MAP


_BRONZE_SCHEMA = None
_MANIFEST_SCHEMA = None


def _build_struct_type(columns):
    """Build a PySpark StructType from a list of _ColumnSpec."""
    from pyspark.sql.types import StructField, StructType
    type_map = _get_spark_type_map()
    return StructType([
        StructField(c.name, type_map[c.type_str], c.nullable)
        for c in columns
    ])


def _get_bronze_schema():
    """Return the bronze StructType, building it once (lazy)."""
    global _BRONZE_SCHEMA
    if _BRONZE_SCHEMA is not None:
        return _BRONZE_SCHEMA
    _BRONZE_SCHEMA = _build_struct_type(BRONZE_COLUMNS)
    return _BRONZE_SCHEMA


def _get_manifest_schema():
    """Return the manifest StructType, building it once (lazy)."""
    global _MANIFEST_SCHEMA
    if _MANIFEST_SCHEMA is not None:
        return _MANIFEST_SCHEMA
    _MANIFEST_SCHEMA = _build_struct_type(MANIFEST_COLUMNS)
    return _MANIFEST_SCHEMA


_DDL_TYPE_MAP = {
    "string": "STRING",
    "int": "INT",
    "bigint": "BIGINT",
    "double": "DOUBLE",
    "float": "FLOAT",
    "boolean": "BOOLEAN",
    "timestamp": "TIMESTAMP",
    "date": "DATE",
    "binary": "BINARY",
    "decimal": "DECIMAL",
    "smallint": "SMALLINT",
    "tinyint": "TINYINT",
}


def _columns_to_ddl(columns) -> str:
    """Generate a DDL column list from _ColumnSpec tuples (no PySpark needed)."""
    parts = []
    for c in columns:
        ddl_type = _DDL_TYPE_MAP.get(c.type_str, c.type_str.upper())
        nullable = "" if c.nullable else " NOT NULL"
        parts.append(f"    {c.name} {ddl_type}{nullable}")
    return ",\n".join(parts)


def _schema_to_ddl_columns(schema) -> str:
    """Generate a DDL column list from a StructType.

    Uses field.dataType.simpleString() for the Spark SQL type name and
    appends NOT NULL where field.nullable is False.  This makes the
    StructType the single source of truth for both CREATE TABLE DDL and
    createDataFrame schemas — they can never drift apart.
    """
    parts = []
    for field in schema.fields:
        spark_type = field.dataType.simpleString()
        ddl_type = _DDL_TYPE_MAP.get(spark_type, spark_type.upper())
        nullable = "" if field.nullable else " NOT NULL"
        parts.append(f"    {field.name} {ddl_type}{nullable}")
    return ",\n".join(parts)


logger = logging.getLogger(__name__)

COMPANY_FACTS_URL = (
    f"{EDGAR_DATA_BASE}/api/xbrl/companyfacts/CIK{{cik}}.json"
)

# ── Pure flattening functions (Spark-free, testable offline) ────────────────


def flatten_company_facts(
    payload: Dict[str, Any],
    cik: str,
    ticker: str,
    run_id: str,
    ingested_at: datetime,
    source_url: str,
    payload_hash: str,
) -> List[Dict[str, Any]]:
    """Flatten a Company Facts JSON payload into one row per unit entry.

    Each row corresponds to one (taxonomy, concept, unit, period, form,
    accession) observation from the SEC Company Facts payload.

    Returns rows ready for Delta append.  Rows where value parsing fails
    have value_decimal=None but preserve raw JSON (malformed fact
    quarantine).
    """
    entity_name = payload.get("entityName", "")
    cik_from_payload = str(payload.get("cik", cik)).zfill(10)
    source_updated_at = payload.get("updated", "")

    facts = payload.get("facts", {})
    rows: List[Dict[str, Any]] = []

    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, dict):
            continue
        for concept, concept_data in concepts.items():
            if not isinstance(concept_data, dict):
                continue
            label = concept_data.get("label", "")
            description = concept_data.get("description", "")
            units = concept_data.get("units", {})

            if not isinstance(units, dict):
                continue

            for unit, entries in units.items():
                if not isinstance(entries, list):
                    continue

                for entry in entries:
                    row = _flatten_one_entry(
                        entry=entry,
                        cik=cik_from_payload,
                        entity_name=entity_name,
                        ticker=ticker,
                        taxonomy=taxonomy,
                        concept=concept,
                        label=label,
                        description=description,
                        unit=unit,
                        run_id=run_id,
                        ingested_at=ingested_at,
                        source_url=source_url,
                        payload_hash=payload_hash,
                        source_updated_at=source_updated_at,
                    )
                    rows.append(row)

    return rows


def _flatten_one_entry(
    entry: Dict[str, Any],
    cik: str,
    entity_name: str,
    ticker: str,
    taxonomy: str,
    concept: str,
    label: str,
    description: str,
    unit: str,
    run_id: str,
    ingested_at: datetime,
    source_url: str,
    payload_hash: str,
    source_updated_at: str,
) -> Dict[str, Any]:
    """Flatten a single Company Facts unit entry into a row dict."""
    value_raw = entry.get("val")
    value_decimal = _try_decimal(value_raw)

    period_start = entry.get("start")
    period_end = entry.get("end")
    instant = entry.get("instant")
    fiscal_year = entry.get("fy")
    fiscal_period = entry.get("fp")
    form_type = entry.get("form")
    accession_number = entry.get("accn", "")
    filed_date = entry.get("filed")
    frame = entry.get("frame")

    raw_fact_json = json.dumps(entry, separators=(",", ":"), sort_keys=True)

    return {
        "ingest_run_id": run_id,
        "ingested_at": ingested_at,
        "source_url": source_url,
        "payload_hash": payload_hash,
        "cik": cik,
        "entity_name": entity_name,
        "ticker": ticker,
        "taxonomy": taxonomy,
        "concept": concept,
        "label": label,
        "description": description,
        "unit": unit,
        "value_raw": str(value_raw) if value_raw is not None else None,
        "value_decimal": value_decimal,
        "period_start": period_start,
        "period_end": period_end,
        "instant": instant,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "form_type": form_type,
        "accession_number": accession_number,
        "filed_date": filed_date,
        "frame": frame,
        "raw_fact_json": raw_fact_json,
        "source_updated_at": source_updated_at,
    }


def _try_decimal(value: Any) -> Optional[float]:
    """Try to convert a raw value to float; return None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _coerce_bronze_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a flattened row dict to match the bronze StructType.

    Ensures:
    - fiscal_year is int or None (not str)
    - period_start/instant/frame are str or None (not missing keys)
    - value_decimal is float or None
    """
    return {
        "ingest_run_id": row.get("ingest_run_id"),
        "ingested_at": row.get("ingested_at"),
        "source_url": row.get("source_url"),
        "payload_hash": row.get("payload_hash"),
        "cik": row.get("cik"),
        "entity_name": row.get("entity_name"),
        "ticker": row.get("ticker"),
        "taxonomy": row.get("taxonomy"),
        "concept": row.get("concept"),
        "label": row.get("label"),
        "description": row.get("description"),
        "unit": row.get("unit"),
        "value_raw": row.get("value_raw"),
        "value_decimal": row.get("value_decimal"),
        "period_start": row.get("period_start"),
        "period_end": row.get("period_end"),
        "instant": row.get("instant"),
        "fiscal_year": int(row["fiscal_year"]) if row.get("fiscal_year") is not None else None,
        "fiscal_period": row.get("fiscal_period"),
        "form_type": row.get("form_type"),
        "accession_number": row.get("accession_number", ""),
        "filed_date": row.get("filed_date"),
        "frame": row.get("frame"),
        "raw_fact_json": row.get("raw_fact_json"),
        "source_updated_at": row.get("source_updated_at"),
    }


def compute_payload_hash(payload_bytes: bytes) -> str:
    """SHA-256 hash of the raw payload bytes."""
    return hashlib.sha256(payload_bytes).hexdigest()


def build_source_url(cik: str) -> str:
    """Build the Company Facts URL for a CIK."""
    return COMPANY_FACTS_URL.format(cik=cik.zfill(10))


# ── Manifest entry ─────────────────────────────────────────────────────────


@dataclass
class CompanyFactsManifestEntry:
    ingest_run_id: str
    cik: str
    ticker: str
    fetch_status: str = ""  # success | failed | skipped_duplicate
    attempt_count: int = 1
    payload_hash: str = ""
    payload_bytes: int = 0
    fact_count: int = 0
    http_status: Optional[int] = None  # last HTTP response status per CIK
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_category: str = ""
    error_message: str = ""


# ── Fetch logic ─────────────────────────────────────────────────────────────


def fetch_company_facts(
    client: SecClient,
    cik: str,
    _attempts: Optional[List[int]] = None,
) -> Tuple[Dict[str, Any], bytes, str, int, int]:
    """Fetch Company Facts JSON for a CIK.

    Returns (parsed_payload, raw_bytes, payload_hash, http_status, attempt_count).
    Raises SecClientError on failure.
    """
    url = build_source_url(cik)
    local = _attempts if _attempts is not None else [0]
    raw_bytes, http_status, _ = _fetch_raw_bytes(client, url, _attempts=local)
    payload_hash = compute_payload_hash(raw_bytes)
    payload = json.loads(raw_bytes)
    return payload, raw_bytes, payload_hash, http_status, local[0]


def _fetch_raw_bytes(client: SecClient, url: str, _attempts: Optional[List[int]] = None) -> Tuple[bytes, int, int]:
    """Fetch raw bytes from SEC.  Uses the client's get_json internally but
    we need raw bytes for hash — fetch via the internal _request method."""
    # We'll use the underlying HTTP client directly with the same headers
    # to get raw bytes, respecting rate limiting via the existing limiter.
    local = _attempts if _attempts is not None else [0]
    resp = client._request(url, expect_json=False, _attempts=local)
    return resp.text.encode("utf-8"), resp.status_code, local[0]


# ── Spark entry point ──────────────────────────────────────────────────────


def run_ingest_companyfacts(
    *,
    catalog: str,
    schema: str,
    tickers: Optional[List[str]] = None,
    run_id: Optional[str] = None,
    dry_run: bool = False,
    user_agent_secret_scope: str = DEFAULT_SECRET_SCOPE,
    user_agent_secret_key: str = DEFAULT_SECRET_KEY,
    cik_overrides_path: Optional[str] = None,
    # Injected dependencies
    universe_reader: Optional[UniverseReader] = None,
    http_client: Optional[HttpClient] = None,
    clock: Optional[Any] = None,
    cik_overrides: Optional[Dict[str, List[str]]] = None,
    # Spark / Delta writer (injected for prod, None for tests)
    delta_writer: Optional[Any] = None,
    manifest_writer: Optional[Any] = None,
    # Cache for company_tickers.json
    cache_path: Optional[str] = None,
    # Track already-written (cik, payload_hash) within this run
    _seen_payloads: Optional[Set[Tuple[str, str]]] = None,
    # Concurrency
    max_workers: int = 4,
    _key_wait_timeout: float = 30.0,
    # Test seam: called when a worker enters key_cond.wait for "in_flight"
    # Signature: _on_key_wait(key, ticker) — ticker identifies the waiting worker.
    _on_key_wait: Optional[Any] = None,
    # Test seam: called before a worker attempts to reserve a key.
    # Signature: _on_pre_reserve(ticker) — blocks until the worker may proceed.
    # Optional, private, inert when absent.
    _on_pre_reserve: Optional[Any] = None,
    # Test seam: called after the inner exception handler sets "failed" and
    # releases the lock, before the outer handler acquires it.
    # Signature: _on_post_inner(ticker) — blocks until it may proceed.
    # Optional, private, inert when absent.
    _on_post_inner: Optional[Any] = None,
    # Test seam: called inside the outer handler's ``with key_cond`` block
    # after the lock is acquired, before the generation-guard check.
    # Signature: _on_outer_lock_held(key, ticker, key_cond) — may call
    # key_cond.wait() to release/reacquire the lock while blocking.
    # Optional, private, inert when absent.
    _on_outer_lock_held: Optional[Any] = None,
    # Test seam: called inside the outer handler's ``with key_cond`` block
    # when the generation guard PASSES and the handler is about to set
    # key_state[key] = "failed".  Fires BEFORE the state change.
    # Signature: _on_outer_clobber(key, ticker).
    # Optional, private, inert when absent.
    _on_outer_clobber: Optional[Any] = None,
    # Test seam: bypass CIK deduplication and submit the given pairs directly.
    # Each entry is (ticker, cik).  When provided, the canonical/alias
    # deduplication is skipped entirely — used by concurrency tests that
    # need multiple workers for the same CIK.
    # Optional, private, inert when absent.
    _ticker_cik_pairs_for_test: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    """Run the SEC Company Facts ingestion pipeline.

    All external dependencies are injected for offline testability.
    Returns a summary dict with counts and errors.
    """
    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")

    result: Dict[str, Any] = {
        "run_id": run_id,
        "dry_run": dry_run,
        "tickers_requested": len(tickers) if tickers else 0,
        "mapped_count": 0,
        "missing_count": 0,
        "fetched_count": 0,
        "failed_count": 0,
        "total_facts": 0,
        "skipped_duplicate_payloads": 0,
        "errors": [],
    }

    seen_payloads: Set[Tuple[str, str]] = (
        set() if _seen_payloads is None else _seen_payloads
    )

    # Resolve and validate user agent
    user_agent = _resolve_user_agent(
        secret_scope=user_agent_secret_scope,
        secret_key=user_agent_secret_key,
    )
    _validate_user_agent(user_agent)

    # Build dependencies
    _clock = clock or _SystemClock()
    limiter = get_global_limiter(
        max_rps=int(
            os.environ.get("SEC_REQUESTS_PER_SECOND", DEFAULT_REQUESTS_PER_SECOND)
        ),
        clock=_clock,
    )

    if http_client is None:
        from pipelines._http_adapter import RequestsAdapter
        http_client = RequestsAdapter()

    sec_config = SecClientConfig(user_agent=user_agent)
    client = SecClient(sec_config, http_client, limiter, _clock)

    # Build CIK mapping
    if tickers:
        ticker_symbols = [t.strip().upper() for t in tickers]
    elif universe_reader is not None:
        entries = universe_reader.read_universe(catalog, schema, include_historical=False)
        ticker_symbols = [e.ticker for e in entries]
    else:
        raise ValueError("Either tickers or universe_reader must be provided")

    is_fallback = False
    if cache_path is None:
        cache_path = os.environ.get(
            "SEC_COMPANY_TICKERS_CACHE",
            f"/Volumes/{catalog}/{schema}/sec_cache/company_tickers.json",
        )
        # Fall back to a temp dir if the default path is not writable
        # (e.g. running outside Databricks where /Volumes does not exist)
        if not os.access(os.path.dirname(cache_path) or ".", os.W_OK):
            import tempfile
            fallback = os.path.join(tempfile.gettempdir(), "sec_cache", "company_tickers.json")
            logger.warning(
                "Cache path %s not writable, falling back to %s",
                cache_path, fallback,
            )
            cache_path = fallback
            is_fallback = True

    tickers_payload = load_company_tickers(
        client, cache_path=cache_path, dry_run=dry_run, is_fallback=is_fallback,
    )

    if cik_overrides is None:
        cik_overrides = load_cik_overrides(cik_overrides_path)

    cik_map = build_cik_map(ticker_symbols, tickers_payload, cik_overrides=cik_overrides)

    # Build ticker -> list of (ticker, cik) pairs
    ticker_cik_pairs: List[Tuple[str, str]] = []
    for symbol, mapping in cik_map.items():
        if mapping.status == "mapped" and mapping.cik:
            ciks_to_use = mapping.ciks if mapping.ciks else [mapping.cik]
            for cik in ciks_to_use:
                ticker_cik_pairs.append((symbol, cik))
            result["mapped_count"] += 1
        elif mapping.status == "ambiguous":
            result["missing_count"] += 1
            logger.warning("CIK mapping: ambiguous — %s: %s", symbol, mapping.reason)
        else:
            result["missing_count"] += 1
            logger.warning("CIK mapping: %s — %s: %s", mapping.status, symbol, mapping.reason)

    # Deduplicate by CIK: group aliases per CIK, pick a deterministic
    # canonical ticker (alphabetically first), and submit only one worker
    # per distinct CIK.  This prevents redundant SEC fetches when multiple
    # ticker aliases share the same CIK.
    # Test seam: _ticker_cik_pairs_for_test bypasses deduplication entirely
    # for concurrency tests that need multiple workers per CIK.
    canonical_pairs: List[Tuple[str, str]] = []  # (canonical_ticker, cik)
    cik_aliases: Dict[str, List[str]] = {}  # cik -> [alias_tickers]
    if _ticker_cik_pairs_for_test is not None:
        canonical_pairs = list(_ticker_cik_pairs_for_test)
    else:
        cik_to_tickers: Dict[str, List[str]] = {}
        for symbol, cik in ticker_cik_pairs:
            cik_to_tickers.setdefault(cik, []).append(symbol)

        for cik, tickers in cik_to_tickers.items():
            canonical = sorted(tickers)[0]
            canonical_pairs.append((canonical, cik))
            cik_aliases[cik] = [t for t in tickers if t != canonical]

    if dry_run:
        total_aliases = sum(len(v) for v in cik_aliases.values())
        logger.info(
            "DRY RUN: mapped=%d, missing=%d, unique CIKs=%d, total aliases=%d",
            result["mapped_count"], result["missing_count"],
            len(canonical_pairs), total_aliases,
        )
        return result

    # Ingest each unique CIK with bounded concurrency
    ingested_at = datetime.now(timezone.utc)
    lock = threading.Lock()
    key_cond = threading.Condition(lock)
    # Per-key state: "in_flight" | "completed" | "failed"
    key_state: Dict[Tuple[str, str], str] = {}
    # Per-key ownership generation: incremented each time a worker acquires
    # ownership.  A stale outer handler compares its recorded generation
    # against the current one to avoid clobbering a successor.
    key_generation: Dict[Tuple[str, str], int] = {}
    worker_count = min(max_workers, len(canonical_pairs)) if canonical_pairs else 1

    def _fetch_one(ticker: str, cik: str, aliases: Optional[List[str]] = None) -> None:
        started_at = datetime.now(timezone.utc)
        source_url = build_source_url(cik)
        manifest = CompanyFactsManifestEntry(
            ingest_run_id=run_id,
            cik=cik,
            ticker=ticker,
            started_at=started_at,
        )

        call_attempts = [0]
        payload_hash = None

        try:
            payload, raw_bytes, payload_hash, http_status, attempt_count = fetch_company_facts(client, cik, _attempts=call_attempts)
            manifest.payload_hash = payload_hash
            manifest.payload_bytes = len(raw_bytes)
            manifest.http_status = http_status

            key = (cik, payload_hash)

            # Acquire ownership or wait for in-flight owner.
            if _on_pre_reserve is not None:
                _on_pre_reserve(ticker)
            with key_cond:
                _my_gen = None  # ownership generation we hold (None = none)
                while True:
                    state = key_state.get(key)
                    if state == "completed":
                        # Already written by another worker.
                        manifest.fetch_status = "skipped_duplicate"
                        manifest.attempt_count = attempt_count
                        manifest.completed_at = datetime.now(timezone.utc)
                        result["skipped_duplicate_payloads"] += 1
                        if manifest_writer is not None:
                            manifest_writer(catalog, schema, manifest)
                        return
                    elif state == "in_flight":
                        # Another worker is appending; wait for outcome.
                        if _on_key_wait is not None:
                            _on_key_wait(key, ticker)
                        notified = key_cond.wait(timeout=_key_wait_timeout)
                        if not notified and key_state.get(key) == "in_flight":
                            raise RuntimeError(
                                f"Key {key} wait timed out after "
                                f"{_key_wait_timeout}s without state change"
                            )
                        # Loop re-checks state after wake.
                    elif state == "failed":
                        # Previous owner failed; acquire ownership for retry.
                        key_generation[key] = key_generation.get(key, 0) + 1
                        _my_gen = key_generation[key]
                        key_state[key] = "in_flight"
                        break
                    else:
                        # Key not seen; acquire ownership.
                        key_generation[key] = key_generation.get(key, 0) + 1
                        _my_gen = key_generation[key]
                        key_state[key] = "in_flight"
                        break

            try:
                # Flatten
                rows = flatten_company_facts(
                    payload=payload,
                    cik=cik,
                    ticker=ticker,
                    run_id=run_id,
                    ingested_at=ingested_at,
                    source_url=source_url,
                    payload_hash=payload_hash,
                )

                manifest.fact_count = len(rows)
                manifest.fetch_status = "success"
                manifest.attempt_count = attempt_count
                manifest.completed_at = datetime.now(timezone.utc)

                # Write rows to Delta
                if delta_writer is not None and rows:
                    delta_writer(catalog, schema, rows)

                with key_cond:
                    result["fetched_count"] += 1
                    result["total_facts"] += len(rows)
                    key_state[key] = "completed"
                    key_cond.notify_all()
            except Exception:
                with key_cond:
                    key_state[key] = "failed"
                    key_cond.notify_all()
                if _on_post_inner is not None:
                    _on_post_inner(ticker)
                raise

            if manifest_writer is not None:
                manifest_writer(catalog, schema, manifest)

            # Write alias manifest entries — truthful provenance for aliases
            # that share this CIK.  Only written after successful fetch so
            # aliases are never reported as skipped_duplicate when nothing
            # was ingested.
            if aliases and manifest_writer is not None:
                for alias in aliases:
                    alias_entry = CompanyFactsManifestEntry(
                        ingest_run_id=run_id,
                        cik=cik,
                        ticker=alias,
                        fetch_status="skipped_duplicate",
                        attempt_count=attempt_count,
                        payload_hash=payload_hash,
                        payload_bytes=len(raw_bytes),
                        fact_count=0,
                        http_status=http_status,
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc),
                    )
                    manifest_writer(catalog, schema, alias_entry)
                    result["skipped_duplicate_payloads"] += 1

            logger.info(
                "Fetched %s (CIK %s): %d facts, hash=%s, attempts=%d",
                ticker, cik, len(rows), payload_hash[:12], attempt_count,
            )

        except SecClientError as e:
            error_text = str(e)[:500]
            with key_cond:
                if _on_outer_lock_held is not None:
                    _on_outer_lock_held(key, ticker, key_cond)
                result["failed_count"] += 1
                if payload_hash is not None:
                    key = (cik, payload_hash)
                    # Only fail the key if we still own it; a successor may
                    # have already acquired ownership after our inner handler
                    # transitioned to "failed" and notified.
                    if (key_state.get(key) == "in_flight"
                            and _my_gen is not None
                            and key_generation.get(key) == _my_gen):
                        if _on_outer_clobber is not None:
                            _on_outer_clobber(key, ticker)
                        key_state[key] = "failed"
                        key_cond.notify_all()
            manifest.fetch_status = "failed"
            manifest.attempt_count = call_attempts[0]
            manifest.http_status = e.status_code
            manifest.completed_at = datetime.now(timezone.utc)
            manifest.error_category = _classify_error(e)
            manifest.error_message = error_text
            with key_cond:
                result["errors"].append({
                    "ticker": ticker,
                    "cik": cik,
                    "error": str(e)[:200],
                })
            logger.error("Failed to fetch %s (CIK %s): %s", ticker, cik, e)
            if manifest_writer is not None:
                manifest_writer(catalog, schema, manifest)

        except Exception as e:
            error_text = str(e)[:500]
            with key_cond:
                if _on_outer_lock_held is not None:
                    _on_outer_lock_held(key, ticker, key_cond)
                result["failed_count"] += 1
                if payload_hash is not None:
                    key = (cik, payload_hash)
                    # Only fail the key if we still own it; a successor may
                    # have already acquired ownership after our inner handler
                    # transitioned to "failed" and notified.
                    if (key_state.get(key) == "in_flight"
                            and _my_gen is not None
                            and key_generation.get(key) == _my_gen):
                        if _on_outer_clobber is not None:
                            _on_outer_clobber(key, ticker)
                        key_state[key] = "failed"
                        key_cond.notify_all()
            manifest.fetch_status = "failed"
            manifest.attempt_count = call_attempts[0]
            manifest.completed_at = datetime.now(timezone.utc)
            manifest.error_category = "unexpected"
            manifest.error_message = error_text
            with key_cond:
                result["errors"].append({
                    "ticker": ticker,
                    "cik": cik,
                    "error": str(e)[:200],
                })
            logger.error("Unexpected error for %s (CIK %s): %s", ticker, cik, e)
            if manifest_writer is not None:
                manifest_writer(catalog, schema, manifest)

    if canonical_pairs:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(_fetch_one, t, c, cik_aliases.get(c, [])): (t, c)
                for t, c in canonical_pairs
            }
            for future in as_completed(futures):
                future.result()  # propagate unhandled exceptions

    logger.info(
        "Company Facts ingestion complete: mapped=%d, fetched=%d, failed=%d, "
        "facts=%d, skipped_dup=%d",
        result["mapped_count"],
        result["fetched_count"],
        result["failed_count"],
        result["total_facts"],
        result["skipped_duplicate_payloads"],
    )

    return result


def _classify_error(exc: SecClientError) -> str:
    """Classify a SecClientError into an error category for the manifest."""
    if exc.status_code == 429:
        return "rate_limited"
    if exc.status_code == 403:
        return "forbidden"
    if exc.status_code is not None and exc.status_code >= 500:
        return "server_error"
    if exc.status_code is not None:
        return f"http_{exc.status_code}"
    return "client_error"


# ── Spark Delta writer (production) ────────────────────────────────────────


class SparkCompanyFactsWriter:
    """Appends flattened Company Facts rows to bronze_sec_xbrl_facts via Spark.

    Creates the table if it does not exist.  Append-only, never overwrites.
    """

    def __init__(self, spark_factory=None):
        self._spark_factory = spark_factory

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        return get_spark()

    def ensure_table(self, catalog: str, schema: str) -> None:
        """Create bronze_sec_xbrl_facts if absent."""
        spark = self._get_spark()
        bronze_schema = _get_bronze_schema()
        cols = _schema_to_ddl_columns(bronze_schema)
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {catalog}.{schema}.bronze_sec_xbrl_facts (
                {cols}
            ) USING DELTA
        """)

    def append_rows(
        self,
        catalog: str,
        schema: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        """Append rows to bronze_sec_xbrl_facts.  Returns count written."""
        if not rows:
            return 0
        spark = self._get_spark()
        bronze_schema = _get_bronze_schema()
        # Coerce values to match the StructType exactly
        coerced = []
        for row in rows:
            coerced.append(_coerce_bronze_row(row))
        df = spark.createDataFrame(coerced, schema=bronze_schema)
        table = f"{catalog}.{schema}.bronze_sec_xbrl_facts"
        df.write.mode("append").saveAsTable(table)
        return len(rows)


class SparkCompanyFactsManifestWriter:
    """Writes per-CIK manifest rows to sec_companyfacts_ingest_log via Spark."""

    def __init__(self, spark_factory=None):
        self._spark_factory = spark_factory

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        return get_spark()

    def ensure_table(self, catalog: str, schema: str) -> None:
        """Create sec_companyfacts_ingest_log if absent; add http_status if missing."""
        spark = self._get_spark()
        manifest_schema = _get_manifest_schema()
        cols = _schema_to_ddl_columns(manifest_schema)
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {catalog}.{schema}.sec_companyfacts_ingest_log (
                {cols}
            ) USING DELTA
        """)
        # Idempotent: add any missing columns from the manifest StructType.
        # Derives column names and types from the schema — no hard-coded list.
        # If ALTER TABLE fails and columns are still missing, propagate the
        # error so the caller knows the manifest table is incomplete.
        try:
            existing = set(spark.table(f"{catalog}.{schema}.sec_companyfacts_ingest_log").columns)
        except Exception:
            # Table may not exist yet — CREATE TABLE above handles that case
            existing = set()
        missing = [
            f for f in manifest_schema.fields if f.name not in existing
        ]
        if missing:
            _TYPE_MAP = {
                "string": "STRING",
                "int": "INT",
                "bigint": "BIGINT",
                "double": "DOUBLE",
                "float": "FLOAT",
                "boolean": "BOOLEAN",
                "timestamp": "TIMESTAMP",
                "date": "DATE",
                "binary": "BINARY",
                "decimal": "DECIMAL",
                "smallint": "SMALLINT",
                "tinyint": "TINYINT",
            }
            parts = []
            for f in missing:
                ddl_type = _TYPE_MAP.get(
                    f.dataType.simpleString(), f.dataType.simpleString().upper()
                )
                parts.append(f"{f.name} {ddl_type}")
            spark.sql(
                f"ALTER TABLE {catalog}.{schema}.sec_companyfacts_ingest_log "
                f"ADD COLUMNS ({', '.join(parts)})"
            )
            # Verify the ALTER actually took effect
            try:
                after = set(spark.table(f"{catalog}.{schema}.sec_companyfacts_ingest_log").columns)
            except Exception:
                after = set()
            still_missing = [f.name for f in manifest_schema.fields if f.name not in after]
            if still_missing:
                raise RuntimeError(
                    f"ALTER TABLE failed to add columns {still_missing} to "
                    f"{catalog}.{schema}.sec_companyfacts_ingest_log"
                )

    def write_manifest(
        self,
        catalog: str,
        schema: str,
        entry: CompanyFactsManifestEntry,
    ) -> None:
        """Append a manifest row."""
        spark = self._get_spark()
        manifest_schema = _get_manifest_schema()
        row = {
            "ingest_run_id": entry.ingest_run_id,
            "cik": entry.cik,
            "ticker": entry.ticker,
            "fetch_status": entry.fetch_status,
            "attempt_count": entry.attempt_count,
            "payload_hash": entry.payload_hash,
            "payload_bytes": entry.payload_bytes,
            "fact_count": entry.fact_count,
            "http_status": entry.http_status,
            "started_at": entry.started_at,
            "completed_at": entry.completed_at,
            "error_category": entry.error_category,
            "error_message": entry.error_message,
            "logged_at": datetime.now(timezone.utc),
        }
        df = spark.createDataFrame([row], schema=manifest_schema)
        table = f"{catalog}.{schema}.sec_companyfacts_ingest_log"
        df.write.mode("append").saveAsTable(table)


# ── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point.  *argv* is parsed instead of sys.argv when given."""
    parser = argparse.ArgumentParser(
        description="SEC Company Facts XBRL Ingestion"
    )
    parser.add_argument("--catalog", default=os.getenv("CATALOG", "bootcamp_students"))
    parser.add_argument("--schema", default=os.getenv("SCHEMA", "evangoh_capstone"))
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--user-agent-secret-scope",
        default=DEFAULT_SECRET_SCOPE,
    )
    parser.add_argument(
        "--user-agent-secret-key",
        default=DEFAULT_SECRET_KEY,
    )
    parser.add_argument(
        "--cik-overrides-path",
        default=None,
        help="Path to CIK overrides YAML (default: config/sec_cik_overrides.yaml)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    # Wire Spark adapters
    delta_writer = SparkCompanyFactsWriter()
    manifest_writer = SparkCompanyFactsManifestWriter()
    universe_reader = SparkUniverseReader()

    delta_writer.ensure_table(args.catalog, args.schema)
    manifest_writer.ensure_table(args.catalog, args.schema)

    def _write_manifest(cat: str, sch: str, entry: CompanyFactsManifestEntry):
        manifest_writer.write_manifest(cat, sch, entry)

    result = run_ingest_companyfacts(
        catalog=args.catalog,
        schema=args.schema,
        tickers=tickers,
        run_id=args.run_id,
        dry_run=args.dry_run,
        user_agent_secret_scope=args.user_agent_secret_scope,
        user_agent_secret_key=args.user_agent_secret_key,
        cik_overrides_path=args.cik_overrides_path,
        universe_reader=universe_reader,
        delta_writer=delta_writer.append_rows,
        manifest_writer=_write_manifest,
    )

    if result["failed_count"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()