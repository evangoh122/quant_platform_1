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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

logger = logging.getLogger(__name__)

COMPANY_FACTS_URL = (
    f"{EDGAR_DATA_BASE}/api/xbrl/companyfacts/CIK{{cik}}.json"
)

# Plan B 2.2 — bronze_sec_xbrl_facts column order
BRONZE_FACT_COLUMNS = [
    "ingest_run_id",
    "ingested_at",
    "source_url",
    "payload_hash",
    "cik",
    "entity_name",
    "ticker",
    "taxonomy",
    "concept",
    "label",
    "description",
    "unit",
    "value_raw",
    "value_decimal",
    "period_start",
    "period_end",
    "instant",
    "fiscal_year",
    "fiscal_period",
    "form_type",
    "accession_number",
    "filed_date",
    "frame",
    "raw_fact_json",
    "source_updated_at",
]

# Plan B 2.1 — sec_companyfacts_ingest_log columns
MANIFEST_COLUMNS = [
    "ingest_run_id",
    "cik",
    "ticker",
    "fetch_status",
    "attempt_count",
    "payload_hash",
    "payload_bytes",
    "fact_count",
    "started_at",
    "completed_at",
    "error_category",
    "error_message",
]


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
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_category: str = ""
    error_message: str = ""


# ── Fetch logic ─────────────────────────────────────────────────────────────


def fetch_company_facts(
    client: SecClient,
    cik: str,
) -> Tuple[Dict[str, Any], bytes, str]:
    """Fetch Company Facts JSON for a CIK.

    Returns (parsed_payload, raw_bytes, payload_hash).
    Raises SecClientError on failure.
    """
    url = build_source_url(cik)
    raw_bytes = _fetch_raw_bytes(client, url)
    payload_hash = compute_payload_hash(raw_bytes)
    payload = json.loads(raw_bytes)
    return payload, raw_bytes, payload_hash


