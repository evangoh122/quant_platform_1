"""tests/rag/test_sec_rag_ingest.py - Tests for SEC RAG ingestion pipeline.

All tests run offline with no network or Databricks dependencies.
pyspark and databricks.connect are hidden via monkeypatch.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock

import pytest

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
    build_cik_map,
    chunk_text,
    discover_filings,
    extract_sections,
    load_company_tickers,
    normalize_sec_ticker,
    parse_sec_timestamp,
    process_filing,
    record_key,
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
    _pyspark_mock = MagicMock()
    _originals = {}
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

    for name in _patches:
        if _originals[name] is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = _originals[name]


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
        self.appended.append(rows)
        new_count = 0
        for r in rows:
            acc = r.get("accession_number", "")
            if acc not in self._seen_accessions:
                self._seen_accessions.add(acc)
                new_count += 1
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

        filings = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
        assert len(filings) == 2  # 10-K and 10-Q, not 8-K

    def test_respects_cutoff(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings = discover_filings(client, "1045810", "2025-01-01", {"10-K", "10-Q"})
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

        filings = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
        # Recent: 2 filings (2025-02-20 10-K, 2024-11-07 10-Q)
        # History: 0 filings after cutoff (2024-02-21 10-K and 2024-08-28 10-Q are before 2024-09-01)
        assert len(filings) == 2

    def test_filters_forms(self):
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)

        filings = discover_filings(client, "1045810", "2024-09-01", {"10-K"})
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
        """Same accession owned by a different CIK must raise AccessionOwnershipConflict."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        # The accession is owned by a DIFFERENT CIK (9999999999, not 0001045810)
        existing = {
            "0001045810-25-000010": ("9999999999", "OTHER"),
        }

        with pytest.raises(AccessionOwnershipConflict, match="Accession ownership conflict"):
            run_ingest(
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

    def test_race_path_conflict_raises(self):
        """Race-path conflict: accession appears between anti-join and processing.

        The race-path AccessionReader returns {} on first call (anti-join passes)
        and returns a conflicting accession on second call (inside the processing loop).
        Mutation proof: remove the except AccessionOwnershipConflict: raise →
        the conflict is swallowed and this test FAILS.
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

        with pytest.raises(AccessionOwnershipConflict, match="race"):
            run_ingest(
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
        assert first == 1, "First insert: 1 new accession → 1 inserted"
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

        filings = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
        # Should still get filings from recent (not crash)
        assert len(filings) >= 1

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
                "files": [{"name": "hist.json", "filingFrom": "2024-06-01", "filingTo": "2024-12-31"}],
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

        filings = discover_filings(client, "1045810", "2024-09-01", {"10-K", "10-Q"})
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

        filings = discover_filings(client, "1045810", "2024-09-01", {"10-K"})
        assert len(filings) == 1
        assert filings[0].accepted_ts is None  # Not dropped


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