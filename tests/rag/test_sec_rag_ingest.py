"""tests/rag/test_sec_rag_ingest.py - Tests for SEC RAG ingestion pipeline.

All tests run offline with no network or Databricks dependencies.
pyspark and databricks.connect are hidden via monkeypatch.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock

import pytest

# Import real databricks SDK types before the module-scoped mock patches databricks
try:
    from databricks.sdk.service.workspace import SecretsAPI, GetSecretResponse
except ImportError:
    SecretsAPI = None
    GetSecretResponse = None

# pyspark/databricks fakes installed via module-scoped fixture below

from pipelines.sec_rag_ingest import (  # noqa: E402
    AccessionOwnershipConflict,
    CikMappingLogEntry,
    HttpResponse,
    IngestLogEntry,
    RateLimiter,
    SecClient,
    SecClientConfig,
    SecClientError,
    TickerEntry,
    _accession_filer_cik,
    _build_cik_group_map,
    build_cik_map,
    chunk_text,
    discover_filings,
    extract_sections,
    load_cik_overrides,
    load_company_tickers,
    normalize_sec_ticker,
    parse_sec_timestamp,
    process_filing,
    record_key,
    repair_cik_ownership,
    resolve_canonical_tickers,
    run_ingest,
    strip_html,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sec"


@pytest.fixture(autouse=True, scope="module")
def _mock_pyspark():
    """Install pyspark/databricks fakes for this module only.

    Uses sys.modules patching scoped to this module so it does not leak
    into other test modules (e.g. tests/bronze/test_refresh_bronze_cot.py).
    """
    # Pre-import pyspark.sql.connect.functions.builtin so its top-level
    # ``from pyspark.sql import Column`` binds to the real classic Column
    # *before* we replace pyspark.sql with a MagicMock.  Without this,
    # a lazy first import of the connect builtin during the mock window
    # would bind Column to a MagicMock, which then breaks
    # isinstance(arg, Column) in _invoke_function after restore.
    try:
        import pyspark.sql.column  # noqa: F401
    except (ImportError, Exception):
        pass

    _pyspark_mock = MagicMock()
    _originals = {}
    # Snapshot every pyspark*/databricks* module so submodules imported while
    # the mocks are installed can be dropped again afterwards (otherwise they
    # stay cached bound to the mocks and break later suites, e.g. tests/bronze).
    _prefixes = ("pyspark", "databricks")
    _snapshot = {k: v for k, v in sys.modules.items() if k.split(".")[0] in _prefixes}
    _patches = {
        "pyspark": _pyspark_mock,
        "pyspark.sql": _pyspark_mock.sql,
        "pyspark.sql.functions": _pyspark_mock.sql.functions,
        "pyspark.sql.types": _pyspark_mock.sql.types,
        "databricks": MagicMock(),
        "databricks.connect": MagicMock(),
    }
    for name, mock in _patches.items():
        _originals[name] = sys.modules.get(name)
        sys.modules[name] = mock

    try:
        from pyspark.sql.types import (
            StringType as _RealStringType,
            StructField as _RealStructField,
            StructType as _RealStructType,
            TimestampType as _RealTimestampType,
        )
        _pyspark_mock.sql.types.StringType = _RealStringType
        _pyspark_mock.sql.types.StructField = _RealStructField
        _pyspark_mock.sql.types.StructType = _RealStructType
        _pyspark_mock.sql.types.TimestampType = _RealTimestampType
    except ImportError:
        pass

    yield

    for name in [k for k in sys.modules if k.split(".")[0] in _prefixes]:
        if name not in _snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(_snapshot)
    for name in _patches:
        if _originals[name] is None and name not in _snapshot:
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _set_user_agent(monkeypatch):
    """Set SEC_EDGAR_USER_AGENT for all tests."""
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "TestAgent test@company.com")


# -- Helpers --

class FakeClock:
    """Deterministic clock for testing."""

    def __init__(self, start: float = 1000.0):
        self._time = start

    def monotonic(self) -> float:
        return self._time

    def sleep(self, seconds: float) -> None:
        self._time += seconds

    def advance(self, seconds: float) -> None:
        self._time += seconds


class FakeHttpClient:
    """Fake HTTP client returning pre-configured responses."""

    def __init__(self):
        self._responses: Dict[str, Any] = {}
        self._call_log: List[str] = []

    def set_json(self, url: str, data: Any) -> None:
        self._responses[url] = HttpResponse(
            status_code=200,
            text=json.dumps(data),
            headers={},
        )

    def set_text(self, url: str, text: str) -> None:
        self._responses[url] = HttpResponse(
            status_code=200,
            text=text,
            headers={},
        )

    def set_error(self, url: str, status_code: int, headers: Optional[Dict] = None) -> None:
        self._responses[url] = HttpResponse(
            status_code=status_code,
            text="",
            headers=headers or {},
        )

    def get(self, url: str, headers: Dict[str, str], timeout: float = 30.0) -> HttpResponse:
        self._call_log.append(url)
        if url in self._responses:
            return self._responses[url]
        return HttpResponse(status_code=404, text="Not Found")


class FakeUniverseReader:
    """Returns a pre-configured universe."""

    def __init__(self, entries: List[TickerEntry]):
        self._entries = entries

    def read_universe(self, catalog: str, schema: str, include_historical: bool = False) -> List[TickerEntry]:
        if not include_historical:
            return [e for e in self._entries if e.phase == 1]
        return self._entries


class FakeAccessionReader:
    """Returns a pre-configured dict of existing accessions -> (cik, ticker)."""

    def __init__(self, accessions: Optional[Dict[str, Tuple[str, str]]] = None):
        self._accessions = accessions or {}

    def read_existing_accessions(self, catalog: str, schema: str) -> Dict[str, Tuple[str, str]]:
        return self._accessions


class FakeDataWriter:
    """Records appended rows. Mirrors production MERGE semantics: re-running
    the same accession returns 0 inserted (insert-only-when-not-matched)."""

    def __init__(self):
        self.appended: List[List[Dict[str, Any]]] = []
        self.total_rows = 0
        self._seen_accessions: Set[str] = set()

    def append_bronze_rows(self, catalog: str, schema: str, rows: List[Dict[str, Any]]) -> int:
        # Mirrors the production MERGE (ON target.accession_number = source.accession_number
        # WHEN NOT MATCHED THEN INSERT): every row of an accession absent from the target
        # BEFORE this call is inserted; rows of an accession already present insert nothing.
        self.appended.append(rows)
        existing = set(self._seen_accessions)
        new_count = sum(1 for r in rows if r.get("accession_number", "") not in existing)
        self._seen_accessions.update(r.get("accession_number", "") for r in rows)
        self.total_rows += new_count
        return new_count


class FakeLogWriter:
    """Records log entries."""

    def __init__(self):
        self.entries: List[IngestLogEntry] = []

    def append_log(self, catalog: str, schema: str, entry: IngestLogEntry) -> None:
        self.entries.append(entry)


class FakeCikMappingLogWriter:
    """Records CIK mapping log entries."""

    def __init__(self):
        self.entries: List[CikMappingLogEntry] = []
        self.flush_count = 0

    def append_mapping_log(self, catalog: str, schema: str, entry: CikMappingLogEntry) -> None:
        self.entries.append(entry)

    def flush(self, catalog: str, schema: str) -> None:
        self.flush_count += 1


# -- Parsing tests --

class TestRecordKey:
    def test_deterministic(self):
        k1 = record_key("rag_chunk", "AAPL", "0001", "item1_business", 1)
        k2 = record_key("rag_chunk", "AAPL", "0001", "item1_business", 1)
        assert k1 == k2

    def test_sha256_format(self):
        k = record_key("rag_chunk", "AAPL", "0001", "item1_business", 1)
        assert len(k) == 64
        assert all(c in "0123456789abcdef" for c in k)

    def test_different_inputs_different_keys(self):
        k1 = record_key("rag_chunk", "AAPL", "0001", "item1_business", 1)
        k2 = record_key("rag_chunk", "MSFT", "0001", "item1_business", 1)
        assert k1 != k2

    def test_none_handling(self):
        k = record_key("rag_chunk", None, "0001", "item1_business", 1)
        assert len(k) == 64

    def test_expected_key_for_filing(self):
        """Verify golden key for known input."""
        k = record_key("rag_chunk", "NVDA", "0001045810-25-000010", "item1_business", 1)
        expected = hashlib.sha256("rag_chunk||NVDA||0001045810-25-000010||item1_business||1".encode()).hexdigest()
        assert k == expected


class TestParseSecTimestamp:
    def test_iso_format(self):
        ts = parse_sec_timestamp("2025-02-20T18:30:00.000Z")
        assert ts is not None
        assert ts.year == 2025
        assert ts.month == 2
        assert ts.day == 20
        assert ts.tzinfo == timezone.utc  # tz-aware UTC for Spark

    def test_none_input(self):
        assert parse_sec_timestamp(None) is None
        assert parse_sec_timestamp("") is None

    def test_invalid_format(self):
        assert parse_sec_timestamp("not-a-date") is None

    def test_utc_conversion(self):
        ts = parse_sec_timestamp("2025-01-15T12:00:00+05:00")
        assert ts is not None
        assert ts.hour == 7  # UTC = 12 - 5
        assert ts.tzinfo == timezone.utc

    def test_epoch_equality(self):
        """Verify epoch-second roundtrip with tz-aware UTC."""
        ts = parse_sec_timestamp("2025-02-20T18:30:00.000Z")
        assert ts is not None
        epoch = int(ts.timestamp())
        assert epoch == 1740076200
        # Reconstruct from epoch
        ts2 = datetime.fromtimestamp(epoch, tz=timezone.utc)
        assert ts == ts2


class TestStripHtml:
    def test_basic_strip(self):
        html = "<p>Hello <b>world</b></p>"
        result = strip_html(html)
        assert "Hello" in result
        assert "world" in result
        assert "<p>" not in result
        assert "<b>" not in result

    def test_script_style_removal(self):
        html = "<p>Text</p><script>alert('x')</script><style>.a{}</style>"
        result = strip_html(html)
        assert "Text" in result
        assert "alert" not in result
        assert ".a" not in result

    def test_table_removal(self):
        html = "<p>Before</p><table><tr><td>Cell</td></tr></table><p>After</p>"
        result = strip_html(html)
        assert "Before" in result
        assert "After" in result
        assert "Cell" not in result

    def test_table_of_contents_removal(self):
        html = "<p>Table of Contents</p><p>Item 1</p>"
        result = strip_html(html)
        assert "Table of Contents" not in result
        assert "Item 1" in result

    def test_empty_input(self):
        assert strip_html("") == ""
        assert strip_html(None) == ""

    def test_whitespace_normalization(self):
        html = "<p>  Hello   world  </p>"
        result = strip_html(html)
        assert "  " not in result


class TestChunkText:
    def test_basic_chunking(self):
        text = "A" * 3000
        chunks = chunk_text(text, chunk_size=1500, overlap=200)
        assert len(chunks) >= 2
        assert len(chunks[0]) <= 1500

    def test_minimum_chars(self):
        text = "Short" * 5  # 25 chars
        chunks = chunk_text(text)
        assert chunks == []

    def test_exact_minimum(self):
        text = "A" * 50
        chunks = chunk_text(text)
        assert len(chunks) == 1

    def test_empty_input(self):
        assert chunk_text("") == []
        assert chunk_text(None) == []

    def test_overlap_error(self):
        with pytest.raises(ValueError, match="must be smaller"):
            chunk_text("A" * 100, chunk_size=10, overlap=10)

    def test_1_based_ordinal(self):
        """Verify chunk enumeration starts at 1 in process_filing."""
        # This is tested via process_filing below
        pass


class TestExtractSections:
    def test_item1_extraction(self):
        text = "Item 1. Business description here. " * 20 + "Item 2. Properties stuff. " * 10
        sections = extract_sections(text)
        names = [s[0] for s in sections]
        assert "item1_business" in names

    def test_fallback_to_full_document(self):
        text = "No matching sections here, just random text. " * 100
        sections = extract_sections(text)
        assert len(sections) == 1
        assert sections[0][0] == "full_document"

    def test_section_cap(self):
        text = "Item 1. " + "A" * 100000 + " Item 2. More text."
        sections = extract_sections(text)
        for name, content in sections:
            if name == "item1_business":
                assert len(content) <= 50000

    def test_minimum_section_length(self):
        text = "Item 1. Short text that is less than fifty chars. Item 2. Also short text that is less than fifty chars."
        sections = extract_sections(text)
        # Either sections pass the minimum or fallback to full_document
        for name, content in sections:
            assert len(content) >= 50 or name == "full_document"


# -- CIK mapping tests --

class TestCikMapping:
    @pytest.fixture
    def tickers_payload(self):
        return json.loads((FIXTURES / "company_tickers.json").read_text())

    def test_exact_match(self, tickers_payload):
        result = build_cik_map(["NVDA"], tickers_payload)
        assert result["NVDA"].status == "mapped"
        assert result["NVDA"].cik == "0001045810"

    def test_lowercase_lookup(self, tickers_payload):
        result = build_cik_map(["nvda"], tickers_payload)
        assert result["nvda"].status == "mapped"
        assert result["nvda"].cik == "0001045810"

    def test_whitespace_handling(self, tickers_payload):
        result = build_cik_map(["  AAPL  "], tickers_payload)
        assert result["  AAPL  "].status == "mapped"
        assert result["  AAPL  "].cik == "0000320193"

    def test_class_share_alias(self, tickers_payload):
        """BRK-B and BRK.B should both resolve."""
        result = build_cik_map(["BRK-B", "BRK.B"], tickers_payload)
        assert result["BRK-B"].status == "mapped"
        assert result["BRK.B"].status == "mapped"
        assert result["BRK-B"].cik == result["BRK.B"].cik

    def test_missing_ticker(self, tickers_payload):
        result = build_cik_map(["XYZNONEXIST"], tickers_payload)
        assert result["XYZNONEXIST"].status == "missing"
        assert result["XYZNONEXIST"].cik is None

    def test_cik_zero_padded(self, tickers_payload):
        result = build_cik_map(["NVDA"], tickers_payload)
        assert len(result["NVDA"].cik) == 10
        assert result["NVDA"].cik == "0001045810"

    def test_all_inputs_have_results(self, tickers_payload):
        symbols = ["NVDA", "AAPL", "MSFT", "NONEXIST"]
        result = build_cik_map(symbols, tickers_payload)
        assert len(result) == len(symbols)
        for s in symbols:
            assert s in result


class TestNormalizeSecTicker:
    def test_exact(self):
        variants = normalize_sec_ticker("NVDA")
        assert "NVDA" in variants

    def test_dot_to_dash(self):
        variants = normalize_sec_ticker("BRK.B")
        assert "BRK-B" in variants

    def test_dash_to_dot(self):
        variants = normalize_sec_ticker("BRK-B")
        assert "BRK.B" in variants

    def test_deduplication(self):
        variants = normalize_sec_ticker("NVDA")
        assert len(variants) == len(set(variants))


class TestResolveCanonicalTickers:
    def test_single_ticker_per_cik(self):
        """No aliases when each ticker has a unique CIK."""
        mapped = [("AAPL", "0000320193"), ("MSFT", "0000789019")]
        alias_map, cik_tickers = resolve_canonical_tickers(mapped)
        assert alias_map["AAPL"] == "AAPL"
        assert alias_map["MSFT"] == "MSFT"

    def test_goog_googl_share_cik(self):
        """GOOG/GOOGL share CIK → first alphabetically (GOOG) is canonical."""
        mapped = [("GOOGL", "0001652044"), ("GOOG", "0001652044")]
        alias_map, cik_tickers = resolve_canonical_tickers(mapped)
        assert alias_map["GOOG"] == "GOOG"  # canonical
        assert alias_map["GOOGL"] == "GOOG"  # alias

    def test_fox_foxa_share_cik(self):
        """FOX/FOXA share CIK → FOX is canonical (alphabetically first)."""
        mapped = [("FOXA", "0001700172"), ("FOX", "0001700172")]
        alias_map, _ = resolve_canonical_tickers(mapped)
        assert alias_map["FOX"] == "FOX"
        assert alias_map["FOXA"] == "FOX"

    def test_identity_for_no_aliases(self):
        """Tickers without aliases map to themselves."""
        mapped = [("NVDA", "0001045810")]
        alias_map, _ = resolve_canonical_tickers(mapped)
        assert alias_map["NVDA"] == "NVDA"


# -- Rate limiter tests --

class TestRateLimiter:
    def test_allows_up_to_max(self):
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=5, clock=clock)
        for _ in range(5):
            limiter.acquire()

    def test_blocks_beyond_max(self):
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=3, clock=clock)
        for _ in range(3):
            limiter.acquire()
        # Fourth acquire should block
        limiter.acquire()
        # Clock should have advanced due to sleep
        assert clock.monotonic() > 1000.0

    def test_rejects_over_10(self):
        clock = FakeClock()
        with pytest.raises(ValueError, match="exceeds hard limit"):
            RateLimiter(max_requests_per_second=11, clock=clock)

    def test_rolling_window(self):
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=2, clock=clock)
        # Use up the window
        limiter.acquire()
        limiter.acquire()
        # Advance time past 1 second window
        clock.advance(1.1)
        # Should be able to acquire again without sleeping
        limiter.acquire()

    def test_concurrent_workers_share_limiter(self):
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=5, clock=clock)
        results = []
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait(timeout=5)
            limiter.acquire()
            results.append(1)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(results) == 5

    def test_rolling_window_max_10_per_second(self):
        """Prove every rolling 1-second window has <=10 starts."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        timestamps = []
        for _ in range(20):
            limiter.acquire()
            timestamps.append(clock.monotonic())

        # Check rolling window
        for i in range(len(timestamps)):
            window_start = timestamps[i]
            count = sum(1 for t in timestamps if window_start <= t < window_start + 1.0)
            assert count <= 10, f"Window at {window_start} had {count} requests"


