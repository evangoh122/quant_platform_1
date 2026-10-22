"""tests/bronze/test_sec_submissions_ingest.py — KG-0 SEC submissions ingestion.

Runs entirely offline (tests/bronze/conftest.py blocks non-loopback sockets):
every external dependency (CIK reader, HTTP client, clock, writer) is injected.
The real Spark writer is exercised through a fake Spark session, so no pyspark
is required under CI.

Covered contracts:
* ``--dry-run`` is the default and performs zero HTTP requests / zero writes
* fair-access headers come from ``SEC_EDGAR_USER_AGENT`` (no hard-coded email)
* 404 -> recorded miss; other failures are reported and not written
* retries with backoff before success
* ``fetched_at`` is stamped when the response completes, never before it
* append-only idempotency on ``(cik, payload_sha256)``
* rate limiter clamped to <= 8 req/s
* silver SQL, job definition and run_silver_gold registration incl. the
  missing-bronze SKIP and the ``is_latest`` / former-name key contracts
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from config.data_sources import validate_data_source
import pipelines.ingest_sec_submissions as ingest
from pipelines.ingest_sec_submissions import (
    BRONZE_COLUMNS,
    MAX_SUBMISSIONS_RPS,
    build_source_url,
    clamp_requests_per_second,
    coerce_bronze_row,
    columns_to_ddl,
    payload_row,
    miss_row,
    run_ingest_submissions,
)
from pipelines.sec_rag_ingest import HttpResponse, RateLimiter
from sec_kg.submissions import MISS_PAYLOAD_SHA256, parse_registrant, payload_sha256

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sec_submissions"
SQL_PATH = REPO_ROOT / "silver" / "09_silver_sec_registrant.sql"
JOBS_PATH = REPO_ROOT / "resources" / "jobs.yml"
RUNNER_PATH = REPO_ROOT / "pipelines" / "run_silver_gold.py"

UA = "QuantPlatformKGTests/1.0 (kg-tests@quant-platform.test)"
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
FIXTURE_TEXT = (FIXTURES / "with_former_names.json").read_text(encoding="utf-8")
OTHER_TEXT = (FIXTURES / "multi_ticker_share_class.json").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _sec_user_agent(monkeypatch):
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", UA)


class FakeClock:
    """Deterministic monotonic clock: sleep advances time instead of waiting."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class RecordingClock(FakeClock):
    """Clock that records when each request slot was granted."""

    def __init__(self, start: float = 1000.0):
        super().__init__(start)
        self.starts: list[float] = []


class ClockBackedNow:
    """Wall clock derived from the injected monotonic clock.

    Lets a test see exactly *when* the ingestion stamped a row: any
    Retry-After cooldown or retry backoff advances ``clock.now``, so a
    pre-request timestamp is distinguishable from a completion timestamp.
    """

    def __init__(self, clock: FakeClock):
        self._clock = clock

    def __call__(self) -> datetime:
        return datetime.fromtimestamp(self._clock.now, tz=timezone.utc)


class FakeHttpClient:
    """URL-keyed fake HTTP client; an unexpected URL fails the test loudly."""

    def __init__(self, responses: dict[str, list[HttpResponse]] | None = None):
        self._queues = {
            url: list(items) for url, items in (responses or {}).items()
        }
        self.calls: list[dict] = []

    def get(self, url: str, headers: dict, timeout: float = 30.0) -> HttpResponse:
        self.calls.append(
            {"url": url, "headers": dict(headers), "timeout": timeout}
        )
        queue = self._queues.get(url)
        if not queue:
            raise AssertionError(f"unexpected HTTP request: {url}")
        return queue.pop(0)