def _fetch_raw_bytes(client: SecClient, url: str) -> bytes:
    """Fetch raw bytes from SEC.  Uses the client's get_json internally but
    we need raw bytes for hash — fetch via the internal _request method."""
    # We'll use the underlying HTTP client directly with the same headers
    # to get raw bytes, respecting rate limiting via the existing limiter.
    resp = client._request(url, expect_json=False)
    return resp.text.encode("utf-8")


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
) -> Dict[str, Any]:
    """Run the SEC Company Facts ingestion pipeline.

    All external dependencies are injected for offline testability.
    Returns a summary dict with counts and errors.
    """
    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

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

    if cache_path is None:
        cache_path = os.environ.get(
            "SEC_COMPANY_TICKERS_CACHE",
            f"/Volumes/{catalog}/{schema}/sec_cache/company_tickers.json",
        )

    tickers_payload = load_company_tickers(
        client, cache_path=cache_path, dry_run=dry_run,
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

    if dry_run:
        logger.info(
            "DRY RUN: mapped=%d, missing=%d, ticker-CIK pairs=%d",
            result["mapped_count"], result["missing_count"], len(ticker_cik_pairs),
        )
        return result

    # Ingest each ticker-CIK with bounded concurrency
    ingested_at = datetime.now(timezone.utc)
    lock = threading.Lock()
    max_workers = min(4, len(ticker_cik_pairs)) if ticker_cik_pairs else 1

    def _fetch_one(ticker: str, cik: str) -> None:
        started_at = datetime.now(timezone.utc)
        source_url = build_source_url(cik)
        manifest = CompanyFactsManifestEntry(
            ingest_run_id=run_id,
            cik=cik,
            ticker=ticker,
            started_at=started_at,
        )

        # Snapshot request count before fetch for attempt tracking
        req_before = client.request_count

        try:
            payload, raw_bytes, payload_hash = fetch_company_facts(client, cik)
            attempt_count = client.request_count - req_before
            manifest.payload_hash = payload_hash
            manifest.payload_bytes = len(raw_bytes)

            # Skip if same (cik, payload_hash) already written this run
            with lock:
                if (cik, payload_hash) in seen_payloads:
                    manifest.fetch_status = "skipped_duplicate"
                    manifest.completed_at = datetime.now(timezone.utc)
                    result["skipped_duplicate_payloads"] += 1
                    if manifest_writer is not None:
                        manifest_writer(catalog, schema, manifest)
                    return

                seen_payloads.add((cik, payload_hash))

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

            with lock:
                result["fetched_count"] += 1
                result["total_facts"] += len(rows)

            if manifest_writer is not None:
                manifest_writer(catalog, schema, manifest)

            logger.info(
                "Fetched %s (CIK %s): %d facts, hash=%s, attempts=%d",
                ticker, cik, len(rows), payload_hash[:12], attempt_count,
            )

        except SecClientError as e:
            attempt_count = client.request_count - req_before
            with lock:
                result["failed_count"] += 1
            manifest.fetch_status = "failed"
            manifest.attempt_count = attempt_count
            manifest.completed_at = datetime.now(timezone.utc)
            manifest.error_category = _classify_error(e)
            manifest.error_message = str(e)[:500]
            with lock:
                result["errors"].append({
                    "ticker": ticker,
                    "cik": cik,
                    "error": str(e)[:200],
                })
            logger.error("Failed to fetch %s (CIK %s): %s", ticker, cik, e)
            if manifest_writer is not None:
                manifest_writer(catalog, schema, manifest)

        except Exception as e:
            attempt_count = client.request_count - req_before
            with lock:
                result["failed_count"] += 1
            manifest.fetch_status = "failed"
            manifest.attempt_count = attempt_count
            manifest.completed_at = datetime.now(timezone.utc)
            manifest.error_category = "unexpected"
            manifest.error_message = str(e)[:500]
            with lock:
                result["errors"].append({
                    "ticker": ticker,
                    "cik": cik,
                    "error": str(e)[:200],
                })
            logger.error("Unexpected error for %s (CIK %s): %s", ticker, cik, e)
            if manifest_writer is not None:
                manifest_writer(catalog, schema, manifest)

    if ticker_cik_pairs:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_fetch_one, t, c): (t, c)
                for t, c in ticker_cik_pairs
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
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()

    def ensure_table(self, catalog: str, schema: str) -> None:
        """Create bronze_sec_xbrl_facts if absent."""
        spark = self._get_spark()
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {catalog}.{schema}.bronze_sec_xbrl_facts (
                ingest_run_id     STRING NOT NULL,
                ingested_at       TIMESTAMP NOT NULL,
                source_url        STRING,
                payload_hash      STRING,
                cik               STRING,
                entity_name       STRING,
                ticker            STRING,
                taxonomy          STRING,
                concept           STRING,
                label             STRING,
                description       STRING,
                unit              STRING,
                value_raw         STRING,
                value_decimal     DOUBLE,
                period_start      STRING,
                period_end        STRING,
                instant           STRING,
                fiscal_year       INT,
                fiscal_period     STRING,
                form_type         STRING,
                accession_number  STRING,
                filed_date        STRING,
                frame             STRING,
                raw_fact_json     STRING,
                source_updated_at STRING
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
        df = spark.createDataFrame(rows)
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
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()

    def ensure_table(self, catalog: str, schema: str) -> None:
        """Create sec_companyfacts_ingest_log if absent."""
        spark = self._get_spark()
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {catalog}.{schema}.sec_companyfacts_ingest_log (
                ingest_run_id   STRING NOT NULL,
                cik             STRING NOT NULL,
                ticker          STRING NOT NULL,
                fetch_status    STRING NOT NULL,
                attempt_count   INT,
                payload_hash    STRING,
                payload_bytes   INT,
                fact_count      INT,
                started_at      TIMESTAMP,
                completed_at    TIMESTAMP,
                error_category  STRING,
                error_message   STRING,
                logged_at       TIMESTAMP NOT NULL
            ) USING DELTA
        """)

    def write_manifest(
        self,
        catalog: str,
        schema: str,
        entry: CompanyFactsManifestEntry,
    ) -> None:
        """Append a manifest row."""
        spark = self._get_spark()
        row = {
            "ingest_run_id": entry.ingest_run_id,
            "cik": entry.cik,
            "ticker": entry.ticker,
            "fetch_status": entry.fetch_status,
            "attempt_count": entry.attempt_count,
            "payload_hash": entry.payload_hash,
            "payload_bytes": entry.payload_bytes,
            "fact_count": entry.fact_count,
            "started_at": entry.started_at,
            "completed_at": entry.completed_at,
            "error_category": entry.error_category,
            "error_message": entry.error_message,
            "logged_at": datetime.now(timezone.utc),
        }
        df = spark.createDataFrame([row])
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