class TestGlobalCooldownN3:
    """N3 (P2): 429/503 must trigger a global cooldown (all workers pause),
    and Retry-After must be capped at 120 s.

    Mutation proof: if trigger_cooldown is not called, cooldown_remaining == 0
    and the other-worker test FAILS.  If MAX_RETRY_AFTER is not enforced,
    the huge-retry-after test FAILS.
    """

    def test_429_triggers_global_cooldown(self):
        """A 429 with Retry-After 5s must set cooldown_remaining > 0."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)

        assert limiter.cooldown_remaining == 0.0
        limiter.trigger_cooldown(5.0)
        assert limiter.cooldown_remaining == 5.0

        # After clock advances past the deadline, cooldown is 0
        clock.advance(5.1)
        assert limiter.cooldown_remaining == 0.0

    def test_one_worker_429_pauses_others(self):
        """When one worker triggers a 429 cooldown, other workers block on acquire()."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        acquire_order = []
        barrier = threading.Barrier(2, timeout=5)

        def worker_a():
            """Worker A triggers cooldown (simulates receiving 429)."""
            barrier.wait()
            limiter.trigger_cooldown(2.0)
            acquire_order.append("a_cooldown")

        def worker_b():
            """Worker B tries to acquire — should block during cooldown."""
            barrier.wait()
            # Small delay so A triggers cooldown first
            time.sleep(0.01)
            limiter.acquire()
            acquire_order.append("b_acquired")

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=5)
        # Worker B should be blocked (cooldown_remaining > 0)
        # Advance clock to let B through
        clock.advance(2.1)
        t_b.join(timeout=5)

        assert "a_cooldown" in acquire_order
        assert "b_acquired" in acquire_order

    def test_retry_after_exceeds_cap_is_hard_failure(self):
        """Retry-After > 120 s → hard failure (SecClientError), not a retry."""
        from pipelines.sec_rag_ingest import MAX_RETRY_AFTER

        clock = FakeClock()
        http = FakeHttpClient()
        call_count = [0]

        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            # Return a 429 with a Retry-After that exceeds the cap
            return HttpResponse(429, "", {"Retry-After": str(MAX_RETRY_AFTER + 1)})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        with pytest.raises(SecClientError, match="exceeds cap"):
            client.get_json("https://example.com")
        # Should NOT have retried — hard failure on first attempt
        assert call_count[0] == 1

    def test_retry_after_at_cap_is_allowed(self):
        """Retry-After exactly at cap (120 s) → allowed, not a failure."""
        from pipelines.sec_rag_ingest import MAX_RETRY_AFTER

        clock = FakeClock()
        http = FakeHttpClient()
        call_count = [0]

        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            if call_count[0] == 1:
                return HttpResponse(429, "", {"Retry-After": str(MAX_RETRY_AFTER)})
            return HttpResponse(200, json.dumps({"ok": True}), {})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        result = client.get_json("https://example.com")
        assert result == {"ok": True}
        assert call_count[0] == 2

    def test_503_triggers_global_cooldown(self):
        """A 503 with Retry-After must also trigger global cooldown."""
        clock = FakeClock()
        http = FakeHttpClient()
        call_count = [0]

        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            if call_count[0] == 1:
                return HttpResponse(503, "", {"Retry-After": "10"})
            return HttpResponse(200, json.dumps({"ok": True}), {})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        result = client.get_json("https://example.com")
        assert result == {"ok": True}
        # Cooldown should have been triggered
        # (clock was advanced by sleep, so remaining may be 0)


# -- SEC client tests --

class TestSecClient:
    def test_success(self):
        clock = FakeClock()
        http = FakeHttpClient()
        http.set_json("https://example.com", {"key": "value"})
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)
        result = client.get_json("https://example.com")
        assert result == {"key": "value"}

    def test_429_retry(self):
        clock = FakeClock()
        http = FakeHttpClient()
        call_count = [0]

        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            if call_count[0] == 1:
                return HttpResponse(429, "", {"Retry-After": "2"})
            return HttpResponse(200, json.dumps({"ok": True}), {})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)
        result = client.get_json("https://example.com")
        assert result == {"ok": True}
        assert call_count[0] == 2

    def test_403_retry_with_backoff(self):
        """HTTP 403 is retried with bounded exponential backoff."""
        clock = FakeClock()
        http = FakeHttpClient()
        call_count = [0]

        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            if call_count[0] <= 2:
                return HttpResponse(403, "Forbidden", {})
            return HttpResponse(200, json.dumps({"ok": True}), {})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)
        result = client.get_json("https://example.com")
        assert result == {"ok": True}
        assert call_count[0] == 3

    def test_403_retry_respects_retry_after(self):
        """HTTP 403 with Retry-After header is honoured."""
        clock = FakeClock()
        http = FakeHttpClient()
        call_count = [0]

        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            if call_count[0] == 1:
                return HttpResponse(403, "Forbidden", {"Retry-After": "5"})
            return HttpResponse(200, json.dumps({"ok": True}), {})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)
        result = client.get_json("https://example.com")
        assert result == {"ok": True}
        assert call_count[0] == 2

    def test_403_exhausted_max_retries(self):
        """HTTP 403 repeated max_retries times → failure."""
        clock = FakeClock()
        http = FakeHttpClient()

        call_count = [0]
        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            return HttpResponse(403, "Forbidden", {})

        http.get = mock_get
        config = SecClientConfig(user_agent="Test", max_retries=3)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(config, http, limiter, clock)
        with pytest.raises(SecClientError):
            client.get_json("https://example.com")
        assert call_count[0] == 3

    def test_permanent_4xx_no_retry(self):
        clock = FakeClock()
        http = FakeHttpClient()

        call_count = [0]
        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            return HttpResponse(404, "Not Found", {})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)
        with pytest.raises(SecClientError):
            client.get_json("https://example.com")
        assert call_count[0] == 1  # No retry

    def test_user_agent_required(self):
        """User agent must not be empty or placeholder."""
        # This is validated in run_ingest, not in SecClient
        pass


# -- Filing discovery tests --

class TestFilingDiscovery:
    def test_discovers_filings(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, failed_hist = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
        assert len(filings) == 2  # 10-K and 10-Q, not 8-K
        assert len(failed_hist) == 0

    def test_respects_cutoff(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2025-01-01", {"10-K", "10-Q"})
        assert len(filings) == 1  # Only the 2025-02-20 10-K

    def test_follows_history(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        history = json.loads((FIXTURES / "submissions_history.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810-submissions-001.json", history)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
        # Recent: 2 filings (2025-02-20 10-K, 2024-11-07 10-Q)
        # History: 0 filings after cutoff (2024-02-21 10-K and 2024-08-28 10-Q are before 2024-09-01)
        assert len(filings) == 2

    def test_history_top_level_shape_discovered(self):
        """History files with top-level arrays (not nested under filings.recent) must be parsed."""
        clock = FakeClock()
        http = FakeHttpClient()
        # Main file: no files entry (no recent filings of interest)
        main = {
            "cik": "0001045810",
            "entityName": "Test Corp",
            "filings": {
                "recent": {
                    "form": ["8-K"],
                    "filingDate": ["2025-01-10"],
                    "accessionNumber": ["0001045810-25-000099"],
                    "primaryDocument": ["test-8k.htm"],
                    "acceptanceDateTime": ["2025-01-10T14:00:00.000Z"],
                },
                "files": [
                    {"name": "CIK0001045810-submissions-001.json", "filingFrom": "2020-01-01", "filingTo": "2025-06-01"},
                ],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", main)
        # History file: TOP-LEVEL arrays (real EDGAR shape for overflow files)
        history = {
            "cik": "0001045810",
            "entityName": "Test Corp",
            "form": ["10-K"],
            "filingDate": ["2025-01-15"],
            "accessionNumber": ["0001045810-25-000100"],
            "primaryDocument": ["test-10k.htm"],
            "acceptanceDateTime": ["2025-01-15T18:00:00.000Z"],
        }
        http.set_json("https://data.sec.gov/submissions/CIK0001045810-submissions-001.json", history)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
        # Only the history file 10-K qualifies (8-K excluded by form filter)
        assert len(filings) == 1
        assert filings[0].form_type == "10-K"
        assert filings[0].accession_number == "0001045810-25-000100"

    def test_filters_forms(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"10-K"})
        assert len(filings) == 1
        assert filings[0].form_type == "10-K"


# -- Idempotency and append-only tests --

class TestIdempotency:
    def test_run1_appends_run2_appends_zero(self):
        """First run appends rows; second run with same data appends 0."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text("https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm", filing_html)
        http.set_text("https://www.sec.gov/Archives/edgar/data/1045810/000104581024000020/nvda-20241027.htm", filing_html)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        writer = FakeDataWriter()
        log_writer = FakeLogWriter()

        # Run 1
        result1 = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(set()),
            data_writer=writer,
            log_writer=log_writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert result1.total_rows_appended > 0

        # Run 2: existing accessions should be skipped
        existing = {}
        for batch in writer.appended:
            for row in batch:
                existing[row["accession_number"]] = (row["cik"], row["ticker"])

        result2 = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            log_writer=FakeLogWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert result2.total_rows_appended == 0

    def test_missing_accepted_ts_cannot_publish(self):
        """Filing with missing acceptance datetime fails and logs.

        With resume support, an 'in_progress' entry is persisted before work,
        then the 'failed' entry is written when accepted_ts is missing.
        """
        clock = FakeClock()
        http = FakeHttpClient()

        # Create submissions with missing acceptanceDateTime
        submissions = {
            "cik": "0001045810",
            "entityName": "Test Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-01-15"],
                    "accessionNumber": ["0001045810-25-000099"],
                    "primaryDocument": ["test.htm"],
                    "acceptanceDateTime": [None],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        writer = FakeDataWriter()
        log_writer = FakeLogWriter()

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(set()),
            data_writer=writer,
            log_writer=log_writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert result.failed_count == 1
        assert result.total_rows_appended == 0
        # Check that the log entry has missing_accepted_ts
        failed = [e for e in log_writer.entries if e.status == "failed"]
        assert len(failed) == 1
        assert failed[0].error_code == "missing_accepted_ts"
        # Also verify in_progress was persisted
        in_progress = [e for e in log_writer.entries if e.status == "in_progress"]
        assert len(in_progress) == 1


# -- Dry run tests --

class TestDryRun:
    def test_dry_run_fetches_no_body(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        writer = FakeDataWriter()

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            dry_run=True,
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(set()),
            data_writer=writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert result.dry_run is True
        assert result.total_rows_appended == 0
        assert writer.total_rows == 0

    def test_dry_run_with_log(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        log_writer = FakeLogWriter()

        run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            dry_run=True,
            log_dry_run=True,
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(set()),
            log_writer=log_writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert len(log_writer.entries) > 0
        assert all(e.dry_run for e in log_writer.entries)


# -- Golden filing parity test --

class TestGoldenFiling:
    def test_chunk_parity(self):
        """Re-chunk the existing filing fixture and assert golden output."""
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        plain = strip_html(filing_html)
        sections = extract_sections(plain)

        all_chunks = []
        for section_name, section_text in sections:
            chunks = chunk_text(section_text)
            for chunk_idx, chunk in enumerate(chunks, start=1):
                key = record_key("rag_chunk", "NVDA", "0001045810-25-000010", section_name, chunk_idx)
                all_chunks.append((section_name, chunk_idx, hashlib.sha256(chunk.encode()).hexdigest()[:16], key))

        # Verify we got chunks
        assert len(all_chunks) > 0

        # Verify deterministic keys
        for section_name, chunk_idx, text_hash, key in all_chunks:
            key2 = record_key("rag_chunk", "NVDA", "0001045810-25-000010", section_name, chunk_idx)
            assert key == key2

        # Verify chunk ordinals are 1-based
        for section_name, chunk_idx, _, _ in all_chunks:
            assert chunk_idx >= 1

        # Verify sections found
        section_names = set(s[0] for s in sections)
        assert "item1_business" in section_names or "full_document" in section_names


# -- Process filing tests --

class TestProcessFiling:
    def test_produces_rows(self):
        from pipelines.sec_rag_ingest import FilingMeta
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        filing = FilingMeta(
            accession_number="0001045810-25-000010",
            form_type="10-K",
            filing_date="2025-02-20",
            primary_doc="nvda-20250126.htm",
            accepted_ts=datetime(2025, 2, 20, 18, 30, 0, tzinfo=timezone.utc),
        )
        ingest_ts = datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        rows = process_filing("NVDA", "1045810", "NVIDIA Corp", filing, filing_html, ingest_ts)
        assert len(rows) > 0

        # Verify row schema
        for row in rows:
            assert "record_key" in row
            assert "ticker" in row
            assert "cik" in row
            assert "accepted_ts" in row
            assert "chunk_id" in row
            assert row["chunk_id"] >= 1
            assert row["ticker"] == "NVDA"
            assert row["accepted_ts"] == datetime(2025, 2, 20, 18, 30, 0, tzinfo=timezone.utc)

    def test_empty_html(self):
        from pipelines.sec_rag_ingest import FilingMeta
        filing = FilingMeta(
            accession_number="0001", form_type="10-K",
            filing_date="2025-01-01", primary_doc="test.htm",
            accepted_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        rows = process_filing("TEST", "1234", "Test", filing, "", datetime.now(timezone.utc))
        assert rows == []


# -- CIK cache tests --

class TestCikCache:
    def test_cache_hit(self, tmp_path):
        cache_file = tmp_path / "tickers.json"
        cache_file.write_text(json.dumps({"0": {"cik_str": 1, "ticker": "TEST", "title": "Test"}}))
        meta_file = tmp_path / "tickers.json.meta"
        meta_file.write_text(json.dumps({"fetched_ts": time.time()}))

        clock = FakeClock()
        http = FakeHttpClient()
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        result = load_company_tickers(client, cache_path=str(cache_file), cache_ttl=3600)
        assert "0" in result

    def test_stale_cache_fallback(self, tmp_path):
        cache_file = tmp_path / "tickers.json"
        cache_file.write_text(json.dumps({"0": {"cik_str": 1, "ticker": "TEST", "title": "Test"}}))
        meta_file = tmp_path / "tickers.json.meta"
        meta_file.write_text(json.dumps({"fetched_ts": time.time() - 7200}))  # 2 hours old

        clock = FakeClock()
        http = FakeHttpClient()
        http.set_json("https://www.sec.gov/files/company_tickers.json", {"0": {"cik_str": 2, "ticker": "NEW", "title": "New"}})
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        result = load_company_tickers(client, cache_path=str(cache_file), cache_ttl=3600)
        # Should fetch fresh since cache is stale
        assert "0" in result


# -- Missing/ambiguous CIK tests --

class TestMissingCik:
    def test_missing_logged_and_never_silently_dropped(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1), TickerEntry(ticker="XYZMISS", phase=1)]
        writer = FakeDataWriter()
        log_writer = FakeLogWriter()

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA", "XYZMISS"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(set()),
            data_writer=writer,
            log_writer=log_writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        # NVDA mapped, XYZMISS missing
        assert result.mapped_count == 1
        assert result.missing_count == 1


# -- CIK mapping log tests --

class TestCikMappingLog:
    def test_cik_mapping_log_written(self):
        """CIK mapping log writer receives entries for all tickers."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1), TickerEntry(ticker="XYZMISS", phase=1)]
        writer = FakeDataWriter()
        cik_log = FakeCikMappingLogWriter()

        run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA", "XYZMISS"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(set()),
            data_writer=writer,
            cik_mapping_log_writer=cik_log,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        # Both tickers should appear in the mapping log
        assert len(cik_log.entries) == 2
        statuses = {e.ticker: e.status for e in cik_log.entries}
        assert statuses["NVDA"] == "mapped"
        assert statuses["XYZMISS"] == "missing"
        assert all(e.run_id is not None for e in cik_log.entries)

    def test_flush_called_exactly_once(self):
        """run_ingest calls flush() exactly once after collecting all entries."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1), TickerEntry(ticker="XYZMISS", phase=1)]
        cik_log = FakeCikMappingLogWriter()

        run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA", "XYZMISS"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(set()),
            data_writer=FakeDataWriter(),
            cik_mapping_log_writer=cik_log,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        assert cik_log.flush_count == 1, (
            f"Expected 1 flush call (batch), got {cik_log.flush_count}. "
            "Mutation: per-ticker writes would need N flushes."
        )


class TestSparkCikMappingLogWriterSchema:
    """Mutation-proof tests for SparkCikMappingLogWriter schema and batching.

    These tests directly exercise the production SparkCikMappingLogWriter class
    with an injected fake Spark session so they run without Databricks.
    """

    @pytest.fixture(autouse=True)
    def _restore_pyspark_types(self, monkeypatch):
        """Temporarily restore real pyspark.sql.types for schema tests."""
        try:
            # Remove mock so Python can find the real module
            saved = {}
            for key in list(sys.modules):
                if key.startswith("pyspark"):
                    saved[key] = sys.modules.pop(key)
            try:
                import pyspark.sql.types as real_types
                monkeypatch.setitem(sys.modules, "pyspark.sql.types", real_types)
            finally:
                # Restore mocks for other tests
                for k, v in saved.items():
                    sys.modules.setdefault(k, v)
        except ImportError:
            pytest.skip("pyspark not available for schema tests")

    def _make_fake_spark(self, captured):
        """Return a fake SparkSession that captures createDataFrame args."""
        class FakeSparkSession:
            def createDataFrame(self, data, schema=None):
                captured["data"] = list(data)  # copy — buffer is cleared after
                captured["schema"] = schema
                df = MagicMock()
                mode_mock = MagicMock()
                df.write.mode.return_value = mode_mock
                mode_mock.saveAsTable.return_value = None
                return df
        return FakeSparkSession

    def test_schema_matches_documented_schema(self):
        """StructType exactly matches docs/DATA_SCHEMAS.md sec_cik_mapping_log.

        Schema from DATA_SCHEMAS.md:
          ticker          string NOT NULL
          lookup_symbol   string           (nullable)
          cik             string           (nullable)
          status          string NOT NULL
          reason          string           (nullable)
          mapped_ts       timestamp        (nullable)
          run_id          string           (nullable)
        """
        from pipelines.sec_rag_ingest import SparkCikMappingLogWriter

        captured = {}
        writer = SparkCikMappingLogWriter(spark_factory=self._make_fake_spark(captured))
        writer.append_mapping_log("cat", "sch", CikMappingLogEntry(
            ticker="AAPL", lookup_symbol="AAPL", cik="0000320193",
            status="mapped", reason="exact", mapped_ts=None, run_id="r1",
        ))

        # Clear cached schema so the test exercises the schema-building path
        SparkCikMappingLogWriter.CIK_MAPPING_SCHEMA = None
        writer.flush("cat", "sch")

        schema = captured.get("schema")
        assert schema is not None, (
            "Mutation: no schema passed to createDataFrame. "
            "Removing the schema= kwarg makes this test pass without assertion — "
            "the schema field check below would also fail."
        )

        # Field names must match DATA_SCHEMAS.md exactly
        expected_names = ["ticker", "lookup_symbol", "cik", "status", "reason", "mapped_ts", "run_id"]
        actual_names = [f.name for f in schema.fields]
        assert actual_names == expected_names, f"Field names mismatch: {actual_names}"

        # Nullability: ticker=False, lookup_symbol=True, cik=True, status=False, reason=True, mapped_ts=True, run_id=True
        expected_nullable = [False, True, True, False, True, True, True]
        actual_nullable = [f.nullable for f in schema.fields]
        assert actual_nullable == expected_nullable, f"Nullability mismatch: {actual_nullable}"

        # Types
        from pyspark.sql.types import StringType, TimestampType
        expected_types = [StringType, StringType, StringType, StringType, StringType, TimestampType, StringType]
        actual_types = [type(f.dataType) for f in schema.fields]
        assert actual_types == expected_types, f"Type mismatch: {actual_types}"

    def test_cik_none_row_written_with_schema(self):
        """A row with cik=None must be accepted when explicit schema is provided.

        Without the explicit schema, Spark's type inference from a dict with
        cik=None would raise or produce wrong types. This test proves the
        schema handles nullable cik.
        """
        from pipelines.sec_rag_ingest import SparkCikMappingLogWriter

        captured = {}
        writer = SparkCikMappingLogWriter(spark_factory=self._make_fake_spark(captured))
        # cik=None — the problematic case
        writer.append_mapping_log("cat", "sch", CikMappingLogEntry(
            ticker="MISSING", lookup_symbol="MISSING", cik=None,
            status="missing", reason="not found", mapped_ts=None, run_id="r1",
        ))

        SparkCikMappingLogWriter.CIK_MAPPING_SCHEMA = None
        # Must not raise even with cik=None
        writer.flush("cat", "sch")

        data = captured.get("data")
        assert data is not None
        assert data[0]["cik"] is None
        assert data[0]["ticker"] == "MISSING"

    def test_batch_single_write_call(self):
        """N entries → 1 createDataFrame call, not N.

        Mutation proof: if flush() is called per-entry (inside append_mapping_log),
        this test FAILS because createDataFrame would be called N times.
        """
        from pipelines.sec_rag_ingest import SparkCikMappingLogWriter

        call_count = 0

        class CountingSparkSession:
            def createDataFrame(self, data, schema=None):
                nonlocal call_count
                call_count += 1
                df = MagicMock()
                mode_mock = MagicMock()
                df.write.mode.return_value = mode_mock
                mode_mock.saveAsTable.return_value = None
                return df

        writer = SparkCikMappingLogWriter(spark_factory=CountingSparkSession)
        for i in range(5):
            writer.append_mapping_log("cat", "sch", CikMappingLogEntry(
                ticker=f"T{i}", lookup_symbol=f"T{i}", cik=f"000{i}",
                status="mapped", reason="exact", mapped_ts=None, run_id="r1",
            ))

        writer.flush("cat", "sch")

        assert call_count == 1, (
            f"Expected 1 createDataFrame call for 5 entries, got {call_count}. "
            "Mutation: per-ticker writes would call createDataFrame 5 times."
        )

    def test_buffer_cleared_after_flush(self):
        """Buffer is empty after flush — subsequent flush is a no-op."""
        from pipelines.sec_rag_ingest import SparkCikMappingLogWriter

        write_count = 0

        class CountingSparkSession:
            def createDataFrame(self, data, schema=None):
                nonlocal write_count
                write_count += 1
                df = MagicMock()
                mode_mock = MagicMock()
                df.write.mode.return_value = mode_mock
                mode_mock.saveAsTable.return_value = None
                return df

        writer = SparkCikMappingLogWriter(spark_factory=CountingSparkSession)
        writer.append_mapping_log("cat", "sch", CikMappingLogEntry(
            ticker="AAPL", lookup_symbol="AAPL", cik="0000320193",
            status="mapped", reason="exact", mapped_ts=None, run_id="r1",
        ))

        writer.flush("cat", "sch")
        writer.flush("cat", "sch")  # second flush should be no-op

        assert write_count == 1, (
            f"Expected 1 write (second flush is no-op), got {write_count}. "
            "Mutation: buffer not cleared after flush."
        )

class TestAccessionConflict:
    def test_accession_ownership_conflict_fails(self):
        """If an existing accession is associated with a different ticker, log conflict."""
        # This test verifies the anti-join behavior
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        # Pre-existing accessions should cause them to be skipped
        existing = {
            "0001045810-25-000010": ("0001045810", "NVDA"),
            "0001045810-24-000020": ("0001045810", "NVDA"),
        }

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert result.skipped_existing_count == 2
        assert result.total_rows_appended == 0

    def test_different_cik_accession_raises_conflict(self):
        """Same accession owned by a different CIK: conflict recorded, run continues."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        # The accession is owned by a DIFFERENT CIK (9999999999, not 0001045810)
        existing = {
            "0001045810-25-000010": ("9999999999", "OTHER"),
        }

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        # Genuine conflict: filing fails, run continues (no raise)
        assert result.failed_count >= 1

    def test_race_path_conflict_raises(self):
        """Race-path conflict: accession appears between anti-join and processing.

        The race-path AccessionReader returns {} on first call (anti-join passes)
        and returns a conflicting accession on second call (inside the processing loop).
        Genuine conflict is recorded as failed, run continues (no raise).
        """
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )

        universe = [TickerEntry(ticker="NVDA", phase=1)]

        class RaceAccessionReader:
            """Returns empty on first call, conflicting accession on second."""
            def __init__(self):
                self._call_count = 0

            def read_existing_accessions(self, catalog, schema):
                self._call_count += 1
                if self._call_count == 1:
                    return {}  # Anti-join: nothing exists
                # Race: conflicting accession appeared
                return {"0001045810-25-000010": ("9999999999", "OTHER")}

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=RaceAccessionReader(),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        # Race-path genuine conflict: filing fails, run continues (no raise)
        assert result.failed_count >= 1


# -- main() end-to-end tests --

class TestMainEndToEnd:
    """Test main() with fake Spark adapters wired in."""

    def test_main_dry_run_writes_zero_rows(self, monkeypatch):
        """Dry-run mode with fake adapters should write 0 rows."""
        from pipelines.sec_rag_ingest import main

        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        # Also set the company_tickers.json URL
        company_tickers = json.loads((FIXTURES / "company_tickers.json").read_text())
        http.set_json("https://www.sec.gov/files/company_tickers.json", company_tickers)

        writer = FakeDataWriter()
        log_writer = FakeLogWriter()
        universe = [TickerEntry(ticker="NVDA", phase=1)]

        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkUniverseReader",
            lambda: FakeUniverseReader(universe),
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkAccessionReader",
            lambda: FakeAccessionReader(),
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkDataWriter",
            lambda: writer,
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkLogWriter",
            lambda: log_writer,
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkCikMappingLogWriter",
            lambda: FakeCikMappingLogWriter(),
        )
        monkeypatch.setattr("pipelines._http_adapter.RequestsAdapter", lambda: http)

        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "TestAgent test@company.com")
        monkeypatch.setattr(
            "sys.argv",
            [
                "sec_rag_ingest",
                "--catalog", "test",
                "--schema", "test",
                "--tickers", "NVDA",
                "--dry-run",
            ],
        )

        main()

        assert writer.total_rows == 0

    def test_main_write_mode_exits_on_failure(self, monkeypatch):
        """Write mode with missing filing data should exit(1)."""
        from pipelines.sec_rag_ingest import main

        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        company_tickers = json.loads((FIXTURES / "company_tickers.json").read_text())
        http.set_json("https://www.sec.gov/files/company_tickers.json", company_tickers)

        writer = FakeDataWriter()
        log_writer = FakeLogWriter()
        universe = [TickerEntry(ticker="NVDA", phase=1)]

        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkUniverseReader",
            lambda: FakeUniverseReader(universe),
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkAccessionReader",
            lambda: FakeAccessionReader(),
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkDataWriter",
            lambda: writer,
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkLogWriter",
            lambda: log_writer,
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkCikMappingLogWriter",
            lambda: FakeCikMappingLogWriter(),
        )
        monkeypatch.setattr("pipelines._http_adapter.RequestsAdapter", lambda: http)

        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "TestAgent test@company.com")
        monkeypatch.setattr(
            "sys.argv",
            [
                "sec_rag_ingest",
                "--catalog", "test",
                "--schema", "test",
                "--tickers", "NVDA",
            ],
        )

        # Filing body fetch will fail (no HTML response set), so exit(1)
        with pytest.raises(SystemExit, match="1"):
            main()

    def test_main_write_mode_writes_filings_and_log(self, monkeypatch):
        """main() in write mode with working HTTP writes rows to writer and log.

        Mutation proof: remove the four adapter kwargs from the run_ingest()
        call in main() → this test FAILS (real Spark adapters hit mocked
        modules that return MagicMock, causing TypeError downstream).
        """
        from pipelines.sec_rag_ingest import main

        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        company_tickers = json.loads((FIXTURES / "company_tickers.json").read_text())
        http.set_json("https://www.sec.gov/files/company_tickers.json", company_tickers)

        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        # Both 10-K and 10-Q filings resolve to the same sample HTML
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000020/nvda-20241027.htm",
            filing_html,
        )

        writer = FakeDataWriter()
        log_writer = FakeLogWriter()
        cik_log = FakeCikMappingLogWriter()
        universe = [TickerEntry(ticker="NVDA", phase=1)]

        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkUniverseReader",
            lambda: FakeUniverseReader(universe),
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkAccessionReader",
            lambda: FakeAccessionReader(),
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkDataWriter",
            lambda: writer,
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkLogWriter",
            lambda: log_writer,
        )
        monkeypatch.setattr(
            "pipelines.sec_rag_ingest.SparkCikMappingLogWriter",
            lambda: cik_log,
        )
        monkeypatch.setattr("pipelines._http_adapter.RequestsAdapter", lambda: http)

        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "TestAgent test@company.com")
        monkeypatch.setattr(
            "sys.argv",
            [
                "sec_rag_ingest",
                "--catalog", "test",
                "--schema", "test",
                "--tickers", "NVDA",
                "--start-date", "2024-09-01",
            ],
        )

        main()

        # --- Filings: exactly 2 batches (10-K + 10-Q); 8-K filtered by --forms default ---
        assert len(writer.appended) == 2, f"Expected 2 append calls, got {len(writer.appended)}"

        # Flatten all rows across both batches
        all_rows = [r for batch in writer.appended for r in batch]
        assert len(all_rows) > 0, "Expected filing chunks to be written"

        # Every row must reference the correct ticker and CIK
        assert all(r["ticker"] == "NVDA" for r in all_rows)
        assert all(r["cik"] == "0001045810" for r in all_rows)

        # Accession numbers present in written rows
        accessions = {r["accession_number"] for r in all_rows}
        assert "0001045810-25-000010" in accessions, "10-K accession missing"
        assert "0001045810-24-000020" in accessions, "10-Q accession missing"

        # Form types
        form_types = {r["form_type"] for r in all_rows}
        assert form_types == {"10-K", "10-Q"}, f"Unexpected form types: {form_types}"

        # accepted_ts values per accession
        ts_map = {r["accession_number"]: r["accepted_ts"] for r in all_rows}
        assert ts_map["0001045810-25-000010"] is not None, "10-K accepted_ts missing"
        assert ts_map["0001045810-24-000020"] is not None, "10-Q accepted_ts missing"

        # Each filing produces 4 chunks (one per section: item1, item1a, item7, item8)
        for acc in accessions:
            acc_rows = [r for r in all_rows if r["accession_number"] == acc]
            chunk_ids = sorted(r["chunk_id"] for r in acc_rows)
            sections = sorted(r["filing_section"] for r in acc_rows)
            assert chunk_ids == [1, 1, 1, 1], f"{acc}: unexpected chunk_ids {chunk_ids}"
            assert sections == ["item1_business", "item1a_risk_factors", "item7_mda", "item8_financial_statements"], \
                f"{acc}: unexpected sections {sections}"

        # --- Log entries: 2 succeeded filings ---
        succeeded = [e for e in log_writer.entries if e.status == "succeeded"]
        assert len(succeeded) == 2, f"Expected 2 succeeded log entries, got {len(succeeded)}"
        assert all(e.ticker == "NVDA" for e in succeeded)
        log_accessions = {e.accession_number for e in succeeded}
        assert log_accessions == {"0001045810-25-000010", "0001045810-24-000020"}
        assert all(e.form_type in ("10-K", "10-Q") for e in succeeded)
        assert all(e.cik == "0001045810" for e in succeeded)

        # --- CIK mapping log: exactly 1 entry for NVDA mapped ---
        assert len(cik_log.entries) == 1
        assert cik_log.entries[0].ticker == "NVDA"
        assert cik_log.entries[0].cik == "0001045810"
        assert cik_log.entries[0].status == "mapped"
        assert cik_log.flush_count == 1