class FakeWriter:
    """Insert-only writer that mimics the Delta MERGE key.

    A row is stored only when its ``(cik, payload_sha256)`` key is new, which is
    exactly the write contract of ``SparkSubmissionsWriter``.
    """

    def __init__(self):
        self.rows: list[dict] = []
        self.calls: list[tuple[str, str, int]] = []
        self.keys: dict[tuple[str, str], dict] = {}

    def write_rows(self, catalog: str, schema: str, rows: list[dict]) -> int:
        self.calls.append((catalog, schema, len(rows)))
        for row in rows:
            key = (row["cik"], row["payload_sha256"])
            if key not in self.keys:
                self.keys[key] = row
                self.rows.append(row)
        return len(rows)


class _FakeDataFrame:
    def createOrReplaceTempView(self, name: str) -> None:
        self.view = name


class FakeSpark:
    """Captures DDL / MERGE statements without importing pyspark."""

    def __init__(self):
        self.statements: list[str] = []
        self.rows: list[dict] = []

    def createDataFrame(self, rows, schema=None):
        self.rows = list(rows)
        self.schema = schema
        return _FakeDataFrame()

    def sql(self, statement: str):
        self.statements.append(statement)
        return None


def _run(
    ciks: list[str],
    http: FakeHttpClient,
    writer: FakeWriter | None = None,
    *,
    clock: FakeClock | None = None,
    requests_per_second=None,
    run_id: str = "run-1",
    live: bool = True,
):
    return run_ingest_submissions(
        catalog="cat",
        schema="sch",
        ciks=ciks,
        live=live,
        run_id=run_id,
        http_client=http,
        writer=writer,
        clock=clock or FakeClock(),
        requests_per_second=requests_per_second,
        now_fn=lambda: NOW,
    )


# ── Dry run ──────────────────────────────────────────────────────────────────


def test_dry_run_is_default_and_makes_zero_network_calls(monkeypatch):
    """Default path must not resolve the UA, fetch, or write."""
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    http = FakeHttpClient({})
    writer = FakeWriter()

    result = run_ingest_submissions(
        catalog="cat",
        schema="sch",
        ciks=["0001234567", "1234567"],
        http_client=http,
        writer=writer,
        now_fn=lambda: NOW,
    )

    assert result["dry_run"] is True
    # Duplicate spellings of the same CIK collapse to one request target.
    assert result["ciks_requested"] == 1
    assert http.calls == []
    assert writer.calls == []


def test_live_run_without_writer_fails_loudly():
    with pytest.raises(ValueError, match="writer"):
        run_ingest_submissions(
            catalog="cat",
            schema="sch",
            ciks=["1234567"],
            live=True,
            http_client=FakeHttpClient({}),
            now_fn=lambda: NOW,
        )


def test_cli_defaults_to_dry_run(capsys):
    ingest.main(
        ["--catalog", "cat", "--schema", "sch", "--ciks", "1234567"]
    )
    out = capsys.readouterr().out
    assert '"dry_run": true' in out


def test_cli_rejects_live_and_dry_run_together():
    with pytest.raises(SystemExit) as exc:
        ingest.main(["--live", "--dry-run"])
    assert exc.value.code == 2


# ── Live fetch / payload rows ────────────────────────────────────────────────


def test_live_fetch_stores_verbatim_payload_and_sha():
    http = FakeHttpClient(
        {build_source_url("1234567"): [HttpResponse(200, FIXTURE_TEXT)]}
    )
    writer = FakeWriter()

    result = _run(["1234567"], http, writer)

    assert result["ciks_fetched"] == 1
    assert result["ciks_missing"] == 0
    assert result["ciks_failed"] == 0
    assert result["registrants_parsed"] == 1
    assert result["rows_submitted"] == 1

    assert http.calls[0]["url"] == (
        "https://data.sec.gov/submissions/CIK0001234567.json"
    )
    assert http.calls[0]["headers"]["User-Agent"] == UA
    assert http.calls[0]["headers"]["Accept"] == "application/json"

    row = writer.rows[0]
    assert row["cik"] == "0001234567"
    assert row["payload"] == FIXTURE_TEXT
    assert row["payload_sha256"] == payload_sha256(FIXTURE_TEXT.encode("utf-8"))
    assert row["http_status"] == 200
    assert row["fetched_at"] == NOW
    assert row["ingest_run_id"] == "run-1"


