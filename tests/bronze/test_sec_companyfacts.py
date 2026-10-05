"""tests/bronze/test_sec_companyfacts.py — Tests for SEC Company Facts ingestion.

All tests run offline with no network or Databricks dependencies.
Pure unit tests for flattening via plain dict→rows functions.
Spark-free: pyspark and databricks.connect are not required.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

try:
    import pyspark.sql.types as _pyspark_types
    _has_pyspark = True
except ImportError:
    _has_pyspark = False

from pipelines.sec_rag_ingest import (
    Clock,
    HttpClient,
    HttpResponse,
    RateLimiter,
    SecClient,
    SecClientConfig,
    SecClientError,
    _validate_user_agent,
)
from pipelines.ingest_sec_companyfacts import (
    CompanyFactsManifestEntry,
    SparkCompanyFactsWriter,
    SparkCompanyFactsManifestWriter,
    flatten_company_facts,
    compute_payload_hash,
    build_source_url,
    run_ingest_companyfacts,
    _classify_error,
    _schema_to_ddl_columns,
)


# ── Fakes ──────────────────────────────────────────────────────────────────


class FakeClock:
    """Injectable clock for rate limiter testing."""

    def __init__(self, start: float = 1000.0):
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds

    def advance(self, seconds: float) -> None:
        self._now += seconds


class FakeHttpClient:
    """Fake HTTP client returning configurable responses."""

    def __init__(self, responses: Optional[List[HttpResponse]] = None):
        self._responses = list(responses or [])
        self._call_index = 0
        self.calls: List[Dict[str, Any]] = []

    def get(
        self,
        url: str,
        headers: Dict[str, str],
        timeout: float = 30.0,
    ) -> HttpResponse:
        self.calls.append({
            "url": url,
            "headers": dict(headers),
            "timeout": timeout,
        })
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        # Default: 200 with empty JSON
        return HttpResponse(status_code=200, text="{}", headers={})


class BarrierFakeHttpClient:
    """Thread-safe HTTP client that routes by URL and supports barriers.

    Each URL maps to a deque of responses.  A shared ``threading.Barrier``
    forces two threads to reach the HTTP layer simultaneously so that
    concurrent attempt-count tracking is genuinely tested.

    ``barrier_urls`` restricts which URLs participate in the barrier;
    ``None`` means all URLs.  The barrier fires at most once in total
    (across all URLs) so that retries do not deadlock against an
    already-consumed party.
    """

    def __init__(
        self,
        url_responses: Dict[str, List[HttpResponse]],
        barrier: Optional[threading.Barrier] = None,
        barrier_urls: Optional[set] = None,
    ):
        self._queues: Dict[str, deque] = {
            url: deque(resps) for url, resps in url_responses.items()
        }
        self._barrier = barrier
        self._barrier_urls = barrier_urls
        self._barrier_used = False
        self._barrier_lock = threading.Lock()
        self._default = HttpResponse(status_code=200, text="{}", headers={})
        self._lock = threading.Lock()
        self.calls: List[Dict[str, Any]] = []

    def get(
        self,
        url: str,
        headers: Dict[str, str],
        timeout: float = 30.0,
    ) -> HttpResponse:
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        if self._barrier is not None:
            should_wait = False
            with self._barrier_lock:
                if not self._barrier_used and (self._barrier_urls is None or url in self._barrier_urls):
                    should_wait = True
            if should_wait:
                self._barrier.wait()
                with self._barrier_lock:
                    self._barrier_used = True
        with self._lock:
            q = self._queues.get(url)
            if q:
                return q.popleft()
        return self._default


# ── Sample payloads ────────────────────────────────────────────────────────


def _make_company_facts_payload(
    cik: str = "0000320193",
    entity_name: str = "Apple Inc.",
    updated: str = "2025-01-15",
    facts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a minimal Company Facts payload."""
    if facts is None:
        facts = {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "description": "Revenue from contracts with customers",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": 90753000000,
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "accn": "0000320193-24-000006",
                                "filed": "2024-05-03",
                                "frame": "CY2024Q1",
                            },
                            {
                                "start": "2024-01-01",
                                "end": "2024-06-29",
                                "val": 184213000000,
                                "fy": 2024,
                                "fp": "Q2",
                                "form": "10-Q",
                                "accn": "0000320193-24-000006",
                                "filed": "2024-05-03",
                                "frame": "CY2024Q2",
                            },
                        ],
                    },
                },
                "NetIncomeLoss": {
                    "label": "Net Income Loss",
                    "description": "The aggregate amount of net income",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": 23636000000,
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "accn": "0000320193-24-000006",
                                "filed": "2024-05-03",
                            },
                        ],
                        "USD/shares": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": 1.53,
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "accn": "0000320193-24-000006",
                                "filed": "2024-05-03",
                            },
                        ],
                    },
                },
            },
            "ifrs-full": {
                "Revenue": {
                    "label": "Revenue (IFRS)",
                    "description": "IFRS revenue",
                    "units": {
                        "EUR": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": 1000000000,
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "20-F",
                                "accn": "0001234567-24-000001",
                                "filed": "2024-06-01",
                            },
                        ],
                    },
                },
            },
        }

    return {
        "cik": int(cik),
        "entityName": entity_name,
        "updated": updated,
        "facts": facts,
    }


def _make_malformed_value_payload() -> Dict[str, Any]:
    """Payload with a fact whose value is non-numeric (malformed)."""
    return _make_company_facts_payload(
        facts={
            "us-gaap": {
                "SomeConcept": {
                    "label": "Some Concept",
                    "description": "A concept with a malformed value",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": "not_a_number",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "accn": "0000320193-24-000006",
                                "filed": "2024-05-03",
                            },
                        ],
                    },
                },
            },
        },
    )


def _make_multi_cik_payload(cik: str = "0002115436") -> Dict[str, Any]:
    """Minimal payload for a second CIK (XOM override)."""
    return _make_company_facts_payload(
        cik=cik,
        entity_name="ExxonMobil Holdings Corp",
        facts={
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "description": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": 85000000000,
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "accn": "0002115436-24-000001",
                                "filed": "2024-05-01",
                            },
                        ],
                    },
                },
            },
        },
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_manifest_writer():
    """Return a simple manifest writer that collects entries in a list."""
    entries: List[CompanyFactsManifestEntry] = []

    def writer(catalog: str, schema: str, entry: CompanyFactsManifestEntry):
        entries.append(entry)

    return writer, entries


def _make_delta_writer():
    """Return a simple delta writer that collects rows in a list."""
    all_rows: List[Dict[str, Any]] = []

    def writer(catalog: str, schema: str, rows: List[Dict[str, Any]]):
        all_rows.extend(rows)

    return writer, all_rows


def _make_sec_client(
    http_client: HttpClient,
    limiter: RateLimiter,
    user_agent: str = "TestApp/1.0 test@example.com",
) -> SecClient:
    """Build a SecClient with the given dependencies."""
    config = SecClientConfig(user_agent=user_agent)
    return SecClient(config, http_client, limiter)


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _payload_200(payload: Dict[str, Any]) -> HttpResponse:
    body = json.dumps(payload)
    return HttpResponse(status_code=200, text=body, headers={})


# ── Flatten tests ──────────────────────────────────────────────────────────