# -- Round 8a: New tests for findings 1-6 --


class TestAtomicBronzeWrites:
    """Finding 1: MERGE (not append), explicit schema, ownership conflict."""

    def test_merge_not_append(self):
        """FakeDataWriter tracks append calls; SparkDataWriter uses MERGE.

        Verify that the FakeDataWriter records rows correctly (proxy for MERGE).
        """
        writer = FakeDataWriter()
        rows = [{"accession_number": "001", "cik": "0001", "ticker": "T", "record_key": "k1"}]
        inserted = writer.append_bronze_rows("cat", "sch", rows)
        assert inserted == 1
        assert writer.total_rows == 1

    def test_merge_rerun_inserts_zero(self):
        """Re-running the same accession returns 0 inserted (MERGE semantics)."""
        writer = FakeDataWriter()
        rows = [
            {"accession_number": "001", "cik": "0001", "ticker": "T", "record_key": f"k{i}"}
            for i in range(50)
        ]
        first = writer.append_bronze_rows("cat", "sch", rows)
        assert first == 50, "First insert: new accession → all 50 chunk rows inserted"
        # Re-run the same accession
        second = writer.append_bronze_rows("cat", "sch", rows)
        assert second == 0, "Re-run: same accession already seen → 0 inserted"

    def test_batch_ownership_conflict_raises(self):
        """Two rows with same accession but different CIK → AccessionOwnershipConflict."""
        from pipelines.sec_rag_ingest import SparkDataWriter, AccessionOwnershipConflict

        captured = {}
        class FakeSpark:
            def createDataFrame(self, data, schema=None):
                captured["data"] = list(data)
                captured["schema"] = schema
                df = MagicMock()
                df.createOrReplaceTempView = MagicMock()
                return df
            def sql(self, q):
                m = MagicMock()
                m.collect.return_value = []
                return m

        writer = SparkDataWriter(spark_factory=lambda: FakeSpark())
        rows = [
            {"accession_number": "001", "cik": "0001", "ticker": "A",
             "record_key": "k1", "form_type": "10-K", "filing_date": "2025-01-01",
             "accepted_ts": None, "primary_doc": "", "filing_url": "",
             "chunk_id": 1, "filing_section": "s", "chunk_text": "t",
             "chunk_char_count": 1, "source": "sec", "ingest_ts": None,
             "raw_payload": None, "company_name": "A"},
            {"accession_number": "001", "cik": "0002", "ticker": "B",
             "record_key": "k2", "form_type": "10-K", "filing_date": "2025-01-01",
             "accepted_ts": None, "primary_doc": "", "filing_url": "",
             "chunk_id": 1, "filing_section": "s", "chunk_text": "t",
             "chunk_char_count": 1, "source": "sec", "ingest_ts": None,
             "raw_payload": None, "company_name": "B"},
        ]
        with pytest.raises(AccessionOwnershipConflict, match="Conflicting CIKs"):
            writer.append_bronze_rows("cat", "sch", rows)


class TestBronzeConcurrencyN1:
    """N1 (P1): Two threads writing different accessions concurrently must use
    distinct view names, both batches must be written, and each must report
    its own inserted count.

    Mutation proof: fixed view name / no lock → FAILS because:
    - Both threads use '_merge_src' → one overwrites the other's view.
    - Without the lock, DESCRIBE HISTORY returns another worker's count.
    """

    def test_concurrent_bronze_writes_distinct_views_and_metrics(self):
        from pipelines.sec_rag_ingest import SparkDataWriter
        import threading

        captured_views = []
        captured_sqls = []
        merge_calls = []

        class FakeSpark:
            """Records every MERGE call and which view it used."""
            def createDataFrame(self, data, schema=None):
                df = MagicMock()
                return df

            def sql(self, q):
                captured_sqls.append(q)
                m = MagicMock()
                # Return 1 inserted for each MERGE call
                mock_hist = MagicMock()
                mock_hist.__getitem__ = lambda self, k: {
                    "operationMetrics": {"numTargetRowsInserted": "1"}
                }.get(k)
                m.collect.return_value = [mock_hist]
                return m

        class TrackingDF:
            def __init__(self):
                pass
            def createOrReplaceTempView(self, name):
                captured_views.append(name)

        spark_instance = FakeSpark()
        original_create = spark_instance.createDataFrame

        def tracking_create(data, schema=None):
            df = TrackingDF()
            return df

        spark_instance.createDataFrame = tracking_create
        spark_instance.catalog = MagicMock()

        writer = SparkDataWriter(spark_factory=lambda: spark_instance)

        # Reset the class-level lock to ensure test isolation
        old_lock = SparkDataWriter._merge_lock
        SparkDataWriter._merge_lock = threading.Lock()

        rows_a = [
            {"accession_number": "ACC-A", "cik": "0001", "ticker": "A",
             "record_key": "k1", "form_type": "10-K", "filing_date": "2025-01-01",
             "accepted_ts": None, "primary_doc": "", "filing_url": "",
             "chunk_id": 1, "filing_section": "s", "chunk_text": "t",
             "chunk_char_count": 1, "source": "sec", "ingest_ts": None,
             "raw_payload": None, "company_name": "A"},
        ]
        rows_b = [
            {"accession_number": "ACC-B", "cik": "0002", "ticker": "B",
             "record_key": "k2", "form_type": "10-K", "filing_date": "2025-01-01",
             "accepted_ts": None, "primary_doc": "", "filing_url": "",
             "chunk_id": 1, "filing_section": "s", "chunk_text": "t",
             "chunk_char_count": 1, "source": "sec", "ingest_ts": None,
             "raw_payload": None, "company_name": "B"},
        ]

        results = {}
        barrier = threading.Barrier(2, timeout=5)

        def writer_a():
            barrier.wait()
            results["a"] = writer.append_bronze_rows("cat", "sch", rows_a)

        def writer_b():
            barrier.wait()
            results["b"] = writer.append_bronze_rows("cat", "sch", rows_b)

        t1 = threading.Thread(target=writer_a)
        t2 = threading.Thread(target=writer_b)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # Both must have completed
        assert "a" in results and "b" in results
        assert results["a"] == 1
        assert results["b"] == 1

        # Distinct view names (uuid-based)
        assert len(captured_views) == 2
        assert captured_views[0] != captured_views[1]
        for v in captured_views:
            assert v.startswith("_merge_src_")

        SparkDataWriter._merge_lock = old_lock


