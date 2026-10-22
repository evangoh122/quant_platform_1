"""pipelines/ingest_sec_submissions.py — SEC submissions API ingestion (KG-0).

Reads the CIK list from ``gold_sec_coverage``, fetches each registrant's
submissions JSON from ``https://data.sec.gov/submissions/CIK##########.json``
with SEC fair-access headers, and appends the raw payload to
``bronze_sec_submissions`` (append-only, idempotent on
``(cik, payload_sha256)``).

The submissions endpoint is the only source in this project that carries the
registrant's real company name, former names, SIC code, tickers and exchanges
(``bronze_sec_filings_v2.company_name`` actually holds the canonical ticker).
Every bronze row carries ``data_source = 'sec_edgar'`` from the controlled
vocabulary in ``config/data_sources.py``.

Safety
------
* ``--dry-run`` is the default: it reads the CIK list, logs the plan and makes
  **zero** HTTP requests and **zero** writes.  A live run requires ``--live``.
* The User-Agent is resolved from ``SEC_EDGAR_USER_AGENT`` (env or Databricks
  secret by scope/key); no email address or contact string is hard-coded.
* Requests go through the shared :class:`SecClient` (retries with backoff,
  429/503 Retry-After cooldown).  Throughput is capped at
  :data:`MAX_SUBMISSIONS_RPS` (8 req/s) regardless of configuration.
* A 404 is recorded as a miss (``http_status = 404``, ``payload = NULL`` and the
  :data:`MISS_PAYLOAD_SHA256` sentinel) instead of failing the run.

Usage:
    python pipelines/ingest_sec_submissions.py --catalog C --schema S
    python pipelines/ingest_sec_submissions.py --catalog C --schema S --live
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple

# Ensure repo root is on sys.path so ``pipelines.*`` / ``sec_kg.*`` resolve when
# invoked via ``python_file`` in a Databricks job (``__file__`` is absent under
# serverless spark_python_task, hence the ``sys.argv[0]`` fallback).
_p = globals().get("__file__") or sys.argv[0]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(_p))))

from config.data_sources import validate_data_source  # noqa: E402
from pipelines._runtime import get_spark  # noqa: E402
from pipelines.sec_rag_ingest import (  # noqa: E402
    DEFAULT_SECRET_KEY,
    DEFAULT_SECRET_SCOPE,
    EDGAR_DATA_BASE,
    HttpClient,
    RateLimiter,
    SecClient,
    SecClientConfig,
    SecClientError,
    _resolve_user_agent,
    _validate_user_agent,
)
from sec_kg.submissions import (  # noqa: E402
    MISS_PAYLOAD_SHA256,
    SEC_EDGAR_DATA_SOURCE,
    normalize_cik,
    parse_registrant_json,
    payload_sha256,
)

logger = logging.getLogger(__name__)

SUBMISSIONS_URL = f"{EDGAR_DATA_BASE}/submissions/CIK{{cik}}.json"

# SEC fair-access upper bound.  The shared RateLimiter also enforces its own
# MAX_REQUESTS_PER_SECOND (10); this job additionally never exceeds 8.
MAX_SUBMISSIONS_RPS = 8

# Flush buffered rows in small batches so a long run does not hold every
# payload in driver memory.
WRITE_BATCH_SIZE = 25

# Plain-Python column spec — the StructType is built lazily so importing this
# module never requires PySpark (offline tests / CI without pyspark).
_ColumnSpec = namedtuple("_ColumnSpec", ["name", "type_str", "nullable"])

BRONZE_COLUMNS = [
    _ColumnSpec("cik", "string", False),
    _ColumnSpec("payload", "string", True),
    _ColumnSpec("payload_sha256", "string", False),
    _ColumnSpec("http_status", "int", False),
    _ColumnSpec("fetched_at", "timestamp", False),
    _ColumnSpec("ingest_run_id", "string", False),
    _ColumnSpec("data_source", "string", False),
]

# Unity Catalog column comments for non-obvious columns.  Only ``data_source``
# carries one today: it is the provenance contract from config/data_sources.py.
_COLUMN_COMMENTS = {
    "data_source": (
        "Provider code from config.data_sources.DATA_SOURCES — "
        "this table is always sec_edgar"
    ),
}

_DDL_TYPE_MAP = {
    "string": "STRING",
    "int": "INT",
    "bigint": "BIGINT",
    "double": "DOUBLE",
    "float": "FLOAT",
    "boolean": "BOOLEAN",
    "timestamp": "TIMESTAMP",
    "date": "DATE",
}

_SPARK_TYPE_MAP: Optional[Dict[str, Any]] = None
_BRONZE_SCHEMA: Optional[Any] = None


def _get_spark_type_map() -> Dict[str, Any]:
    """Build the Spark type map on first call (requires PySpark)."""
    global _SPARK_TYPE_MAP
    if _SPARK_TYPE_MAP is not None:
        return _SPARK_TYPE_MAP
    from pyspark.sql.types import (  # noqa: PLC0415
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


def _get_bronze_schema():
    """Return the bronze StructType, building it once (lazy)."""
    global _BRONZE_SCHEMA
    if _BRONZE_SCHEMA is not None:
        return _BRONZE_SCHEMA
    from pyspark.sql.types import StructField, StructType  # noqa: PLC0415

    type_map = _get_spark_type_map()
    _BRONZE_SCHEMA = StructType(
        [
            StructField(c.name, type_map[c.type_str], c.nullable)
            for c in BRONZE_COLUMNS
        ]
    )
    return _BRONZE_SCHEMA


def columns_to_ddl(columns) -> str:
    """Generate a DDL column list from ``_ColumnSpec`` tuples (no PySpark)."""
    parts = []
    for c in columns:
        ddl_type = _DDL_TYPE_MAP.get(c.type_str, c.type_str.upper())
        nullable = "" if c.nullable else " NOT NULL"
        comment = _COLUMN_COMMENTS.get(c.name)
        comment_sql = f" COMMENT '{comment}'" if comment else ""
        parts.append(f"    {c.name} {ddl_type}{nullable}{comment_sql}")
    return ",\n".join(parts)


# ── Pure helpers ─────────────────────────────────────────────────────────────


def clamp_requests_per_second(value: Any = None) -> int:
    """Clamp a configured rate to ``[1, MAX_SUBMISSIONS_RPS]``.

    ``None``, blanks and unparsable values fall back to the fair-access cap so a
    bad environment variable can never disable the limiter.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return MAX_SUBMISSIONS_RPS
    try:
        rps = int(value)
    except (TypeError, ValueError):
        return MAX_SUBMISSIONS_RPS
    return max(1, min(rps, MAX_SUBMISSIONS_RPS))