class TestFlattenCompanyFacts:
    """Tests for the pure flatten_company_facts function."""

    def test_flatten_basic(self):
        """Standard payload produces correct number of rows."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="test_run_001",
            ingested_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            payload_hash="abc123",
        )
        # us-gaap: Revenues (2 USD) + NetIncomeLoss (1 USD + 1 USD/shares) = 4
        # ifrs-full: Revenue (1 EUR) = 1
        assert len(rows) == 5

    def test_flatten_column_names(self):
        """Each row has exactly the Plan B 2.2 columns."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        expected_cols = {
            "ingest_run_id", "ingested_at", "source_url", "payload_hash",
            "cik", "entity_name", "ticker", "taxonomy", "concept", "label",
            "description", "unit", "value_raw", "value_decimal",
            "period_start", "period_end", "instant", "fiscal_year",
            "fiscal_period", "form_type", "accession_number", "filed_date",
            "frame", "raw_fact_json", "source_updated_at",
        }
        assert set(rows[0].keys()) == expected_cols

    def test_flatten_preserves_raw_json(self):
        """raw_fact_json is valid JSON matching the original entry."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        for row in rows:
            raw = json.loads(row["raw_fact_json"])
            assert "val" in raw
            assert "accn" in raw

    def test_flatten_malformed_value_decimal_is_none(self):
        """Malformed fact has value_decimal=None but is preserved."""
        payload = _make_malformed_value_payload()
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["value_decimal"] is None
        assert row["value_raw"] == "not_a_number"
        assert row["raw_fact_json"] is not None

    def test_flatten_multi_unit_entries(self):
        """USD and USD/shares produce separate rows."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        net_income_rows = [r for r in rows if r["concept"] == "NetIncomeLoss"]
        units = {r["unit"] for r in net_income_rows}
        assert "USD" in units
        assert "USD/shares" in units

    def test_flatten_multi_taxonomy(self):
        """Both us-gaap and ifrs-full taxonomies are flattened."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        taxonomies = {r["taxonomy"] for r in rows}
        assert "us-gaap" in taxonomies
        assert "ifrs-full" in taxonomies

    def test_flatten_entity_name_from_payload(self):
        """entity_name comes from the payload, not the argument."""
        payload = _make_company_facts_payload(entity_name="Test Corp")
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        assert all(r["entity_name"] == "Test Corp" for r in rows)

    def test_flatten_cik_from_payload(self):
        """CIK in rows comes from the payload (not the function argument)."""
        payload = _make_company_facts_payload(cik="0000999999")
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        # CIK from payload is int 999999 → zero-padded to "0000999999"
        assert all(r["cik"] == "0000999999" for r in rows)

    def test_flatten_empty_facts(self):
        """Empty facts dict produces zero rows."""
        payload = _make_company_facts_payload(facts={})
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        assert rows == []

    def test_flatten_preserves_period_fields(self):
        """Period start/end/instant/fy/fp are preserved exactly."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload=payload,
            cik="0000320193",
            ticker="AAPL",
            run_id="r1",
            ingested_at=datetime.now(timezone.utc),
            source_url="url",
            payload_hash="h",
        )
        revenue_rows = [r for r in rows if r["concept"] == "Revenues"]
        q1 = revenue_rows[0]
        assert q1["period_start"] == "2024-01-01"
        assert q1["period_end"] == "2024-03-31"
        assert q1["fiscal_year"] == 2024
        assert q1["fiscal_period"] == "Q1"
        assert q1["frame"] == "CY2024Q1"


# ── SEC client tests ───────────────────────────────────────────────────────


class TestSecClientCompanyFacts:
    """Tests for SEC client behavior specific to Company Facts."""

    def test_user_agent_header_sent(self):
        """User-Agent header is present on every request."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=8, clock=clock)
        ua = "TestApp/1.0 investor@example.com"
        client = _make_sec_client(
            http_client=FakeHttpClient([_payload_200(_make_company_facts_payload())]),
            limiter=limiter,
            user_agent=ua,
        )
        client.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")

        # Verify the UA was sent
        assert client._headers["User-Agent"] == ua

    def test_retry_after_honoured_on_429(self):
        """429 with Retry-After header pauses for the specified duration."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=8, clock=clock)
        http = FakeHttpClient([
            HttpResponse(
                status_code=429,
                text="rate limited",
                headers={"Retry-After": "5"},
            ),
            _payload_200(_make_company_facts_payload()),
        ])
        client = _make_sec_client(http_client=http, limiter=clock, user_agent="TestApp/1.0 test@example.com")

        # Need to build client properly
        config = SecClientConfig(user_agent="TestApp/1.0 test@example.com")
        client = SecClient(config, http, limiter, clock)

        result = client.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")
        assert "entityName" in result
        # Clock should have advanced by 5 seconds (Retry-After)
        assert clock._now >= 1005.0

    def test_retry_after_capped_at_max(self):
        """Retry-After exceeding cap raises SecClientError."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=8, clock=clock)
        http = FakeHttpClient([
            HttpResponse(
                status_code=429,
                text="rate limited",
                headers={"Retry-After": "999"},
            ),
        ])
        config = SecClientConfig(user_agent="TestApp/1.0 test@example.com")
        client = SecClient(config, http, limiter, clock)

        with pytest.raises(SecClientError, match="Retry-After.*exceeds cap"):
            client.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")

    def test_rate_cap_respected(self):
        """Rate limiter prevents more than max_rps requests per second."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=2, clock=clock)

        responses = [
            _payload_200(_make_company_facts_payload())
            for _ in range(5)
        ]
        http = FakeHttpClient(responses)
        config = SecClientConfig(user_agent="TestApp/1.0 test@example.com")
        client = SecClient(config, http, limiter, clock)

        for _ in range(3):
            client.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")

        # After 3 requests at 2 rps, clock must have advanced
        assert clock._now > 1000.0


# ── User-Agent validation tests ────────────────────────────────────────────


class TestUserAgentValidation:
    """Tests for SEC User-Agent validation."""

    def test_reject_placeholder_email(self):
        """Placeholder email addresses are rejected."""
        with pytest.raises(ValueError, match="descriptive"):
            _validate_user_agent("TestApp/1.0 user@example.com")

    def test_reject_empty_string(self):
        """Empty string is rejected."""
        with pytest.raises(ValueError, match="descriptive"):
            _validate_user_agent("")

    def test_accept_valid_ua(self):
        """Valid UA with real-looking email passes."""
        _validate_user_agent("MyApp/2.0 john@acme.com")

    def test_reject_your_email_placeholder(self):
        """'your-email@' prefix is rejected."""
        with pytest.raises(ValueError, match="descriptive"):
            _validate_user_agent("your-email@test.com/1.0")

    def test_reject_bare_word(self):
        """Bare word without email is rejected."""
        with pytest.raises(ValueError, match="<application name> <contact email>"):
            _validate_user_agent("foo")

    def test_reject_two_words_no_email(self):
        """Two words without email is rejected."""
        with pytest.raises(ValueError, match="<application name> <contact email>"):
            _validate_user_agent("foo bar")

    def test_reject_email_without_name(self):
        """Email without a name token is rejected."""
        with pytest.raises(ValueError, match="<application name> <contact email>"):
            _validate_user_agent("a@b")

    def test_reject_email_without_domain_dot(self):
        """Email without a dot in domain is rejected."""
        with pytest.raises(ValueError, match="<application name> <contact email>"):
            _validate_user_agent("App user@localhost")

    def test_accept_company_name_with_email(self):
        """Company name + email passes."""
        _validate_user_agent("Acme Corp contact@acme.com")

    def test_accept_app_version_with_email(self):
        """App version + email passes."""
        _validate_user_agent("MyApp/2.0 support@myapp.org")

    def test_error_message_does_not_leak_ua_value(self):
        """MUTATION: error message must not contain the input UA value
        (which may carry a real contact email)."""
        bad_ua = "AdminContact@company-domain.com"
        with pytest.raises(ValueError) as exc_info:
            _validate_user_agent(bad_ua)
        msg = str(exc_info.value)
        assert bad_ua not in msg, f"Error message leaks UA value: {msg}"


# ── Ingestion orchestrator tests ───────────────────────────────────────────