def test_source_has_no_hardcoded_contact_email():
    source = Path(ingest.__file__).read_text(encoding="utf-8")
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", source), (
        "the User-Agent contact must come from SEC_EDGAR_USER_AGENT, "
        "never a hard-coded address"
    )


# ── Misses and failures ──────────────────────────────────────────────────────


def test_404_is_recorded_as_miss_not_failure():
    url = build_source_url("1234567")
    http = FakeHttpClient({url: [HttpResponse(404, "Not Found")]})
    writer = FakeWriter()

    result = _run(["1234567"], http, writer)

    assert result["ciks_missing"] == 1
    assert result["ciks_failed"] == 0
    assert result["ciks_fetched"] == 0

    row = writer.rows[0]
    assert row["http_status"] == 404
    assert row["payload"] is None
    assert row["payload_sha256"] == MISS_PAYLOAD_SHA256


def test_404_miss_is_idempotent_across_runs():
    url = build_source_url("1234567")
    writer = FakeWriter()

    _run(["1234567"], FakeHttpClient({url: [HttpResponse(404, "")]}), writer)
    _run(["1234567"], FakeHttpClient({url: [HttpResponse(404, "")]}), writer)

    assert len(writer.rows) == 1
    assert len(writer.keys) == 1


def test_retry_with_backoff_then_success():
    url = build_source_url("1234567")
    http = FakeHttpClient(
        {url: [HttpResponse(500, "oops"), HttpResponse(200, FIXTURE_TEXT)]}
    )
    writer = FakeWriter()
    clock = FakeClock()

    result = _run(["1234567"], http, writer, clock=clock)

    assert result["ciks_fetched"] == 1
    assert len(http.calls) == 2
    # first retry backoff is 2**0 = 1 second
    assert clock.now >= 1001.0
    assert len(writer.rows) == 1


def test_fetched_at_is_the_completion_time_after_a_retry_after_cooldown():
    """Regression: ``fetched_at`` must be stamped when the response completes.

    The fake API answers 503 + Retry-After: 60 and then 200; the injected
    monotonic clock advances by the cooldown.  Mutation: stamping before the
    request (the old behaviour) stores the pre-cooldown time and fails here.
    """
    url = build_source_url("1234567")
    http = FakeHttpClient(
        {
            url: [
                HttpResponse(503, "busy", {"Retry-After": "60"}),
                HttpResponse(200, FIXTURE_TEXT),
            ]
        }
    )
    writer = FakeWriter()
    clock = FakeClock()
    started_at = datetime.fromtimestamp(clock.now, tz=timezone.utc)

    result = run_ingest_submissions(
        catalog="cat",
        schema="sch",
        ciks=["1234567"],
        live=True,
        run_id="run-1",
        http_client=http,
        writer=writer,
        clock=clock,
        now_fn=ClockBackedNow(clock),
    )

    completed_at = datetime.fromtimestamp(clock.now, tz=timezone.utc)
    assert result["ciks_fetched"] == 1
    assert len(http.calls) == 2
    assert completed_at > started_at, "the Retry-After cooldown must advance time"
    assert writer.rows[0]["fetched_at"] == completed_at
    assert writer.rows[0]["fetched_at"] != started_at


class AdvancingHttpClient(FakeHttpClient):
    """Fake client that advances the clock *after* producing the response.

    Models the real latency: the response is complete only once ``get`` has
    returned, so a timestamp read after the call is the completion time.
    """

    def __init__(self, responses, clock: FakeClock, advance: float = 5.0):
        super().__init__(responses)
        self._clock = clock
        self._advance = advance

    def get(self, url: str, headers: dict, timeout: float = 30.0) -> HttpResponse:
        response = super().get(url, headers, timeout)
        self._clock.now += self._advance
        return response


