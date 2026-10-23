"""Filing de-duplication (Sol R4 S9 / v4 §H).

Equal ``ingest_ts`` resolves on the smallest ``record_key``; absent metadata
becomes ``null`` plus a quality issue; conflicts keep the earliest row's value
and are reported.  Results are independent of ingestion order.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pytest

from sec_kg.contracts import filings

ACCESSION = "0001045810-24-000001"
ACCESSION_LATER = "0001045810-24-000002"
CIK = "0001045810"
EQUA = datetime(2024, 1, 29, 12, 0, tzinfo=timezone.utc)


def dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def equal_ingest_rows():
    """Three chunk rows of one accession, all ingested at the same instant."""
    common = {
        "accession": ACCESSION,
        "ingest_ts": EQUA,
        "cik": CIK,
        "filing_date": "2024-01-28",
        "filing_url": "https://www.sec.gov/Archives/edgar/data/1045810/x-index.htm",
        "period_of_report": None,
        "amendment_target": None,
    }
    rows = [
        filings.FilingRow(
            record_key="b",
            form_type="10-K",
            accepted_ts=dt(2024, 1, 28, 12),
            bronze_company_label=None,
            primary_doc=None,
            **common,
        ),
        filings.FilingRow(
            record_key="a",
            form_type="10-K/A",
            accepted_ts=dt(2024, 1, 28, 11),
            bronze_company_label=None,
            primary_doc=None,
            **common,
        ),
        filings.FilingRow(
            record_key="c",
            form_type="10-Q",
            accepted_ts=dt(2024, 1, 28, 10),
            bronze_company_label=None,
            primary_doc=None,
            **common,
        ),
    ]
    return rows


def earlier_ingest_rows():
    """Two rows where the earliest ingest has the *larger* record_key."""
    return [
        filings.FilingRow(
            accession=ACCESSION_LATER,
            record_key="z",
            ingest_ts=dt(2024, 2, 1, 1),
            cik=CIK,
            form_type="10-K",
            filing_date="2024-01-31",
            accepted_ts=dt(2024, 1, 31, 23),
            bronze_company_label="NVIDIA Corporation",
            primary_doc="primary.htm",
            filing_url="https://www.sec.gov/Archives/edgar/data/1045810/y-index.htm",
        ),
        filings.FilingRow(
            accession=ACCESSION_LATER,
            record_key="a",
            ingest_ts=dt(2024, 2, 1, 2),
            cik=CIK,
            form_type="10-Q",
            filing_date="2024-01-31",
            accepted_ts=dt(2024, 1, 31, 22),
            bronze_company_label="NVIDIA Corporation",
            primary_doc="primary.htm",
            filing_url="https://www.sec.gov/Archives/edgar/data/1045810/y-index.htm",
        ),
    ]


def test_filing_dedup_equal_ingest_missing_metadata_shuffle():
    rows = equal_ingest_rows() + earlier_ingest_rows()
    result = filings.dedupe_filings(rows)

    assert len(result.filings) == 2
    by_accession = {filing.accession: filing for filing in result.filings}
    deduped = by_accession[ACCESSION]

    # Equal ingest_ts: the smallest record_key wins every disputed field.
    assert deduped.record_key == "a"
    assert deduped.form_type == "10-K/A"
    assert deduped.accepted_ts == dt(2024, 1, 28, 11)
    # Shared metadata is taken as-is, with no issue.
    assert deduped.filing_date == "2024-01-28"
    assert deduped.cik == CIK
    assert deduped.source_row_count == 3
    # Absent metadata becomes null plus a quality issue, never an invented value.
    assert deduped.bronze_company_label is None
    assert deduped.primary_doc is None
    # The bronze column is surfaced as a label, never as a registrant name.
    assert "bronze_company_label" in deduped.as_row()
    assert "company_name" not in deduped.as_row()
    # Nullable evidence-only fields are null without an issue.
    assert deduped.period_of_report is None
    assert deduped.amendment_target is None

    missing = {
        issue.field for issue in result.issues
        if issue.accession == ACCESSION and issue.kind == filings.ISSUE_MISSING
    }
    assert missing == {"bronze_company_label", "primary_doc"}
    conflicts = {
        issue.field: issue for issue in result.issues
        if issue.accession == ACCESSION and issue.kind == filings.ISSUE_CONFLICT
    }
    assert set(conflicts) == {"form_type", "accepted_ts"}
    assert conflicts["form_type"].values == ("10-K", "10-K/A", "10-Q")
    assert set(conflicts["form_type"].record_keys) == {"a", "b", "c"}
    # No issue is raised for fields that were shared.
    assert "filing_date" not in missing and "filing_date" not in conflicts
    assert "period_of_report" not in missing
    assert "amendment_target" not in missing

    # Earliest ingest_ts outranks record_key ordering.
    later = by_accession[ACCESSION_LATER]
    assert later.record_key == "z"
    assert later.form_type == "10-K"
    assert later.accepted_ts == dt(2024, 1, 31, 23)
    assert later.bronze_company_label == "NVIDIA Corporation"
    assert later.primary_doc == "primary.htm"

    # Every ingestion permutation yields byte-identical rows and issues.
    baseline_rows = result.as_rows()
    baseline_issues = result.issue_rows()
    for permutation in itertools.permutations(rows):
        candidate = filings.dedupe_filings(permutation)
        assert candidate.as_rows() == baseline_rows
        assert candidate.issue_rows() == baseline_issues
    # Repeated runs are idempotent.
    assert filings.dedupe_filings(rows).as_rows() == baseline_rows

    # A group whose metadata is shared by every row produces no issues at all.
    shared_rows = [
        filings.FilingRow(
            accession="0001045810-24-000003",
            record_key=key,
            ingest_ts=EQUA,
            cik=CIK,
            form_type="10-K",
            filing_date="2024-01-28",
            accepted_ts=dt(2024, 1, 28, 12),
            bronze_company_label="NVIDIA Corporation",
            primary_doc="primary.htm",
            filing_url="https://www.sec.gov/Archives/edgar/data/1045810/x-index.htm",
        )
        for key in ("b", "a")
    ]
    shared = filings.dedupe_filings(shared_rows)
    assert shared.issues == ()
    assert shared.filings[0].record_key == "a"

    # Malformed identity is rejected, never silently dropped.
    with pytest.raises(filings.FilingsError):
        filings.FilingRow(accession="", record_key="a", ingest_ts=EQUA)
    with pytest.raises(filings.FilingsError):
        filings.FilingRow(accession=ACCESSION, record_key="", ingest_ts=EQUA)


# ═══════════════════════════════════════════════════════════════════════════════
# CodeRabbit full review (PR #76) items 2 and 3 — a total tie-break order for
# identical row identities, and real calendar dates
# ═══════════════════════════════════════════════════════════════════════════════

def test_equal_ingest_and_record_key_resolve_by_payload_not_input_order():
    common = {
        "accession": ACCESSION,
        "record_key": "same",
        "ingest_ts": EQUA,
        "cik": CIK,
        "filing_date": "2024-01-28",
    }
    first = filings.FilingRow(
        form_type="10-K",
        accepted_ts=dt(2024, 1, 28, 12),
        primary_doc="a.htm",
        **common,
    )
    second = filings.FilingRow(
        form_type="10-Q",
        accepted_ts=dt(2024, 1, 28, 11),
        primary_doc="b.htm",
        **common,
    )

    baseline = filings.dedupe_filings([first, second])
    # Every ingestion permutation yields byte-identical rows and issues, even
    # though `ingest_ts` and `record_key` are identical: the payload columns
    # complete the order.
    for permutation in itertools.permutations([first, second]):
        candidate = filings.dedupe_filings(permutation)
        assert candidate.as_rows() == baseline.as_rows()
        assert candidate.issue_rows() == baseline.issue_rows()
    assert baseline.filings[0].record_key == "same"
    assert baseline.filings[0].form_type == "10-K"
    assert baseline.filings[0].primary_doc == "a.htm"
    conflict = next(
        issue for issue in baseline.issues
        if issue.field == "form_type" and issue.kind == filings.ISSUE_CONFLICT
    )
    assert conflict.values == ("10-K", "10-Q")


def test_filing_dates_must_be_real_calendar_dates():
    impossible = filings.FilingRow(
        accession=ACCESSION,
        record_key="a",
        ingest_ts=EQUA,
        filing_date="2024-02-30",
    )
    with pytest.raises(filings.FilingsError, match="calendar"):
        filings.dedupe_filings([impossible])

    bad_period = filings.FilingRow(
        accession=ACCESSION,
        record_key="a",
        ingest_ts=EQUA,
        filing_date="2024-01-28",
        period_of_report="2024-04-31",
    )
    with pytest.raises(filings.FilingsError, match="calendar"):
        filings.dedupe_filings([bad_period])

    # A real leap day still passes: the check is calendar validity, not a ban
    # on unusual dates.
    leap = filings.FilingRow(
        accession=ACCESSION,
        record_key="a",
        ingest_ts=EQUA,
        filing_date="2024-02-29",
        period_of_report="2024-02-29",
    )
    deduped = filings.dedupe_filings([leap]).filings[0]
    assert deduped.filing_date == "2024-02-29"
    assert deduped.period_of_report == "2024-02-29"