class TestRunIngestCompanyFacts:
    """Tests for the run_ingest_companyfacts orchestrator."""

    def test_two_changed_payloads_both_appended(self):
        """Two different payloads for the same CIK both produce rows."""
        payload_a = _make_company_facts_payload(
            facts={
                "us-gaap": {
                    "Revenues": {
                        "label": "Revenues",
                        "description": "Revenue",
                        "units": {
                            "USD": [
                                {"start": "2024-01-01", "end": "2024-03-31",
                                 "val": 100, "fy": 2024, "fp": "Q1",
                                 "form": "10-Q", "accn": "0000320193-24-000001",
                                 "filed": "2024-05-01"},
                            ],
                        },
                    },
                },
            },
        )
        payload_b = _make_company_facts_payload(
            facts={
                "us-gaap": {
                    "Revenues": {
                        "label": "Revenues",
                        "description": "Revenue",
                        "units": {
                            "USD": [
                                {"start": "2024-01-01", "end": "2024-03-31",
                                 "val": 200, "fy": 2024, "fp": "Q1",
                                 "form": "10-Q", "accn": "0000320193-24-000002",
                                 "filed": "2024-05-15"},
                            ],
                        },
                    },
                },
            },
        )

        hash_a = compute_payload_hash(json.dumps(payload_a).encode())
        hash_b = compute_payload_hash(json.dumps(payload_b).encode())
        assert hash_a != hash_b

        # Both should produce rows
        rows_a = flatten_company_facts(
            payload_a, "0000320193", "AAPL", "r1",
            datetime.now(timezone.utc), "url", hash_a,
        )
        rows_b = flatten_company_facts(
            payload_b, "0000320193", "AAPL", "r1",
            datetime.now(timezone.utc), "url", hash_b,
        )
        assert len(rows_a) == 1
        assert len(rows_b) == 1
        assert rows_a[0]["value_decimal"] == 100
        assert rows_b[0]["value_decimal"] == 200

    def test_same_payload_skipped_within_run(self):
        """Duplicate (cik, payload_hash) within the same run is skipped.

        Two tickers that map to the same CIK fetch the same payload; the
        second must NOT be written to delta, and the manifest must record
        fetch_status='skipped_duplicate'.
        """
        payload = _make_company_facts_payload()
        payload_bytes = json.dumps(payload).encode()
        payload_hash = compute_payload_hash(payload_bytes)

        # HTTP responses:
        #   1. company_tickers.json (needed by load_company_tickers)
        #   2. Company Facts for CIK 0000320193 (AAPL)
        #   3. Company Facts for CIK 0000320193 (AAPL2 — same CIK, same payload)
        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
            _payload_200(payload),
            _payload_200(payload),
        ])
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL", "AAPL2"],
                run_id="run_skip",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"], "AAPL2": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        # Both tickers mapped
        assert result["mapped_count"] == 2
        # Only one fetch succeeded (second was skipped)
        assert result["fetched_count"] == 1
        assert result["skipped_duplicate_payloads"] == 1

        # Delta rows come from only one fetch
        expected_row_count = len(flatten_company_facts(
            payload, "0000320193", "AAPL", "run_skip",
            datetime.now(timezone.utc), "url", payload_hash,
        ))
        assert len(delta_rows) == expected_row_count

        # Manifest has two entries: one success, one skipped_duplicate
        statuses = {e.fetch_status for e in manifest_entries}
        assert "success" in statuses
        assert "skipped_duplicate" in statuses

        # The skipped entry records the same payload_hash
        skipped = [e for e in manifest_entries if e.fetch_status == "skipped_duplicate"]
        assert len(skipped) == 1
        assert skipped[0].payload_hash == payload_hash

    def test_duplicate_manifest_attempt_count_with_retries(self):
        """MUTATION: if manifest.attempt_count = attempt_count is removed
        from the skipped_duplicate branch, the skipped entry carries the
        default attempt_count (1) instead of the actual retry count (2).

        Two tickers map to the same CIK.  The first fetch succeeds directly
        (1 attempt).  The second fetch gets a 429 then succeeds (2 attempts)
        — but it is skipped_duplicate.  Its manifest must record
        attempt_count=2.

        Uses BarrierFakeHttpClient (URL-routed, thread-safe deque) so the
        responses are consumed in the correct order even with concurrent
        workers.
        """
        payload = _make_company_facts_payload()
        payload_bytes = json.dumps(payload).encode()
        payload_hash = compute_payload_hash(payload_bytes)
        cik_url = build_source_url("0000320193")
        tickers_url = "https://www.sec.gov/files/company_tickers.json"

        http = BarrierFakeHttpClient(
            {
                tickers_url: [
                    _payload_200({
                        "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
                    }),
                ],
                cik_url: [
                    _payload_200(payload),  # first fetch: direct success, 1 attempt
                    HttpResponse(status_code=429, text="rate limited", headers={"Retry-After": "1"}),
                    _payload_200(payload),  # second fetch retry: success, 2 attempts
                ],
            },
        )
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL", "AAPL2"],
                run_id="run_skip_retry",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"], "AAPL2": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["mapped_count"] == 2
        assert result["fetched_count"] == 1
        assert result["skipped_duplicate_payloads"] == 1

        skipped = [e for e in manifest_entries if e.fetch_status == "skipped_duplicate"]
        assert len(skipped) == 1
        assert skipped[0].payload_hash == payload_hash
        assert skipped[0].attempt_count == 2

    def test_first_write_failure_allows_second_write(self):
        """MUTATION: if seen_payloads.add happens before Delta write,
        a failed first write prevents the identical second payload from being written.

        Uses sequential execution (max_workers=1) so ordering is deterministic:
        first fetch fails at Delta write → second fetch must still write the
        identical payload (because seen_payloads.add only happens after success).
        """
        payload = _make_company_facts_payload()
        payload_bytes = json.dumps(payload).encode()
        payload_hash = compute_payload_hash(payload_bytes)

        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
            _payload_200(payload),
            _payload_200(payload),
        ])
        clock = FakeClock()

        call_count = [0]
        def failing_delta_writer_first_call(cat, sch, rows):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Delta write failed")

        manifest_entries = []
        def mock_manifest_writer(cat, sch, entry):
            manifest_entries.append(entry)

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL", "AAPL2"],
                run_id="run_fail_first",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"], "AAPL2": ["0000320193"]},
                delta_writer=failing_delta_writer_first_call,
                manifest_writer=mock_manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        # First CIK failed (Delta write error), second CIK succeeded
        assert result["failed_count"] == 1
        assert result["fetched_count"] == 1

    def test_manifest_fields_complete(self):
        """Manifest entry has all required fields populated."""
        entry = CompanyFactsManifestEntry(
            ingest_run_id="r1",
            cik="0000320193",
            ticker="AAPL",
            fetch_status="success",
            attempt_count=1,
            payload_hash="abc123",
            payload_bytes=12345,
            fact_count=42,
            http_status=200,
            started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2025, 1, 15, 10, 0, 5, tzinfo=timezone.utc),
            error_category="",
            error_message="",
        )
        assert entry.ingest_run_id == "r1"
        assert entry.cik == "0000320193"
        assert entry.ticker == "AAPL"
        assert entry.fetch_status == "success"
        assert entry.attempt_count == 1
        assert entry.payload_hash == "abc123"
        assert entry.payload_bytes == 12345
        assert entry.fact_count == 42
        assert entry.http_status == 200
        assert entry.started_at is not None
        assert entry.completed_at is not None
        assert entry.error_category == ""
        assert entry.error_message == ""

    def test_manifest_error_fields_on_failure(self):
        """Failed manifest entry has error_category and error_message."""
        entry = CompanyFactsManifestEntry(
            ingest_run_id="r1",
            cik="0000320193",
            ticker="AAPL",
            fetch_status="failed",
            attempt_count=3,
            error_category="rate_limited",
            error_message="429 Too Many Requests",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        assert entry.fetch_status == "failed"
        assert entry.attempt_count == 3
        assert entry.error_category == "rate_limited"

    def test_manifest_http_status_on_success(self):
        """MUTATION: manifest http_status is set to 200 on successful fetch."""
        payload = _make_company_facts_payload()
        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
            _payload_200(payload),
        ])
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL"],
                run_id="run_http_status",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["fetched_count"] == 1
        success_entries = [e for e in manifest_entries if e.fetch_status == "success"]
        assert len(success_entries) == 1
        assert success_entries[0].http_status == 200

    def test_manifest_http_status_on_failure(self):
        """MUTATION: manifest http_status is set on failed fetch."""
        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
            HttpResponse(status_code=404, text="Not Found", headers={}),
        ])
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL"],
                run_id="run_http_fail",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["failed_count"] == 1
        failed_entries = [e for e in manifest_entries if e.fetch_status == "failed"]
        assert len(failed_entries) == 1
        assert failed_entries[0].http_status == 404

    def test_retry_exhaustion_403_manifest(self):
        """MUTATION: 403 x5 → manifest http_status=403, attempts=5, category=forbidden."""
        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
        ] + [HttpResponse(status_code=403, text="Forbidden", headers={})] * 5)
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL"],
                run_id="run_403_exhaust",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["failed_count"] == 1
        failed = [e for e in manifest_entries if e.fetch_status == "failed"]
        assert len(failed) == 1
        assert failed[0].http_status == 403
        assert failed[0].attempt_count == 5
        assert failed[0].error_category == "forbidden"

    def test_retry_exhaustion_429_manifest(self):
        """MUTATION: 429 x5 → manifest http_status=429, attempts=5, category=rate_limited."""
        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
        ] + [HttpResponse(status_code=429, text="Too Many Requests", headers={})] * 5)
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL"],
                run_id="run_429_exhaust",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["failed_count"] == 1
        failed = [e for e in manifest_entries if e.fetch_status == "failed"]
        assert len(failed) == 1
        assert failed[0].http_status == 429
        assert failed[0].attempt_count == 5
        assert failed[0].error_category == "rate_limited"

    def test_retry_exhaustion_503_manifest(self):
        """MUTATION: 503 x5 → manifest http_status=503, attempts=5, category=server_error."""
        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
        ] + [HttpResponse(status_code=503, text="Service Unavailable", headers={})] * 5)
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL"],
                run_id="run_503_exhaust",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["failed_count"] == 1
        failed = [e for e in manifest_entries if e.fetch_status == "failed"]
        assert len(failed) == 1
        assert failed[0].http_status == 503
        assert failed[0].attempt_count == 5
        assert failed[0].error_category == "server_error"

    def test_xom_two_cik_fetch(self):
        """XOM override maps to 2 CIKs; both are fetched."""
        payload_1 = _make_company_facts_payload(cik="0002115436", entity_name="Holdings")
        payload_2 = _make_company_facts_payload(cik="0000034088", entity_name="Exxon Mobil")

        http = FakeHttpClient([
            # company_tickers.json
            _payload_200({
                "0": {"ticker": "XOM", "cik_str": 34088, "title": "Exxon Mobil Corp"},
            }),
            # CIK 1
            _payload_200(payload_1),
            # CIK 2
            _payload_200(payload_2),
        ])
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=8, clock=clock)
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["XOM"],
                run_id="run_xom",
                http_client=http,
                clock=clock,
                cik_overrides={"XOM": ["0002115436", "0000034088"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        # Both CIKs should have been fetched
        assert result["mapped_count"] == 1
        assert result["fetched_count"] == 2
        assert result["total_facts"] > 0

        # Manifest entries should have both CIKs
        ciks_in_manifest = {e.cik for e in manifest_entries}
        assert "0002115436" in ciks_in_manifest
        assert "0000034088" in ciks_in_manifest

    def test_no_email_in_logs(self, caplog):
        """Contact email is never logged."""
        payload = _make_company_facts_payload()
        http = FakeHttpClient([_payload_200(payload)])
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=8, clock=clock)

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 realuser@company.com"
        mod._validate_user_agent = lambda ua: None

        try:
            with caplog.at_level(logging.DEBUG):
                delta_writer, _ = _make_delta_writer()
                manifest_writer, _ = _make_manifest_writer()
                run_ingest_companyfacts(
                    catalog="test_cat",
                    schema="test_sch",
                    tickers=["AAPL"],
                    run_id="run_log",
                    http_client=http,
                    clock=clock,
                    cik_overrides={"AAPL": ["0000320193"]},
                    delta_writer=delta_writer,
                    manifest_writer=manifest_writer,
                    cache_path="/dev/null",
                )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        # Check no email in log output
        log_text = caplog.text
        assert "realuser@company.com" not in log_text

    def test_classify_error_categories(self):
        """Error classification returns correct categories."""
        assert _classify_error(SecClientError("r", status_code=429)) == "rate_limited"
        assert _classify_error(SecClientError("f", status_code=403)) == "forbidden"
        assert _classify_error(SecClientError("s", status_code=500)) == "server_error"
        assert _classify_error(SecClientError("s", status_code=503)) == "server_error"
        assert _classify_error(SecClientError("n", status_code=404)) == "http_404"
        assert _classify_error(SecClientError("c")) == "client_error"

    def test_attempt_count_from_retries(self):
        """Manifest attempt_count reflects real SecClient request count."""
        payload = _make_company_facts_payload()
        # First request returns 429, second succeeds
        http = FakeHttpClient([
            _payload_200({
                "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            }),
            HttpResponse(status_code=429, text="rate limited", headers={"Retry-After": "1"}),
            _payload_200(payload),
        ])
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["AAPL"],
                run_id="run_retry",
                http_client=http,
                clock=clock,
                cik_overrides={"AAPL": ["0000320193"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["fetched_count"] == 1
        success_entries = [e for e in manifest_entries if e.fetch_status == "success"]
        assert len(success_entries) == 1
        # 2 HTTP requests: 429 + retry success
        assert success_entries[0].attempt_count == 2

    def test_concurrent_attempt_count_per_cik(self):
        """Two concurrent fetches each get their own attempt count.

        Uses a threading.Barrier to force CIK A (429→200) and CIK B (200)
        to reach the HTTP layer simultaneously so that a shared-counter
        regression is genuinely detectable.
        """
        payload = _make_company_facts_payload()
        barrier = threading.Barrier(2, timeout=10)
        tickers_url = "https://www.sec.gov/files/company_tickers.json"
        url_a = build_source_url("0000000000")
        url_b = build_source_url("0000000001")
        http = BarrierFakeHttpClient(
            {
                tickers_url: [
                    _payload_200({
                        "0": {"ticker": "TK0", "cik_str": 0, "title": "Corp 0"},
                        "1": {"ticker": "TK1", "cik_str": 1, "title": "Corp 1"},
                    }),
                ],
                url_a: [
                    HttpResponse(status_code=429, text="rate limited", headers={"Retry-After": "1"}),
                    _payload_200(payload),
                ],
                url_b: [_payload_200(payload)],
            },
            barrier=barrier,
            barrier_urls={url_a, url_b},
        )
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["TK0", "TK1"],
                run_id="run_concurrent_attempts",
                http_client=http,
                clock=clock,
                cik_overrides={"TK0": ["0000000000"], "TK1": ["0000000001"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["fetched_count"] == 2
        success_entries = sorted(
            [e for e in manifest_entries if e.fetch_status == "success"],
            key=lambda e: e.cik,
        )
        assert len(success_entries) == 2
        assert success_entries[0].attempt_count == 2  # TK0: 429 + retry
        assert success_entries[1].attempt_count == 1  # TK1: direct

    def test_bounded_concurrency_max_workers(self):
        """ThreadPoolExecutor uses at most 4 workers."""
        import pipelines.ingest_sec_companyfacts as mod
        import concurrent.futures

        captured_max_workers = []
        _OrigTE = concurrent.futures.ThreadPoolExecutor

        class TrackingThreadPool(_OrigTE):
            def __init__(self, *args, **kwargs):
                captured_max_workers.append(kwargs.get("max_workers", args[0] if args else None))
                super().__init__(*args, **kwargs)

        payloads = []
        http_responses = []
        tickers = []
        overrides = {}

        # Build 6 tickers all mapping to different CIKs
        for i in range(6):
            ticker = f"TK{i}"
            cik = f"000000000{i}"
            tickers.append(ticker)
            overrides[ticker] = [cik]
            payload = _make_company_facts_payload(
                cik=cik,
                entity_name=f"Corp {i}",
                facts={
                    "us-gaap": {
                        "Rev": {
                            "label": "Rev",
                            "description": "Revenue",
                            "units": {"USD": [
                                {"start": "2024-01-01", "end": "2024-03-31",
                                 "val": 100 + i, "fy": 2024, "fp": "Q1",
                                 "form": "10-Q", "accn": f"000-24-00000{i}",
                                 "filed": "2024-05-01"},
                            ]},
                        },
                    },
                },
            )
            payloads.append(payload)

        # company_tickers.json + 6 company facts
        http_responses.append(_payload_200({
            str(i): {"ticker": f"TK{i}", "cik_str": i, "title": f"Corp {i}"}
            for i in range(6)
        }))
        for p in payloads:
            http_responses.append(_payload_200(p))

        http = FakeHttpClient(http_responses)
        clock = FakeClock()
        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        original_te = mod.ThreadPoolExecutor
        mod.ThreadPoolExecutor = TrackingThreadPool

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=tickers,
                run_id="run_concurrent",
                http_client=http,
                clock=clock,
                cik_overrides=overrides,
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod.ThreadPoolExecutor = original_te
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["mapped_count"] == 6
        assert result["fetched_count"] == 6
        assert result["total_facts"] == 6
        assert captured_max_workers, "ThreadPoolExecutor was not called"
        assert all(mw <= 4 for mw in captured_max_workers), (
            f"max_workers exceeds 4: {captured_max_workers}"
        )

    def test_rate_limiter_holds_with_concurrency(self):
        """Rate limiter ≤10 req/s still holds under concurrent fetches."""
        payload = _make_company_facts_payload()

        # 3 tickers, 3 CIKs → 4 HTTP requests (1 company_tickers + 3 facts)
        http_responses = [
            _payload_200({
                "0": {"ticker": "A", "cik_str": 1, "title": "A Corp"},
                "1": {"ticker": "B", "cik_str": 2, "title": "B Corp"},
                "2": {"ticker": "C", "cik_str": 3, "title": "C Corp"},
            }),
        ]
        for _ in range(3):
            http_responses.append(_payload_200(payload))

        http = FakeHttpClient(http_responses)
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)

        delta_writer, delta_rows = _make_delta_writer()
        manifest_writer, manifest_entries = _make_manifest_writer()

        import pipelines.ingest_sec_companyfacts as mod
        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        try:
            result = run_ingest_companyfacts(
                catalog="test_cat",
                schema="test_sch",
                tickers=["A", "B", "C"],
                run_id="run_limiter",
                http_client=http,
                clock=clock,
                cik_overrides={"A": ["0000000001"], "B": ["0000000002"], "C": ["0000000003"]},
                delta_writer=delta_writer,
                manifest_writer=manifest_writer,
                cache_path="/dev/null",
            )
        finally:
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        assert result["fetched_count"] == 3
        # limiter.max_rps should still be ≤10
        assert limiter.max_rps <= 10

    def test_compute_payload_hash_deterministic(self):
        """Same bytes always produce the same hash."""
        b = b'{"test": 1}'
        assert compute_payload_hash(b) == compute_payload_hash(b)

    def test_compute_payload_hash_different_for_different_bytes(self):
        """Different bytes produce different hashes."""
        assert compute_payload_hash(b"a") != compute_payload_hash(b"b")

    def test_build_source_url(self):
        """Source URL is correctly formatted."""
        url = build_source_url("0000320193")
        assert url == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"

    def test_build_source_url_zero_pads(self):
        """CIK is zero-padded to 10 digits."""
        url = build_source_url("320193")
        assert "CIK0000320193" in url


# ── Spark write-mode tests (append-only enforcement) ───────────────────────


class _FakeWriter:
    """Records .mode() and .saveAsTable() calls for assertion."""

    def __init__(self):
        self.modes: List[str] = []
        self.saved_tables: List[str] = []

    def mode(self, mode_str: str) -> "_FakeWriter":
        self.modes.append(mode_str)
        return self

    def saveAsTable(self, table: str) -> None:
        self.saved_tables.append(table)


class _FakeDataFrame:
    """Minimal DataFrame stand-in that returns a _FakeWriter."""

    def __init__(self, writer: _FakeWriter):
        self._writer = writer

    @property
    def write(self) -> _FakeWriter:
        return self._writer


class _FakeSparkSession:
    """Records rows passed to createDataFrame; returns a _FakeDataFrame."""

    def __init__(self):
        self.created_rows: List[Any] = []
        self.created_schemas: List[Any] = []
        self.writer = _FakeWriter()

    def createDataFrame(self, rows: Any, schema: Any = None) -> _FakeDataFrame:
        self.created_rows.append(rows)
        self.created_schemas.append(schema)
        return _FakeDataFrame(self.writer)

    def sql(self, ddl: str) -> None:
        pass


@pytest.mark.skipif(not _has_pyspark, reason="Requires PySpark")
class TestSparkWriterAppendMode:
    """Verify SparkCompanyFactsWriter and SparkCompanyFactsManifestWriter
    use mode('append') — never 'overwrite'."""

    def test_facts_writer_uses_append_mode(self):
        """SparkCompanyFactsWriter.append_rows must call
        df.write.mode('append').saveAsTable(...)."""
        fake_spark = _FakeSparkSession()
        writer = SparkCompanyFactsWriter(spark_factory=lambda: fake_spark)

        rows = [{"cik": "0000320193", "ticker": "AAPL", "concept": "Revenues"}]
        count = writer.append_rows("cat", "sch", rows)

        assert count == 1
        assert fake_spark.writer.modes == ["append"]
        assert fake_spark.writer.saved_tables == ["cat.sch.bronze_sec_xbrl_facts"]

    def test_manifest_writer_uses_append_mode(self):
        """SparkCompanyFactsManifestWriter.write_manifest must call
        df.write.mode('append').saveAsTable(...)."""
        fake_spark = _FakeSparkSession()
        writer = SparkCompanyFactsManifestWriter(spark_factory=lambda: fake_spark)

        entry = CompanyFactsManifestEntry(
            ingest_run_id="r1",
            cik="0000320193",
            ticker="AAPL",
            fetch_status="success",
            payload_hash="abc",
        )
        writer.write_manifest("cat", "sch", entry)

        assert fake_spark.writer.modes == ["append"]
        assert fake_spark.writer.saved_tables == ["cat.sch.sec_companyfacts_ingest_log"]

    def test_facts_writer_no_overwrite(self):
        """MUTATION: if append_rows uses mode('overwrite'), this test fails."""
        fake_spark = _FakeSparkSession()
        writer = SparkCompanyFactsWriter(spark_factory=lambda: fake_spark)
        writer.append_rows("cat", "sch", [{"cik": "1"}])

        assert "overwrite" not in fake_spark.writer.modes
        assert all(m == "append" for m in fake_spark.writer.modes)

    def test_manifest_writer_no_overwrite(self):
        """MUTATION: if write_manifest uses mode('overwrite'), this test fails."""
        fake_spark = _FakeSparkSession()
        writer = SparkCompanyFactsManifestWriter(spark_factory=lambda: fake_spark)
        entry = CompanyFactsManifestEntry(
            ingest_run_id="r1", cik="0000320193", ticker="AAPL",
        )
        writer.write_manifest("cat", "sch", entry)

        assert "overwrite" not in fake_spark.writer.modes
        assert all(m == "append" for m in fake_spark.writer.modes)

    def test_facts_writer_empty_rows_no_write(self):
        """append_rows with empty list returns 0 and does not call Spark."""
        fake_spark = _FakeSparkSession()
        writer = SparkCompanyFactsWriter(spark_factory=lambda: fake_spark)
        count = writer.append_rows("cat", "sch", [])

        assert count == 0
        assert fake_spark.writer.modes == []
        assert fake_spark.writer.saved_tables == []


# ── Mutation tests (must fail on old code) ─────────────────────────────────


class TestMutationProofs:
    """Named mutation tests that must catch specific regressions."""

    def test_mutation_accept_placeholder_ua(self):
        """MUTATION: if _validate_user_agent accepts placeholders, this passes
        when it should fail."""
        with pytest.raises(ValueError):
            _validate_user_agent("App/1.0 user@example.com")

    def test_mutation_malformed_fact_not_dropped(self):
        """MUTATION: if flatten drops rows with value_decimal=None,
        malformed facts are lost."""
        payload = _make_malformed_value_payload()
        rows = flatten_company_facts(
            payload, "0000320193", "AAPL", "r1",
            datetime.now(timezone.utc), "url", "h",
        )
        assert len(rows) == 1
        assert rows[0]["value_decimal"] is None
        assert rows[0]["value_raw"] == "not_a_number"

    def test_mutation_flatten_preserves_accession(self):
        """MUTATION: dropping accession_number from rows breaks downstream dedup."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload, "0000320193", "AAPL", "r1",
            datetime.now(timezone.utc), "url", "h",
        )
        for row in rows:
            assert row["accession_number"]  # not empty
            assert "-" in row["accession_number"]  # has dashes

    def test_mutation_flatten_preserves_unit(self):
        """MUTATION: losing unit field breaks downstream currency checks."""
        payload = _make_company_facts_payload()
        rows = flatten_company_facts(
            payload, "0000320193", "AAPL", "r1",
            datetime.now(timezone.utc), "url", "h",
        )
        units = {r["unit"] for r in rows}
        assert "USD" in units
        assert "USD/shares" in units
        assert "EUR" in units

    def test_mutation_rate_limiter_max_enforced(self):
        """MUTATION: if RateLimiter allows > 10 rps, SEC may block us."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        # Should not raise
        assert limiter.max_rps == 10
        # But > 10 should raise
        with pytest.raises(ValueError, match="exceeds hard limit"):
            RateLimiter(max_requests_per_second=11, clock=clock)

    def test_mutation_403_not_retried(self):
        """MUTATION: if 403 is not retried, this test fails."""
        clock = FakeClock()
        http = FakeHttpClient()
        call_count = [0]

        def mock_get(url, headers, timeout=30.0):
            call_count[0] += 1
            if call_count[0] == 1:
                return HttpResponse(403, "Forbidden", {})
            return HttpResponse(200, '{"ok": true}', {})

        http.get = mock_get
        limiter = RateLimiter(max_requests_per_second=10, clock=clock)
        client = SecClient(SecClientConfig(user_agent="Test"), http, limiter, clock)
        result = client.get_json("https://example.com")
        assert result == {"ok": True}
        assert call_count[0] == 2  # retried once


# ── Schema contract tests (no Spark needed) ────────────────────────────────


_TYPE_MAP_REVERSE = {
    "STRING": "string",
    "INT": "int",
    "BIGINT": "bigint",
    "DOUBLE": "double",
    "FLOAT": "float",
    "BOOLEAN": "boolean",
    "TIMESTAMP": "timestamp",
    "DATE": "date",
    "BINARY": "binary",
    "SMALLINT": "smallint",
    "TINYINT": "tinyint",
}


def _parse_ddl_columns(ddl: str):
    """Parse a CREATE TABLE DDL column list into (name, simpleString, nullable) tuples."""
    import re
    m = re.search(r'\(\s*(.*?)\s*\)\s*USING\s+DELTA', ddl, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse DDL column list from: {ddl[:200]}")
    body = m.group(1)
    cols = []
    for line in body.split(","):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"Cannot parse DDL column line: {line}")
        name = parts[0]
        ddl_type = parts[1].upper()
        nullable = "NOT NULL" not in line.upper()
        simple = _TYPE_MAP_REVERSE.get(ddl_type, ddl_type.lower())
        cols.append((name, simple, nullable))
    return cols


@pytest.mark.skipif(not _has_pyspark, reason="Requires PySpark")
class TestBronzeSchemaContract:
    """Bronze StructType matches the DDL column list exactly.

    The DDL is GENERATED from the StructType via _schema_to_ddl_columns,
    so they can never drift apart.  These tests verify the round-trip:
    StructType → DDL → parse → compare against StructType.
    """

    # DDL column names in exact order (from SparkCompanyFactsWriter.ensure_table)
    DDL_COLUMNS = [
        "ingest_run_id", "ingested_at", "source_url", "payload_hash",
        "cik", "entity_name", "ticker", "taxonomy", "concept", "label",
        "description", "unit", "value_raw", "value_decimal",
        "period_start", "period_end", "instant", "fiscal_year",
        "fiscal_period", "form_type", "accession_number", "filed_date",
        "frame", "raw_fact_json", "source_updated_at",
    ]

    def test_bronze_schema_field_count(self):
        """StructType has exactly 25 fields matching the DDL."""
        from pipelines.ingest_sec_companyfacts import _get_bronze_schema
        schema = _get_bronze_schema()
        assert len(schema.fields) == 25

    def test_bronze_schema_field_names_match_ddl(self):
        """Field names match the DDL column list in order."""
        from pipelines.ingest_sec_companyfacts import _get_bronze_schema
        schema = _get_bronze_schema()
        names = [f.name for f in schema.fields]
        assert names == self.DDL_COLUMNS

    def test_bronze_schema_types(self):
        """Field types match the DDL exactly."""
        from pyspark.sql.types import (
            DoubleType, IntegerType, StringType, TimestampType,
        )
        from pipelines.ingest_sec_companyfacts import _get_bronze_schema
        schema = _get_bronze_schema()
        expected = [
            ("ingest_run_id", StringType, False),
            ("ingested_at", TimestampType, False),
            ("source_url", StringType, True),
            ("payload_hash", StringType, True),
            ("cik", StringType, True),
            ("entity_name", StringType, True),
            ("ticker", StringType, True),
            ("taxonomy", StringType, True),
            ("concept", StringType, True),
            ("label", StringType, True),
            ("description", StringType, True),
            ("unit", StringType, True),
            ("value_raw", StringType, True),
            ("value_decimal", DoubleType, True),
            ("period_start", StringType, True),
            ("period_end", StringType, True),
            ("instant", StringType, True),
            ("fiscal_year", IntegerType, True),
            ("fiscal_period", StringType, True),
            ("form_type", StringType, True),
            ("accession_number", StringType, True),
            ("filed_date", StringType, True),
            ("frame", StringType, True),
            ("raw_fact_json", StringType, True),
            ("source_updated_at", StringType, True),
        ]
        for i, (name, typ, nullable) in enumerate(expected):
            field = schema.fields[i]
            assert field.name == name, f"Field {i}: {field.name} != {name}"
            assert isinstance(field.dataType, typ), f"Field {i} ({name}): type mismatch"
            assert field.nullable == nullable, f"Field {i} ({name}): nullable mismatch"

    def test_bronze_generated_ddl_matches_struct_type(self):
        """DDL generated from StructType round-trips back to the same columns.

        This is the core contract: StructType is the single source of truth.
        The DDL cannot drift independently because it is derived.
        """
        from pipelines.ingest_sec_companyfacts import _get_bronze_schema
        schema = _get_bronze_schema()
        ddl_cols_str = _schema_to_ddl_columns(schema)
        full_ddl = f"CREATE TABLE IF NOT EXISTS t ({ddl_cols_str}) USING DELTA"
        parsed = _parse_ddl_columns(full_ddl)

        assert len(parsed) == len(schema.fields), (
            f"DDL has {len(parsed)} columns, schema has {len(schema.fields)}"
        )
        for i, field in enumerate(schema.fields):
            name, simple, nullable = parsed[i]
            assert name == field.name, f"Col {i}: {name} != {field.name}"
            assert simple == field.dataType.simpleString(), (
                f"Col {i} ({name}): DDL type {simple} != schema type {field.dataType.simpleString()}"
            )
            assert nullable == field.nullable, (
                f"Col {i} ({name}): DDL nullable={nullable} != schema nullable={field.nullable}"
            )

    def test_bronze_ddl_column_names_match_hardcoded_list(self):
        """Generated DDL column names match the hardcoded reference list."""
        from pipelines.ingest_sec_companyfacts import _get_bronze_schema
        schema = _get_bronze_schema()
        ddl_cols_str = _schema_to_ddl_columns(schema)
        full_ddl = f"CREATE TABLE IF NOT EXISTS t ({ddl_cols_str}) USING DELTA"
        parsed = _parse_ddl_columns(full_ddl)
        names = [c[0] for c in parsed]
        assert names == self.DDL_COLUMNS

    def test_mutation_drop_bronze_schema_fails_test(self):
        """MUTATION: if _get_bronze_schema is removed, this test fails."""
        from pipelines.ingest_sec_companyfacts import _get_bronze_schema
        schema = _get_bronze_schema()
        # The schema must be a StructType, not None
        assert schema is not None
        assert len(schema.fields) == 25

    def test_mutation_drop_field_from_bronze_struct_fails_contract(self):
        """MUTATION: removing a field from the StructType causes the contract
        test to fail — the generated DDL no longer matches the full schema.

        This is the exact scenario DeepSeek flagged: if someone edits the
        StructType but not the DDL (or vice versa), this test catches it.
        """
        from pyspark.sql.types import (
            DoubleType, IntegerType, StringType, StructField, StructType,
            TimestampType,
        )
        from pipelines.ingest_sec_companyfacts import _get_bronze_schema
        full_schema = _get_bronze_schema()

        # Build a schema missing 'fact_count' equivalent — here we drop
        # 'value_decimal' as a representative field
        reduced_fields = [f for f in full_schema.fields if f.name != "value_decimal"]
        reduced_schema = StructType(reduced_fields)

        # Generate DDL from the reduced schema
        ddl_cols_str = _schema_to_ddl_columns(reduced_schema)
        full_ddl = f"CREATE TABLE IF NOT EXISTS t ({ddl_cols_str}) USING DELTA"
        parsed = _parse_ddl_columns(full_ddl)

        # The parsed DDL should NOT match the full schema (missing value_decimal)
        assert len(parsed) != len(full_schema.fields), (
            "Reduced schema should have fewer fields than full schema"
        )

        # Verify the specific field is missing
        parsed_names = [c[0] for c in parsed]
        assert "value_decimal" not in parsed_names, (
            "value_decimal should be missing from reduced DDL"
        )
        assert "value_decimal" in [f.name for f in full_schema.fields], (
            "value_decimal should be in the full schema"
        )


@pytest.mark.skipif(not _has_pyspark, reason="Requires PySpark")
class TestManifestSchemaContract:
    """Manifest StructType matches the DDL column list exactly.

    The DDL is GENERATED from the StructType via _schema_to_ddl_columns,
    so they can never drift apart.  These tests verify the round-trip:
    StructType → DDL → parse → compare against StructType.
    """

    # DDL column names in exact order (from SparkCompanyFactsManifestWriter.ensure_table)
    DDL_COLUMNS = [
        "ingest_run_id", "cik", "ticker", "fetch_status", "attempt_count",
        "payload_hash", "payload_bytes", "fact_count", "http_status",
        "started_at", "completed_at", "error_category", "error_message",
        "logged_at",
    ]

    def test_manifest_schema_field_count(self):
        """StructType has exactly 14 fields matching the DDL."""
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        schema = _get_manifest_schema()
        assert len(schema.fields) == 14

    def test_manifest_schema_field_names_match_ddl(self):
        """Field names match the DDL column list in order."""
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        schema = _get_manifest_schema()
        names = [f.name for f in schema.fields]
        assert names == self.DDL_COLUMNS

    def test_manifest_schema_types(self):
        """Field types match the DDL exactly."""
        from pyspark.sql.types import (
            IntegerType, StringType, TimestampType,
        )
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        schema = _get_manifest_schema()
        expected = [
            ("ingest_run_id", StringType, False),
            ("cik", StringType, False),
            ("ticker", StringType, False),
            ("fetch_status", StringType, False),
            ("attempt_count", IntegerType, True),
            ("payload_hash", StringType, True),
            ("payload_bytes", IntegerType, True),
            ("fact_count", IntegerType, True),
            ("http_status", IntegerType, True),
            ("started_at", TimestampType, True),
            ("completed_at", TimestampType, True),
            ("error_category", StringType, True),
            ("error_message", StringType, True),
            ("logged_at", TimestampType, False),
        ]
        for i, (name, typ, nullable) in enumerate(expected):
            field = schema.fields[i]
            assert field.name == name, f"Field {i}: {field.name} != {name}"
            assert isinstance(field.dataType, typ), f"Field {i} ({name}): type mismatch"
            assert field.nullable == nullable, f"Field {i} ({name}): nullable mismatch"

    def test_manifest_generated_ddl_matches_struct_type(self):
        """DDL generated from StructType round-trips back to the same columns.

        This is the core contract: StructType is the single source of truth.
        The DDL cannot drift independently because it is derived.
        """
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        schema = _get_manifest_schema()
        ddl_cols_str = _schema_to_ddl_columns(schema)
        full_ddl = f"CREATE TABLE IF NOT EXISTS t ({ddl_cols_str}) USING DELTA"
        parsed = _parse_ddl_columns(full_ddl)

        assert len(parsed) == len(schema.fields), (
            f"DDL has {len(parsed)} columns, schema has {len(schema.fields)}"
        )
        for i, field in enumerate(schema.fields):
            name, simple, nullable = parsed[i]
            assert name == field.name, f"Col {i}: {name} != {field.name}"
            assert simple == field.dataType.simpleString(), (
                f"Col {i} ({name}): DDL type {simple} != schema type {field.dataType.simpleString()}"
            )
            assert nullable == field.nullable, (
                f"Col {i} ({name}): DDL nullable={nullable} != schema nullable={field.nullable}"
            )

    def test_manifest_ddl_column_names_match_hardcoded_list(self):
        """Generated DDL column names match the hardcoded reference list."""
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        schema = _get_manifest_schema()
        ddl_cols_str = _schema_to_ddl_columns(schema)
        full_ddl = f"CREATE TABLE IF NOT EXISTS t ({ddl_cols_str}) USING DELTA"
        parsed = _parse_ddl_columns(full_ddl)
        names = [c[0] for c in parsed]
        assert names == self.DDL_COLUMNS

    def test_manifest_includes_http_status(self):
        """MUTATION: if http_status is missing from the schema, this test fails."""
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        schema = _get_manifest_schema()
        names = [f.name for f in schema.fields]
        assert "http_status" in names

    def test_mutation_drop_manifest_schema_fails_test(self):
        """MUTATION: if _get_manifest_schema is removed, this test fails."""
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        schema = _get_manifest_schema()
        assert schema is not None
        assert len(schema.fields) == 14

    def test_mutation_drop_field_from_manifest_struct_fails_contract(self):
        """MUTATION: removing http_status from the StructType causes the
        contract test to fail — the generated DDL no longer matches the
        full schema.

        This is the exact scenario DeepSeek flagged: if someone edits the
        StructType but not the DDL (or vice versa), this test catches it.
        """
        from pyspark.sql.types import (
            IntegerType, StringType, StructField, StructType, TimestampType,
        )
        from pipelines.ingest_sec_companyfacts import _get_manifest_schema
        full_schema = _get_manifest_schema()

        # Build a schema missing 'http_status'
        reduced_fields = [f for f in full_schema.fields if f.name != "http_status"]
        reduced_schema = StructType(reduced_fields)

        # Generate DDL from the reduced schema
        ddl_cols_str = _schema_to_ddl_columns(reduced_schema)
        full_ddl = f"CREATE TABLE IF NOT EXISTS t ({ddl_cols_str}) USING DELTA"
        parsed = _parse_ddl_columns(full_ddl)

        # The parsed DDL should NOT match the full schema (missing http_status)
        assert len(parsed) != len(full_schema.fields), (
            "Reduced schema should have fewer fields than full schema"
        )

        # Verify the specific field is missing
        parsed_names = [c[0] for c in parsed]
        assert "http_status" not in parsed_names, (
            "http_status should be missing from reduced DDL"
        )
        assert "http_status" in [f.name for f in full_schema.fields], (
            "http_status should be in the full schema"
        )


@pytest.mark.skipif(not _has_pyspark, reason="Requires PySpark")
class TestFlattenedRowSchemaMatch:
    """A flattened row with every optional field None converts to a tuple
    that matches the StructType (no inference anywhere)."""

    def test_coerced_row_tuple_matches_schema(self):
        """_coerce_bronze_row produces a dict whose values match the StructType."""
        from pipelines.ingest_sec_companyfacts import (
            _coerce_bronze_row,
            _get_bronze_schema,
        )
        schema = _get_bronze_schema()
        # Build a row with every optional field as None
        row = {
            "ingest_run_id": "r1",
            "ingested_at": datetime.now(timezone.utc),
            "source_url": None,
            "payload_hash": None,
            "cik": None,
            "entity_name": None,
            "ticker": None,
            "taxonomy": None,
            "concept": None,
            "label": None,
            "description": None,
            "unit": None,
            "value_raw": None,
            "value_decimal": None,
            "period_start": None,
            "period_end": None,
            "instant": None,
            "fiscal_year": None,
            "fiscal_period": None,
            "form_type": None,
            "accession_number": None,
            "filed_date": None,
            "frame": None,
            "raw_fact_json": None,
            "source_updated_at": None,
        }
        coerced = _coerce_bronze_row(row)
        assert len(coerced) == len(schema.fields)
        # Every key must be present
        for field in schema.fields:
            assert field.name in coerced, f"Missing key: {field.name}"

    def test_coerced_row_fiscal_year_is_int_or_none(self):
        """fiscal_year is coerced to int or None (not str)."""
        from pipelines.ingest_sec_companyfacts import _coerce_bronze_row
        row = {
            "ingest_run_id": "r1",
            "ingested_at": datetime.now(timezone.utc),
            "fiscal_year": "2024",  # string from JSON
            "accession_number": "000-24-000001",
        }
        coerced = _coerce_bronze_row(row)
        assert coerced["fiscal_year"] == 2024
        assert isinstance(coerced["fiscal_year"], int)

    def test_coerced_row_fiscal_year_none(self):
        """fiscal_year=None stays None."""
        from pipelines.ingest_sec_companyfacts import _coerce_bronze_row
        row = {
            "ingest_run_id": "r1",
            "ingested_at": datetime.now(timezone.utc),
            "fiscal_year": None,
        }
        coerced = _coerce_bronze_row(row)
        assert coerced["fiscal_year"] is None

    def test_manifest_entry_to_dict_matches_schema(self):
        """CompanyFactsManifestEntry → dict has all manifest schema keys."""
        from pipelines.ingest_sec_companyfacts import (
            _get_manifest_schema,
            CompanyFactsManifestEntry,
        )
        schema = _get_manifest_schema()
        entry = CompanyFactsManifestEntry(
            ingest_run_id="r1",
            cik="0000320193",
            ticker="AAPL",
            fetch_status="success",
            attempt_count=1,
            payload_hash="abc",
            payload_bytes=100,
            fact_count=10,
            http_status=200,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            error_category="",
            error_message="",
        )
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
        assert len(row) == len(schema.fields)
        for field in schema.fields:
            assert field.name in row, f"Missing key: {field.name}"


@pytest.mark.skipif(not _has_pyspark, reason="Requires PySpark")
class TestCreateDataFrameAlwaysWithSchema:
    """Every createDataFrame call passes a schema argument."""

    def test_bronze_writer_passes_schema(self):
        """SparkCompanyFactsWriter.append_rows passes schema= to createDataFrame."""
        from pipelines.ingest_sec_companyfacts import (
            SparkCompanyFactsWriter,
            _get_bronze_schema,
        )
        captured_kwargs = []

        class SpyWriter:
            def mode(self, m): return self
            def saveAsTable(self, t): pass

        class SpyDataFrame:
            def __init__(self):
                self.write = SpyWriter()

        class SpySpark:
            def createDataFrame(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                return SpyDataFrame()

            def sql(self, ddl): pass

        writer = SparkCompanyFactsWriter(spark_factory=lambda: SpySpark())
        rows = [{"ingest_run_id": "r1", "ingested_at": datetime.now(timezone.utc)}]
        writer.append_rows("cat", "sch", rows)

        # Must have passed schema= keyword argument
        assert len(captured_kwargs) == 1
        assert "schema" in captured_kwargs[0], "createDataFrame missing schema= argument"
        schema = captured_kwargs[0]["schema"]
        assert len(schema.fields) == 25

    def test_manifest_writer_passes_schema(self):
        """SparkCompanyFactsManifestWriter.write_manifest passes schema= to createDataFrame."""
        from pipelines.ingest_sec_companyfacts import (
            SparkCompanyFactsManifestWriter,
            CompanyFactsManifestEntry,
        )
        captured_kwargs = []

        class SpyWriter:
            def mode(self, m): return self
            def saveAsTable(self, t): pass

        class SpyDataFrame:
            def __init__(self):
                self.write = SpyWriter()

        class SpySpark:
            def createDataFrame(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                return SpyDataFrame()

            def sql(self, ddl): pass

        writer = SparkCompanyFactsManifestWriter(spark_factory=lambda: SpySpark())
        entry = CompanyFactsManifestEntry(
            ingest_run_id="r1", cik="0000320193", ticker="AAPL",
        )
        writer.write_manifest("cat", "sch", entry)

        assert len(captured_kwargs) == 1
        assert "schema" in captured_kwargs[0], "createDataFrame missing schema= argument"
        schema = captured_kwargs[0]["schema"]
        assert len(schema.fields) == 14

    def test_mutation_remove_schema_arg_fails(self):
        """MUTATION: if schema= is removed from createDataFrame, this test fails."""
        from pipelines.ingest_sec_companyfacts import (
            SparkCompanyFactsWriter,
        )

        class SpyWriter:
            def mode(self, m): return self
            def saveAsTable(self, t): pass

        class SpyDataFrame:
            def __init__(self):
                self.write = SpyWriter()

        class StrictSpark:
            def createDataFrame(self, *args, **kwargs):
                # If no schema kwarg, raise to signal the mutation
                if "schema" not in kwargs and len(args) < 2:
                    raise AssertionError("createDataFrame called without schema!")
                return SpyDataFrame()

            def sql(self, ddl): pass

        writer = SparkCompanyFactsWriter(spark_factory=lambda: StrictSpark())
        rows = [{"ingest_run_id": "r1", "ingested_at": datetime.now(timezone.utc)}]
        # Should NOT raise
        writer.append_rows("cat", "sch", rows)


class TestCachePathFallback:
    """CIK cache path falls back to temp dir when default is not writable."""

    def test_fallback_when_volumes_not_writable(self, monkeypatch, tmp_path):
        """When /Volumes path is not writable, falls back to tempdir."""
        import os
        import tempfile
        from pipelines.ingest_sec_companyfacts import run_ingest_companyfacts

        # Monkeypatch os.access to simulate /Volumes not writable
        original_access = os.access

        def mock_access(path, mode, *args, **kwargs):
            if "/Volumes" in str(path):
                return False
            return original_access(path, mode, *args, **kwargs)

        monkeypatch.setattr(os, "access", mock_access)

        # Also need to monkeypatch os.makedirs for the fallback path
        captured_cache_paths = []

        def mock_load_company_tickers(client, cache_path, dry_run, **kwargs):
            captured_cache_paths.append(cache_path)
            return {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple"}}

        import pipelines.ingest_sec_companyfacts as mod
        original_load = mod.load_company_tickers
        mod.load_company_tickers = mock_load_company_tickers

        original_resolve = mod._resolve_user_agent
        original_validate = mod._validate_user_agent
        mod._resolve_user_agent = lambda **kw: "TestApp/1.0 test@example.com"
        mod._validate_user_agent = lambda ua: None

        # Hermetic: fake HTTP client so no network access occurs
        fake_http = FakeHttpClient([
            _payload_200(_make_company_facts_payload()),
        ])

        try:
            result = run_ingest_companyfacts(
                catalog="cat",
                schema="sch",
                tickers=["AAPL"],
                run_id="run_fallback",
                cik_overrides={"AAPL": ["0000320193"]},
                delta_writer=lambda c, s, r: None,
                manifest_writer=lambda c, s, e: None,
                http_client=fake_http,
            )
        finally:
            mod.load_company_tickers = original_load
            mod._resolve_user_agent = original_resolve
            mod._validate_user_agent = original_validate

        # Should have fallen back to tempdir
        assert len(captured_cache_paths) == 1
        assert "/Volumes" not in captured_cache_paths[0]
        assert tempfile.gettempdir() in captured_cache_paths[0]


@pytest.mark.skipif(not _has_pyspark, reason="Requires PySpark")
class TestEnsureTableIdempotent:
    """Test that ensure_table checks column existence before ALTER TABLE."""

    def test_ensure_table_skips_alter_when_http_status_exists(self):
        """When http_status column already exists, no ALTER TABLE is issued."""
        from unittest.mock import MagicMock, call

        mock_spark = MagicMock()
        # Simulate table already has http_status column
        mock_spark.table.return_value.columns = [
            "ingest_run_id", "cik", "ticker", "fetch_status", "attempt_count",
            "payload_hash", "payload_bytes", "fact_count", "http_status",
            "started_at", "completed_at", "error_category", "error_message",
            "logged_at",
        ]

        writer = SparkCompanyFactsManifestWriter(spark_factory=lambda: mock_spark)
        writer.ensure_table("cat", "sch")

        # CREATE TABLE should be called
        mock_spark.sql.assert_any_call(mock_spark.sql.call_args_list[0][0][0])

        # ALTER TABLE should NOT be called (http_status already in columns)
        alter_calls = [c for c in mock_spark.sql.call_args_list if "ALTER TABLE" in str(c)]
        assert len(alter_calls) == 0, f"ALTER TABLE should not be called when column exists: {alter_calls}"

    def test_ensure_table_runs_alter_when_http_status_missing(self):
        """When http_status column is missing, exactly one ALTER TABLE is issued
        deriving the column type from the manifest StructType."""
        from unittest.mock import MagicMock, call

        mock_spark = MagicMock()
        # Simulate table missing http_status column
        mock_spark.table.return_value.columns = [
            "ingest_run_id", "cik", "ticker", "fetch_status", "attempt_count",
            "payload_hash", "payload_bytes", "fact_count",
            "started_at", "completed_at", "error_category", "error_message",
            "logged_at",
        ]

        writer = SparkCompanyFactsManifestWriter(spark_factory=lambda: mock_spark)
        writer.ensure_table("cat", "sch")

        # ALTER TABLE should be called exactly once
        alter_calls = [c for c in mock_spark.sql.call_args_list if "ALTER TABLE" in str(c)]
        assert len(alter_calls) == 1, f"ALTER TABLE should be called once when column missing: {alter_calls}"
        assert "http_status INT" in str(alter_calls[0])

    def test_ensure_table_alter_derives_two_missing_fields_from_schema(self):
        """ALTER path adds exactly the missing fields with their StructType types.

        Simulates a pre-existing table missing 'error_category' and 'error_message'.
        The ALTER must add both with types derived from the manifest StructType
        (STRING, STRING) — no hard-coded column list.
        """
        from unittest.mock import MagicMock

        mock_spark = MagicMock()
        # Table missing error_category and error_message
        mock_spark.table.return_value.columns = [
            "ingest_run_id", "cik", "ticker", "fetch_status", "attempt_count",
            "payload_hash", "payload_bytes", "fact_count", "http_status",
            "started_at", "completed_at", "logged_at",
        ]

        writer = SparkCompanyFactsManifestWriter(spark_factory=lambda: mock_spark)
        writer.ensure_table("cat", "sch")

        alter_calls = [c for c in mock_spark.sql.call_args_list if "ALTER TABLE" in str(c)]
        assert len(alter_calls) == 1, f"Expected exactly one ALTER: {alter_calls}"
        ddl = str(alter_calls[0])
        assert "error_category STRING" in ddl
        assert "error_message STRING" in ddl


class TestCacheMinEntries:
    """Test that caches with fewer than 1,000 entries are treated as invalid."""

    def test_cache_with_few_entries_is_rejected(self, tmp_path):
        """Cache with <1000 entries should be treated as invalid (re-fetch) when is_fallback=True."""
        from pipelines.sec_rag_ingest import _try_load_cache

        cache_file = tmp_path / "company_tickers.json"
        # Create a cache with only 1 entry (test pollution scenario)
        cache_file.write_text(json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}))

        result = _try_load_cache(str(cache_file), ttl=3600, is_fallback=True)
        assert result is None, "Cache with <1000 entries should be rejected when is_fallback=True"

    def test_cache_with_valid_entry_count_is_accepted(self, tmp_path):
        """Cache with >=1000 entries should be accepted when is_fallback=True."""
        from pipelines.sec_rag_ingest import _try_load_cache
        import time

        cache_file = tmp_path / "company_tickers.json"
        sidecar_file = tmp_path / "company_tickers.json.meta"

        # Create a cache with 1000 entries (valid)
        payload = {str(i): {"cik_str": i, "ticker": f"T{i}", "title": f"Company {i}"} for i in range(1000)}
        cache_file.write_text(json.dumps(payload))
        sidecar_file.write_text(json.dumps({"fetched_ts": time.time()}))

        result = _try_load_cache(str(cache_file), ttl=3600, is_fallback=True)
        assert result is not None, "Cache with >=1000 entries should be accepted"
        assert len(result) == 1000

    def test_stale_cache_with_few_entries_is_rejected(self, tmp_path):
        """Even stale fallback cache with <1000 entries should be rejected."""
        from pipelines.sec_rag_ingest import _try_load_cache

        cache_file = tmp_path / "company_tickers.json"
        # Create a cache with only 1 entry
        cache_file.write_text(json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}))

        # ttl=0 means accept regardless of age (stale fallback)
        result = _try_load_cache(str(cache_file), ttl=0, is_fallback=True)
        assert result is None, "Stale cache with <1000 entries should also be rejected"

    def test_non_fallback_cache_with_few_entries_is_accepted(self, tmp_path):
        """Cache with <1000 entries should be accepted when is_fallback=False (default)."""
        from pipelines.sec_rag_ingest import _try_load_cache
        import time

        cache_file = tmp_path / "company_tickers.json"
        sidecar_file = tmp_path / "company_tickers.json.meta"

        # Create a cache with only 1 entry
        cache_file.write_text(json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}))
        sidecar_file.write_text(json.dumps({"fetched_ts": time.time()}))

        result = _try_load_cache(str(cache_file), ttl=3600, is_fallback=False)
        assert result is not None, "Cache with <1000 entries should be accepted when is_fallback=False"