"""pipelines/sec_rag_ingest.py — SEC EDGAR RAG ingestion pipeline.

Production CLI and pure/core implementation for SEC filing ingestion.
All pyspark, delta, and databricks imports are behind the Databricks adapter
boundary so pure tests run without those dependencies.

Usage:
    python pipelines/sec_rag_ingest.py --dry-run --start-date 2024-09-01 --forms 10-K,10-Q
    python pipelines/sec_rag_ingest.py --tickers AAPL,MSFT --start-date 2024-09-01
    python pipelines/sec_rag_ingest.py --include-historical --start-date 2024-09-01
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
)

# Ensure repo root is on sys.path so ``pipelines.*`` resolves when invoked
# via ``python_file`` in a Databricks job.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200
SECTION_CAP = 50000
FULL_DOCUMENT_CAP = 100000
MIN_CHUNK_CHARS = 50
DEFAULT_START_DATE = "2024-09-01"
DEFAULT_FORMS = "10-K,10-Q"
EDGAR_DATA_BASE = "https://data.sec.gov"
EDGAR_WWW_BASE = "https://www.sec.gov"
DEFAULT_REQUESTS_PER_SECOND = 8
MAX_REQUESTS_PER_SECOND = 10
DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_RETRIES = 5
DEFAULT_TICKER_CACHE_TTL = 86400
DEFAULT_SECRET_SCOPE = "evangoh_capstone"
DEFAULT_SECRET_KEY = "sec_edgar_user_agent"

# ── Process-wide SEC rate limiter ───────────────────────────────────────────
# One singleton limiter shared by sec_rag_ingest and xbrl_client so the
# aggregate rate stays ≤ MAX_REQUESTS_PER_SECOND across all callers.

_global_limiter: Optional["RateLimiter"] = None
_global_limiter_lock = threading.Lock()


def get_global_limiter(
    max_rps: int = DEFAULT_REQUESTS_PER_SECOND,
    clock: Optional["Clock"] = None,
) -> "RateLimiter":
    """Return the process-wide RateLimiter singleton (thread-safe)."""
    global _global_limiter
    if _global_limiter is None:
        with _global_limiter_lock:
            if _global_limiter is None:
                _global_limiter = RateLimiter(
                    max_requests_per_second=min(max_rps, MAX_REQUESTS_PER_SECOND),
                    clock=clock,
                )
    return _global_limiter


def _resolve_user_agent(
    secret_scope: str = DEFAULT_SECRET_SCOPE,
    secret_key: str = DEFAULT_SECRET_KEY,
) -> str:
    """Resolve SEC EDGAR User-Agent from env or Databricks secret.

    Resolution order:
      1. Environment variable ``SEC_EDGAR_USER_AGENT``
      2. Databricks secret via ``dbutils.secrets.get`` (cluster notebooks)
      3. Databricks secret via ``WorkspaceClient().secrets.get_secret_value`` (SDK)

    The SDK returns a base64-encoded value — decoded automatically.
    Never logs/prints the actual value; logs only the source.
    """
    import base64

    env_val = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    if env_val:
        logger.info("SEC_EDGAR_USER_AGENT resolved from source=env")
        return env_val

    # Try dbutils (available on Databricks clusters)
    try:
        import IPython  # noqa: F811
        dbutils = IPython.get_ipython().user_ns.get("dbutils")  # type: ignore[union-attr]
        if dbutils is not None:
            secret_val = dbutils.secrets.get(scope=secret_scope, key=secret_key)
            if secret_val:
                logger.info(
                    "SEC_EDGAR_USER_AGENT resolved from source=secret (dbutils, scope=%s)",
                    secret_scope,
                )
                return secret_val
    except Exception:
        pass

    # Try WorkspaceClient SDK (base64-encoded response)
    try:
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient()
        resp = client.secrets.get_secret_value(scope=secret_scope, key=secret_key)
        if resp.value is not None:
            decoded = base64.b64decode(resp.value).decode("utf-8")
            logger.info(
                "SEC_EDGAR_USER_AGENT resolved from source=secret (sdk, scope=%s)",
                secret_scope,
            )
            return decoded
    except Exception:
        pass

    raise ValueError(
        f"SEC_EDGAR_USER_AGENT not found. Set the environment variable or create "
        f"a Databricks secret: scope='{secret_scope}', key='{secret_key}'."
    )


def _validate_user_agent(user_agent: str) -> None:
    """Validate user agent is non-empty and not a placeholder."""
    if not user_agent or "example" in user_agent.lower():
        raise ValueError(
            "SEC_EDGAR_USER_AGENT must be set to a descriptive application/contact string. "
            "Set it from environment or Databricks secret."
        )


# ── Section patterns (10-K / 10-Q) ────────────────────────────────────────────

SECTION_PATTERNS: List[Tuple[str, str]] = [
    (r"(?i)item\s*1[^0-9a].*?(?=item\s*[2-9]|$)", "item1_business"),
    (r"(?i)item\s*1a[^0-9a].*?(?=item\s*[2-9]|$)", "item1a_risk_factors"),
    (r"(?i)item\s*7[^a0-9].*?(?=item\s*[89]|$)", "item7_mda"),
    (r"(?i)item\s*7a[^0-9].*?(?=item\s*8|$)", "item7a_quant_risk"),
    (r"(?i)item\s*8[^0-9a].*?(?=item\s*9|$)", "item8_financial_statements"),
]


class AccessionOwnershipConflict(ValueError):
    """Raised when an accession number is already owned by a different CIK."""
    pass


# ── Protocols (dependency injection) ──────────────────────────────────────────

class HttpClient(Protocol):
    """HTTP client interface for SEC requests."""

    def get(
        self,
        url: str,
        headers: Dict[str, str],
        timeout: float = 30.0,
    ) -> "HttpResponse": ...


@dataclass
class HttpResponse:
    status_code: int
    text: str
    headers: Dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.text)


class Clock(Protocol):
    """Monotonic clock for rate limiting."""

    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class UniverseReader(Protocol):
    """Reads ticker universe from the data platform."""

    def read_universe(
        self,
        catalog: str,
        schema: str,
        include_historical: bool = False,
    ) -> List["TickerEntry"]: ...


@dataclass
class TickerEntry:
    ticker: str
    phase: int


class ExistingAccessionReader(Protocol):
    """Reads existing accession numbers from bronze table.

    Returns a mapping of accession_number -> (cik, ticker) for conflict detection.
    An accession already owned by a different CIK must fail loudly.
    """

    def read_existing_accessions(
        self,
        catalog: str,
        schema: str,
    ) -> Dict[str, Tuple[str, str]]: ...


class DataWriter(Protocol):
    """Writes bronze filing rows to Delta."""

    def append_bronze_rows(
        self,
        catalog: str,
        schema: str,
        rows: List[Dict[str, Any]],
    ) -> Optional[int]: ...


class IngestLogWriter(Protocol):
    """Writes ingest log entries."""

    def append_log(
        self,
        catalog: str,
        schema: str,
        entry: "IngestLogEntry",
    ) -> None: ...


class IngestLogReader(Protocol):
    """Reads ingest log entries for resume support.

    Returns a set of (run_id, ticker, accession_number) tuples that have
    already succeeded in previous runs.
    """

    def read_succeeded_accessions(
        self,
        catalog: str,
        schema: str,
        run_id: str,
    ) -> Set[Tuple[str, str, str]]: ...

    def read_max_attempt(
        self,
        catalog: str,
        schema: str,
        run_id: str,
        ticker: str,
        accession_number: str,
    ) -> int: ...


class CikMappingLogWriter(Protocol):
    """Writes CIK mapping log entries."""

    def append_mapping_log(
        self,
        catalog: str,
        schema: str,
        entry: "CikMappingLogEntry",
    ) -> None: ...

    def flush(self, catalog: str, schema: str) -> None:
        """Persist any buffered entries. No-op if nothing is buffered."""
        ...


@dataclass
class CikMappingLogEntry:
    ticker: str
    lookup_symbol: Optional[str]
    cik: Optional[str]
    status: str
    reason: str
    mapped_ts: Optional[datetime] = None
    run_id: Optional[str] = None


@dataclass
class IngestLogEntry:
    run_id: str
    ticker: str
    cik: str
    accession_number: str
    form_type: str
    filing_date: Optional[str]
    accepted_ts: Optional[datetime]
    status: str
    rows_appended: Optional[int] = None
    attempt: int = 1
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_ts: Optional[datetime] = None
    completed_ts: Optional[datetime] = None
    dry_run: bool = False


# ── Parsing functions (refactored from notebook) ──────────────────────────────

def record_key(*parts: Any) -> str:
    """Create deterministic SHA-256 identifier.

    Same logical SEC record always generates exactly the same record_key.
    """
    text = "||".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_sec_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse SEC timestamp string to tz-aware UTC datetime for Spark.

    Returns tz-aware UTC datetime so that PySpark serializes correctly
    regardless of the local timezone (naive datetimes are serialized via
    time.mktime which uses the local TZ, causing 8-hour shifts in UTC+8).
    """
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        return ts
    except Exception:
        return None


