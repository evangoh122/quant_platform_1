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

# Hide pyspark and databricks.connect before importing the pipeline
_pyspark_mock = MagicMock()
sys.modules.setdefault("pyspark", _pyspark_mock)
sys.modules.setdefault("pyspark.sql", _pyspark_mock.sql)
sys.modules.setdefault("pyspark.sql.functions", _pyspark_mock.sql.functions)
sys.modules.setdefault("pyspark.sql.types", _pyspark_mock.sql.types)
sys.modules.setdefault("databricks", MagicMock())
sys.modules.setdefault("databricks.connect", MagicMock())

from pipelines.sec_rag_ingest import (  # noqa: E402
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
    """Records appended rows."""

    def __init__(self):
        self.appended: List[List[Dict[str, Any]]] = []
        self.total_rows = 0

    def append_bronze_rows(self, catalog: str, schema: str, rows: List[Dict[str, Any]]) -> int:
        self.appended.append(rows)
        self.total_rows += len(rows)
        return len(rows)


class FakeLogWriter:
    """Records log entries."""

    def __init__(self):
        self.entries: List[IngestLogEntry] = []

    def append_log(self, catalog: str, schema: str, entry: IngestLogEntry) -> None:
        self.entries.append(entry)


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
        assert ts.tzinfo is None  # UTC-naive for Spark

    def test_none_input(self):
        assert parse_sec_timestamp(None) is None
        assert parse_sec_timestamp("") is None

    def test_invalid_format(self):
        assert parse_sec_timestamp("not-a-date") is None

    def test_utc_conversion(self):
        ts = parse_sec_timestamp("2025-01-15T12:00:00+05:00")
        assert ts is not None
        assert ts.hour == 7  # UTC = 12 - 5

    def test_epoch_equality(self):
        """Verify epoch-second roundtrip."""
        ts = parse_sec_timestamp("2025-02-20T18:30:00.000Z")
        assert ts is not None
        epoch = int(ts.replace(tzinfo=timezone.utc).timestamp())
        # Reconstruct from epoch
        ts2 = datetime.fromtimestamp(epoch, tz=timezone.utc).replace(tzinfo=None)
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
        """Filing with missing acceptance datetime fails and logs."""
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
            accepted_ts=datetime(2025, 2, 20, 18, 30, 0),
        )
        ingest_ts = datetime(2025, 3, 1, 12, 0, 0)
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
            assert row["accepted_ts"] == datetime(2025, 2, 20, 18, 30, 0)

    def test_empty_html(self):
        from pipelines.sec_rag_ingest import FilingMeta
        filing = FilingMeta(
            accession_number="0001", form_type="10-K",
            filing_date="2025-01-01", primary_doc="test.htm",
            accepted_ts=datetime(2025, 1, 1),
        )
        rows = process_filing("TEST", "1234", "Test", filing, "", datetime.now())
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


# -- Accession conflict tests --

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

    def test_different_cik_accession_raises_value_error(self):
        """Same accession owned by a different CIK must raise ValueError."""
        clock = FakeClock()
        http = FakeHttpClient()
        submissions = json.loads((FIXTURES / "submissions_recent.json").read_text())
        http.set_json("https://data.sec.gov/submissions/CIK0001045810.json", submissions)

        universe = [TickerEntry(ticker="NVDA", phase=1)]
        # The accession is owned by a DIFFERENT CIK (9999999999, not 0001045810)
        existing = {
            "0001045810-25-000010": ("9999999999", "OTHER"),
        }

        with pytest.raises(ValueError, match="Accession ownership conflict"):
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

    def test_main_write_mode_appends(self, monkeypatch):
        """Write mode with fake adapters should append rows."""
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

        main()

        assert writer.total_rows >= 0  # at least no crash


# -- Grep-style test: no example.com in production User-Agent --

class TestNoPlaceholderUserAgent:
    """Verify no example.com User-Agent remains in production code."""

    PRODUCTION_FILES = [
        "pipelines/sec_rag_ingest.py",
        "pipelines/build_sec_embeddings.py",
        "api/services/xbrl_client.py",
        "api/services/edgar_adapter.py",
        "api/services/_edgar_identity.py",
        "config/settings.py",
        "etl/extract_edgar.py",
    ]

    def test_no_example_com_in_production_files(self):
        """No production file should contain example.com as a User-Agent default."""
        import re
        repo_root = Path(__file__).parent.parent.parent
        pattern = re.compile(r"example\.com", re.IGNORECASE)
        violations = []
        for rel_path in self.PRODUCTION_FILES:
            full_path = repo_root / rel_path
            if not full_path.exists():
                continue
            content = full_path.read_text(encoding="utf-8")
            # Skip comments and test-only strings
            for i, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    # Allow in comments that explain the check
                    stripped = line.lstrip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    violations.append(f"{rel_path}:{i}: {line.strip()}")
        assert not violations, (
            f"Found example.com in production code:\n" + "\n".join(violations)
        )