def test_fetched_at_for_a_final_404_is_the_response_time():
    """A recorded miss is stamped when the 404 completes, not when it starts."""
    url = build_source_url("1234567")
    clock = FakeClock()
    http = AdvancingHttpClient({url: [HttpResponse(404, "Not Found")]}, clock)
    writer = FakeWriter()

    result = run_ingest_submissions(
        catalog="cat",
        schema="sch",
        ciks=["1234567"],
        live=True,
        run_id="run-1",
        http_client=http,
        writer=writer,
        clock=clock,
        now_fn=ClockBackedNow(clock),
    )

    assert result["ciks_missing"] == 1
    assert writer.rows[0]["fetched_at"] == datetime.fromtimestamp(
        clock.now, tz=timezone.utc
    )
    assert writer.rows[0]["http_status"] == 404


def test_permanent_failure_is_reported_without_write():
    url = build_source_url("1234567")
    http = FakeHttpClient({url: [HttpResponse(403, "forbidden")] * 5})
    writer = FakeWriter()

    result = _run(["1234567"], http, writer)

    assert result["ciks_failed"] == 1
    assert result["ciks_fetched"] == 0
    assert writer.rows == []
    assert result["errors"][0]["cik"] == "0001234567"
    assert result["errors"][0]["http_status"] == 403


def test_payload_for_a_different_cik_is_not_written():
    url = build_source_url("1234567")
    http = FakeHttpClient({url: [HttpResponse(200, OTHER_TEXT)]})
    writer = FakeWriter()

    result = _run(["1234567"], http, writer)

    assert result["ciks_failed"] == 1
    assert writer.rows == []
    assert "cik mismatch" in result["errors"][0]["error"]


def test_unparsable_payload_is_not_written():
    url = build_source_url("1234567")
    http = FakeHttpClient({url: [HttpResponse(200, "not json at all")]})
    writer = FakeWriter()

    result = _run(["1234567"], http, writer)

    assert result["ciks_failed"] == 1
    assert writer.rows == []


# ── Idempotency ──────────────────────────────────────────────────────────────


def test_idempotency_key_is_cik_and_payload_sha256():
    url = build_source_url("1234567")
    writer = FakeWriter()

    first = _run(
        ["1234567"], FakeHttpClient({url: [HttpResponse(200, FIXTURE_TEXT)]}), writer
    )
    assert first["ciks_fetched"] == 1
    assert len(writer.rows) == 1

    # Same payload again: MERGE key already present -> no second row.
    _run(
        ["1234567"], FakeHttpClient({url: [HttpResponse(200, FIXTURE_TEXT)]}), writer
    )
    assert len(writer.rows) == 1

    # Same CIK, different payload -> different sha -> a second observation.
    changed = FIXTURE_TEXT.replace(
        "Northwind Semiconductor Holdings, Inc.",
        "Northwind Semiconductor Holdings, Inc. (renamed)",
    )
    assert payload_sha256(changed.encode()) != payload_sha256(
        FIXTURE_TEXT.encode()
    )
    _run(["1234567"], FakeHttpClient({url: [HttpResponse(200, changed)]}), writer)

    assert len(writer.rows) == 2
    assert len({row["payload_sha256"] for row in writer.rows}) == 2


def test_merge_matches_on_both_key_columns(monkeypatch):
    """Mutation guard: dropping payload_sha256 from ON makes this fail."""
    fake = FakeSpark()
    monkeypatch.setattr(ingest, "_BRONZE_SCHEMA", object())

    writer = ingest.SparkSubmissionsWriter(spark_factory=lambda: fake)
    writer.write_rows(
        "cat",
        "sch",
        [
            payload_row("1234567", FIXTURE_TEXT, "run-1", NOW),
            miss_row("7654321", "run-1", NOW),
        ],
    )

    merge_sql = " ".join(fake.statements[-1].split())
    assert (
        "ON t.cik = s.cik AND t.payload_sha256 = s.payload_sha256" in merge_sql
    )
    assert "WHEN NOT MATCHED THEN INSERT *" in merge_sql
    # Append-only: never update or delete an existing observation.
    assert "WHEN MATCHED" not in merge_sql
    assert len(fake.rows) == 2