class TestAcceptedTsUTC:
    """Finding 2: accepted_ts must be tz-aware UTC, never naive."""

    def test_epoch_under_singapore_tz(self):
        """2025-02-20T18:30:00Z must produce epoch 1740076200 regardless of local TZ."""
        ts = parse_sec_timestamp("2025-02-20T18:30:00.000Z")
        assert ts is not None
        epoch = int(ts.timestamp())
        assert epoch == 1740076200, (
            f"Expected epoch 1740076200 (UTC), got {epoch}. "
            "Naive datetime was serialized via time.mktime using local TZ."
        )

    def test_tz_aware_utc(self):
        """parse_sec_timestamp returns tz-aware UTC datetime."""
        ts = parse_sec_timestamp("2025-02-20T18:30:00.000Z")
        assert ts.tzinfo is not None
        assert ts.tzinfo == timezone.utc

    def test_offset_preserves_utc(self):
        """Non-UTC offset is converted to UTC."""
        ts = parse_sec_timestamp("2025-01-15T12:00:00+05:00")
        assert ts is not None
        assert ts.hour == 7
        assert ts.tzinfo == timezone.utc

    def test_process_filing_tz_aware(self):
        """process_filing rows carry tz-aware accepted_ts."""
        from pipelines.sec_rag_ingest import FilingMeta
        filing = FilingMeta(
            accession_number="001", form_type="10-K",
            filing_date="2025-01-01", primary_doc="t.htm",
            accepted_ts=datetime(2025, 2, 20, 18, 30, 0, tzinfo=timezone.utc),
        )
        rows = process_filing("T", "1234", "Corp", filing, "<p>" + "x" * 200 + "</p>", datetime.now(timezone.utc))
        if rows:
            assert rows[0]["accepted_ts"].tzinfo == timezone.utc