def strip_html(html_text: str) -> str:
    """Strip HTML tags and normalize whitespace.

    Removes script, style, noscript, and table tags.
    Removes 'Table of Contents' text.
    """
    if not html_text:
        return ""

    # Try lxml first, fall back to html.parser
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "lxml")
    except Exception:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup(["script", "style", "noscript", "table"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"Table of Contents", "", text, flags=re.IGNORECASE)
    return text


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into overlapping chunks.

    Chunks below 50 characters are discarded.
    """
    if not text:
        return []
    if len(text) < MIN_CHUNK_CHARS:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += chunk_size - overlap
    return chunks


def extract_sections(plain_text: str) -> List[Tuple[str, str]]:
    """Extract named sections from plain text using regex patterns.

    Falls back to full_document if no sections match.
    """
    sections_found: List[Tuple[str, str]] = []

    for pattern, section_name in SECTION_PATTERNS:
        match = re.search(pattern, plain_text, flags=re.DOTALL)
        if not match:
            continue
        section_text = match.group(0).strip()
        section_text = section_text[:SECTION_CAP]
        if len(section_text) >= MIN_CHUNK_CHARS:
            sections_found.append((section_name, section_text))

    if not sections_found:
        sections_found = [("full_document", plain_text[:FULL_DOCUMENT_CAP])]

    return sections_found


# ── CIK mapping ───────────────────────────────────────────────────────────────

def normalize_sec_ticker(symbol: str) -> List[str]:
    """Return lookup variants for SEC ticker resolution.

    Tries exact spelling, then BRK-B/BRK.B aliases in both directions.
    Normalizes whitespace/case and treats . and - as equivalent.
    """
    sym = symbol.strip().upper()
    variants = [sym]

    # Generate alias variants for class-share separators
    if "." in sym:
        variants.append(sym.replace(".", "-"))
    if "-" in sym:
        variants.append(sym.replace("-", "."))

    # Deduplicate while preserving order
    seen: Set[str] = set()
    result: List[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def build_cik_map(
    symbols: List[str],
    company_tickers_payload: Dict[str, Any],
) -> Dict[str, "CikMappingResult"]:
    """Build ticker-to-CIK mapping from SEC company_tickers.json payload.

    CIKs are zero-padded to 10 digits.
    Returns a mapping result for every input symbol.
    A ticker that maps to multiple distinct CIKs is marked 'ambiguous'.
    """
    # Build reverse lookup: normalized ticker -> set of CIKs
    ticker_to_ciks: Dict[str, Set[str]] = {}
    for _key, entry in company_tickers_payload.items():
        if isinstance(entry, dict) and "ticker" in entry and "cik_str" in entry:
            raw_ticker = entry["ticker"].strip().upper()
            cik = str(entry["cik_str"]).zfill(10)
            ticker_to_ciks.setdefault(raw_ticker, set()).add(cik)

    results: Dict[str, CikMappingResult] = {}
    now = datetime.now(timezone.utc)

    for symbol in symbols:
        variants = normalize_sec_ticker(symbol)
        matched_ciks: Optional[Set[str]] = None
        matched_lookup: Optional[str] = None

        for variant in variants:
            if variant in ticker_to_ciks:
                matched_ciks = ticker_to_ciks[variant]
                matched_lookup = variant
                break

        if matched_ciks:
            if len(matched_ciks) > 1:
                results[symbol] = CikMappingResult(
                    ticker=symbol,
                    lookup_symbol=matched_lookup,
                    cik=None,
                    status="ambiguous",
                    reason=f"Multiple CIKs for {symbol}: {', '.join(sorted(matched_ciks))}",
                    mapped_ts=now,
                )
            else:
                results[symbol] = CikMappingResult(
                    ticker=symbol,
                    lookup_symbol=matched_lookup,
                    cik=next(iter(matched_ciks)),
                    status="mapped",
                    reason="",
                    mapped_ts=now,
                )
        else:
            results[symbol] = CikMappingResult(
                ticker=symbol,
                lookup_symbol=variants[0],
                cik=None,
                status="missing",
                reason=f"No CIK found for {symbol} (tried {', '.join(variants)})",
                mapped_ts=now,
            )

    return results


@dataclass
class CikMappingResult:
    ticker: str
    lookup_symbol: Optional[str]
    cik: Optional[str]
    status: str  # mapped | missing | ambiguous
    reason: str
    mapped_ts: Optional[datetime] = None


# ── Rate limiter ──────────────────────────────────────────────────────────────

MAX_RETRY_AFTER = 120  # Cap Retry-After at 120 s; above → hard failure


class RateLimiter:
    """Thread-safe sliding-window rate limiter with global cooldown.

    Guarantees no more than max_requests request starts in any rolling
    one-second window. Uses injectable clock and sleep for testing.

    When a 429/503 is received, ``trigger_cooldown`` pauses ALL workers
    until the Retry-After deadline (capped at MAX_RETRY_AFTER seconds).
    """

    def __init__(
        self,
        max_requests_per_second: int = DEFAULT_REQUESTS_PER_SECOND,
        clock: Optional[Clock] = None,
    ):
        if max_requests_per_second > MAX_REQUESTS_PER_SECOND:
            raise ValueError(
                f"max_requests_per_second={max_requests_per_second} exceeds "
                f"hard limit of {MAX_REQUESTS_PER_SECOND}"
            )
        if max_requests_per_second <= 0:
            raise ValueError("max_requests_per_second must be positive")

        self._max_rps = max_requests_per_second
        self._clock = clock or _SystemClock()
        self._lock = threading.Lock()
        self._timestamps: List[float] = []
        self._cooldown_until: float = 0.0  # global cooldown deadline

    def acquire(self) -> None:
        """Block until a request slot is available and no global cooldown active."""
        while True:
            with self._lock:
                # Honour global cooldown first
                now = self._clock.monotonic()
                if now < self._cooldown_until:
                    wait_time = self._cooldown_until - now
                    self._lock.release()
                    try:
                        self._clock.sleep(wait_time)
                    finally:
                        self._lock.acquire()
                    continue

                # Remove timestamps outside the 1-second window
                cutoff = now - 1.0
                self._timestamps = [t for t in self._timestamps if t > cutoff]

                if len(self._timestamps) < self._max_rps:
                    self._timestamps.append(now)
                    return

                # Need to wait until the oldest timestamp expires
                wait_time = self._timestamps[0] - cutoff + 0.01

            self._clock.sleep(wait_time)

    def trigger_cooldown(self, seconds: float) -> None:
        """Set a global cooldown deadline — all workers pause until it expires.

        Only extends the deadline (never shortens it) so that overlapping 429s
        don't race.
        """
        deadline = self._clock.monotonic() + seconds
        with self._lock:
            if deadline > self._cooldown_until:
                self._cooldown_until = deadline

    @property
    def cooldown_remaining(self) -> float:
        """Seconds remaining in the global cooldown (0 if idle)."""
        with self._lock:
            remaining = self._cooldown_until - self._clock.monotonic()
            return max(remaining, 0.0)

    @property
    def max_rps(self) -> int:
        return self._max_rps


class _SystemClock:
    """Real monotonic clock for production use."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


# ── SEC client ────────────────────────────────────────────────────────────────

@dataclass
class SecClientConfig:
    user_agent: str
    requests_per_second: int = DEFAULT_REQUESTS_PER_SECOND
    max_retries: int = DEFAULT_MAX_RETRIES


class SecClient:
    """Centralized SEC EDGAR HTTP client with rate limiting and retries."""

    def __init__(
        self,
        config: SecClientConfig,
        http_client: HttpClient,
        limiter: RateLimiter,
        clock: Optional[Clock] = None,
    ):
        self._config = config
        self._http = http_client
        self._limiter = limiter
        self._clock = clock or _SystemClock()
        self._headers = {
            "User-Agent": config.user_agent,
            "Accept": "application/json",
        }
        self._request_count = 0
        self._retry_count = 0

    def get_json(self, url: str) -> Any:
        """Fetch JSON from SEC with rate limiting and retries."""
        resp = self._request(url, expect_json=True)
        return resp.json()

    def get_text(self, url: str) -> str:
        """Fetch text/HTML from SEC with rate limiting and retries."""
        resp = self._request(url, expect_json=False)
        return resp.text

    def _request(
        self,
        url: str,
        expect_json: bool = True,
    ) -> HttpResponse:
        """Execute request with rate limiting, retries, and backoff."""
        last_error: Optional[Exception] = None

        for attempt in range(self._config.max_retries):
            self._limiter.acquire()
            self._request_count += 1

            try:
                resp = self._http.get(url, self._headers, timeout=30.0)

                if resp.status_code == 200:
                    return resp

                if resp.status_code in (429, 503):
                    retry_after = self._parse_retry_after(resp.headers)
                    if retry_after is not None:
                        # Cap Retry-After; above cap → hard failure
                        if retry_after > MAX_RETRY_AFTER:
                            raise SecClientError(
                                f"Retry-After {retry_after:.0f}s exceeds cap "
                                f"({MAX_RETRY_AFTER}s) for {url}",
                                status_code=resp.status_code,
                                url=url,
                            )
                        # Global cool-down: pause ALL workers until deadline
                        self._limiter.trigger_cooldown(retry_after)
                        self._clock.sleep(retry_after)
                    else:
                        backoff = min(2 ** attempt, 60)
                        self._limiter.trigger_cooldown(backoff)
                        self._clock.sleep(backoff)
                    self._retry_count += 1
                    continue

                if resp.status_code >= 500:
                    backoff = min(2 ** attempt, 60)
                    self._clock.sleep(backoff)
                    self._retry_count += 1
                    continue

                # Permanent 4xx - don't retry
                raise SecClientError(
                    f"SEC request failed: {resp.status_code} for {url}",
                    status_code=resp.status_code,
                    url=url,
                )

            except (TimeoutError, ConnectionError, OSError) as e:
                last_error = e
                backoff = min(2 ** attempt, 60)
                self._clock.sleep(backoff)
                self._retry_count += 1
                continue

        raise SecClientError(
            f"SEC request failed after {self._config.max_retries} attempts for {url}: {last_error}",
            url=url,
        )

    @staticmethod
    def _parse_retry_after(headers: Dict[str, str]) -> Optional[float]:
        """Parse Retry-After header (numeric seconds or HTTP-date).

        Handles both:
        - Numeric seconds: "120"
        - HTTP-date: "Wed, 21 Oct 2015 07:28:00 GMT" (RFC 7231 §7.1.3)
        """
        value = headers.get("Retry-After") or headers.get("retry-after")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            pass
        # Try HTTP-date format
        try:
            from email.utils import parsedate_to_datetime
            target = parsedate_to_datetime(value)
            now = datetime.now(timezone.utc)
            delta = (target - now).total_seconds()
            return max(delta, 0.0)
        except Exception:
            return None

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def retry_count(self) -> int:
        return self._retry_count


class SecClientError(Exception):
    """SEC client error with status code and URL context."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        url: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


# ── Filing discovery ──────────────────────────────────────────────────────────

@dataclass
class FilingMeta:
    accession_number: str
    form_type: str
    filing_date: str
    primary_doc: str
    accepted_ts: Optional[datetime]


def discover_filings(
    client: SecClient,
    cik: str,
    start_date: str,
    forms: Set[str],
) -> Tuple[List[FilingMeta], Set[str]]:
    """Discover all 10-K/10-Q accessions from start_date onward.

    Follows submissions-history JSON files to cover the cutoff date.
    Preserves acceptanceDateTime from EDGAR.
    Raises SecClientError if the initial submissions request fails after retries.

    Returns (filings, failed_history_urls).  ``failed_history_urls`` is the set
    of history-file URLs that failed to fetch — the caller can use this to
    mark the ticker as partial coverage.
    """
    cik_padded = cik.zfill(10)
    submissions_url = (
        f"{EDGAR_DATA_BASE}/submissions/CIK{cik_padded}.json"
    )

    filings: List[FilingMeta] = []
    failed_history_urls: Set[str] = set()

    data = client.get_json(submissions_url)

    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return filings, failed_history_urls

    forms_list = recent.get("form", [])
    dates_list = recent.get("filingDate", [])
    accessions_list = recent.get("accessionNumber", [])
    docs_list = recent.get("primaryDocument", [])
    acceptance_list = recent.get("acceptanceDateTime", [])

    _collect_filings(
        forms_list, dates_list, accessions_list, docs_list,
        acceptance_list, start_date, forms, filings,
    )

    # Follow archive history files for older filings
    files = data.get("filings", {}).get("files", [])
    for file_entry in files:
        name = file_entry.get("name", "")
        if not name:
            continue

        # History inclusion: file OVERLAPS [start_date, now]
        filing_from = file_entry.get("filingFrom", "")
        filing_to = file_entry.get("filingTo", "")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if filing_from and filing_to and filing_to < start_date:
            # Entire file is before the cutoff — skip
            continue
        if filing_from and filing_from > today:
            # Entire file is in the future — skip
            continue

        history_url = f"{EDGAR_DATA_BASE}/submissions/{name}"
        try:
            hist_data = client.get_json(history_url)
        except SecClientError as e:
            logger.warning("History file fetch failed for %s: %s", name, e)
            failed_history_urls.add(history_url)
            continue

        hist_recent = hist_data.get("filings", {}).get("recent", {})
        if not hist_recent:
            continue

        _collect_filings(
            hist_recent.get("form", []),
            hist_recent.get("filingDate", []),
            hist_recent.get("accessionNumber", []),
            hist_recent.get("primaryDocument", []),
            hist_recent.get("acceptanceDateTime", []),
            start_date, forms, filings,
        )

    return filings, failed_history_urls


def _collect_filings(
    forms_list: List[str],
    dates_list: List[str],
    accessions_list: List[str],
    docs_list: List[str],
    acceptance_list: List[Any],
    start_date: str,
    forms: Set[str],
    filings: List[FilingMeta],
) -> None:
    """Collect qualifying filings from a submissions batch.

    Iterates over the longest available array (forms/dates/accessions) rather
    than truncating to the acceptance array length.  Rows with a missing or
    unparseable acceptanceDateTime are still included with accepted_ts=None
    so they are not silently dropped.
    """
    n = max(
        len(forms_list), len(dates_list), len(accessions_list),
        len(docs_list),
    )

    for i in range(n):
        form = forms_list[i] if i < len(forms_list) else None
        filing_date = dates_list[i] if i < len(dates_list) else None
        accession = accessions_list[i] if i < len(accessions_list) else None

        if not form or not filing_date or not accession:
            continue
        if form not in forms:
            continue
        if filing_date < start_date:
            continue

        accepted_ts: Optional[datetime] = None
        if i < len(acceptance_list):
            accepted_raw = acceptance_list[i]
            if isinstance(accepted_raw, (int, float)):
                accepted_ts = datetime.fromtimestamp(
                    accepted_raw / 1000 if accepted_raw > 1e12 else accepted_raw,
                    tz=timezone.utc,
                )
            elif isinstance(accepted_raw, str):
                accepted_ts = parse_sec_timestamp(accepted_raw)

        primary_doc = docs_list[i] if i < len(docs_list) else ""

        filings.append(FilingMeta(
            accession_number=accession,
            form_type=form,
            filing_date=filing_date,
            primary_doc=primary_doc,
            accepted_ts=accepted_ts,
        ))


def fetch_filing_text(
    client: SecClient,
    cik: str,
    accession: str,
    primary_doc: str,
) -> Optional[str]:
    """Fetch filing HTML/text from EDGAR archive.

    Falls back to index.json if primary document fetch fails.
    """
    accession_clean = accession.replace("-", "")

    # Try primary document first
    if primary_doc:
        url = (
            f"{EDGAR_WWW_BASE}/Archives/edgar/data/"
            f"{int(cik)}/{accession_clean}/{primary_doc}"
        )
        try:
            text = client.get_text(url)
            if text and len(text.strip()) > 100:
                return text
        except SecClientError:
            pass

    # Fallback: fetch index and try HTML files
    index_url = (
        f"{EDGAR_DATA_BASE}/submissions/CIK{cik.zfill(10)}.json"
    )
    try:
        index_url = (
            f"{EDGAR_WWW_BASE}/Archives/edgar/data/"
            f"{int(cik)}/{accession_clean}/index.json"
        )
        data = client.get_json(index_url)
        items = data.get("directory", {}).get("item", [])
        for item in items:
            name = item.get("name", "")
            if name.endswith((".htm", ".html")):
                doc_url = (
                    f"{EDGAR_WWW_BASE}/Archives/edgar/data/"
                    f"{int(cik)}/{accession_clean}/{name}"
                )
                try:
                    text = client.get_text(doc_url)
                    if text and len(text.strip()) > 100:
                        return text
                except SecClientError:
                    continue
    except SecClientError:
        pass

    return None


# ── Filing processing ─────────────────────────────────────────────────────────

def process_filing(
    ticker: str,
    cik: str,
    company_name: str,
    filing: FilingMeta,
    raw_html: str,
    ingest_ts: datetime,
) -> List[Dict[str, Any]]:
    """Process a single filing into bronze chunk rows.

    Returns list of row dicts ready for Delta append.
    """
    plain_text = strip_html(raw_html)
    if not plain_text:
        return []

    sections = extract_sections(plain_text)
    accession_clean = filing.accession_number.replace("-", "")
    filing_url = (
        f"{EDGAR_WWW_BASE}/Archives/edgar/data/"
        f"{int(cik)}/{accession_clean}/{filing.primary_doc}"
    )

    rows: List[Dict[str, Any]] = []
    for section_name, section_text in sections:
        chunks = chunk_text(section_text)
        for chunk_idx, chunk in enumerate(chunks, start=1):
            key = record_key("rag_chunk", ticker, filing.accession_number, section_name, chunk_idx)
            rows.append({
                "record_key": key,
                "ticker": ticker,
                "cik": cik,
                "company_name": company_name,
                "form_type": filing.form_type,
                "filing_date": filing.filing_date,
                "accepted_ts": filing.accepted_ts,
                "accession_number": filing.accession_number,
                "primary_doc": filing.primary_doc,
                "filing_url": filing_url,
                "chunk_id": chunk_idx,
                "filing_section": section_name,
                "chunk_text": chunk,
                "chunk_char_count": len(chunk),
                "source": "sec_edgar",
                "ingest_ts": ingest_ts,
                "raw_payload": None,
            })

    return rows


# ── Ticker CIK cache ──────────────────────────────────────────────────────────

def load_company_tickers(
    client: SecClient,
    cache_path: Optional[str] = None,
    cache_ttl: int = DEFAULT_TICKER_CACHE_TTL,
    force_refresh: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Load SEC company_tickers.json with optional caching.

    Returns the parsed JSON payload. Uses cache sidecar for TTL.
    When dry_run=True, never writes to the persistent cache.
    """
    url = "https://www.sec.gov/files/company_tickers.json"

    if cache_path and not force_refresh:
        cached = _try_load_cache(cache_path, cache_ttl)
        if cached is not None:
            return cached

    try:
        payload = client.get_json(url)
        if cache_path and not dry_run:
            _write_cache(cache_path, payload)
        return payload
    except SecClientError as e:
        if cache_path:
            cached = _try_load_cache(cache_path, ttl=0)
            if cached is not None:
                age_str = _cache_age_str(cache_path)
                logger.warning("Using stale cache (age=%s) after fetch failure: %s", age_str, e)
                return cached
        raise


def _try_load_cache(
    cache_path: str,
    ttl: int,
) -> Optional[Dict[str, Any]]:
    """Try to load cached payload if valid.

    ttl > 0  → accept cache younger than ttl seconds
    ttl == 0 → accept cache regardless of age (stale fallback)
    """
    try:
        path = Path(cache_path)
        sidecar = Path(cache_path + ".meta")

        if not path.exists():
            return None

        if sidecar.exists() and ttl > 0:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            fetched_ts = meta.get("fetched_ts", 0)
            if time.time() - fetched_ts > ttl:
                return None

        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def _write_cache(cache_path: str, payload: Dict[str, Any]) -> None:
    """Write payload and metadata sidecar to cache."""
    try:
        path = Path(cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

        sidecar = Path(cache_path + ".meta")
        sidecar.write_text(
            json.dumps({"fetched_ts": time.time()}),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Failed to write cache: %s", e)


def _cache_age_str(cache_path: str) -> str:
    """Return human-readable age of cache sidecar, or 'unknown'."""
    try:
        sidecar = Path(cache_path + ".meta")
        if sidecar.exists():
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            fetched_ts = meta.get("fetched_ts", 0)
            age_secs = int(time.time() - fetched_ts)
            if age_secs < 0:
                return "future"
            days = age_secs // 86400
            hours = (age_secs % 86400) // 3600
            if days > 0:
                return f"{days}d{hours}h"
            return f"{hours}h{(age_secs % 3600) // 60}m"
    except Exception:
        pass
    return "unknown"


# ── Universe selection ────────────────────────────────────────────────────────

UNIVERSE_SQL = """
WITH latest AS (SELECT max(trade_date) AS d FROM {catalog}.{schema}.gold_tradable_universe),
ranked AS (
  SELECT upper(trim(symbol)) AS ticker, 1 AS phase
  FROM {catalog}.{schema}.gold_tradable_universe, latest
  WHERE trade_date = latest.d
  UNION
  SELECT upper(trim(symbol)) AS ticker, 2 AS phase
  FROM {catalog}.{schema}.gold_tradable_universe
)
SELECT ticker, min(phase) AS phase FROM ranked GROUP BY ticker ORDER BY phase, ticker
"""


# ── Ingestion orchestrator ────────────────────────────────────────────────────

@dataclass
class IngestResult:
    run_id: str
    mapped_count: int = 0
    missing_count: int = 0
    discovered_count: int = 0
    existing_count: int = 0
    planned_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    partial_count: int = 0
    skipped_existing_count: int = 0
    total_requests: int = 0
    total_retries: int = 0
    total_rows_appended: Optional[int] = 0
    dry_run: bool = False
    partial_tickers: List[str] = field(default_factory=list)


def run_ingest(
    *,
    catalog: str,
    schema: str,
    start_date: str = DEFAULT_START_DATE,
    forms_str: str = DEFAULT_FORMS,
    tickers: Optional[List[str]] = None,
    include_historical: bool = False,
    dry_run: bool = False,
    log_dry_run: bool = False,
    refresh_cik_cache: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    run_id: Optional[str] = None,
    user_agent_secret_scope: str = DEFAULT_SECRET_SCOPE,
    user_agent_secret_key: str = DEFAULT_SECRET_KEY,
    # Injected dependencies
    universe_reader: Optional[UniverseReader] = None,
    accession_reader: Optional[ExistingAccessionReader] = None,
    data_writer: Optional[DataWriter] = None,
    log_writer: Optional[IngestLogWriter] = None,
    ingest_log_reader: Optional[IngestLogReader] = None,
    cik_mapping_log_writer: Optional[CikMappingLogWriter] = None,
    http_client: Optional[HttpClient] = None,
    clock: Optional[Clock] = None,
    cache_path: Optional[str] = None,
) -> IngestResult:
    """Run the SEC RAG ingestion pipeline.

    All external dependencies are injected for offline testability.
    """
    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    forms = set(f.strip() for f in forms_str.split(","))
    invalid = forms - {"10-K", "10-Q"}
    if invalid:
        raise ValueError(f"Unsupported forms: {invalid}. Only 10-K and 10-Q are in scope.")

    result = IngestResult(run_id=run_id, dry_run=dry_run)

    # Resolve and validate user agent (env → Databricks secret)
    user_agent = _resolve_user_agent(
        secret_scope=user_agent_secret_scope,
        secret_key=user_agent_secret_key,
    )
    _validate_user_agent(user_agent)

    # Build dependencies if not injected
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

    # Load CIK mapping
    if cache_path is None:
        cache_path = os.environ.get(
            "SEC_COMPANY_TICKERS_CACHE",
            f"/Volumes/{catalog}/{schema}/sec_cache/company_tickers.json",
        )

    tickers_payload = load_company_tickers(
        client, cache_path=cache_path, force_refresh=refresh_cik_cache,
        dry_run=dry_run,
    )

    # Get universe
    if tickers:
        entries = [TickerEntry(ticker=t.upper().strip(), phase=1) for t in tickers]
    elif universe_reader is not None:
        entries = universe_reader.read_universe(catalog, schema, include_historical)
    else:
        raise ValueError("Either tickers or universe_reader must be provided")

    symbols = [e.ticker for e in entries]

    # Map tickers to CIKs
    cik_map = build_cik_map(symbols, tickers_payload)
    mapped_tickers: List[Tuple[str, str]] = []  # (ticker, cik)

    for symbol, mapping in cik_map.items():
        if mapping.status == "mapped" and mapping.cik:
            mapped_tickers.append((symbol, mapping.cik))
            result.mapped_count += 1
        elif mapping.status == "ambiguous":
            result.missing_count += 1
            logger.warning("CIK mapping: ambiguous — %s: %s", symbol, mapping.reason)
        else:
            result.missing_count += 1
            logger.warning("CIK mapping: %s — %s: %s", mapping.status, symbol, mapping.reason)

    # Write CIK mapping log
    if cik_mapping_log_writer is not None:
        for symbol, mapping in cik_map.items():
            cik_log_entry = CikMappingLogEntry(
                ticker=mapping.ticker,
                lookup_symbol=mapping.lookup_symbol,
                cik=mapping.cik,
                status=mapping.status,
                reason=mapping.reason,
                mapped_ts=mapping.mapped_ts,
                run_id=run_id,
            )
            cik_mapping_log_writer.append_mapping_log(catalog, schema, cik_log_entry)
        cik_mapping_log_writer.flush(catalog, schema)

    # Get existing accessions for anti-join (with ownership info)
    existing_accessions: Dict[str, Tuple[str, str]] = {}
    if accession_reader is not None:
        existing_accessions = accession_reader.read_existing_accessions(catalog, schema)
    result.existing_count = len(existing_accessions)

    # Discover filings — record failures per ticker, never silently succeed
    all_filings: Dict[str, List[FilingMeta]] = {}
    failed_tickers: Set[str] = set()
    for ticker, cik in mapped_tickers:
        try:
            filings, failed_hist = discover_filings(client, cik, start_date, forms)
            all_filings[ticker] = filings
            result.discovered_count += len(filings)
            if failed_hist:
                # History-file fetch failures → partial coverage
                result.partial_count += 1
                result.partial_tickers.append(ticker)
                logger.warning(
                    "Partial coverage for %s (CIK %s): %d history file(s) failed",
                    ticker, cik, len(failed_hist),
                )
                if log_writer is not None:
                    log_writer.append_log(catalog, schema, IngestLogEntry(
                        run_id=run_id,
                        ticker=ticker,
                        cik=cik,
                        accession_number="PARTIAL_COVERAGE",
                        form_type="N/A",
                        filing_date=None,
                        accepted_ts=None,
                        status="partial",
                        error_code="history_fetch_failed",
                        error_message=f"{len(failed_hist)} history file(s) failed: "
                                      f"{', '.join(sorted(failed_hist)[:3])}",
                        started_ts=datetime.now(timezone.utc),
                        completed_ts=datetime.now(timezone.utc),
                    ))
        except SecClientError as e:
            failed_tickers.add(ticker)
            result.failed_count += 1
            logger.error("Discovery failed for %s (CIK %s): %s", ticker, cik, e)
            if log_writer is not None:
                log_writer.append_log(catalog, schema, IngestLogEntry(
                    run_id=run_id,
                    ticker=ticker,
                    cik=cik,
                    accession_number="DISCOVERY_FAILED",
                    form_type="N/A",
                    filing_date=None,
                    accepted_ts=None,
                    status="failed",
                    error_code="discovery_failed",
                    error_message=str(e)[:500],
                    started_ts=datetime.now(timezone.utc),
                    completed_ts=datetime.now(timezone.utc),
                ))

    # Anti-join against existing — with conflict detection
    planned: List[Tuple[str, str, str, FilingMeta]] = []  # (ticker, cik, company_name, filing)
    for ticker, cik in mapped_tickers:
        if ticker in failed_tickers:
            continue
        for filing in all_filings.get(ticker, []):
            dashed = filing.accession_number
            if dashed in existing_accessions:
                existing_cik, existing_ticker = existing_accessions[dashed]
                if existing_cik != cik:
                    # Record the conflict in the audit log before raising
                    if log_writer is not None:
                        log_writer.append_log(catalog, schema, IngestLogEntry(
                            run_id=run_id,
                            ticker=ticker,
                            cik=cik,
                            accession_number=dashed,
                            form_type=filing.form_type,
                            filing_date=filing.filing_date,
                            accepted_ts=filing.accepted_ts,
                            status="failed",
                            error_code="ownership_conflict",
                            error_message=(
                                f"Accession ownership conflict: {dashed} already owned by "
                                f"CIK {existing_cik} (ticker={existing_ticker}), "
                                f"but current request is CIK {cik} (ticker={ticker})"
                            ),
                            started_ts=datetime.now(timezone.utc),
                            completed_ts=datetime.now(timezone.utc),
                        ))
                    raise AccessionOwnershipConflict(
                        f"Accession ownership conflict: {dashed} already owned by "
                        f"CIK {existing_cik} (ticker={existing_ticker}), "
                        f"but current request is CIK {cik} (ticker={ticker})"
                    )
                result.skipped_existing_count += 1
                continue
            planned.append((ticker, cik, ticker, filing))
            result.planned_count += 1

    if dry_run:
        # Dry run: print planned counts, don't fetch bodies
        logger.info(
            "DRY RUN: mapped=%d, missing=%d, discovered=%d, existing=%d, "
            "planned=%d, skipped=%d",
            result.mapped_count, result.missing_count,
            result.discovered_count, result.existing_count,
            result.planned_count, result.skipped_existing_count,
        )
        if log_dry_run and log_writer is not None:
            for ticker, cik, company_name, filing in planned:
                entry = IngestLogEntry(
                    run_id=run_id,
                    ticker=ticker,
                    cik=cik,
                    accession_number=filing.accession_number,
                    form_type=filing.form_type,
                    filing_date=filing.filing_date,
                    accepted_ts=filing.accepted_ts,
                    status="planned",
                    dry_run=True,
                )
                log_writer.append_log(catalog, schema, entry)
        return result

    # Resume: skip accessions that already succeeded in this run
    succeeded_keys: Set[Tuple[str, str, str]] = set()
    if ingest_log_reader is not None:
        succeeded_keys = ingest_log_reader.read_succeeded_accessions(
            catalog, schema, run_id,
        )
        if succeeded_keys:
            pre_count = len(planned)
            planned = [
                (t, c, cn, f) for t, c, cn, f in planned
                if (run_id, t, f.accession_number) not in succeeded_keys
            ]
            result.skipped_existing_count += pre_count - len(planned)
            logger.info("Resume: skipped %d already-succeeded accessions", pre_count - len(planned))

    # Process filings
    ingest_ts = datetime.now(timezone.utc)

    def _process_one(
        ticker: str, cik: str, company_name: str, filing: FilingMeta,
    ) -> Optional[IngestLogEntry]:
        """Process a single filing. Returns the log entry (already written)."""
        started_ts = datetime.now(timezone.utc)

        # Determine attempt number from previous log entries
        attempt = 1
        if ingest_log_reader is not None:
            prev_max = ingest_log_reader.read_max_attempt(
                catalog, schema, run_id, ticker, filing.accession_number,
            )
            attempt = prev_max + 1

        log_entry = IngestLogEntry(
            run_id=run_id,
            ticker=ticker,
            cik=cik,
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            accepted_ts=filing.accepted_ts,
            status="in_progress",
            started_ts=started_ts,
            attempt=attempt,
        )

        # Persist in_progress before work begins (separate object so mutations
        # to log_entry don't corrupt the stored in_progress record)
        if log_writer:
            in_progress_entry = IngestLogEntry(
                run_id=run_id, ticker=ticker, cik=cik,
                accession_number=filing.accession_number,
                form_type=filing.form_type, filing_date=filing.filing_date,
                accepted_ts=filing.accepted_ts, status="in_progress",
                started_ts=started_ts, attempt=attempt,
            )
            log_writer.append_log(catalog, schema, in_progress_entry)

        try:
            # Second anti-join (race safety) with conflict detection
            if accession_reader is not None:
                current_existing = accession_reader.read_existing_accessions(catalog, schema)
                if filing.accession_number in current_existing:
                    existing_cik, existing_ticker = current_existing[filing.accession_number]
                    if existing_cik != cik:
                        # Record as failed, then raise
                        log_entry.status = "failed"
                        log_entry.error_code = "ownership_conflict"
                        log_entry.error_message = (
                            f"Accession ownership conflict (race): {filing.accession_number} "
                            f"already owned by CIK {existing_cik} (ticker={existing_ticker}), "
                            f"but current request is CIK {cik} (ticker={ticker})"
                        )
                        log_entry.completed_ts = datetime.now(timezone.utc)
                        if log_writer:
                            log_writer.append_log(catalog, schema, log_entry)
                        raise AccessionOwnershipConflict(log_entry.error_message)
                    log_entry.status = "skipped_existing"
                    log_entry.completed_ts = datetime.now(timezone.utc)
                    if log_writer:
                        log_writer.append_log(catalog, schema, log_entry)
                    return log_entry

            # Validate accepted_ts
            if filing.accepted_ts is None:
                log_entry.status = "failed"
                log_entry.error_code = "missing_accepted_ts"
                log_entry.error_message = "Filing lacks acceptance datetime"
                log_entry.completed_ts = datetime.now(timezone.utc)
                if log_writer:
                    log_writer.append_log(catalog, schema, log_entry)
                return log_entry

            # Fetch filing body
            raw_html = fetch_filing_text(client, cik, filing.accession_number, filing.primary_doc)
            if not raw_html:
                log_entry.status = "failed"
                log_entry.error_code = "fetch_failed"
                log_entry.error_message = "Could not fetch filing text"
                log_entry.completed_ts = datetime.now(timezone.utc)
                if log_writer:
                    log_writer.append_log(catalog, schema, log_entry)
                return log_entry

            # Process into chunks
            rows = process_filing(ticker, cik, company_name, filing, raw_html, ingest_ts)
            if not rows:
                log_entry.status = "failed"
                log_entry.error_code = "no_chunks"
                log_entry.error_message = "Filing produced no chunks"
                log_entry.completed_ts = datetime.now(timezone.utc)
                if log_writer:
                    log_writer.append_log(catalog, schema, log_entry)
                return log_entry

            # Write to bronze
            if data_writer is not None:
                inserted = data_writer.append_bronze_rows(catalog, schema, rows)
            else:
                inserted = len(rows)

            log_entry.status = "succeeded"
            log_entry.rows_appended = inserted
            log_entry.completed_ts = datetime.now(timezone.utc)
            if log_writer:
                log_writer.append_log(catalog, schema, log_entry)
            return log_entry

        except AccessionOwnershipConflict:
            raise
        except Exception as e:
            log_entry.status = "failed"
            log_entry.error_code = "exception"
            log_entry.error_message = str(e)[:500]
            log_entry.completed_ts = datetime.now(timezone.utc)
            if log_writer:
                log_writer.append_log(catalog, schema, log_entry)
            logger.error("Failed to process %s/%s: %s", ticker, filing.accession_number, e)
            return log_entry

    # Execute with bounded ThreadPoolExecutor
    if max_workers > 1 and len(planned) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process_one, t, c, cn, f): (t, f)
                for t, c, cn, f in planned
            }
            for future in as_completed(futures):
                ticker, filing = futures[future]
                try:
                    entry = future.result()
                    if entry is not None:
                        if entry.status == "succeeded":
                            result.succeeded_count += 1
                            if entry.rows_appended is None:
                                result.total_rows_appended = None
                            elif result.total_rows_appended is not None:
                                result.total_rows_appended += entry.rows_appended
                        elif entry.status == "skipped_existing":
                            result.skipped_existing_count += 1
                        else:
                            result.failed_count += 1
                except AccessionOwnershipConflict:
                    result.failed_count += 1
                    raise
                except Exception as e:
                    result.failed_count += 1
                    logger.error("Worker failed for %s/%s: %s", ticker, filing.accession_number, e)
    else:
        # Serial path (max_workers=1 or single filing)
        for ticker, cik, company_name, filing in planned:
            try:
                entry = _process_one(ticker, cik, company_name, filing)
                if entry is not None:
                    if entry.status == "succeeded":
                        result.succeeded_count += 1
                        if entry.rows_appended is None:
                            result.total_rows_appended = None
                        elif result.total_rows_appended is not None:
                            result.total_rows_appended += entry.rows_appended
                    elif entry.status == "skipped_existing":
                        result.skipped_existing_count += 1
                    else:
                        result.failed_count += 1
            except AccessionOwnershipConflict:
                result.failed_count += 1
                raise

    result.total_requests = client.request_count
    result.total_retries = client.retry_count

    logger.info(
        "Ingestion complete: mapped=%d, missing=%d, discovered=%d, existing=%d, "
        "planned=%d, succeeded=%d, failed=%d, partial=%d, skipped=%d, rows=%s, "
        "requests=%d, retries=%d",
        result.mapped_count, result.missing_count, result.discovered_count,
        result.existing_count, result.planned_count, result.succeeded_count,
        result.failed_count, result.partial_count, result.skipped_existing_count,
        "unknown" if result.total_rows_appended is None else result.total_rows_appended,
        result.total_requests, result.total_retries,
    )

    return result


# ── Spark adapters (Databricks production) ───────────────────────────────────

class SparkUniverseReader:
    """Reads ticker universe from gold_tradable_universe via Spark."""

    def read_universe(
        self,
        catalog: str,
        schema: str,
        include_historical: bool = False,
    ) -> List[TickerEntry]:
        from databricks.connect import DatabricksSession
        spark = DatabricksSession.builder.serverless(True).getOrCreate()
        sql = UNIVERSE_SQL.format(catalog=catalog, schema=schema)
        rows = spark.sql(sql).collect()
        entries = [TickerEntry(ticker=row["ticker"], phase=row["phase"]) for row in rows]
        if not include_historical:
            entries = [e for e in entries if e.phase == 1]
        return entries


class SparkAccessionReader:
    """Reads existing accession numbers from bronze_sec_filings_v2 via Spark."""

    def read_existing_accessions(
        self,
        catalog: str,
        schema: str,
    ) -> Dict[str, Tuple[str, str]]:
        from databricks.connect import DatabricksSession
        spark = DatabricksSession.builder.serverless(True).getOrCreate()
        rows = (
            spark.table(f"{catalog}.{schema}.bronze_sec_filings_v2")
            .select("accession_number", "cik", "ticker")
            .distinct()
            .collect()
        )
        return {row["accession_number"]: (row["cik"], row["ticker"]) for row in rows}


class SparkDataWriter:
    """Merges bronze filing rows into Delta via MERGE (insert-only when not matched).

    Uses explicit StructType so that always-null columns like raw_payload are
    typed correctly.  Keyed on accession_number — concurrent/re-runs cannot
    duplicate rows.  Ownership conflicts (same accession, different CIK) raise
    AccessionOwnershipConflict.  Returns the actual inserted count from
    MERGE operationMetrics.

    Concurrency: uses a process-wide lock so that only one MERGE + metrics-read
    pair executes at a time on the same Delta table.  Each call creates a unique
    temp view name (uuid) to avoid Spark session conflicts under
    ``--max-workers 4``.
    """

    BRONZE_SCHEMA = None  # lazily built once (needs pyspark import)
    _merge_lock = threading.Lock()  # process-wide, one writer at a time

    def __init__(self, spark_factory=None) -> None:
        self._spark_factory = spark_factory

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()

    def _ensure_schema(self):
        if SparkDataWriter.BRONZE_SCHEMA is not None:
            return
        from pyspark.sql.types import (
            IntegerType, StringType, StructField, StructType, TimestampType,
        )
        SparkDataWriter.BRONZE_SCHEMA = StructType([
            StructField("record_key", StringType(), True),
            StructField("ticker", StringType(), True),
            StructField("cik", StringType(), True),
            StructField("company_name", StringType(), True),
            StructField("form_type", StringType(), True),
            StructField("filing_date", StringType(), True),
            StructField("accepted_ts", TimestampType(), True),
            StructField("accession_number", StringType(), True),
            StructField("primary_doc", StringType(), True),
            StructField("filing_url", StringType(), True),
            StructField("chunk_id", IntegerType(), True),
            StructField("filing_section", StringType(), True),
            StructField("chunk_text", StringType(), True),
            StructField("chunk_char_count", IntegerType(), True),
            StructField("source", StringType(), True),
            StructField("ingest_ts", TimestampType(), True),
            StructField("raw_payload", StringType(), True),
        ])

    def append_bronze_rows(
        self,
        catalog: str,
        schema: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        self._ensure_schema()
        spark = self._get_spark()
        table = f"{catalog}.{schema}.bronze_sec_filings_v2"

        # Collect distinct accession numbers and their CIKs from the batch
        batch_accessions: Dict[str, str] = {}
        for row in rows:
            acc = row["accession_number"]
            cik = row["cik"]
            if acc in batch_accessions:
                if batch_accessions[acc] != cik:
                    raise AccessionOwnershipConflict(
                        f"Conflicting CIKs for {acc} in batch: "
                        f"{batch_accessions[acc]} vs {cik}"
                    )
            else:
                batch_accessions[acc] = cik

        # Unique view name per call to avoid concurrent-view conflicts
        view_name = f"_merge_src_{uuid.uuid4().hex[:12]}"

        df = spark.createDataFrame(rows, schema=SparkDataWriter.BRONZE_SCHEMA)
        df.createOrReplaceTempView(view_name)

        try:
            # Serialize MERGE + ownership check + metrics read on the target
            with SparkDataWriter._merge_lock:
                # Check for ownership conflicts with existing data
                existing_check = spark.sql(f"""
                    SELECT accession_number, cik FROM {table}
                    WHERE accession_number IN (
                        SELECT DISTINCT accession_number FROM {view_name}
                    )
                """).collect()
                for r in existing_check:
                    acc = r["accession_number"]
                    existing_cik = r["cik"]
                    if acc in batch_accessions and existing_cik != batch_accessions[acc]:
                        raise AccessionOwnershipConflict(
                            f"Accession ownership conflict: {acc} already owned by "
                            f"CIK {existing_cik}, but batch has CIK {batch_accessions[acc]}"
                        )

                # MERGE: insert-only when not matched
                spark.sql(f"""
                    MERGE INTO {table} AS target
                    USING {view_name} AS source
                    ON target.accession_number = source.accession_number
                    WHEN NOT MATCHED THEN INSERT (
                        record_key, ticker, cik, company_name, form_type, filing_date,
                        accepted_ts, accession_number, primary_doc, filing_url,
                        chunk_id, filing_section, chunk_text, chunk_char_count,
                        source, ingest_ts, raw_payload
                    ) VALUES (
                        source.record_key, source.ticker, source.cik, source.company_name,
                        source.form_type, source.filing_date, source.accepted_ts,
                        source.accession_number, source.primary_doc, source.filing_url,
                        source.chunk_id, source.filing_section, source.chunk_text,
                        source.chunk_char_count, source.source, source.ingest_ts,
                        source.raw_payload
                    )
                """)

                # Get actual inserted count from this MERGE's own metrics,
                # read inside the lock so it cannot be attributed to another
                # worker's MERGE.
                inserted: Optional[int] = None
                try:
                    hist = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()
                    if hist:
                        metrics = hist[0]["operationMetrics"]
                        if metrics and "numTargetRowsInserted" in metrics:
                            inserted = int(metrics["numTargetRowsInserted"])
                        else:
                            logger.warning(
                                "DESCRIBE HISTORY returned no operationMetrics or "
                                "numTargetRowsInserted key; reporting inserted count as unknown"
                            )
                    else:
                        logger.warning(
                            "DESCRIBE HISTORY returned no rows; "
                            "reporting inserted count as unknown"
                        )
                except Exception:
                    logger.warning(
                        "Could not read MERGE metrics from DESCRIBE HISTORY; "
                        "reporting inserted count as unknown"
                    )

                return inserted
        finally:
            # Drop the unique temp view to avoid Spark catalog bloat
            try:
                spark.catalog.dropTempView(view_name)
            except Exception:
                pass


class SparkLogWriter:
    """Writes ingest log entries to sec_ingest_log via Spark.

    Uses an explicit StructType so that all-None columns (e.g. completed_ts,
    error_code, error_message on an ``in_progress`` row) are typed correctly
    instead of being inferred as unresolved ``NullType``.
    """

    INGEST_LOG_SCHEMA = None  # lazily built once (needs pyspark import)

    def __init__(self, spark_factory=None) -> None:
        self._spark_factory = spark_factory

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()

    def _ensure_schema(self):
        if SparkLogWriter.INGEST_LOG_SCHEMA is not None:
            return
        from pyspark.sql.types import (
            BooleanType, IntegerType, StringType, StructField,
            StructType, TimestampType,
        )
        SparkLogWriter.INGEST_LOG_SCHEMA = StructType([
            StructField("run_id", StringType(), False),
            StructField("ticker", StringType(), False),
            StructField("cik", StringType(), False),
            StructField("accession_number", StringType(), False),
            StructField("form_type", StringType(), False),
            StructField("filing_date", StringType(), True),
            StructField("accepted_ts", TimestampType(), True),
            StructField("status", StringType(), False),
            StructField("rows_appended", IntegerType(), True),
            StructField("attempt", IntegerType(), True),
            StructField("error_code", StringType(), True),
            StructField("error_message", StringType(), True),
            StructField("started_ts", TimestampType(), True),
            StructField("completed_ts", TimestampType(), True),
            StructField("dry_run", BooleanType(), True),
            StructField("logged_ts", TimestampType(), False),
        ])

    def append_log(
        self,
        catalog: str,
        schema: str,
        entry: IngestLogEntry,
    ) -> None:
        self._ensure_schema()
        spark = self._get_spark()
        row = {
            "run_id": entry.run_id,
            "ticker": entry.ticker,
            "cik": entry.cik,
            "accession_number": entry.accession_number,
            "form_type": entry.form_type,
            "filing_date": entry.filing_date,
            "accepted_ts": entry.accepted_ts,
            "status": entry.status,
            "rows_appended": entry.rows_appended,
            "attempt": entry.attempt,
            "error_code": entry.error_code,
            "error_message": entry.error_message,
            "started_ts": entry.started_ts,
            "completed_ts": entry.completed_ts,
            "dry_run": entry.dry_run,
            "logged_ts": datetime.now(timezone.utc),
        }
        df = spark.createDataFrame([row], schema=SparkLogWriter.INGEST_LOG_SCHEMA)
        df.write.mode("append").saveAsTable(f"{catalog}.{schema}.sec_ingest_log")


def ensure_ingest_log_table(spark, catalog: str, schema: str) -> None:
    """Create sec_ingest_log table if it does not exist (cold-start safety).

    The schema matches docs/DATA_SCHEMAS.md exactly.  Called once at startup
    before any reader or writer touches the table.
    """
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.sec_ingest_log (
            run_id            STRING    NOT NULL,
            ticker            STRING    NOT NULL,
            cik               STRING    NOT NULL,
            accession_number  STRING    NOT NULL,
            form_type         STRING    NOT NULL,
            filing_date       STRING,
            accepted_ts       TIMESTAMP,
            status            STRING    NOT NULL,
            rows_appended     INT,
            attempt           INT,
            error_code        STRING,
            error_message     STRING,
            started_ts        TIMESTAMP,
            completed_ts      TIMESTAMP,
            dry_run           BOOLEAN,
            logged_ts         TIMESTAMP NOT NULL
        ) USING DELTA
    """)


class SparkIngestLogReader:
    """Reads ingest log entries from sec_ingest_log for resume support.

    Pushes down predicates on run_id and ticker to minimize scanned data.
    """

    def __init__(self, spark_factory=None) -> None:
        self._spark_factory = spark_factory

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()

    def read_succeeded_accessions(
        self,
        catalog: str,
        schema: str,
        run_id: str,
    ) -> Set[Tuple[str, str, str]]:
        spark = self._get_spark()
        try:
            rows = spark.sql(f"""
                SELECT DISTINCT run_id, ticker, accession_number
                FROM {catalog}.{schema}.sec_ingest_log
                WHERE run_id = '{run_id}'
                  AND status = 'succeeded'
            """).collect()
        except Exception:
            # Table does not exist yet (cold start) — no prior attempts
            return set()
        return {(r["run_id"], r["ticker"], r["accession_number"]) for r in rows}

    def read_max_attempt(
        self,
        catalog: str,
        schema: str,
        run_id: str,
        ticker: str,
        accession_number: str,
    ) -> int:
        spark = self._get_spark()
        try:
            rows = spark.sql(f"""
                SELECT max(attempt) AS max_attempt
                FROM {catalog}.{schema}.sec_ingest_log
                WHERE run_id = '{run_id}'
                  AND ticker = '{ticker}'
                  AND accession_number = '{accession_number}'
            """).collect()
        except Exception:
            # Table does not exist yet (cold start)
            return 0
        if rows and rows[0]["max_attempt"] is not None:
            return int(rows[0]["max_attempt"])
        return 0


class SparkCikMappingLogWriter:
    """Writes CIK mapping log entries to sec_cik_mapping_log via Spark.

    Buffers entries in memory and writes once per flush() call (typically once
    per run).  Uses an explicit StructType so that cik=None rows are handled
    correctly — Spark cannot infer a nullable StringType from a None value.
    """

    CIK_MAPPING_SCHEMA = None  # lazily built once (needs pyspark import)

    def __init__(self, spark_factory=None) -> None:
        self._buffer: list = []
        self._spark_factory = spark_factory  # injectable for testing

    def _get_spark(self):
        if self._spark_factory is not None:
            return self._spark_factory()
        from databricks.connect import DatabricksSession
        return DatabricksSession.builder.serverless(True).getOrCreate()

    def append_mapping_log(
        self,
        catalog: str,
        schema: str,
        entry: CikMappingLogEntry,
    ) -> None:
        self._buffer.append({
            "ticker": entry.ticker,
            "lookup_symbol": entry.lookup_symbol,
            "cik": entry.cik,
            "status": entry.status,
            "reason": entry.reason,
            "mapped_ts": entry.mapped_ts,
            "run_id": entry.run_id,
        })

    def flush(self, catalog: str, schema: str) -> None:
        if not self._buffer:
            return
        from pyspark.sql.types import (
            StringType,
            StructField,
            StructType,
            TimestampType,
        )

        spark = self._get_spark()
        if SparkCikMappingLogWriter.CIK_MAPPING_SCHEMA is None:
            SparkCikMappingLogWriter.CIK_MAPPING_SCHEMA = StructType([
                StructField("ticker", StringType(), False),
                StructField("lookup_symbol", StringType(), True),
                StructField("cik", StringType(), True),
                StructField("status", StringType(), False),
                StructField("reason", StringType(), True),
                StructField("mapped_ts", TimestampType(), True),
                StructField("run_id", StringType(), True),
            ])

        df = spark.createDataFrame(
            self._buffer,
            schema=SparkCikMappingLogWriter.CIK_MAPPING_SCHEMA,
        )
        df.write.mode("append").saveAsTable(f"{catalog}.{schema}.sec_cik_mapping_log")
        self._buffer.clear()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point.  *argv* is parsed instead of sys.argv when given."""
    parser = argparse.ArgumentParser(description="SEC EDGAR RAG Ingestion")
    parser.add_argument("--catalog", default=os.getenv("CATALOG", "bootcamp_students"))
    parser.add_argument("--schema", default=os.getenv("SCHEMA", "evangoh_capstone"))
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--forms", default=DEFAULT_FORMS)
    parser.add_argument("--tickers", default=None, help="Comma-separated ticker override")
    parser.add_argument("--include-historical", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-dry-run", action="store_true")
    parser.add_argument("--refresh-cik-cache", action="store_true")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--user-agent-secret-scope",
        default=DEFAULT_SECRET_SCOPE,
        help="Databricks secret scope for SEC EDGAR User-Agent",
    )
    parser.add_argument(
        "--user-agent-secret-key",
        default=DEFAULT_SECRET_KEY,
        help="Databricks secret key for SEC EDGAR User-Agent",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    tickers = None
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]

    # Wire real Spark adapters for production use
    universe_reader = SparkUniverseReader()
    accession_reader = SparkAccessionReader()
    data_writer = SparkDataWriter()
    log_writer = SparkLogWriter()
    ingest_log_reader = SparkIngestLogReader()
    cik_mapping_log_writer = SparkCikMappingLogWriter()

    # Ensure sec_ingest_log exists before any reader/writer touches it
    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless(True).getOrCreate()
    ensure_ingest_log_table(spark, args.catalog, args.schema)

    result = run_ingest(
        catalog=args.catalog,
        schema=args.schema,
        start_date=args.start_date,
        forms_str=args.forms,
        tickers=tickers,
        include_historical=args.include_historical,
        dry_run=args.dry_run,
        log_dry_run=args.log_dry_run,
        refresh_cik_cache=args.refresh_cik_cache,
        max_workers=args.max_workers,
        run_id=args.run_id,
        user_agent_secret_scope=args.user_agent_secret_scope,
        user_agent_secret_key=args.user_agent_secret_key,
        universe_reader=universe_reader,
        accession_reader=accession_reader,
        data_writer=data_writer,
        log_writer=log_writer,
        ingest_log_reader=ingest_log_reader,
        cik_mapping_log_writer=cik_mapping_log_writer,
    )

    if result.failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()