def test_ensure_table_ddl_is_the_column_spec():
    ddl = columns_to_ddl(BRONZE_COLUMNS)
    assert "cik STRING NOT NULL" in ddl
    assert "payload STRING" in ddl
    assert "payload STRING NOT NULL" not in ddl  # 404 misses carry NULL
    assert "payload_sha256 STRING NOT NULL" in ddl
    assert "http_status INT NOT NULL" in ddl
    assert "fetched_at TIMESTAMP NOT NULL" in ddl
    assert "ingest_run_id STRING NOT NULL" in ddl
    assert "data_source STRING NOT NULL" in ddl
    assert "data_source STRING NOT NULL COMMENT" in ddl

    fake = FakeSpark()
    writer = ingest.SparkSubmissionsWriter(spark_factory=lambda: fake)
    writer.ensure_table("cat", "sch")
    create_sql = " ".join(fake.statements[0].split())
    assert "CREATE TABLE IF NOT EXISTS cat.sch.bronze_sec_submissions" in create_sql
    assert "USING DELTA" in create_sql


def test_bronze_schema_column_order():
    assert [c.name for c in BRONZE_COLUMNS] == [
        "cik",
        "payload",
        "payload_sha256",
        "http_status",
        "fetched_at",
        "ingest_run_id",
        "data_source",
    ]


def test_bronze_rows_carry_a_valid_data_source():
    """Both row builders and the coercion step stamp the provider code.

    Mutation: delete ``data_source`` from ``payload_row`` and this fails.
    """
    rows = [
        payload_row("1234567", FIXTURE_TEXT, "run-1", NOW),
        miss_row("7654321", "run-1", NOW),
    ]

    for row in rows:
        assert row["data_source"] == "sec_edgar"
        assert validate_data_source(row["data_source"]) == "sec_edgar"

    coerced = coerce_bronze_row(rows[0])
    assert coerced["data_source"] == "sec_edgar"
    assert set(coerced) == {c.name for c in BRONZE_COLUMNS}


def test_a_row_without_a_data_source_is_rejected():
    """A row whose provenance is missing must fail instead of being written."""
    row = payload_row("1234567", FIXTURE_TEXT, "run-1", NOW)
    del row["data_source"]

    with pytest.raises(KeyError):
        coerce_bronze_row(row)


# ── Rate limiting ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "configured,expected",
    [
        (None, MAX_SUBMISSIONS_RPS),
        ("", MAX_SUBMISSIONS_RPS),
        ("nonsense", MAX_SUBMISSIONS_RPS),
        (12, MAX_SUBMISSIONS_RPS),
        ("10", MAX_SUBMISSIONS_RPS),
        (8, 8),
        ("3", 3),
        (0, 1),
        (-5, 1),
    ],
)
def test_requests_per_second_is_clamped(configured, expected):
    assert clamp_requests_per_second(configured) == expected


def test_rate_limiter_never_exceeds_eight_starts_per_second():
    clock = RecordingClock()
    limiter = RateLimiter(max_requests_per_second=MAX_SUBMISSIONS_RPS, clock=clock)

    for _ in range(20):
        limiter.acquire()
        clock.starts.append(clock.now)

    # Sliding window: the 9th start must be >= 1s after the 1st, etc.
    for i in range(len(clock.starts) - MAX_SUBMISSIONS_RPS):
        delta = clock.starts[i + MAX_SUBMISSIONS_RPS] - clock.starts[i]
        assert delta >= 1.0, (
            f"more than {MAX_SUBMISSIONS_RPS} starts inside one second "
            f"(index {i}: delta={delta})"
        )


def test_rate_limiter_hard_cap_rejects_above_ten():
    with pytest.raises(ValueError):
        RateLimiter(max_requests_per_second=11, clock=FakeClock())


# ── Silver SQL static checks ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def silver_sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


def test_silver_sql_uses_placeholders_only(silver_sql):
    assert "{catalog}" in silver_sql
    assert "{schema}" in silver_sql
    assert "bootcamp_students" not in silver_sql
    assert "evangoh_capstone" not in silver_sql