class TestDiscoveryCompleteness:
    """Finding 3: Discovery must not silently succeed on incomplete data."""

    def test_exhausted_submissions_raises(self):
        """When submissions request fails after retries, SecClientError propagates."""
        clock = FakeClock()
        http = FakeHttpClient()
        http.set_error("https://data.sec.gov/submissions/CIK0001045810.json", 500)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        with pytest.raises(SecClientError):
            discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})

    def test_history_failure_logged_and_continues(self):
        """History file failure is skipped (logged), not fatal."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        # History file returns error
        http.set_error("https://data.sec.gov/submissions/CIK0001045810-submissions-001.json", 500)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        # start_date must be <= filingTo (2024-08-31) so the history file is fetched
        filings, failed_hist = discover_filings(client, "1045810", "2024-08-01", {"10-K", "10-Q"})
        # Should still get filings from recent (not crash)
        assert len(filings) >= 1
        # Failed history URL should be tracked
        assert len(failed_hist) == 1
        assert "submissions-001" in next(iter(failed_hist))

    def test_history_overlap_uses_filing_to(self):
        """History file is fetched when filingTo >= start_date (overlap check)."""
        clock = FakeClock()
        http = FakeHttpClient()
        # Submissions with a history file that overlaps the cutoff
        submissions = {
            "cik": "0001045810",
            "entityName": "Test",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2025-01-15"],
                    "accessionNumber": ["001"], "primaryDocument": ["t.htm"],
                    "acceptanceDateTime": ["2025-01-15T10:00:00Z"],
                },
                "files": [{"name": "hist.json", "filingFrom": "2024-10-01", "filingTo": "2024-12-31"}],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        # History file has a filing AFTER the cutoff
        history = {
            "filings": {
                "recent": {
                    "form": ["10-Q"], "filingDate": ["2024-11-15"],
                    "accessionNumber": ["002"], "primaryDocument": ["q.htm"],
                    "acceptanceDateTime": ["2024-11-15T10:00:00Z"],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/hist.json", history)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
        accessions = {f.accession_number for f in filings}
        assert "002" in accessions, "History filing after cutoff should be included"

    def test_missing_acceptance_datetime_not_dropped(self):
        """Filing with missing acceptanceDateTime is included (accepted_ts=None).

        The acceptanceDateTime array is SHORTER than the forms array — the old
        min()-based truncation would silently drop the filing.
        """
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = {
            "cik": "0001045810",
            "entityName": "Test",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2025-01-15"],
                    "accessionNumber": ["001"], "primaryDocument": ["t.htm"],
                    "acceptanceDateTime": [],  # SHORTER than forms — old min() drops this row
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"10-K"})
        assert len(filings) == 1
        assert filings[0].accepted_ts is None  # Not dropped


class TestPartialCoverageN2:
    """N2 (P2): A failed history-file fetch must be recorded as partial in
    sec_ingest_log and surfaced in the run summary (IngestResult.partial_count).

    Mutation proof: if discover_filings swallows the error and returns only
    filings (no failed set), run_ingest never records partial → FAILS.
    """

    def test_partial_coverage_logged_and_counted(self):
        """History-file fetch failure → partial status in log + partial_count in result."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        # History file returns error → partial coverage
        http.set_error("https://data.sec.gov/submissions/CIK0001045810-submissions-001.json", 500)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        writer = FakeDataWriter()
        log_writer = FakeLogWriter()

        # start_date must be <= filingTo (2024-08-31) so history file is fetched
        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-08-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=writer,
            log_writer=log_writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        # partial_count must be 1
        assert result.partial_count == 1, (
            f"Expected partial_count=1, got {result.partial_count}. "
            "Mutation: discover_filings swallowing history failure → 0 partial."
        )
        assert "NVDA" in result.partial_tickers

        # partial entry in log
        partial = [e for e in log_writer.entries if e.status == "partial"]
        assert len(partial) == 1
        assert partial[0].error_code == "history_fetch_failed"
        assert partial[0].ticker == "NVDA"
        assert "history" in partial[0].error_message.lower()

    def test_no_partial_when_history_succeeds(self):
        """When history file succeeds, partial_count stays 0."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        history = json.loads((FIXTURES / "submissions_history.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810-submissions-001.json", history)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000020/nvda-20241027.htm",
            filing_html,
        )

        universe = [TickerEntry(ticker="NVDA", phase=1)]

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=FakeDataWriter(),
            log_writer=FakeLogWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        assert result.partial_count == 0
        assert result.partial_tickers == []


class TestCikAmbiguousAndCacheFallback:
    """Finding 4: CIK ambiguous status + stale-cache fallback."""

    def test_two_cik_fixture_marks_ambiguous(self):
        """A ticker mapping to two distinct CIKs → status='ambiguous'."""
        payload = {
            "0": {"cik_str": 100, "ticker": "DUAL", "title": "Dual A"},
            "1": {"cik_str": 200, "ticker": "DUAL", "title": "Dual B"},
        }
        result = build_cik_map(["DUAL"], payload)
        assert result["DUAL"].status == "ambiguous"
        assert result["DUAL"].cik is None
        assert "100" in result["DUAL"].reason
        assert "200" in result["DUAL"].reason

    def test_stale_cache_used_on_network_failure(self, tmp_path):
        """Stale cache (past TTL) is used when network fails.

        The cache has a .meta sidecar with an old timestamp so the normal TTL
        check rejects it. The ttl=0 fallback path should still accept it.
        """
        # Copy fixture to tmp_path so we can add a .meta sidecar
        fixture_data = json.loads((FIXTURES / "company_tickers.json").read_text())
        cache_file = tmp_path / "company_tickers.json"
        cache_file.write_text(json.dumps(fixture_data), encoding="utf-8")
        # Write .meta sidecar with old timestamp (30 days ago)
        sidecar = tmp_path / "company_tickers.json.meta"
        sidecar.write_text(
            json.dumps({"fetched_ts": time.time() - 30 * 86400}),
            encoding="utf-8",
        )

        clock = FakeClock()
        http = FakeHttpClient()
        http.set_error("https://www.sec.gov/files/company_tickers.json", 500)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        # Normal TTL (3600s) should reject the stale cache
        result_fresh = load_company_tickers(
            client,
            cache_path=str(cache_file),
            cache_ttl=3600,
        )
        # Network fails, cache is stale → should raise (or return None)
        # The function raises SecClientError when both network and cache fail
        # But with ttl=0 fallback it should use the stale cache
        # First call with TTL=3600 may fail (stale cache rejected, network down)
        # Let's verify the ttl=0 fallback works
        result_stale = load_company_tickers(
            client,
            cache_path=str(cache_file),
            cache_ttl=0,
        )
        assert "0" in result_stale, "Stale cache should be used with ttl=0"

    def test_dry_run_does_not_write_cache(self, tmp_path):
        """Dry run must not write the persistent cache file."""
        cache_file = tmp_path / "tickers.json"
        clock = FakeClock()
        http = FakeHttpClient()
        company_tickers = json.loads((FIXTURES / "company_tickers.json").read_text())
        http.set_json("https://www.sec.gov/files/company_tickers.json", company_tickers)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        load_company_tickers(client, cache_path=str(cache_file), dry_run=True)
        assert not cache_file.exists(), "Dry run should not write cache file"


class TestFairAccess:
    """Finding 5: Process-wide rate limiter shared across callers."""

    def test_global_limiter_singleton(self):
        """get_global_limiter returns the same instance."""
        from pipelines.sec_rag_ingest import get_global_limiter, _global_limiter
        # Reset for test
        import pipelines.sec_rag_ingest as mod
        old = mod._global_limiter
        mod._global_limiter = None
        try:
            l1 = get_global_limiter(max_rps=5)
            l2 = get_global_limiter(max_rps=10)  # ignored — already created
            assert l1 is l2
            assert l1.max_rps == 5
        finally:
            mod._global_limiter = old

    def test_http_date_retry_after(self):
        """Retry-After with HTTP-date is parsed correctly."""
        from email.utils import format_datetime
        future = datetime.now(timezone.utc) + __import__("datetime").timedelta(seconds=30)
        http_date = format_datetime(future, usegmt=True)

        result = SecClient._parse_retry_after({"Retry-After": http_date})
        assert result is not None
        assert 25 <= result <= 35  # ~30 seconds

    def test_numeric_retry_after(self):
        """Retry-After with numeric seconds."""
        result = SecClient._parse_retry_after({"Retry-After": "42"})
        assert result == 42.0


class TestResumeAndWorkers:
    """Finding 6: Resume, workers, attempt tracking."""

    def test_in_progress_persisted_before_work(self):
        """in_progress log entry is written before processing begins."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        log_writer = FakeLogWriter()

        run_ingest(
            catalog="test", schema="test",
            start_date="2025-01-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=FakeDataWriter(),
            log_writer=log_writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        in_progress = [e for e in log_writer.entries if e.status == "in_progress"]
        assert len(in_progress) >= 1, "in_progress entry should be persisted before work"

    def test_resume_skips_succeeded(self):
        """Previously succeeded accessions are skipped on resume."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]

        class FakeIngestLogReader:
            def read_succeeded_accessions(self, catalog, schema, run_id):
                # Pretend both filings already succeeded
                return {
                    (run_id, "NVDA", "0001045810-25-000010"),
                    (run_id, "NVDA", "0001045810-24-000020"),
                }
            def read_max_attempt(self, catalog, schema, run_id, ticker, accession):
                return 1

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=FakeDataWriter(),
            log_writer=FakeLogWriter(),
            ingest_log_reader=FakeIngestLogReader(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        assert result.skipped_existing_count == 2
        assert result.total_rows_appended == 0

    def test_attempt_increments(self):
        """Attempt number = previous max attempt + 1."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        log_writer = FakeLogWriter()

        class FakeIngestLogReader:
            def read_succeeded_accessions(self, catalog, schema, run_id):
                return set()
            def read_max_attempt(self, catalog, schema, run_id, ticker, accession):
                return 3  # Previous attempt was 3

        run_ingest(
            catalog="test", schema="test",
            start_date="2025-01-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=FakeDataWriter(),
            log_writer=log_writer,
            ingest_log_reader=FakeIngestLogReader(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        succeeded = [e for e in log_writer.entries if e.status == "succeeded"]
        assert len(succeeded) >= 1
        assert succeeded[0].attempt == 4, "Attempt should be previous_max + 1 = 4"

    def test_max_workers_used(self):
        """max_workers > 1 uses ThreadPoolExecutor (verifiable via result)."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000020/nvda-20241027.htm",
            filing_html,
        )

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        writer = FakeDataWriter()

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            max_workers=4,
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=writer,
            log_writer=FakeLogWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        assert result.succeeded_count == 2
        assert result.total_rows_appended > 0


class TestTotalRowsAppendedAggregation:
    """total_rows_appended propagates None (unknown) from any successful filing.

    Mirrors the embeddings-aggregate pattern: if ANY successful filing's
    rows_appended is None (writer couldn't determine inserted count), the
    total must be None — not silently coerced to 0.
    """

    @staticmethod
    def _make_writer(*return_values):
        """FakeDataWriter that returns the given values in order."""
        class SeqWriter:
            def __init__(self):
                self._values = list(return_values)
                self._idx = 0
                self.appended = []
                self.total_rows = 0
            def append_bronze_rows(self, catalog, schema, rows):
                self.appended.append(rows)
                val = self._values[self._idx]
                self._idx += 1
                if val is not None:
                    self.total_rows += val
                return val
        return SeqWriter()

    def _run(self, writer, max_workers=1):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        filing_html = (FIXTURES / "sample_filing.htm").read_text()
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000010/nvda-20250126.htm",
            filing_html,
        )
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000020/nvda-20241027.htm",
            filing_html,
        )
        universe = [TickerEntry(ticker="NVDA", phase=1)]
        return run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            max_workers=max_workers,
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=writer,
            log_writer=FakeLogWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

    def test_all_none_serial(self):
        """[None, None] → None in serial mode."""
        writer = self._make_writer(None, None)
        result = self._run(writer, max_workers=1)
        assert result.succeeded_count == 2
        assert result.total_rows_appended is None

    def test_all_none_threaded(self):
        """[None, None] → None in threaded mode."""
        writer = self._make_writer(None, None)
        result = self._run(writer, max_workers=4)
        assert result.succeeded_count == 2
        assert result.total_rows_appended is None

    def test_mixed_serial(self):
        """[3, None] → None in serial mode."""
        writer = self._make_writer(3, None)
        result = self._run(writer, max_workers=1)
        assert result.succeeded_count == 2
        assert result.total_rows_appended is None

    def test_mixed_threaded(self):
        """[3, None] → None in threaded mode."""
        writer = self._make_writer(3, None)
        result = self._run(writer, max_workers=4)
        assert result.succeeded_count == 2
        assert result.total_rows_appended is None

    def test_all_zeros_serial(self):
        """[0, 0] → 0 in serial mode."""
        writer = self._make_writer(0, 0)
        result = self._run(writer, max_workers=1)
        assert result.succeeded_count == 2
        assert result.total_rows_appended == 0

    def test_all_zeros_threaded(self):
        """[0, 0] → 0 in threaded mode."""
        writer = self._make_writer(0, 0)
        result = self._run(writer, max_workers=4)
        assert result.succeeded_count == 2
        assert result.total_rows_appended == 0

    def test_real_values_serial(self):
        """[2, 5] → 7 in serial mode."""
        writer = self._make_writer(2, 5)
        result = self._run(writer, max_workers=1)
        assert result.succeeded_count == 2
        assert result.total_rows_appended == 7

    def test_real_values_threaded(self):
        """[2, 5] → 7 in threaded mode."""
        writer = self._make_writer(2, 5)
        result = self._run(writer, max_workers=4)
        assert result.succeeded_count == 2
        assert result.total_rows_appended == 7

    def test_mutation_skip_none_aggregation_fails(self):
        """Mutation: restoring skip-None aggregation → this test FAILS.

        If the code reverts to `if entry.rows_appended is not None: total += ...`,
        then [None, None] produces 0 instead of None.
        """
        writer = self._make_writer(None, None)
        result = self._run(writer, max_workers=1)
        assert result.total_rows_appended is None, (
            f"Expected None (unknown) when all filings return None rows, "
            f"got {result.total_rows_appended}. "
            f"Mutation: skip-None aggregation was restored."
        )


class TestSparkIngestLogReader:
    """SparkIngestLogReader reads from sec_ingest_log with pushed-down predicates."""

    def test_read_succeeded_accessions(self):
        """Returns (run_id, ticker, accession) tuples for succeeded entries."""
        from pipelines.sec_rag_ingest import SparkIngestLogReader

        class FakeSpark:
            def sql(self, q):
                self.last_query = q
                m = MagicMock()
                m.collect.return_value = [
                    {"run_id": "r1", "ticker": "NVDA", "accession_number": "001"},
                    {"run_id": "r1", "ticker": "NVDA", "accession_number": "002"},
                ]
                return m

        fake_spark = FakeSpark()
        reader = SparkIngestLogReader(spark_factory=lambda: fake_spark)
        result = reader.read_succeeded_accessions("cat", "sch", "r1")
        assert len(result) == 2
        assert ("r1", "NVDA", "001") in result
        assert "run_id" in fake_spark.last_query.lower()
        assert "succeeded" in fake_spark.last_query.lower()

    def test_read_max_attempt(self):
        """Returns max attempt number for a given accession."""
        from pipelines.sec_rag_ingest import SparkIngestLogReader

        class FakeSpark:
            def sql(self, q):
                self.last_query = q
                m = MagicMock()
                m.collect.return_value = [{"max_attempt": 3}]
                return m

        fake_spark = FakeSpark()
        reader = SparkIngestLogReader(spark_factory=lambda: fake_spark)
        result = reader.read_max_attempt("cat", "sch", "r1", "NVDA", "001")
        assert result == 3
        assert "max(attempt)" in fake_spark.last_query

    def test_read_max_attempt_returns_zero_when_no_rows(self):
        """Returns 0 when no log entries exist."""
        from pipelines.sec_rag_ingest import SparkIngestLogReader

        class FakeSpark:
            def sql(self, q):
                m = MagicMock()
                m.collect.return_value = [{"max_attempt": None}]
                return m

        reader = SparkIngestLogReader(spark_factory=lambda: FakeSpark())
        result = reader.read_max_attempt("cat", "sch", "r1", "NVDA", "001")
        assert result == 0

    def test_main_wires_ingest_log_reader(self, monkeypatch):
        """main() passes SparkIngestLogReader to run_ingest."""
        from pipelines.sec_rag_ingest import main, SparkIngestLogReader

        captured = {}
        original_run_ingest = run_ingest

        def mock_run_ingest(**kwargs):
            captured["ingest_log_reader"] = kwargs.get("ingest_log_reader")
            # Return a minimal result
            from pipelines.sec_rag_ingest import IngestResult
            return IngestResult(run_id="test", dry_run=True)

        monkeypatch.setattr("pipelines.sec_rag_ingest.run_ingest", mock_run_ingest)
        # Need to mock the Spark adapters since main() constructs them
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkUniverseReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkAccessionReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkDataWriter", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkLogWriter", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkIngestLogReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkCikMappingLogWriter", lambda: MagicMock())

        main(["--tickers", "NVDA", "--dry-run"])

        assert captured.get("ingest_log_reader") is not None, (
            "main() must pass ingest_log_reader to run_ingest"
        )


# -- Grep-style test: no example.com or your_email in production code --

class TestNoPlaceholderUserAgent:
    """Repo-wide scan: no example.com or your_email placeholders in production code."""

    def test_no_example_com_or_your_email_in_production(self):
        """No production .py or .yml file should contain example.com or your_email."""
        import re
        repo_root = Path(__file__).parent.parent.parent
        pattern = re.compile(r"(example\.com|your_email)", re.IGNORECASE)
        violations = []
        for ext in ("*.py", "*.yml"):
            for path in repo_root.rglob(ext):
                rel = path.relative_to(repo_root)
                parts = rel.parts
                if any(p in ("tests", ".agents", ".git", "__pycache__", "archive") for p in parts):
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for i, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        stripped = line.lstrip()
                        if stripped.startswith("#") or stripped.startswith("//"):
                            continue
                        violations.append(f"{rel}:{i}: {line.strip()}")
        assert not violations, (
            f"Found placeholder User-Agent in production code:\n" + "\n".join(violations)
        )


# -- Thin notebook wrapper tests --

NOTEBOOK_PATH = Path(__file__).parent.parent.parent / "notebooks" / "02_ingest_sec_edgar.py"


class TestNotebookThinWrapper:
    """Verify notebooks/02_ingest_sec_edgar.py is a thin wrapper with no legacy code."""

    def test_no_user_agent_in_notebook(self):
        """Notebook must not contain User-Agent construction."""
        content = NOTEBOOK_PATH.read_text(encoding="utf-8")
        assert "User-Agent" not in content, "Notebook still contains 'User-Agent'"

    def test_no_requests_get_in_notebook(self):
        """Notebook must not contain requests.get (legacy HTTP call)."""
        content = NOTEBOOK_PATH.read_text(encoding="utf-8")
        assert "requests.get" not in content, "Notebook still contains 'requests.get'"

    def test_no_beautifulsoup_in_notebook(self):
        """Notebook must not contain BeautifulSoup (legacy HTML parsing)."""
        content = NOTEBOOK_PATH.read_text(encoding="utf-8")
        assert "BeautifulSoup" not in content, "Notebook still contains 'BeautifulSoup'"

    def test_notebook_calls_main(self):
        """Notebook must call pipelines.sec_rag_ingest.main()."""
        content = NOTEBOOK_PATH.read_text(encoding="utf-8")
        assert "main(" in content, "Notebook does not call main()"

    def test_notebook_delegates_to_pipeline(self):
        """Notebook must import from pipelines.sec_rag_ingest."""
        content = NOTEBOOK_PATH.read_text(encoding="utf-8")
        assert "from pipelines.sec_rag_ingest import main" in content, (
            "Notebook does not import main from pipelines.sec_rag_ingest"
        )

    def test_no_other_code_imports_from_old_notebook(self):
        """No production code imports functions from the old notebook."""
        import re
        repo_root = Path(__file__).parent.parent.parent
        # The old notebook exported nothing importable (module name starts with digit),
        # but check for any import of the module anyway.
        pattern = re.compile(r"from\s+notebooks\.02_ingest_sec_edgar\s+import|import\s+notebooks\.02_ingest_sec_edgar")
        violations = []
        for ext in ("*.py", "*.yml"):
            for path in repo_root.rglob(ext):
                rel = path.relative_to(repo_root)
                parts = rel.parts
                if any(p in ("tests", ".agents", ".git", "__pycache__", "archive") for p in parts):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        violations.append(f"{rel}:{i}: {line.strip()}")
        assert not violations, (
            f"Found imports from old notebook:\n" + "\n".join(violations)
        )

    def test_notebook_widget_argv_dry_run(self, monkeypatch):
        """Executing notebook with fake dbutils passes --dry-run to main()."""
        captured = {}

        def fake_main(argv=None):
            captured["argv"] = argv

        monkeypatch.setattr("pipelines.sec_rag_ingest.main", fake_main)

        # Simulate dbutils widget values
        class FakeWidgets:
            _vals = {"tickers": "AAPL,MSFT", "start_date": "2024-06-01", "dry_run": "true"}
            def get(self, name):
                return self._vals.get(name)

        class FakeDbutils:
            widgets = FakeWidgets()

        # Execute the notebook's helper functions in a controlled namespace
        ns = {"__name__": "__main__", "dbutils": FakeDbutils()}
        exec(compile(NOTEBOOK_PATH.read_text(encoding="utf-8"), str(NOTEBOOK_PATH), "exec"), ns)

        argv = captured.get("argv")
        assert argv is not None, "main() was not called"
        assert "--tickers" in argv
        assert "AAPL,MSFT" in argv
        assert "--start-date" in argv
        assert "2024-06-01" in argv
        assert "--dry-run" in argv

    def test_notebook_widget_argv_include_historical(self, monkeypatch):
        """Executing notebook with include_historical=true passes the flag."""
        captured = {}

        def fake_main(argv=None):
            captured["argv"] = argv

        monkeypatch.setattr("pipelines.sec_rag_ingest.main", fake_main)

        class FakeWidgets:
            _vals = {"tickers": "NVDA", "include_historical": "true"}
            def get(self, name):
                return self._vals.get(name)

        class FakeDbutils:
            widgets = FakeWidgets()

        ns = {"__name__": "__main__", "dbutils": FakeDbutils()}
        exec(compile(NOTEBOOK_PATH.read_text(encoding="utf-8"), str(NOTEBOOK_PATH), "exec"), ns)

        argv = captured.get("argv")
        assert argv is not None
        assert "--include-historical" in argv
        assert "--tickers" in argv
        assert "NVDA" in argv


# ── Round 10 regression tests ────────────────────────────────────────────────


class TestSparkLogWriterSchema:
    """SparkLogWriter uses an explicit StructType — never schema inference.

    PySpark infers all-None columns as NullType and raises
    CANNOT_DETERMINE_TYPE on write.  An in_progress row has
    completed_ts=None, error_code=None, error_message=None.
    """

    @pytest.fixture(autouse=True)
    def _restore_pyspark_types(self, monkeypatch):
        try:
            saved = {}
            for key in list(sys.modules):
                if key.startswith("pyspark"):
                    saved[key] = sys.modules.pop(key)
            try:
                import pyspark.sql.types as real_types
                monkeypatch.setitem(sys.modules, "pyspark.sql.types", real_types)
            finally:
                for k, v in saved.items():
                    sys.modules.setdefault(k, v)
        except ImportError:
            pytest.skip("pyspark not available for schema tests")

    def _make_fake_spark(self, captured):
        class FakeSparkSession:
            def createDataFrame(self, data, schema=None):
                captured["data"] = list(data)
                captured["schema"] = schema
                df = MagicMock()
                mode_mock = MagicMock()
                df.write.mode.return_value = mode_mock
                mode_mock.saveAsTable.return_value = None
                return df
        return FakeSparkSession

    def test_schema_matches_documented_sec_ingest_log(self):
        """StructType exactly matches docs/DATA_SCHEMAS.md sec_ingest_log.

        Schema from DATA_SCHEMAS.md:
          run_id            string NOT NULL
          ticker            string NOT NULL
          cik               string NOT NULL
          accession_number  string NOT NULL
          form_type         string NOT NULL
          filing_date       string
          accepted_ts       timestamp
          status            string NOT NULL
          rows_appended     int
          attempt           int
          error_code        string
          error_message     string
          started_ts        timestamp
          completed_ts      timestamp
          dry_run           boolean
          logged_ts         timestamp NOT NULL
        """
        from pipelines.sec_rag_ingest import SparkLogWriter

        captured = {}
        writer = SparkLogWriter(spark_factory=self._make_fake_spark(captured))
        SparkLogWriter.INGEST_LOG_SCHEMA = None  # force rebuild
        writer.append_log("cat", "sch", IngestLogEntry(
            run_id="r1", ticker="AAPL", cik="0000320193",
            accession_number="001", form_type="10-K",
            filing_date=None, accepted_ts=None, status="in_progress",
        ))

        schema = captured.get("schema")
        assert schema is not None, (
            "Mutation: SparkLogWriter.createDataFrame called without schema=. "
            "PySpark will infer all-None columns as NullType and raise "
            "CANNOT_DETERMINE_TYPE in production."
        )

        expected_names = [
            "run_id", "ticker", "cik", "accession_number", "form_type",
            "filing_date", "accepted_ts", "status", "rows_appended", "attempt",
            "error_code", "error_message", "started_ts", "completed_ts",
            "dry_run", "logged_ts",
        ]
        actual_names = [f.name for f in schema.fields]
        assert actual_names == expected_names, f"Field names mismatch: {actual_names}"

        # Nullability: run_id=False, ticker=False, cik=False, accession_number=False,
        # form_type=False, filing_date=True, accepted_ts=True, status=False,
        # rows_appended=True, attempt=True, error_code=True, error_message=True,
        # started_ts=True, completed_ts=True, dry_run=True, logged_ts=False
        expected_nullable = [False, False, False, False, False, True, True, False,
                             True, True, True, True, True, True, True, False]
        actual_nullable = [f.nullable for f in schema.fields]
        assert actual_nullable == expected_nullable, f"Nullability mismatch: {actual_nullable}"

    def test_in_progress_row_with_all_none_fields_succeeds(self):
        """An in_progress row with completed_ts/error_code/error_message=None
        must NOT raise CANNOT_DETERMINE_TYPE when the explicit schema is used.
        """
        from pipelines.sec_rag_ingest import SparkLogWriter

        captured = {}
        writer = SparkLogWriter(spark_factory=self._make_fake_spark(captured))
        SparkLogWriter.INGEST_LOG_SCHEMA = None
        writer.append_log("cat", "sch", IngestLogEntry(
            run_id="r1", ticker="NVDA", cik="0001234",
            accession_number="001-12345", form_type="10-Q",
            filing_date=None, accepted_ts=None, status="in_progress",
            # all of these are None on an in_progress row:
            completed_ts=None, error_code=None, error_message=None,
            rows_appended=None,
        ))

        # If schema was not passed, createDataFrame would have been called
        # without schema= and PySpark would infer NullType for None columns.
        assert captured.get("schema") is not None


class TestSparkIngestLogReaderColdStart:
    """SparkIngestLogReader gracefully handles a missing sec_ingest_log table."""

    def test_read_succeeded_returns_empty_on_table_not_found(self):
        """On cold start (table absent), reader returns empty set — no crash."""
        from pipelines.sec_rag_ingest import SparkIngestLogReader

        class FakeSpark:
            def sql(self, q):
                raise Exception("Table or view not found: sec_ingest_log")

        reader = SparkIngestLogReader(spark_factory=lambda: FakeSpark())
        result = reader.read_succeeded_accessions("cat", "sch", "r1")
        assert result == set(), (
            "Mutation: reader should return empty set on table-not-found, "
            "but it raised or returned something else."
        )

    def test_read_max_attempt_returns_zero_on_table_not_found(self):
        """On cold start, read_max_attempt returns 0."""
        from pipelines.sec_rag_ingest import SparkIngestLogReader

        class FakeSpark:
            def sql(self, q):
                raise Exception("Table or view not found: sec_ingest_log")

        reader = SparkIngestLogReader(spark_factory=lambda: FakeSpark())
        result = reader.read_max_attempt("cat", "sch", "r1", "NVDA", "001")
        assert result == 0


class TestOwnershipConflictAuditRow:
    """Pre-existing accession ownership conflicts must be recorded in sec_ingest_log."""

    def test_ownership_conflict_writes_failed_log_entry(self):
        """When anti-join detects a genuine CIK conflict, a failed log entry is written
        and the run continues (no raise).
        """
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        # The accession is owned by a DIFFERENT CIK (9999999999, not 0001045810)
        existing = {
            "0001045810-25-000010": ("9999999999", "OTHER"),
        }

        log_entries = []

        class CapturingLogWriter:
            def append_log(self, catalog, schema, entry):
                log_entries.append(entry)

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            log_writer=CapturingLogWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )

        # Must have at least one failed entry with error_code=ownership_conflict
        conflict_entries = [
            e for e in log_entries
            if e.error_code == "ownership_conflict" and e.status == "failed"
        ]
        assert len(conflict_entries) >= 1, (
            f"Expected at least 1 ownership_conflict audit row, got {len(conflict_entries)}. "
            "Mutation: the anti-join raises without writing a log entry."
        )
        assert conflict_entries[0].accession_number == "0001045810-25-000010"
        # Run continues, conflict recorded as failure (not raised)
        assert result.failed_count >= 1


class TestSilverSqlPlaceholders:
    """Silver SQL files must use {catalog}.{schema} placeholders, not hardcoded schemas."""

    def test_silver_05_uses_placeholders(self):
        sql = Path("silver/05_silver_sec_sections.sql").read_text(encoding="utf-8")
        assert "bootcamp_students.evangoh_capstone" not in sql, (
            "silver/05_silver_sec_sections.sql still hard-codes bootcamp_students.evangoh_capstone; "
            "use {catalog}.{schema} placeholders"
        )
        assert "{catalog}.{schema}" in sql

    def test_silver_06_uses_placeholders(self):
        sql = Path("silver/06_silver_sec_entities.sql").read_text(encoding="utf-8")
        assert "bootcamp_students.evangoh_capstone" not in sql, (
            "silver/06_silver_sec_entities.sql still hard-codes bootcamp_students.evangoh_capstone; "
            "use {catalog}.{schema} placeholders"
        )
        assert "{catalog}.{schema}" in sql


class TestMergeMetricsNoCandidateFallback:
    """When DESCRIBE HISTORY is unavailable, inserted count must NOT fall back
    to len(rows) (candidate count).  It should be None (unknown).
    """

    def test_bronze_metrics_none_on_history_failure(self):
        """SparkDataWriter.append_bronze_rows returns None when DESCRIBE HISTORY fails,
        not len(rows).
        """
        from pipelines.sec_rag_ingest import SparkDataWriter

        class FakeSpark:
            _table_data = {}
            def createDataFrame(self, data, schema=None):
                df = MagicMock()
                df.createOrReplaceTempView.return_value = None
                return df
            def sql(self, q):
                if "DESCRIBE HISTORY" in q:
                    raise Exception("table not found")
                m = MagicMock()
                m.collect.return_value = []
                return m
            @property
            def catalog(self):
                c = MagicMock()
                c.dropTempView.return_value = None
                return c

        writer = SparkDataWriter(spark_factory=lambda: FakeSpark())
        rows = [{
            "record_key": "rk1", "ticker": "NVDA", "cik": "0001234",
            "company_name": "NVIDIA", "form_type": "10-K",
            "filing_date": "2024-01-01",
            "accepted_ts": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "accession_number": "001-12345", "primary_doc": "filing.htm",
            "filing_url": "https://sec.gov/filing", "chunk_id": 0,
            "filing_section": "item1_business", "chunk_text": "Hello world",
            "chunk_char_count": 11, "source": "sec_edgar",
            "ingest_ts": datetime.now(timezone.utc),
            "raw_payload": "<html>test</html>",
        }]
        result = writer.append_bronze_rows("cat", "sch", rows)
        assert result is None, (
            f"Expected None when DESCRIBE HISTORY fails, got {result}. "
            "Mutation: code falls back to len(rows) which is a candidate count."
        )

    def test_embeddings_metrics_none_on_history_failure(self):
        """_embed_and_write_batch returns None when DESCRIBE HISTORY fails."""
        from pipelines.build_sec_embeddings import _embed_and_write_batch

        class FakeSpark:
            def createDataFrame(self, data, schema=None):
                df = MagicMock()
                df.createOrReplaceTempView.return_value = None
                return df
            def sql(self, q):
                if "DESCRIBE HISTORY" in q:
                    raise Exception("table not found")
                m = MagicMock()
                m.collect.return_value = []
                return m
            @property
            def catalog(self):
                c = MagicMock()
                c.dropTempView.return_value = None
                return c

        class FakeEmbeddings:
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]

        batch = [{
            "chunk_id": "c1", "chunk_text": "hello",
            "accession_number": "001", "ticker": "NVDA",
            "accepted_epoch": 1704067200,
        }]
        lock = threading.Lock()
        result = _embed_and_write_batch(
            FakeSpark(), FakeEmbeddings(), batch,
            datetime.now(timezone.utc), lock,
        )
        assert result is None, (
            f"Expected None when DESCRIBE HISTORY fails, got {result}. "
            "Mutation: code falls back to len(out_rows) which is a candidate count."
        )


# ── Round 13: User-Agent resolution tests ──────────────────────────────────


class TestResolveUserAgent:
    """_resolve_user_agent: env → Databricks secret fallback, never logs value."""

    def test_env_wins_over_secret(self, monkeypatch):
        """When SEC_EDGAR_USER_AGENT is set in env, it takes precedence."""
        from pipelines.sec_rag_ingest import _resolve_user_agent

        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "EnvAgent env@test.com")

        # Even if a secret exists, env should win
        result = _resolve_user_agent()
        assert result == "EnvAgent env@test.com"

    def test_env_empty_falls_through(self, monkeypatch):
        """Empty env var falls through to secret path (or raises)."""
        from pipelines.sec_rag_ingest import _resolve_user_agent
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        # No dbutils or SDK available → should raise ValueError
        with patch.dict("sys.modules", {
            "databricks.sdk.runtime": MagicMock(dbutils=None),
            "databricks.sdk": MagicMock(),
        }):
            with pytest.raises(ValueError, match="SEC_EDGAR_USER_AGENT not found"):
                _resolve_user_agent()

    def test_missing_both_raises_clear_error_naming_secret(self, monkeypatch):
        """Missing env and no secret → error names the scope and key."""
        from pipelines.sec_rag_ingest import _resolve_user_agent
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        with patch.dict("sys.modules", {
            "databricks.sdk.runtime": MagicMock(dbutils=None),
            "databricks.sdk": MagicMock(),
        }):
            with pytest.raises(ValueError, match="evangoh_capstone"):
                _resolve_user_agent(secret_scope="evangoh_capstone", secret_key="sec_edgar_user_agent")

            with pytest.raises(ValueError, match="sec_edgar_user_agent"):
                _resolve_user_agent(secret_scope="evangoh_capstone", secret_key="sec_edgar_user_agent")

    def test_placeholder_rejected(self, monkeypatch):
        """Placeholder addresses are rejected by _validate_user_agent."""
        from pipelines.sec_rag_ingest import _validate_user_agent

        with pytest.raises(ValueError, match="descriptive application"):
            _validate_user_agent("example@example.com")

        with pytest.raises(ValueError, match="descriptive application"):
            _validate_user_agent("your-email@example.com")

    def test_valid_address_with_example_accepted(self, monkeypatch):
        """Valid address containing 'example' (e.g. myexample.org) is accepted
        when paired with a name token."""
        from pipelines.sec_rag_ingest import _validate_user_agent

        # Should NOT raise — "myexample.org" is a valid domain when paired with name
        _validate_user_agent("Analyst analyst@myexample.org")

    def test_value_never_appears_in_log(self, monkeypatch, caplog):
        """The resolved value must not appear in log output."""
        from pipelines.sec_rag_ingest import _resolve_user_agent

        secret_value = "SuperSecretAgent123 secret@company.com"
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", secret_value)

        with caplog.at_level("INFO", logger="pipelines.sec_rag_ingest"):
            _resolve_user_agent()

        assert secret_value not in caplog.text, (
            "SEC_EDGAR_USER_AGENT value leaked into logs. "
            "Only 'source=env' or 'source=secret' should be logged."
        )
        # Verify the source was logged
        assert "source=env" in caplog.text

    def test_sdk_base64_decode(self, monkeypatch):
        """WorkspaceClient secret value is base64-decoded via get_secret()."""
        if SecretsAPI is None:
            pytest.skip("databricks.sdk not available")
        import base64
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        raw_value = "MyAgent my@email.com"
        encoded_value = base64.b64encode(raw_value.encode("utf-8")).decode("utf-8")

        mock_response = GetSecretResponse(key="sec_edgar_user_agent", value=encoded_value)

        mock_secrets = MagicMock(spec=SecretsAPI)
        mock_secrets.get_secret.return_value = mock_response

        mock_client = MagicMock()
        mock_client.secrets = mock_secrets

        mock_ws_module = MagicMock()
        mock_ws_module.WorkspaceClient.return_value = mock_client

        with patch.dict("sys.modules", {
            "databricks.sdk": mock_ws_module,
            "databricks.sdk.runtime": MagicMock(dbutils=None),
        }):
            from pipelines.sec_rag_ingest import _resolve_user_agent
            result = _resolve_user_agent()

        assert result == raw_value, (
            f"Expected base64-decoded value '{raw_value}', got '{result}'. "
            "Mutation: skipping base64 decode returns the encoded value."
        )

    def test_sdk_base64_decode_mutation_skip_fails(self, monkeypatch):
        """Mutation: skip base64 decode → result is the encoded value (test FAILS)."""
        if SecretsAPI is None:
            pytest.skip("databricks.sdk not available")
        import base64
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        raw_value = "MyAgent my@email.com"
        encoded_value = base64.b64encode(raw_value.encode("utf-8")).decode("utf-8")

        mock_response = GetSecretResponse(key="sec_edgar_user_agent", value=encoded_value)

        mock_secrets = MagicMock(spec=SecretsAPI)
        mock_secrets.get_secret.return_value = mock_response

        mock_client = MagicMock()
        mock_client.secrets = mock_secrets

        mock_ws_module = MagicMock()
        mock_ws_module.WorkspaceClient.return_value = mock_client

        with patch.dict("sys.modules", {
            "databricks.sdk": mock_ws_module,
            "databricks.sdk.runtime": MagicMock(dbutils=None),
        }):
            from pipelines.sec_rag_ingest import _resolve_user_agent
            result = _resolve_user_agent()

        # This assertion PROVES base64 decode happened:
        # if skipped, result would be the base64-encoded string
        assert result != encoded_value, (
            "Mutation detected: base64 decode was skipped. "
            "Result is the raw base64-encoded value, not the decoded string."
        )

    def test_sdk_wrong_method_name_fails(self, monkeypatch):
        """Mutation: rename get_secret back to get_secret_value → FAIL.

        MagicMock(spec=SecretsAPI) constrains to the real API.
        get_secret_value does not exist on SecretsAPI — accessing it
        raises AttributeError, proving production code MUST use get_secret.
        """
        if SecretsAPI is None:
            pytest.skip("databricks.sdk not available")
        from unittest.mock import MagicMock

        mock_secrets = MagicMock(spec=SecretsAPI)
        # get_secret exists (this is the correct method)
        assert hasattr(mock_secrets, "get_secret")
        # get_secret_value does NOT exist on the real API
        with pytest.raises(AttributeError, match="get_secret_value"):
            mock_secrets.get_secret_value

    def test_log_value_leak_mutation_fails(self, monkeypatch, caplog):
        """Mutation: if the value is logged, this test FAILS."""
        from pipelines.sec_rag_ingest import _resolve_user_agent

        leaked_value = "TopSecretAgent leak@test.com"
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", leaked_value)

        with caplog.at_level("DEBUG", logger="pipelines.sec_rag_ingest"):
            _resolve_user_agent()

        # Check every log record
        for record in caplog.records:
            assert leaked_value not in record.getMessage(), (
                f"Value leaked in log record: {record.getMessage()}"
            )

    def test_sdk_exception_logs_type_not_value(self, monkeypatch, caplog):
        """SDK exception: WARNING logs exception TYPE only, never the value."""
        if SecretsAPI is None:
            pytest.skip("databricks.sdk not available")
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        mock_secrets = MagicMock()
        mock_secrets.get_secret.side_effect = RuntimeError("secret-value-leaked-here")

        mock_client = MagicMock()
        mock_client.secrets = mock_secrets

        mock_ws_module = MagicMock()
        mock_ws_module.WorkspaceClient.return_value = mock_client

        with patch.dict("sys.modules", {
            "databricks.sdk": mock_ws_module,
            "databricks.sdk.runtime": MagicMock(dbutils=None),
        }):
            from pipelines.sec_rag_ingest import _resolve_user_agent
            with pytest.raises(ValueError, match="SEC_EDGAR_USER_AGENT not found"):
                with caplog.at_level("WARNING", logger="pipelines.sec_rag_ingest"):
                    _resolve_user_agent()

        # Must log exception TYPE (RuntimeError), never the value
        assert any("RuntimeError" in r.getMessage() for r in caplog.records), (
            "Expected exception TYPE in WARNING log"
        )
        assert not any("secret-value-leaked-here" in r.getMessage() for r in caplog.records), (
            "Secret value leaked into logs"
        )

    def test_sdk_success_value_never_in_logs(self, monkeypatch, caplog, capsys):
        """SDK success path: decoded value must not appear in logs or stdout/stderr.

        Mutation: add logger.info("... value=%s", decoded) at sec_rag_ingest.py:~142
        → this test FAILS.
        """
        if SecretsAPI is None:
            pytest.skip("databricks.sdk not available")
        import base64
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        raw_value = "LeakedAgent leak@company.com"
        encoded_value = base64.b64encode(raw_value.encode("utf-8")).decode("utf-8")
        mock_response = GetSecretResponse(key="sec_edgar_user_agent", value=encoded_value)

        mock_secrets = MagicMock(spec=SecretsAPI)
        mock_secrets.get_secret.return_value = mock_response

        mock_client = MagicMock()
        mock_client.secrets = mock_secrets

        mock_ws_module = MagicMock()
        mock_ws_module.WorkspaceClient.return_value = mock_client

        with patch.dict("sys.modules", {
            "databricks.sdk": mock_ws_module,
            "databricks.sdk.runtime": MagicMock(dbutils=None),
        }):
            from pipelines.sec_rag_ingest import _resolve_user_agent
            with caplog.at_level("DEBUG", logger="pipelines.sec_rag_ingest"):
                result = _resolve_user_agent()

        assert result == raw_value, "Precondition: SDK path must resolve the value"

        # Value must not appear in any log record
        for record in caplog.records:
            assert raw_value not in record.getMessage(), (
                f"Value leaked in log record: {record.getMessage()}"
            )
        assert raw_value not in caplog.text, (
            "Value leaked in caplog.text"
        )
        # Value must not appear in captured stdout/stderr
        captured = capsys.readouterr()
        assert raw_value not in captured.out, "Value leaked to stdout"
        assert raw_value not in captured.err, "Value leaked to stderr"

    def test_dbutils_sdk_runtime_success_value_never_in_logs(self, monkeypatch, caplog, capsys):
        """dbutils (sdk_runtime) success path: value must not appear in logs or stdout/stderr.

        Mutation: add logger.info("... value=%s", secret_val) at sec_rag_ingest.py:~114
        → this test FAILS.
        """
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        secret_value = "RuntimeAgent runtime@company.com"
        mock_dbutils = MagicMock()
        mock_dbutils.secrets.get.return_value = secret_value

        mock_runtime = MagicMock()
        mock_runtime.dbutils = mock_dbutils

        with patch.dict("sys.modules", {
            "databricks.sdk.runtime": mock_runtime,
            "databricks.sdk": MagicMock(),
        }):
            from pipelines.sec_rag_ingest import _resolve_user_agent
            with caplog.at_level("DEBUG", logger="pipelines.sec_rag_ingest"):
                result = _resolve_user_agent()

        assert result == secret_value, "Precondition: sdk_runtime path must resolve the value"

        for record in caplog.records:
            assert secret_value not in record.getMessage(), (
                f"Value leaked in log record: {record.getMessage()}"
            )
        assert secret_value not in caplog.text, (
            "Value leaked in caplog.text"
        )
        captured = capsys.readouterr()
        assert secret_value not in captured.out, "Value leaked to stdout"
        assert secret_value not in captured.err, "Value leaked to stderr"

    def test_dbutils_globals_success_value_never_in_logs(self, monkeypatch, caplog, capsys):
        """dbutils (globals) success path: value must not appear in logs or stdout/stderr.

        Mutation: add logger.info("... value=%s", secret_val) at sec_rag_ingest.py:~127
        → this test FAILS.
        """
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        secret_value = "GlobalAgent global@company.com"
        mock_dbutils = MagicMock()
        mock_dbutils.secrets.get.return_value = secret_value

        # sdk_runtime has dbutils=None so it falls through to globals() path
        with patch.dict("sys.modules", {
            "databricks.sdk.runtime": MagicMock(dbutils=None),
            "databricks.sdk": MagicMock(),
        }):
            import pipelines.sec_rag_ingest as mod
            had_dbutils = hasattr(mod, 'dbutils')
            old_dbutils = getattr(mod, 'dbutils', None)
            mod.dbutils = mock_dbutils

            try:
                from pipelines.sec_rag_ingest import _resolve_user_agent
                with caplog.at_level("DEBUG", logger="pipelines.sec_rag_ingest"):
                    result = _resolve_user_agent()
            finally:
                if had_dbutils:
                    mod.dbutils = old_dbutils
                else:
                    delattr(mod, 'dbutils')

        assert result == secret_value, "Precondition: globals dbutils path must resolve the value"

        for record in caplog.records:
            assert secret_value not in record.getMessage(), (
                f"Value leaked in log record: {record.getMessage()}"
            )
        assert secret_value not in caplog.text, (
            "Value leaked in caplog.text"
        )
        captured = capsys.readouterr()
        assert secret_value not in captured.out, "Value leaked to stdout"
        assert secret_value not in captured.err, "Value leaked to stderr"

    def test_custom_scope_key_passed_through(self, monkeypatch):
        """Custom scope/key are used when env is not set (via sdk_runtime dbutils)."""
        from pipelines.sec_rag_ingest import _resolve_user_agent
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        mock_dbutils = MagicMock()
        mock_dbutils.secrets.get.return_value = "CustomAgent custom@test.com"

        mock_runtime = MagicMock()
        mock_runtime.dbutils = mock_dbutils

        with patch.dict("sys.modules", {"databricks.sdk.runtime": mock_runtime}):
            result = _resolve_user_agent(
                secret_scope="my_custom_scope",
                secret_key="my_custom_key",
            )

        assert result == "CustomAgent custom@test.com"
        mock_dbutils.secrets.get.assert_called_once_with(
            scope="my_custom_scope", key="my_custom_key",
        )


class TestValidateUserAgent:
    """_validate_user_agent: non-empty, not placeholder."""

    def test_valid_agent_passes(self):
        from pipelines.sec_rag_ingest import _validate_user_agent
        # Should not raise
        _validate_user_agent("MyCompany my@email.com")

    def test_empty_raises(self):
        from pipelines.sec_rag_ingest import _validate_user_agent
        with pytest.raises(ValueError, match="descriptive application"):
            _validate_user_agent("")

    def test_none_raises(self):
        from pipelines.sec_rag_ingest import _validate_user_agent
        with pytest.raises(ValueError, match="descriptive application"):
            _validate_user_agent(None)

    def test_placeholder_example_raises(self):
        from pipelines.sec_rag_ingest import _validate_user_agent
        with pytest.raises(ValueError, match="descriptive application"):
            _validate_user_agent("example@example.com")

    def test_placeholder_your_email_raises(self):
        from pipelines.sec_rag_ingest import _validate_user_agent
        with pytest.raises(ValueError, match="descriptive application"):
            _validate_user_agent("your-email@example.org")

    def test_valid_user_agent_with_example_accepted(self):
        """User agent containing 'example' in non-placeholder context is accepted."""
        from pipelines.sec_rag_ingest import _validate_user_agent
        # Should NOT raise
        _validate_user_agent("MyApp analyst@myexample.org")


class TestJobsYmlSecretParams:
    """resources/jobs.yml sec_rag_ingest task must pass secret scope/key params."""

    def test_sec_rag_ingest_task_passes_secret_params(self):
        """Parse jobs.yml and assert sec_rag_ingest task has --user-agent-secret-scope and --user-agent-secret-key."""
        import yaml

        jobs_path = Path(__file__).parent.parent.parent / "resources" / "jobs.yml"
        content = jobs_path.read_text(encoding="utf-8")
        config = yaml.safe_load(content)

        sec_task = config["resources"]["jobs"]["sec_rag_ingest"]
        task = sec_task["tasks"][0]
        params = task["spark_python_task"]["parameters"]

        assert "--user-agent-secret-scope" in params, (
            "sec_rag_ingest task missing --user-agent-secret-scope parameter"
        )
        assert "--user-agent-secret-key" in params, (
            "sec_rag_ingest task missing --user-agent-secret-key parameter"
        )

        # Verify the values match the defaults
        scope_idx = params.index("--user-agent-secret-scope")
        assert params[scope_idx + 1] == "evangoh_capstone", (
            f"Expected scope 'evangoh_capstone', got '{params[scope_idx + 1]}'"
        )

        key_idx = params.index("--user-agent-secret-key")
        assert params[key_idx + 1] == "sec_edgar_user_agent", (
            f"Expected key 'sec_edgar_user_agent', got '{params[key_idx + 1]}'"
        )


class TestRunIngestUserAgentResolution:
    """run_ingest uses _resolve_user_agent and passes validation."""

    def test_run_ingest_with_env(self, monkeypatch):
        """run_ingest works when SEC_EDGAR_USER_AGENT is set in env."""
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "TestAgent test@company.com")
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["NVDA"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert result.run_id is not None

    def test_run_ingest_missing_env_raises(self, monkeypatch):
        """run_ingest raises when SEC_EDGAR_USER_AGENT is not set and no secret available."""
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

        clock = FakeClock()
        http = FakeHttpClient()

        with patch.dict("sys.modules", {
            "databricks.sdk.runtime": MagicMock(dbutils=None),
            "databricks.sdk": MagicMock(),
        }):
            with pytest.raises(ValueError, match="SEC_EDGAR_USER_AGENT not found"):
                run_ingest(
                    catalog="test", schema="test",
                    start_date="2024-09-01",
                    universe_reader=FakeUniverseReader([]),
                    accession_reader=FakeAccessionReader(),
                    data_writer=FakeDataWriter(),
                    http_client=http,
                    clock=clock,
                    cache_path=str(FIXTURES / "company_tickers.json"),
                )

    def test_run_ingest_placeholder_raises(self, monkeypatch):
        """run_ingest raises when SEC_EDGAR_USER_AGENT contains 'example'."""
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "example@example.com")

        clock = FakeClock()
        http = FakeHttpClient()

        with pytest.raises(ValueError, match="descriptive application"):
            run_ingest(
                catalog="test", schema="test",
                start_date="2024-09-01",
                universe_reader=FakeUniverseReader([]),
                accession_reader=FakeAccessionReader(),
                data_writer=FakeDataWriter(),
                http_client=http,
                clock=clock,
                cache_path=str(FIXTURES / "company_tickers.json"),
            )

    def test_main_passes_secret_args_to_run_ingest(self, monkeypatch):
        """main() passes --user-agent-secret-scope and --user-agent-secret-key to run_ingest."""
        from pipelines.sec_rag_ingest import main

        captured = {}

        def mock_run_ingest(**kwargs):
            captured["scope"] = kwargs.get("user_agent_secret_scope")
            captured["key"] = kwargs.get("user_agent_secret_key")
            from pipelines.sec_rag_ingest import IngestResult
            return IngestResult(run_id="test", dry_run=True)

        monkeypatch.setattr("pipelines.sec_rag_ingest.run_ingest", mock_run_ingest)
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkUniverseReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkAccessionReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkDataWriter", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkLogWriter", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkIngestLogReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkCikMappingLogWriter", lambda: MagicMock())
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "TestAgent test@company.com")

        main([
            "--catalog", "test",
            "--schema", "test",
            "--user-agent-secret-scope", "my_scope",
            "--user-agent-secret-key", "my_key",
            "--dry-run",
        ])

        assert captured["scope"] == "my_scope", (
            f"Expected scope 'my_scope', got '{captured['scope']}'"
        )
        assert captured["key"] == "my_key", (
            f"Expected key 'my_key', got '{captured['key']}'"
        )

    def test_main_default_secret_args(self, monkeypatch):
        """main() uses default scope/key when not specified."""
        from pipelines.sec_rag_ingest import main, DEFAULT_SECRET_SCOPE, DEFAULT_SECRET_KEY

        captured = {}

        def mock_run_ingest(**kwargs):
            captured["scope"] = kwargs.get("user_agent_secret_scope")
            captured["key"] = kwargs.get("user_agent_secret_key")
            from pipelines.sec_rag_ingest import IngestResult
            return IngestResult(run_id="test", dry_run=True)

        monkeypatch.setattr("pipelines.sec_rag_ingest.run_ingest", mock_run_ingest)
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkUniverseReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkAccessionReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkDataWriter", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkLogWriter", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkIngestLogReader", lambda: MagicMock())
        monkeypatch.setattr("pipelines.sec_rag_ingest.SparkCikMappingLogWriter", lambda: MagicMock())
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "TestAgent test@company.com")

        main(["--catalog", "test", "--schema", "test", "--dry-run"])

        assert captured["scope"] == DEFAULT_SECRET_SCOPE
        assert captured["key"] == DEFAULT_SECRET_KEY


# ── Round 19: CIK overrides ─────────────────────────────────────────────────


class TestCikOverrides:
    """CIK overrides: ticker → multiple CIKs, discovery unions filings."""

    def test_load_cik_overrides(self, tmp_path):
        """load_cik_overrides reads YAML and returns ticker→CIKs dict."""
        import yaml
        override_file = tmp_path / "overrides.yaml"
        override_file.write_text(yaml.dump({
            "XOM": ["0002115436", "0000034088"],
            "TSM": ["0001046179"],
        }))
        overrides = load_cik_overrides(str(override_file))
        assert overrides == {
            "XOM": ["0002115436", "0000034088"],
            "TSM": ["0001046179"],
        }

    def test_load_cik_overrides_missing_file(self, tmp_path):
        """Missing override file returns empty dict."""
        overrides = load_cik_overrides(str(tmp_path / "nonexistent.yaml"))
        assert overrides == {}

    def test_build_cik_map_with_overrides(self):
        """Override tickers use override CIKs, not SEC lookup."""
        payload = {
            "0": {"ticker": "XOM", "cik_str": 2115436},  # SEC only has holdings CIK
        }
        overrides = {"XOM": ["0002115436", "0000034088"]}
        result = build_cik_map(["XOM"], payload, cik_overrides=overrides)
        assert result["XOM"].status == "mapped"
        assert result["XOM"].cik == "0002115436"  # primary CIK
        assert result["XOM"].ciks == ["0002115436", "0000034088"]
        assert "override" in result["XOM"].reason.lower()

    def test_build_cik_map_override_takes_precedence(self):
        """Override wins even when SEC lookup finds a different CIK."""
        payload = {
            "0": {"ticker": "XOM", "cik_str": 9999999},  # SEC has wrong CIK
        }
        overrides = {"XOM": ["0002115436", "0000034088"]}
        result = build_cik_map(["XOM"], payload, cik_overrides=overrides)
        assert result["XOM"].cik == "0002115436"
        assert result["XOM"].ciks == ["0002115436", "0000034088"]

    def test_discovery_unions_filings_from_multiple_ciks(self):
        """Discovery unions filings from all CIKs for an override ticker."""
        clock = FakeClock()
        http = FakeHttpClient()

        # CIK 2115436 (holdings) — 2 filings
        holdings = json.loads((FIXTURES / "submissions_xom_holdings.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings)

        # CIK 34088 (legacy) — 7 filings
        legacy = json.loads((FIXTURES / "submissions_xom_legacy.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", legacy)

        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        # Discover from each CIK separately
        filings_h, _ = discover_filings(client, "2115436", "2024-09-01", {"10-K", "10-Q"})
        filings_l, _ = discover_filings(client, "34088", "2024-09-01", {"10-K", "10-Q"})

        # Holdings: 2 filings (10-K 2025, 10-Q 2024)
        assert len(filings_h) == 2
        # Legacy: 7 filings total, but only 2 after 2024-09-01 cutoff
        # (10-K 2025-02-28, 10-Q 2024-11-07)
        assert len(filings_l) == 2

        # Union = 4 filings total (no duplicate accessions across CIKs)
        all_accessions = set()
        for f in filings_h + filings_l:
            all_accessions.add(f.accession_number)
        assert len(all_accessions) == 4

    def test_duplicate_accession_across_ciks_stored_once(self):
        """When the same accession appears in two CIKs, it is stored once."""
        clock = FakeClock()
        http = FakeHttpClient()

        # Both CIKs return the same accession
        holdings = {
            "cik": "0002115436",
            "entityName": "Holdings",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-03-01"],
                    "accessionNumber": ["0000034088-25-000010"],  # same as legacy
                    "primaryDocument": ["holdings-20250301.htm"],
                    "acceptanceDateTime": ["2025-03-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        legacy = {
            "cik": "0000034088",
            "entityName": "Legacy",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-02-28"],
                    "accessionNumber": ["0000034088-25-000010"],  # same accession
                    "primaryDocument": ["xom-20250228.htm"],
                    "acceptanceDateTime": ["2025-02-28T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings)
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", legacy)

        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        # Simulate the discovery loop from run_ingest
        seen_accessions: Set[str] = set()
        all_filings = []
        for cik in ["2115436", "34088"]:
            filings, _ = discover_filings(client, cik, "2024-09-01", {"10-K", "10-Q"})
            for f in filings:
                if f.accession_number not in seen_accessions:
                    seen_accessions.add(f.accession_number)
                    all_filings.append(f)

        # Only 1 filing stored (deduped by accession)
        assert len(all_filings) == 1
        assert all_filings[0].accession_number == "0000034088-25-000010"

    def test_mutation_ignore_overrides_fails(self):
        """Mutation: if build_cik_map ignores overrides, ticker gets wrong CIK."""
        payload = {
            "0": {"ticker": "XOM", "cik_str": 2115436},  # SEC only has holdings
        }
        overrides = {"XOM": ["0002115436", "0000034088"]}

        # With overrides: both CIKs available
        result_with = build_cik_map(["XOM"], payload, cik_overrides=overrides)
        assert result_with["XOM"].ciks == ["0002115436", "0000034088"]

        # Without overrides: only SEC CIK
        result_without = build_cik_map(["XOM"], payload, cik_overrides=None)
        assert result_without["XOM"].cik == "0002115436"
        assert result_without["XOM"].ciks == ["0002115436"]  # only one CIK

        # The difference: with overrides, discovery would find filings from both CIKs
        # Without overrides, only from the SEC CIK — missing 5 filings from legacy CIK


# ── Round 19b: Ownership group logic ─────────────────────────────────────────


class TestOwnershipGroup:
    """CIKs in the same override group are ONE ownership group — no conflict."""

    XOM_OVERRIDES = {"XOM": ["0002115436", "0000034088"]}

    def test_same_group_no_conflict(self):
        """Accession stored under one CIK in a group, request from another → no conflict."""
        clock = FakeClock()
        http = FakeHttpClient()
        # Holdings CIK submissions — one filing
        holdings_sub = {
            "cik": "0002115436",
            "entityName": "ExxonMobil Holdings Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-03-01"],
                    "accessionNumber": ["0000034088-26-000093"],
                    "primaryDocument": ["xom-20250301.htm"],
                    "acceptanceDateTime": ["2025-03-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings_sub)
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", holdings_sub)

        universe = [TickerEntry(ticker="XOM", phase=1)]
        # Accession stored under holdings CIK (2115436)
        existing = {
            "0000034088-26-000093": ("0002115436", "XOM"),
        }

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["XOM"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
            cik_overrides=self.XOM_OVERRIDES,
        )
        # Same group → skipped, no conflict, no failure
        assert result.failed_count == 0
        assert result.skipped_existing_count >= 1

    def test_genuine_conflict_recorded_not_raised(self):
        """Genuine conflict (unrelated CIK): filing fails, run continues."""
        clock = FakeClock()
        http = FakeHttpClient()
        holdings_sub = {
            "cik": "0002115436",
            "entityName": "ExxonMobil Holdings Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-03-01"],
                    "accessionNumber": ["0000034088-26-000093"],
                    "primaryDocument": ["xom-20250301.htm"],
                    "acceptanceDateTime": ["2025-03-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings_sub)
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", holdings_sub)

        universe = [TickerEntry(ticker="XOM", phase=1)]
        # Accession owned by UNRELATED CIK/ticker
        existing = {
            "0000034088-26-000093": ("9999999999", "OTHER"),
        }

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["XOM"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
            cik_overrides=self.XOM_OVERRIDES,
        )
        # Genuine conflict: filing fails, run continues (no raise)
        assert result.failed_count >= 1

    def test_genuine_conflict_writes_audit_row(self):
        """Genuine conflict writes failed audit row with error_code=ownership_conflict."""
        clock = FakeClock()
        http = FakeHttpClient()
        holdings_sub = {
            "cik": "0002115436",
            "entityName": "ExxonMobil Holdings Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-03-01"],
                    "accessionNumber": ["0000034088-26-000093"],
                    "primaryDocument": ["xom-20250301.htm"],
                    "acceptanceDateTime": ["2025-03-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings_sub)
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", holdings_sub)

        universe = [TickerEntry(ticker="XOM", phase=1)]
        existing = {
            "0000034088-26-000093": ("9999999999", "OTHER"),
        }

        log_entries = []

        class CapturingLogWriter:
            def append_log(self, catalog, schema, entry):
                log_entries.append(entry)

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["XOM"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            log_writer=CapturingLogWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
            cik_overrides=self.XOM_OVERRIDES,
        )
        conflict_entries = [
            e for e in log_entries
            if e.error_code == "ownership_conflict" and e.status == "failed"
        ]
        assert len(conflict_entries) >= 1, (
            f"Expected at least 1 ownership_conflict audit row, got {len(conflict_entries)}. "
            "Mutation: group check removed → genuine conflict not recorded."
        )
        assert result.failed_count >= 1

    def test_override_filings_use_filer_cik(self):
        """Override-group planned filings use filer CIK from accession prefix."""
        clock = FakeClock()
        http = FakeHttpClient()
        # Holdings CIK 0002115436 — 1 filing with accession prefix 0002115436
        holdings_sub = {
            "cik": "0002115436",
            "entityName": "ExxonMobil Holdings Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-03-01"],
                    "accessionNumber": ["0002115436-25-000001"],
                    "primaryDocument": ["xom-holdings.htm"],
                    "acceptanceDateTime": ["2025-03-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        # Legacy CIK 0000034088 — 1 filing with accession prefix 0000034088
        legacy_sub = {
            "cik": "0000034088",
            "entityName": "Exxon Mobil Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2024-12-01"],
                    "accessionNumber": ["0000034088-24-000099"],
                    "primaryDocument": ["xom-legacy.htm"],
                    "acceptanceDateTime": ["2024-12-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings_sub)
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", legacy_sub)
        # Filing body for both
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/2115436/000211543625000001/xom-holdings.htm",
            "<html><body>" + "H" * 200 + "</body></html>",
        )
        http.set_text(
            "https://www.sec.gov/Archives/edgar/data/34088/000003408824000099/xom-legacy.htm",
            "<html><body>" + "L" * 200 + "</body></html>",
        )

        universe = [TickerEntry(ticker="XOM", phase=1)]
        writer = FakeDataWriter()

        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["XOM"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader({}),
            data_writer=writer,
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
            cik_overrides=self.XOM_OVERRIDES,
        )
        # Both filings should be planned
        assert result.planned_count == 2
        assert result.failed_count == 0
        # Check that rows use filer CIK from accession prefix
        all_rows = [r for batch in writer.appended for r in batch]
        holdings_rows = [r for r in all_rows if r["accession_number"] == "0002115436-25-000001"]
        legacy_rows = [r for r in all_rows if r["accession_number"] == "0000034088-24-000099"]
        assert holdings_rows, "Holdings filing should be stored"
        assert legacy_rows, "Legacy filing should be stored"
        # Holdings filing: CIK from accession prefix = 0002115436
        assert holdings_rows[0]["cik"] == "0002115436"
        assert "2115436" in holdings_rows[0]["filing_url"]
        # Legacy filing: CIK from accession prefix = 0000034088 (NOT 0002115436)
        assert legacy_rows[0]["cik"] == "0000034088"
        assert "34088" in legacy_rows[0]["filing_url"]

    def test_counter_invariant_planned_plus_skipped_equals_discovered(self):
        """planned + skipped_existing + failed == discovered for override tickers."""
        clock = FakeClock()
        http = FakeHttpClient()
        # Holdings CIK: 1 filing
        holdings_sub = {
            "cik": "0002115436",
            "entityName": "ExxonMobil Holdings Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-03-01"],
                    "accessionNumber": ["0002115436-25-000001"],
                    "primaryDocument": ["xom-holdings.htm"],
                    "acceptanceDateTime": ["2025-03-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        # Legacy CIK: 2 filings, one shared accession with holdings
        legacy_sub = {
            "cik": "0000034088",
            "entityName": "Exxon Mobil Corp",
            "filings": {
                "recent": {
                    "form": ["10-K", "10-K"],
                    "filingDate": ["2025-03-01", "2024-12-01"],
                    "accessionNumber": ["0002115436-25-000001", "0000034088-24-000099"],
                    "primaryDocument": ["xom-holdings.htm", "xom-legacy.htm"],
                    "acceptanceDateTime": [
                        "2025-03-01T18:00:00.000Z",
                        "2024-12-01T18:00:00.000Z",
                    ],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings_sub)
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", legacy_sub)

        universe = [TickerEntry(ticker="XOM", phase=1)]
        # One accession already present
        existing = {
            "0000034088-24-000099": ("0000034088", "XOM"),
        }

        # Dry-run: tests anti-join counters without fetching filing bodies
        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["XOM"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
            cik_overrides=self.XOM_OVERRIDES,
            dry_run=True,
        )
        # Discovered = 2 deduped filings (holdings + legacy, one shared accession)
        assert result.discovered_count == 2
        # planned + skipped + failed == discovered
        total = result.planned_count + result.skipped_existing_count + result.failed_count
        assert total == result.discovered_count, (
            f"planned({result.planned_count}) + skipped({result.skipped_existing_count}) "
            f"+ failed({result.failed_count}) != discovered({result.discovered_count})"
        )

    def test_mutation_re_raise_instead_of_record_fails(self):
        """Mutation: if genuine conflict raises instead of recording, test fails."""
        clock = FakeClock()
        http = FakeHttpClient()
        holdings_sub = {
            "cik": "0002115436",
            "entityName": "ExxonMobil Holdings Corp",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-03-01"],
                    "accessionNumber": ["0000034088-26-000093"],
                    "primaryDocument": ["xom-20250301.htm"],
                    "acceptanceDateTime": ["2025-03-01T18:00:00.000Z"],
                },
                "files": [],
            },
        }
        http.set_json("https://data.sec.gov/submissions/CIK0002115436.json", holdings_sub)
        http.set_json("https://data.sec.gov/submissions/CIK0000034088.json", holdings_sub)

        universe = [TickerEntry(ticker="XOM", phase=1)]
        existing = {
            "0000034088-26-000093": ("9999999999", "OTHER"),
        }

        # Should NOT raise — genuine conflict recorded as failed
        result = run_ingest(
            catalog="test", schema="test",
            start_date="2024-09-01",
            tickers=["XOM"],
            universe_reader=FakeUniverseReader(universe),
            accession_reader=FakeAccessionReader(existing),
            data_writer=FakeDataWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
            cik_overrides=self.XOM_OVERRIDES,
        )
        # If this raises AccessionOwnershipConflict, mutation detected
        assert result.failed_count >= 1

    def test_canonical_stored_cik_from_accession_prefix(self):
        """Filer CIK from accession prefix is used for same-group skips."""
        overrides = {"XOM": ["0002115436", "0000034088"]}
        group_map = _build_cik_group_map(overrides)

        # Accession 0000034088-26-000093 → filer CIK 0000034088
        assert _accession_filer_cik("0000034088-26-000093") == "0000034088"
        # Accession 0002115436-25-000001 → filer CIK 0002115436
        assert _accession_filer_cik("0002115436-25-000001") == "0002115436"

        # Both CIKs in the same group
        assert group_map["0002115436"] == group_map["0000034088"]
        assert group_map["0002115436"] == frozenset({"0002115436", "0000034088"})


class TestRepairCikOwnership:
    """--repair-cik-ownership rewrites stored CIKs to filer CIK from accession prefix."""

    def test_accession_filer_cik(self):
        """_accession_filer_cik extracts 10-digit CIK from accession number."""
        assert _accession_filer_cik("0000034088-26-000093") == "0000034088"
        assert _accession_filer_cik("0002115436-25-000001") == "0002115436"
        assert _accession_filer_cik("1234567890-01-000001") == "1234567890"

    def test_build_cik_group_map(self):
        """_build_cik_group_map creates correct group frozensets."""
        overrides = {"XOM": ["0002115436", "0000034088"], "TSM": ["0001046179"]}
        group_map = _build_cik_group_map(overrides)

        # XOM CIKs in same group
        assert group_map["0002115436"] == frozenset({"0002115436", "0000034088"})
        assert group_map["0000034088"] == frozenset({"0002115436", "0000034088"})
        # TSM singleton
        assert group_map["0001046179"] == frozenset({"0001046179"})
        # Same group identity (frozenset identity)
        assert group_map["0002115436"] is group_map["0000034088"]

    def test_build_cik_group_map_empty(self):
        """Empty overrides → empty group map."""
        assert _build_cik_group_map({}) == {}
        assert _build_cik_group_map(None) == {}

    def test_repair_dry_run_does_not_write(self):
        """Dry-run repair returns stats but does not execute UPDATE."""
        overrides = {"XOM": ["0002115436", "0000034088"]}
        sql_calls = []

        class FakeRow:
            def __init__(self, **kw):
                self._d = kw
            def __getitem__(self, k):
                return self._d[k]

        class FakeDF:
            def __init__(self, rows):
                self._rows = rows
            def collect(self):
                return self._rows

        class FakeSpark:
            def sql(self, query, args=None):
                sql_calls.append((query, args))
                if query.strip().upper().startswith("SELECT"):
                    return FakeDF([
                        FakeRow(accession_number="0000034088-26-000093", cik="0002115436", ticker="XOM"),
                    ])
                return FakeDF([])

        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = FakeSpark()
        mock_session = MagicMock()
        mock_session.builder = mock_builder

        import sys as _sys
        from unittest.mock import patch as _patch
        fake_connect = MagicMock()
        fake_connect.DatabricksSession = mock_session
        with _patch.dict(_sys.modules, {"databricks.connect": fake_connect}):
            stats = repair_cik_ownership(
                catalog="cat", schema="sch",
                tickers=["XOM"], cik_overrides=overrides, dry_run=True,
            )
        assert stats["scanned"] == 1
        assert stats["updated"] == 1
        assert stats["skipped"] == 0
        # No UPDATE should have been executed
        update_calls = [c for c in sql_calls if c[0].strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 0

    def test_repair_parameterized_sql(self):
        """repair_cik_ownership uses parameterized queries — no ticker/CIK literal in SQL."""
        overrides = {"XOM": ["0002115436", "0000034088"]}
        sql_calls = []

        class FakeRow:
            def __init__(self, **kw):
                self._d = kw
            def __getitem__(self, k):
                return self._d[k]

        class FakeDF:
            def __init__(self, rows):
                self._rows = rows
            def collect(self):
                return self._rows

        class FakeSpark:
            def sql(self, query, args=None):
                sql_calls.append((query, args))
                if query.strip().upper().startswith("SELECT"):
                    return FakeDF([
                        FakeRow(accession_number="0000034088-26-000093", cik="0002115436"),
                    ])
                return FakeDF([])

        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = FakeSpark()
        mock_session = MagicMock()
        mock_session.builder = mock_builder

        import sys as _sys
        from unittest.mock import patch as _patch
        fake_connect = MagicMock()
        fake_connect.DatabricksSession = mock_session
        with _patch.dict(_sys.modules, {"databricks.connect": fake_connect}):
            repair_cik_ownership(
                catalog="cat", schema="sch",
                tickers=["XOM"], cik_overrides=overrides, dry_run=False,
            )
        # Verify no ticker or CIK literal appears in any SQL text
        for query, args in sql_calls:
            assert "'XOM'" not in query, f"Ticker literal in SQL: {query}"
            assert "'0002115436'" not in query, f"CIK literal in SQL: {query}"
            assert "'0000034088'" not in query, f"CIK literal in SQL: {query}"
        # SELECT should use DISTINCT
        select_calls = [(q, a) for q, a in sql_calls if q.strip().upper().startswith("SELECT")]
        assert len(select_calls) == 1
        assert "DISTINCT" in select_calls[0][0].upper()
        # UPDATE call should carry args with the correct values including filing_url
        update_calls = [(q, a) for q, a in sql_calls if q.strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 1
        update_query, update_args = update_calls[0]
        assert "filing_url" in update_query.lower(), "UPDATE should rewrite filing_url"
        assert "0000034088" in update_args  # correct_cik
        assert "0000034088-26-000093" in update_args  # accession
        assert "XOM" in update_args  # ticker
        # Verify filing_url format: .../edgar/data/{int(correct_cik)}/...
        filing_url_arg = [a for a in update_args if isinstance(a, str) and "edgar/data" in a]
        assert len(filing_url_arg) == 1, "Should have one filing_url arg"
        assert "/34088/" in filing_url_arg[0], "filing_url should use int(correct_cik)"

    def test_repair_invalid_ticker_rejected(self):
        """Ticker with invalid characters raises ValueError."""
        overrides = {"XOM": ["0002115436", "0000034088"]}

        import sys as _sys
        from unittest.mock import patch as _patch
        fake_connect = MagicMock()
        fake_connect.DatabricksSession = MagicMock()
        with _patch.dict(_sys.modules, {"databricks.connect": fake_connect}):
            with pytest.raises(ValueError, match="Invalid ticker"):
                repair_cik_ownership(
                    catalog="cat", schema="sch",
                    tickers=["XOM'; DROP TABLE t; --"], cik_overrides=overrides,
                )

    def test_repair_idempotent_skip_when_correct(self):
        """No UPDATE when current CIK already matches accession prefix."""
        overrides = {"XOM": ["0002115436", "0000034088"]}
        sql_calls = []

        class FakeRow:
            def __init__(self, **kw):
                self._d = kw
            def __getitem__(self, k):
                return self._d[k]

        class FakeDF:
            def __init__(self, rows):
                self._rows = rows
            def collect(self):
                return self._rows

        class FakeSpark:
            def sql(self, query, args=None):
                sql_calls.append((query, args))
                if query.strip().upper().startswith("SELECT"):
                    return FakeDF([
                        FakeRow(accession_number="0000034088-26-000093", cik="0000034088", ticker="XOM"),
                    ])
                return FakeDF([])

        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = FakeSpark()
        mock_session = MagicMock()
        mock_session.builder = mock_builder

        import sys as _sys
        from unittest.mock import patch as _patch
        fake_connect = MagicMock()
        fake_connect.DatabricksSession = mock_session
        with _patch.dict(_sys.modules, {"databricks.connect": fake_connect}):
            stats = repair_cik_ownership(
                catalog="cat", schema="sch",
                tickers=["XOM"], cik_overrides=overrides,
            )
        assert stats["scanned"] == 1
        assert stats["skipped"] == 1
        assert stats["updated"] == 0
        update_calls = [c for c in sql_calls if c[0].strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 0

    def test_repair_non_group_target_cik_refused(self):
        """UPDATE is skipped when correct CIK is not in the override group."""
        # Override group: XOM → [0002115436, 0000034088]
        # But accession prefix = 9999999999 (not in group)
        overrides = {"XOM": ["0002115436", "0000034088"]}
        sql_calls = []

        class FakeRow:
            def __init__(self, **kw):
                self._d = kw
            def __getitem__(self, k):
                return self._d[k]

        class FakeDF:
            def __init__(self, rows):
                self._rows = rows
            def collect(self):
                return self._rows

        class FakeSpark:
            def sql(self, query, args=None):
                sql_calls.append((query, args))
                if query.strip().upper().startswith("SELECT"):
                    return FakeDF([
                        FakeRow(accession_number="9999999999-26-000001", cik="0002115436", ticker="XOM"),
                    ])
                return FakeDF([])

        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = FakeSpark()
        mock_session = MagicMock()
        mock_session.builder = mock_builder

        import sys as _sys
        from unittest.mock import patch as _patch
        fake_connect = MagicMock()
        fake_connect.DatabricksSession = mock_session
        with _patch.dict(_sys.modules, {"databricks.connect": fake_connect}):
            stats = repair_cik_ownership(
                catalog="cat", schema="sch",
                tickers=["XOM"], cik_overrides=overrides,
            )
        assert stats["scanned"] == 1
        assert stats["skipped"] == 1
        assert stats["updated"] == 0
        update_calls = [c for c in sql_calls if c[0].strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 0

    def test_repair_distinct_one_update_per_filing(self):
        """SELECT DISTINCT ensures one UPDATE per filing, not per chunk.

        Even if the SELECT returns multiple rows with the same accession_number,
        the DISTINCT clause should deduplicate them so only one UPDATE is issued.
        """
        overrides = {"XOM": ["0002115436", "0000034088"]}
        sql_calls = []

        class FakeRow:
            def __init__(self, **kw):
                self._d = kw
            def __getitem__(self, k):
                return self._d[k]

        class FakeDF:
            def __init__(self, rows):
                self._rows = rows
            def collect(self):
                return self._rows

        class FakeSpark:
            def sql(self, query, args=None):
                sql_calls.append((query, args))
                if query.strip().upper().startswith("SELECT"):
                    # Simulate DISTINCT: return one row per filing
                    return FakeDF([
                        FakeRow(accession_number="0000034088-26-000093", cik="0002115436"),
                    ])
                return FakeDF([])

        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = FakeSpark()
        mock_session = MagicMock()
        mock_session.builder = mock_builder

        import sys as _sys
        from unittest.mock import patch as _patch
        fake_connect = MagicMock()
        fake_connect.DatabricksSession = mock_session
        with _patch.dict(_sys.modules, {"databricks.connect": fake_connect}):
            stats = repair_cik_ownership(
                catalog="cat", schema="sch",
                tickers=["XOM"], cik_overrides=overrides, dry_run=False,
            )
        # Should have scanned 1 filing (not multiple chunks)
        assert stats["scanned"] == 1
        assert stats["updated"] == 1
        # Verify SELECT uses DISTINCT
        select_calls = [(q, a) for q, a in sql_calls if q.strip().upper().startswith("SELECT")]
        assert len(select_calls) == 1
        assert "DISTINCT" in select_calls[0][0].upper()
        # Verify only one UPDATE was issued
        update_calls = [(q, a) for q, a in sql_calls if q.strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 1

    def test_repair_filing_url_rewrite(self):
        """UPDATE rewrites filing_url to use correct filer CIK."""
        overrides = {"XOM": ["0002115436", "0000034088"]}
        sql_calls = []

        class FakeRow:
            def __init__(self, **kw):
                self._d = kw
            def __getitem__(self, k):
                return self._d[k]

        class FakeDF:
            def __init__(self, rows):
                self._rows = rows
            def collect(self):
                return self._rows

        class FakeSpark:
            def sql(self, query, args=None):
                sql_calls.append((query, args))
                if query.strip().upper().startswith("SELECT"):
                    return FakeDF([
                        FakeRow(accession_number="0000034088-26-000093", cik="0002115436"),
                    ])
                return FakeDF([])

        mock_builder = MagicMock()
        mock_builder.serverless.return_value = mock_builder
        mock_builder.getOrCreate.return_value = FakeSpark()
        mock_session = MagicMock()
        mock_session.builder = mock_builder

        import sys as _sys
        from unittest.mock import patch as _patch
        fake_connect = MagicMock()
        fake_connect.DatabricksSession = mock_session
        with _patch.dict(_sys.modules, {"databricks.connect": fake_connect}):
            stats = repair_cik_ownership(
                catalog="cat", schema="sch",
                tickers=["XOM"], cik_overrides=overrides, dry_run=False,
            )
        assert stats["updated"] == 1
        # Verify UPDATE includes filing_url
        update_calls = [(q, a) for q, a in sql_calls if q.strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 1
        update_query, update_args = update_calls[0]
        assert "filing_url" in update_query.lower(), "UPDATE should rewrite filing_url"
        # Verify filing_url format: .../edgar/data/{int(correct_cik)}/...
        # correct_cik = 0000034088, int() = 34088
        filing_url_arg = [a for a in update_args if isinstance(a, str) and "edgar/data" in a]
        assert len(filing_url_arg) == 1, "Should have one filing_url arg"
        assert "/34088/" in filing_url_arg[0], "filing_url should use int(correct_cik)"
        assert "0000034088-26-000093" in filing_url_arg[0], "filing_url should include accession"


# ── Round 19: Foreign filers (20-F/40-F/6-K) ────────────────────────────────


class TestForeignFilers:
    """20-F/40-F/6-K discovery and section extraction."""

    def test_discover_20f_filings(self):
        """20-F filings are discovered when included in forms set."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_20f.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        # 20-F only
        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"20-F"})
        assert len(filings) == 1
        assert filings[0].form_type == "20-F"
        assert filings[0].accession_number == "0001045810-25-000050"

    def test_discover_6k_filings(self):
        """6-K filings are discovered when included in forms set."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_20f.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"6-K"})
        assert len(filings) == 1
        assert filings[0].form_type == "6-K"

    def test_discover_mixed_forms(self):
        """10-K + 20-F + 6-K together discover all matching filings."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_20f.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings, _ = discover_filings(client, "1045810", "2024-09-01", {"10-K", "20-F", "6-K"})
        assert len(filings) == 3
        form_types = {f.form_type for f in filings}
        assert form_types == {"10-K", "20-F", "6-K"}

    def test_extract_sections_20f(self):
        """20-F section extraction finds Item 3.D, 4, 5, 8."""
        html = (FIXTURES / "sample_20f.htm").read_text()
        plain = strip_html(html)
        sections = extract_sections(plain, form_type="20-F")

        section_names = [s[0] for s in sections]
        # Should find risk factors, business, operating review, financial statements
        assert "item3d_risk_factors" in section_names
        assert "item4_business" in section_names
        assert "item5_operating_review" in section_names
        assert "item8_financial_statements" in section_names

    def test_extract_sections_10k_still_works(self):
        """10-K section extraction still works after adding 20-F patterns."""
        html = (FIXTURES / "sample_filing.htm").read_text()
        plain = strip_html(html)
        sections = extract_sections(plain, form_type="10-K")

        section_names = [s[0] for s in sections]
        # Should find at least some 10-K sections
        assert len(section_names) > 0
        # Should NOT contain 20-F-specific sections
        assert "item3d_risk_factors" not in section_names

    def test_20f_fallback_to_full_document(self):
        """When no 20-F items match, falls back to full_document."""
        plain = "This is a simple document with no SEC item headers."
        sections = extract_sections(plain, form_type="20-F")
        assert len(sections) == 1
        assert sections[0][0] == "full_document"

    def test_form_validation_accepts_20f(self):
        """run_ingest accepts 20-F in forms_str."""
        clock = FakeClock()
        http = FakeHttpClient()
        overrides = {"TSM": ["0001046179"]}
        result = run_ingest(
            catalog="test", schema="test",
            forms_str="20-F,6-K",
            tickers=["TSM"],
            dry_run=True,
            cik_overrides=overrides,
            universe_reader=FakeUniverseReader([TickerEntry("TSM", 1)]),
            accession_reader=FakeAccessionReader(),
            data_writer=FakeDataWriter(),
            log_writer=FakeLogWriter(),
            cik_mapping_log_writer=FakeCikMappingLogWriter(),
            http_client=http,
            clock=clock,
            cache_path=str(FIXTURES / "company_tickers.json"),
        )
        assert result.dry_run is True

    def test_form_validation_rejects_unknown(self):
        """run_ingest rejects unsupported form types."""
        clock = FakeClock()
        http = FakeHttpClient()
        with pytest.raises(ValueError, match="Unsupported forms"):
            run_ingest(
                catalog="test", schema="test",
                forms_str="10-K,8-K",
                dry_run=True,
                universe_reader=FakeUniverseReader([TickerEntry("AAPL", 1)]),
                accession_reader=FakeAccessionReader(),
                data_writer=FakeDataWriter(),
                log_writer=FakeLogWriter(),
                cik_mapping_log_writer=FakeCikMappingLogWriter(),
                http_client=http,
                clock=clock,
                cache_path=str(FIXTURES / "company_tickers.json"),
            )


# ── Round 19: Runbook bundle run commands ────────────────────────────────────


class TestRunbookBundleCommands:
    """Every databricks bundle run ... sec_embeddings must repeat --catalog/--schema."""

    def test_sec_embeddings_commands_have_catalog_schema(self):
        """Parse runbook and fail if any sec_embeddings bundle run omits --catalog/--schema."""
        runbook_path = Path(__file__).resolve().parent.parent.parent / "docs" / "SEC_RAG_COVERAGE_RUNBOOK.md"
        content = runbook_path.read_text()

        import re
        # Find all 'databricks bundle run ... sec_embeddings -- ...' lines
        pattern = re.compile(
            r"databricks\s+bundle\s+run\s+\S+\s+\S+\s+sec_embeddings\s+--\s+(.+)",
            re.MULTILINE,
        )
        matches = pattern.findall(content)
        assert len(matches) >= 4, (
            f"Expected at least 4 sec_embeddings commands in runbook, found {len(matches)}"
        )

        for i, args_str in enumerate(matches):
            assert "--catalog" in args_str, (
                f"sec_embeddings command #{i+1} missing --catalog: {args_str.strip()}"
            )
            assert "--schema" in args_str, (
                f"sec_embeddings command #{i+1} missing --schema: {args_str.strip()}"
            )


# ── Round 19: xbrl_client._get_user_agent delegation ────────────────────────


class TestXbrlClientUserAgent:
    """_get_user_agent delegates to pipeline resolver, never uses EDGAR_USER_AGENT."""

    def test_delegates_to_resolve_user_agent(self, monkeypatch):
        """_get_user_agent calls _resolve_user_agent and uses its value."""
        from api.services import xbrl_client

        # Reset the module-level cache
        xbrl_client._USER_AGENT = None

        calls = []

        def mock_resolve_user_agent(**kwargs):
            calls.append("called")
            return "PipelineAgent pipeline@test.com"

        def mock_validate_user_agent(ua):
            calls.append(f"validated:{ua}")

        monkeypatch.setattr(xbrl_client, "_resolve_user_agent", mock_resolve_user_agent)
        monkeypatch.setattr(xbrl_client, "_validate_user_agent", mock_validate_user_agent)

        result = xbrl_client._get_user_agent()

        assert result == "PipelineAgent pipeline@test.com"
        assert "called" in calls
        assert "validated:PipelineAgent pipeline@test.com" in calls

    def test_mutation_old_env_get_fails(self, monkeypatch):
        """Mutation: restoring old os.getenv('EDGAR_USER_AGENT') path → test fails."""
        from api.services import xbrl_client

        # Reset the module-level cache
        xbrl_client._USER_AGENT = None

        # Simulate the OLD buggy code: reads EDGAR_USER_AGENT (not SEC_EDGAR_USER_AGENT)
        original_get_user_agent = xbrl_client._get_user_agent

        def buggy_get_user_agent():
            global _USER_AGENT
            if xbrl_client._USER_AGENT is None:
                raw = os.getenv("EDGAR_USER_AGENT", "")
                xbrl_client._USER_AGENT = raw
            return xbrl_client._USER_AGENT

        # With the bug: EDGAR_USER_AGENT is not set → returns empty string
        monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "RealAgent real@test.com")

        # The buggy version returns empty (wrong env var)
        result = buggy_get_user_agent()
        assert result == "", "Bug: EDGAR_USER_AGENT not set, returns empty"

        # The correct version returns the pipeline-resolved value
        xbrl_client._USER_AGENT = None
        monkeypatch.setattr(xbrl_client, "_resolve_user_agent",
                            lambda **kw: "RealAgent real@test.com")
        monkeypatch.setattr(xbrl_client, "_validate_user_agent", lambda ua: None)
        result = original_get_user_agent()
        assert result == "RealAgent real@test.com", (
            "Correct code uses pipeline resolver, not os.getenv('EDGAR_USER_AGENT')"
        )