def build_source_url(cik: str) -> str:
    """Build the submissions URL for a CIK (zero-padded to ten digits)."""
    return SUBMISSIONS_URL.format(cik=normalize_cik(cik))


def coerce_bronze_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a row with exactly the bronze columns and Spark-friendly types."""
    status = row.get("http_status")
    return {
        "cik": normalize_cik(row.get("cik")),
        "payload": row.get("payload"),
        "payload_sha256": row.get("payload_sha256") or MISS_PAYLOAD_SHA256,
        "http_status": int(status) if status is not None else 200,
        "fetched_at": row.get("fetched_at"),
        "ingest_run_id": row.get("ingest_run_id"),
        # A row without a valid provider code must fail here, not be written.
        "data_source": validate_data_source(row["data_source"]),
    }


def miss_row(cik: str, ingest_run_id: str, fetched_at: datetime) -> Dict[str, Any]:
    """Row recorded for an HTTP 404 (the CIK has no submissions document)."""
    return {
        "cik": normalize_cik(cik),
        "payload": None,
        "payload_sha256": MISS_PAYLOAD_SHA256,
        "http_status": 404,
        "fetched_at": fetched_at,
        "ingest_run_id": ingest_run_id,
        "data_source": SEC_EDGAR_DATA_SOURCE,
    }


def payload_row(
    cik: str,
    text: str,
    ingest_run_id: str,
    fetched_at: datetime,
) -> Dict[str, Any]:
    """Row recorded for a successful fetch (payload stored verbatim)."""
    return {
        "cik": normalize_cik(cik),
        "payload": text,
        "payload_sha256": payload_sha256(text.encode("utf-8")),
        "http_status": 200,
        "fetched_at": fetched_at,
        "ingest_run_id": ingest_run_id,
        "data_source": SEC_EDGAR_DATA_SOURCE,
    }


# ── Dependency-injection boundaries ──────────────────────────────────────────


class CikReader(Protocol):
    """Reads the CIK list to ingest."""

    def read_ciks(self, catalog: str, schema: str) -> List[str]: ...


class SubmissionsWriter(Protocol):
    """Append-only writer for bronze submissions rows."""

    def write_rows(
        self,
        catalog: str,
        schema: str,
        rows: List[Dict[str, Any]],
    ) -> int: ...


class SparkCikReader:
    """Reads distinct non-null CIKs from ``gold_sec_coverage``."""

    def __init__(self, spark_factory: Optional[Callable[[], Any]] = None):
        self._spark_factory = spark_factory

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        return get_spark()

    def read_ciks(self, catalog: str, schema: str) -> List[str]:
        spark = self._get_spark()
        rows = (
            spark.table(f"{catalog}.{schema}.gold_sec_coverage")
            .select("cik")
            .where("cik IS NOT NULL")
            .distinct()
            .collect()
        )
        ciks: Set[str] = set()
        for row in rows:
            value = row[0]
            if value is None or not str(value).strip():
                continue
            ciks.add(normalize_cik(value))
        return sorted(ciks)


class SparkSubmissionsWriter:
    """Creates and MERGEs into ``bronze_sec_submissions`` via Spark.

    The MERGE only ever inserts (``WHEN NOT MATCHED THEN INSERT *``), so the
    table is append-only while repeated runs with the same
    ``(cik, payload_sha256)`` are no-ops.
    """

    _TEMP_VIEW = "_sec_submissions_incoming"

    def __init__(self, spark_factory: Optional[Callable[[], Any]] = None):
        self._spark_factory = spark_factory

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        return get_spark()

    @staticmethod
    def table_name(catalog: str, schema: str) -> str:
        return f"{catalog}.{schema}.bronze_sec_submissions"

    def ensure_table(self, catalog: str, schema: str) -> None:
        spark = self._get_spark()
        spark.sql(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name(catalog, schema)} (
                {columns_to_ddl(BRONZE_COLUMNS)}
            ) USING DELTA
            """
        )

    def write_rows(
        self,
        catalog: str,
        schema: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        spark = self._get_spark()
        coerced = [coerce_bronze_row(row) for row in rows]
        df = spark.createDataFrame(coerced, schema=_get_bronze_schema())
        df.createOrReplaceTempView(self._TEMP_VIEW)
        spark.sql(
            f"""
            MERGE INTO {self.table_name(catalog, schema)} AS t
            USING {self._TEMP_VIEW} AS s
            ON t.cik = s.cik AND t.payload_sha256 = s.payload_sha256
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        return len(coerced)


# ── Run summary ──────────────────────────────────────────────────────────────


@dataclass
class IngestSummary:
    run_id: str
    dry_run: bool
    ciks_requested: int = 0
    ciks_fetched: int = 0
    ciks_missing: int = 0
    ciks_failed: int = 0
    registrants_parsed: int = 0
    rows_submitted: int = 0
    skipped_duplicate_payloads: int = 0
    errors: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "ciks_requested": self.ciks_requested,
            "ciks_fetched": self.ciks_fetched,
            "ciks_missing": self.ciks_missing,
            "ciks_failed": self.ciks_failed,
            "registrants_parsed": self.registrants_parsed,
            "rows_submitted": self.rows_submitted,
            "skipped_duplicate_payloads": self.skipped_duplicate_payloads,
            "errors": list(self.errors or []),
        }


# ── Ingestion ────────────────────────────────────────────────────────────────


def run_ingest_submissions(
    *,
    catalog: str,
    schema: str,
    ciks: Optional[List[str]] = None,
    run_id: Optional[str] = None,
    live: bool = False,
    user_agent_secret_scope: str = DEFAULT_SECRET_SCOPE,
    user_agent_secret_key: str = DEFAULT_SECRET_KEY,
    requests_per_second: Any = None,
    cik_reader: Optional[CikReader] = None,
    http_client: Optional[HttpClient] = None,
    clock: Optional[Any] = None,
    writer: Optional[SubmissionsWriter] = None,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> Dict[str, Any]:
    """Run submissions ingestion.

    ``live=False`` (the default) is a dry run: it resolves the CIK list, logs
    the plan, and returns before creating an HTTP client, resolving the
    User-Agent, or writing anything.

    All external dependencies are injectable so the pipeline is testable
    offline.  A live run requires ``writer``; returning a dry-run success for a
    requested live run would silently skip ingestion.

    ``fetched_at`` is read from ``now_fn`` only after a response completes — the
    successful body, or the final 404 — never before the request, so a
    Retry-After cooldown or retry backoff cannot back-date the observation.
    """
    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    _now = now_fn or (lambda: datetime.now(timezone.utc))
    summary = IngestSummary(run_id=run_id, dry_run=not live, errors=[])

    # Resolve the CIK list (injected list wins over the reader).
    if ciks is None:
        if cik_reader is None:
            raise ValueError("Either ciks or cik_reader must be provided")
        ciks = cik_reader.read_ciks(catalog, schema)

    normalized: List[str] = []
    seen_ciks: Set[str] = set()
    for value in ciks:
        cik = normalize_cik(value)
        if cik in seen_ciks:
            continue
        seen_ciks.add(cik)
        normalized.append(cik)
    summary.ciks_requested = len(normalized)

    if not live:
        logger.info(
            "DRY RUN: %d CIK(s) from %s.%s.gold_sec_coverage; no HTTP requests, "
            "no writes. Pass --live to ingest.",
            len(normalized),
            catalog,
            schema,
        )
        return summary.to_dict()

    if writer is None:
        raise ValueError("a live run requires a writer")

    user_agent = _resolve_user_agent(
        secret_scope=user_agent_secret_scope,
        secret_key=user_agent_secret_key,
    )
    _validate_user_agent(user_agent)

    rps = clamp_requests_per_second(
        requests_per_second
        if requests_per_second is not None
        else os.environ.get("SEC_SUBMISSIONS_REQUESTS_PER_SECOND")
    )
    limiter = RateLimiter(max_requests_per_second=rps, clock=clock)

    if http_client is None:
        from pipelines._http_adapter import RequestsAdapter  # noqa: PLC0415

        http_client = RequestsAdapter()

    client = SecClient(
        SecClientConfig(user_agent=user_agent),
        http_client,
        limiter,
        clock,
    )

    buffered: List[Dict[str, Any]] = []
    seen_keys: Set[Tuple[str, str]] = set()

    def _flush() -> None:
        nonlocal buffered
        if not buffered:
            return
        summary.rows_submitted += int(
            writer.write_rows(catalog, schema, list(buffered))
        )
        buffered = []

    for cik in normalized:
        try:
            text = client.get_text(build_source_url(cik))
        except SecClientError as exc:
            if exc.status_code == 404:
                # Recorded miss: the CIK has no submissions document.  The
                # observation time is stamped when the final response arrives,
                # not before the request, so rate-limit waits and retries can
                # never back-date it.
                fetched_at = _now()
                buffered.append(miss_row(cik, run_id, fetched_at))
                summary.ciks_missing += 1
                if len(buffered) >= WRITE_BATCH_SIZE:
                    _flush()
                logger.info("CIK %s: 404 (recorded miss)", cik)
                continue
            summary.ciks_failed += 1
            summary.errors.append(
                {
                    "cik": cik,
                    "http_status": exc.status_code,
                    "error": str(exc)[:200],
                }
            )
            logger.error("CIK %s: fetch failed (%s)", cik, exc.status_code)
            continue

        # The successful response has completed: stamp the observation now, so
        # the timestamp covers the Retry-After cooldown and every retry that
        # preceded this response instead of the moment before the request.
        fetched_at = _now()

        key = (cik, payload_sha256(text.encode("utf-8")))
        if key in seen_keys:
            summary.skipped_duplicate_payloads += 1
            continue

        try:
            record = parse_registrant_json(text, fetched_at)
        except (TypeError, ValueError) as exc:
            summary.ciks_failed += 1
            summary.errors.append(
                {"cik": cik, "http_status": 200, "error": str(exc)[:200]}
            )
            logger.error("CIK %s: unparsable submissions payload", cik)
            continue

        if record.cik10 != cik:
            # A payload for a different CIK must never be filed under the
            # requested one: the bronze key would be wrong for every consumer.
            summary.ciks_failed += 1
            summary.errors.append(
                {
                    "cik": cik,
                    "http_status": 200,
                    "error": f"payload cik mismatch: {record.cik10}",
                }
            )
            logger.error(
                "CIK %s: payload cik mismatch (%s); not written",
                cik,
                record.cik10,
            )
            continue

        seen_keys.add(key)
        buffered.append(payload_row(cik, text, run_id, fetched_at))
        summary.ciks_fetched += 1
        summary.registrants_parsed += 1
        logger.info(
            "CIK %s: fetched %d bytes, name=%r, %d former name(s)",
            cik,
            len(text),
            record.name,
            len(record.former_names),
        )
        if len(buffered) >= WRITE_BATCH_SIZE:
            _flush()

    _flush()

    logger.info(
        "Submissions ingestion complete: requested=%d fetched=%d missing=%d "
        "failed=%d rows=%d",
        summary.ciks_requested,
        summary.ciks_fetched,
        summary.ciks_missing,
        summary.ciks_failed,
        summary.rows_submitted,
    )
    return summary.to_dict()


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="SEC submissions API ingestion (KG-0 registrant identity)"
    )
    parser.add_argument("--catalog", default=os.getenv("CATALOG", "bootcamp_students"))
    parser.add_argument("--schema", default=os.getenv("SCHEMA", "evangoh_capstone"))
    parser.add_argument(
        "--ciks",
        default=None,
        help="Comma-separated CIKs to ingest instead of reading gold_sec_coverage",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform HTTP requests and writes (default: dry run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry run (default); mutually exclusive with --live",
    )
    parser.add_argument(
        "--user-agent-secret-scope",
        default=DEFAULT_SECRET_SCOPE,
    )
    parser.add_argument(
        "--user-agent-secret-key",
        default=DEFAULT_SECRET_KEY,
    )
    parser.add_argument(
        "--requests-per-second",
        default=None,
        help=f"Desired rate; clamped to <= {MAX_SUBMISSIONS_RPS}",
    )
    args = parser.parse_args(argv)

    if args.live and args.dry_run:
        parser.error("--live and --dry-run are mutually exclusive")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    ciks = None
    if args.ciks:
        ciks = [c.strip() for c in args.ciks.split(",") if c.strip()]

    # Dry run never constructs a Spark writer: no table is created and no write
    # path is reachable.
    writer = None
    if args.live:
        writer = SparkSubmissionsWriter()
        writer.ensure_table(args.catalog, args.schema)

    result = run_ingest_submissions(
        catalog=args.catalog,
        schema=args.schema,
        ciks=ciks,
        run_id=args.run_id,
        live=args.live,
        user_agent_secret_scope=args.user_agent_secret_scope,
        user_agent_secret_key=args.user_agent_secret_key,
        requests_per_second=args.requests_per_second,
        cik_reader=SparkCikReader(),
        writer=writer,
    )

    print(json.dumps(result, indent=2, default=str))

    if result["ciks_failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