def test_silver_registrant_columns_and_types(silver_sql):
    for token in [
        "cik10",
        "payload_sha256",
        "name",
        "sic",
        "sic_description",
        "tickers",
        "exchanges",
        "state_of_incorporation",
        "fiscal_year_end",
        "entity_type",
        "observed_at",
        "ingest_run_id",
        "processed_ts",
        "is_latest",
    ]:
        assert token in silver_sql, f"missing column: {token}"

    assert "ARRAY<STRING>" in silver_sql
    assert "current_timestamp()" in silver_sql
    # One row per (cik, payload_sha256) observation.
    window = " ".join(silver_sql.split())
    assert "PARTITION BY cik, payload_sha256" in window
    # 404 misses (payload IS NULL) never reach silver.
    assert "WHERE payload IS NOT NULL" in window


def test_silver_registrant_marks_the_latest_payload_per_cik(silver_sql):
    """Many rows per CIK by design; ``is_latest`` marks the newest payload.

    The window is asserted exactly: mutation (dropping the window, partitioning
    by the payload key instead of cik10, or using ASC) fails here.
    """
    window = " ".join(silver_sql.split())
    assert (
        "ROW_NUMBER() OVER ( PARTITION BY p.cik10 "
        "ORDER BY p.observed_at DESC, p.payload_sha256 DESC ) = 1 AS is_latest"
        in window
    )


def test_silver_tables_carry_the_sec_edgar_data_source(silver_sql):
    """Both silver tables project the provider code and comment the column.

    Mutation: dropping the ``data_source`` projection from either SELECT fails.
    """
    blocks = silver_sql.split("CREATE OR REPLACE TABLE")
    assert len(blocks) == 3, "expected the header plus two table statements"

    window = " ".join(silver_sql.split())
    assert window.count("'sec_edgar' AS data_source") == 2

    for table, block in zip(
        ("silver_sec_registrant", "silver_sec_registrant_former_names"),
        blocks[1:],
    ):
        table_sql = " ".join(block.split())
        assert "'sec_edgar' AS data_source" in table_sql, table
        assert (
            f"ALTER TABLE {{catalog}}.{{schema}}.{table} "
            "ALTER COLUMN data_source COMMENT" in table_sql
        ), table
        assert (
            f"ALTER TABLE {{catalog}}.{{schema}}.{table} "
            "ALTER COLUMN data_source SET NOT NULL" in table_sql
        ), table


def test_silver_sql_splits_into_intact_statements(silver_sql):
    """The runner splits on ';', so a comment string must not contain one."""
    from pipelines.run_silver_gold import split_statements

    statements = split_statements(silver_sql)

    assert len(statements) == 6
    assert [stmt.split()[0] for stmt in statements] == [
        "CREATE",
        "ALTER",
        "ALTER",
        "CREATE",
        "ALTER",
        "ALTER",
    ]
    assert statements[2].endswith("SET NOT NULL")
    assert statements[5].endswith("SET NOT NULL")
    assert all(stmt.count("'") % 2 == 0 for stmt in statements), statements


def test_silver_former_names_is_exploded_and_inclusive(silver_sql):
    window = " ".join(silver_sql.split())
    assert "silver_sec_registrant_former_names" in window
    assert "LATERAL VIEW explode" in window
    assert "former_name" in window
    assert "from_date" in window
    assert "to_date" in window
    # The SEC publishes formerNames[].from/.to as ISO-8601 midnight-UTC
    # timestamps ("2001-04-02T00:00:00.000Z"); the calendar date is taken
    # explicitly instead of relying on a raw string -> date cast.
    assert "try_to_date(substring(fn.`from`, 1, 10))" in window
    assert "try_to_date(substring(fn.`to`, 1, 10))" in window
    # Inclusive as published: no +/- 1 day adjustment anywhere.
    assert "DATE_SUB" not in window.upper()
    assert "DATE_ADD" not in window.upper()
    assert "- 1 DAY" not in window.upper()


