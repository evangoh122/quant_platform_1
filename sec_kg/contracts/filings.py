"""sec_kg/contracts/filings.py — accession de-duplication (KG-A).

Design of record: ``KG_DATA_MODEL_v3`` §5 and ``v4`` §H.

``dim_filing`` has one row per accession, grouped from the chunk-bearing bronze
rows.  For each metadata field: a value shared by every row wins; on
disagreement the value from the row with the earliest ``ingest_ts`` wins, with
the smallest ``record_key`` breaking ties at equal ``ingest_ts``.  Conflicts and
absent metadata become ``kg_quality_issues`` rows (absent metadata yields a
``null`` column, never an invented value).  ``period_of_report`` and the
amendment target are nullable by design and are sourced only from explicit
evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sec_kg.model import ensure_utc, normalize_accession, normalize_unicode

#: Fields that must always be resolved (missing -> null + quality issue).
CORE_METADATA_FIELDS: Tuple[str, ...] = (
    "cik",
    "form_type",
    "filing_date",
    "accepted_ts",
    "company_name",
    "primary_doc",
    "filing_url",
)

#: Nullable fields, populated only from evidence.
NULLABLE_METADATA_FIELDS: Tuple[str, ...] = (
    "period_of_report",
    "amendment_target",
)

METADATA_FIELDS: Tuple[str, ...] = CORE_METADATA_FIELDS + NULLABLE_METADATA_FIELDS

ISSUE_MISSING = "missing"
ISSUE_CONFLICT = "conflict"


class FilingsError(ValueError):
    """Base class for filing-contract violations."""


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = normalize_unicode(str(value))
    return text or None


def _as_utc(value: Any, label: str) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise FilingsError(f"{label} {value!r} must carry a UTC offset")
        return ensure_utc(parsed)
    raise FilingsError(f"{label} must be a datetime or ISO string, got {value!r}")


def _as_date(value: Any, label: str) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _text(value)
    if text is None:
        return None
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise FilingsError(f"{label} must be an ISO date (YYYY-MM-DD): {value!r}")
    return text


@dataclass(frozen=True)
class FilingRow:
    """One bronze row: a chunk or metadata row of one accession."""

    accession: str
    record_key: str
    ingest_ts: datetime
    cik: Optional[str] = None
    form_type: Optional[str] = None
    filing_date: Any = None
    accepted_ts: Any = None
    company_name: Optional[str] = None
    primary_doc: Optional[str] = None
    filing_url: Optional[str] = None
    period_of_report: Any = None
    amendment_target: Optional[str] = None

    def __post_init__(self) -> None:
        accession = normalize_accession(str(self.accession or ""))
        if not accession:
            raise FilingsError("accession must not be blank")
        object.__setattr__(self, "accession", accession)
        record_key = _text(self.record_key)
        if not record_key:
            raise FilingsError("record_key must not be blank")
        object.__setattr__(self, "record_key", record_key)
        object.__setattr__(
            self, "ingest_ts", ensure_utc(self.ingest_ts)
        )


@dataclass(frozen=True)
class QualityIssue:
    accession: str
    field: str
    kind: str
    values: Tuple[Optional[str], ...] = ()
    record_keys: Tuple[str, ...] = ()

    def as_row(self) -> Dict[str, Any]:
        return {
            "accession": self.accession,
            "field": self.field,
            "kind": self.kind,
            "values": list(self.values),
            "record_keys": list(self.record_keys),
        }


@dataclass(frozen=True)
class DimFiling:
    accession: str
    record_key: str
    source_row_count: int
    cik: Optional[str] = None
    form_type: Optional[str] = None
    filing_date: Optional[str] = None
    accepted_ts: Optional[datetime] = None
    company_name: Optional[str] = None
    primary_doc: Optional[str] = None
    filing_url: Optional[str] = None
    period_of_report: Optional[str] = None
    amendment_target: Optional[str] = None

    def as_row(self) -> Dict[str, Any]:
        return {
            "accession": self.accession,
            "cik": self.cik,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "accepted_ts": (
                None if self.accepted_ts is None else self.accepted_ts.isoformat()
            ),
            "company_name": self.company_name,
            "primary_doc": self.primary_doc,
            "filing_url": self.filing_url,
            "period_of_report": self.period_of_report,
            "amendment_target": self.amendment_target,
            "record_key": self.record_key,
            "source_row_count": self.source_row_count,
        }


@dataclass(frozen=True)
class DedupeResult:
    filings: Tuple[DimFiling, ...]
    issues: Tuple[QualityIssue, ...]

    def as_rows(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(filing.as_row() for filing in self.filings)

    def issue_rows(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(issue.as_row() for issue in self.issues)


def _field_value(row: FilingRow, field_name: str) -> Optional[str]:
    """Normalise a metadata field to a comparable string (or ``None``)."""
    if field_name == "accepted_ts":
        value = _as_utc(row.accepted_ts, "accepted_ts")
        return None if value is None else value.isoformat()
    if field_name == "filing_date":
        return _as_date(row.filing_date, "filing_date")
    if field_name == "period_of_report":
        return _as_date(row.period_of_report, "period_of_report")
    return _text(getattr(row, field_name))


def _resolve_field(
    accession: str,
    rows: Sequence[FilingRow],
    field_name: str,
) -> Tuple[Optional[str], List[QualityIssue]]:
    rows = sorted(rows, key=lambda row: (row.ingest_ts, row.record_key))
    candidates = [
        (row, _field_value(row, field_name))
        for row in rows
        if _field_value(row, field_name) is not None
    ]
    issues: List[QualityIssue] = []
    if not candidates:
        if field_name in CORE_METADATA_FIELDS:
            issues.append(
                QualityIssue(
                    accession=accession,
                    field=field_name,
                    kind=ISSUE_MISSING,
                    values=(None,),
                    record_keys=tuple(row.record_key for row in rows),
                )
            )
        return None, issues

    distinct = sorted({value for _, value in candidates})
    if len(distinct) == 1:
        return distinct[0], issues

    winner_row, winner_value = candidates[0]
    issues.append(
        QualityIssue(
            accession=accession,
            field=field_name,
            kind=ISSUE_CONFLICT,
            values=tuple(distinct),
            record_keys=tuple(row.record_key for row, _ in candidates),
        )
    )
    return winner_value, issues


def dedupe_filings(rows: Iterable[FilingRow]) -> DedupeResult:
    """Group bronze rows by accession into one ``dim_filing`` row each."""
    groups: Dict[str, List[FilingRow]] = {}
    for row in rows:
        if not isinstance(row, FilingRow):
            raise FilingsError(
                f"expected FilingRow, got {type(row).__name__}"
            )
        groups.setdefault(row.accession, []).append(row)

    filings: List[DimFiling] = []
    issues: List[QualityIssue] = []
    for accession in sorted(groups):
        group = sorted(groups[accession], key=lambda row: (row.ingest_ts, row.record_key))
        resolved: Dict[str, Optional[str]] = {}
        for field_name in METADATA_FIELDS:
            value, field_issues = _resolve_field(accession, group, field_name)
            resolved[field_name] = value
            issues.extend(field_issues)

        accepted = resolved["accepted_ts"]
        filings.append(
            DimFiling(
                accession=accession,
                record_key=group[0].record_key,
                source_row_count=len(group),
                cik=resolved["cik"],
                form_type=resolved["form_type"],
                filing_date=resolved["filing_date"],
                accepted_ts=(
                    None if accepted is None else datetime.fromisoformat(accepted)
                ),
                company_name=resolved["company_name"],
                primary_doc=resolved["primary_doc"],
                filing_url=resolved["filing_url"],
                period_of_report=resolved["period_of_report"],
                amendment_target=resolved["amendment_target"],
            )
        )

    issues.sort(key=lambda issue: (issue.accession, issue.field, issue.kind))
    return DedupeResult(filings=tuple(filings), issues=tuple(issues))
