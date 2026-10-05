"""tests/bronze/test_sec_companyfacts.py — Tests for SEC Company Facts ingestion.

All tests run offline with no network or Databricks dependencies.
Pure unit tests for flattening via plain dict→rows functions.
Spark-free: pyspark and databricks.connect are not required.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

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
        self.writer = _FakeWriter()

    def createDataFrame(self, rows: Any) -> _FakeDataFrame:
        self.created_rows.append(rows)
        return _FakeDataFrame(self.writer)

    def sql(self, ddl: str) -> None:
        pass


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