def test_silver_former_name_dates_are_null_safe(silver_sql):
    """A malformed SEC date must become NULL, not abort the shared refresh.

    ANSI mode makes a bare ``to_date`` raise on a string it cannot parse, so a
    single bad published value would fail every table in the silver/gold
    refresh.  ``try_to_date`` returns NULL instead (the file header documents
    what NULL means).  Mutation: reverting either projection to ``to_date(``
    makes the bare-cast assertion below fail.
    """
    window = " ".join(silver_sql.split())

    assert "try_to_date(substring(fn.`from`, 1, 10))" in window
    assert "try_to_date(substring(fn.`to`, 1, 10))" in window

    # No bare to_date( anywhere in this file (the only dates it produces are
    # SEC-published strings), and no CAST(... AS DATE) either.
    assert not re.search(r"(?<!try_)\bto_date\s*\(", window), (
        "silver/09_silver_sec_registrant.sql still calls to_date( directly; "
        "use try_to_date so an unparseable SEC date becomes NULL"
    )
    assert not re.search(r"\bAS\s+DATE\b", window, re.IGNORECASE), (
        "silver/09_silver_sec_registrant.sql casts to DATE; use try_to_date"
    )


def test_silver_former_names_key_includes_from_date(silver_sql):
    """A reused name needs from_date in the key or two periods collapse."""
    window = " ".join(silver_sql.split())
    assert (
        "PARTITION BY e.cik, e.payload_sha256, e.former_name, e.from_date"
        in window
    )


def test_same_former_name_in_two_periods_is_two_rows(silver_sql):
    """The recorded payload publishes 'Atlas Re Corp.' in two periods.

    Both rows must survive: the dedupe key read from the SQL keeps from_date,
    and the parser emits two distinct keys for the payload.
    """
    window = " ".join(silver_sql.split())
    partition = re.search(
        r"PARTITION BY e\.cik, e\.payload_sha256, e\.former_name, e\.from_date",
        window,
    )
    assert partition, "former-name dedupe must key on (cik, payload_sha256, former_name, from_date)"

    payload = json.loads(
        (FIXTURES / "same_former_name_two_periods.json").read_text(encoding="utf-8")
    )
    names = parse_registrant(payload, NOW).former_names
    atlas_periods = [
        (fn.name, fn.from_date) for fn in names if fn.name == "Atlas Re Corp."
    ]
    assert len(atlas_periods) == 2
    assert len(set(atlas_periods)) == 2, "both periods must be distinct rows"
    # Proof the from_date component is what keeps them apart: without it the
    # two periods collapse into a single key and one row would be dropped.
    assert len({name for name, _from in atlas_periods}) == 1


def test_silver_step_is_registered_in_runner():
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    assert (
        '("silver_sec_registrant", "silver/09_silver_sec_registrant.sql", "sql")'
        in runner
    )


# ── run_silver_gold: missing bronze source must SKIP, not abort ──────────────

_SILVER_STEPS_WITHOUT_KG0 = [
    "silver_ohlcv",
    "silver_ohlcv_quarantine_batch",
    "silver_options_quotes",
    "silver_options_trades",
    "silver_sec_sections",
    "silver_sec_entities",
    "silver_cot_positions",
    "silver_ohlcv_day_adjusted",
    "data_quality_breaks",
]


def _drive_runner_silver(monkeypatch, *, bronze_exists) -> list[str]:
    """Run ``main(--only silver)`` with a fake Spark and a recording executor.

    ``bronze_exists`` is True/False for a working catalog check, or None to make
    the check itself raise (permissions-style failure).  Every executed step is
    returned in order; no real SQL is ever run.
    """
    import pipelines.run_silver_gold as runner

    executed: list[str] = []

    class _Catalog:
        def tableExists(self, fqn: str) -> bool:
            assert fqn == f"{runner.FQN}.bronze_sec_submissions", fqn
            if bronze_exists is None:
                raise RuntimeError("PERMISSION_DENIED")
            return bronze_exists

    class _FakeSpark:
        def __init__(self):
            self.catalog = _Catalog()

        def sql(self, statement: str):  # pragma: no cover - must not be reached
            raise AssertionError(f"unexpected SQL in the step loop: {statement}")

    spark = _FakeSpark()
    monkeypatch.setattr(runner, "get_spark", lambda: spark)
    monkeypatch.setattr(runner, "register_universe", lambda s: ["AAA"])
    monkeypatch.setattr(
        runner, "run_step", lambda s, name, path, kind, syms: executed.append(name)
    )
    monkeypatch.setattr(runner, "count", lambda s, t: 0)
    monkeypatch.setattr(sys, "argv", ["run_silver_gold.py", "--only", "silver"])

    runner.main()
    return executed


def test_runner_skips_kg0_step_when_bronze_table_is_absent(monkeypatch, capsys):
    """BLOCKING regression (Opus M-1 / Sol P1): a shared refresh must not abort.

    Mutation: removing the existence check from the step loop executes the KG-0
    step here and the exact ``executed`` list assertion fails.
    """
    executed = _drive_runner_silver(monkeypatch, bronze_exists=False)
    out = capsys.readouterr().out

    assert executed == _SILVER_STEPS_WITHOUT_KG0
    assert "silver_sec_registrant" not in executed
    assert "SKIP silver_sec_registrant" in out
    assert "bronze_sec_submissions" in out


def test_runner_runs_kg0_step_when_bronze_table_exists(monkeypatch, capsys):
    """Once the owner has run the live ingest, the step runs in its slot."""
    executed = _drive_runner_silver(monkeypatch, bronze_exists=True)
    out = capsys.readouterr().out

    index = executed.index("silver_sec_registrant")
    assert executed[index - 1] == "silver_sec_entities"
    assert executed[index + 1] == "silver_cot_positions"
    assert executed[index + 2] == "silver_ohlcv_day_adjusted"
    assert "SKIP silver_sec_registrant" not in out


def test_runner_attempts_kg0_step_when_the_existence_check_fails(monkeypatch, capsys):
    """A broken check must attempt the step, never silently skip real work."""
    executed = _drive_runner_silver(monkeypatch, bronze_exists=None)
    out = capsys.readouterr().out

    assert "silver_sec_registrant" in executed
    assert "WARNING: cannot check" in out
    assert "SKIP silver_sec_registrant" not in out


# ── Job definition ───────────────────────────────────────────────────────────


def test_job_is_manual_and_single_concurrency():
    bundle = yaml.safe_load(JOBS_PATH.read_text(encoding="utf-8"))
    job = bundle["resources"]["jobs"]["sec_submissions_ingest"]

    assert "schedule" not in job
    assert job["max_concurrent_runs"] == 1
    task = job["tasks"][0]
    assert task["task_key"] == "ingest_sec_submissions"
    assert task["spark_python_task"]["python_file"] == (
        "../pipelines/ingest_sec_submissions.py"
    )
    assert task["environment_key"] == "serverless"
    params = task["spark_python_task"]["parameters"]
    assert "--catalog" in params and "--schema" in params
    # The job stays dry-run; a live run passes --live explicitly.
    assert "--live" not in params


def test_job_comment_documents_the_full_python_params_live_invocation():
    """``--python-params`` replaces the task parameters, so the owner must repeat
    the whole list.  A comment that shows only ``--live`` would lose --catalog,
    --schema and the User-Agent secret scope/key on a live run."""
    text = JOBS_PATH.read_text(encoding="utf-8")
    marker = "# KG-0 registrant identity."
    assert marker in text
    comment = text[text.index(marker):text.index("sec_submissions_ingest:")]

    assert "--python-params" in comment
    assert "REPLACES" in comment
    for flag in (
        "--catalog",
        "--schema",
        "--user-agent-secret-scope",
        "--user-agent-secret-key",
        "--live",
    ):
        assert flag in comment, f"live-run comment must show {flag}"
