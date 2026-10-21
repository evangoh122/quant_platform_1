"""sec_kg/contracts/names.py — registrant name precedence (KG-A).

Design of record: ``KG_DATA_MODEL_v4`` §A.

``bronze_sec_filings_v2.company_name`` is *not* a company name (the ingestion
planner passes the canonical ticker into it), so it is removed from name
precedence entirely.  Precedence is:

1. SEC submissions ``formerNames`` intervals, with their stated inclusive
   ``from``/``to`` dates;
2. the submissions current ``name``, valid from the end of the last former name
   (or from first observation when there is none);
3. Company-Facts ``entityName`` — observation-time evidence only, never a
   reconciled label.

Inclusive source dates are converted explicitly to half-open UTC intervals
(``to`` + 1 day at 00:00Z).  Gaps between former-name intervals stay gaps: no
name is inferred across them.  Ties at one instant resolve by rank, then by the
lexicographically smaller evidence id.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, List, Optional, Tuple

from sec_kg.contracts.temporal import at_midnight_utc, day_after
from sec_kg.model import ensure_utc, normalize_unicode

NAME_SOURCE_FORMER = "former_name"
NAME_SOURCE_CURRENT = "current_name"
NAME_SOURCE_OBSERVATION = "company_facts_observation"

RANK_FORMER = 1
RANK_CURRENT = 2
RANK_OBSERVATION = 3


class NameError(ValueError):
    """Base class for name-contract violations."""


def _required(label: str, value: str) -> str:
    text = normalize_unicode(str(value)) if value is not None else ""
    if not text:
        raise NameError(f"{label} must not be blank")
    return text


def _as_date(value: date, label: str) -> date:
    if isinstance(value, datetime):
        raise NameError(f"{label} must be a date, not a datetime")
    if not isinstance(value, date):
        raise NameError(f"{label} must be a date, got {type(value).__name__}")
    return value


@dataclass(frozen=True)
class FormerName:
    """One ``formerNames`` entry; both dates are inclusive in the source."""

    name: str
    from_date: date
    to_date: date
    evidence_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required("former name", self.name))
        start = _as_date(self.from_date, "from_date")
        end = _as_date(self.to_date, "to_date")
        if end < start:
            raise NameError(
                f"former name {self.name!r}: to_date {end} precedes from_date {start}"
            )
        object.__setattr__(self, "from_date", start)
        object.__setattr__(self, "to_date", end)
        object.__setattr__(
            self, "evidence_id", normalize_unicode(str(self.evidence_id or ""))
        )

    def half_open_interval(self) -> Tuple[datetime, datetime]:
        """Inclusive ``[from, to]`` -> half-open ``[from, to + 1 day)`` UTC."""
        return (at_midnight_utc(self.from_date), day_after(self.to_date))


@dataclass(frozen=True)
class SubmissionsSnapshot:
    """The submissions payload columns the contract needs."""

    current_name: str
    former_names: Tuple[FormerName, ...]
    first_observed_at: datetime
    observed_at: datetime
    evidence_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_name", _required("current_name", self.current_name))
        former = tuple(self.former_names)
        for item in former:
            if not isinstance(item, FormerName):
                raise NameError("former_names must contain FormerName values")
        object.__setattr__(self, "former_names", former)
        object.__setattr__(
            self, "first_observed_at", ensure_utc(self.first_observed_at)
        )
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(
            self, "evidence_id", normalize_unicode(str(self.evidence_id or ""))
        )


@dataclass(frozen=True)
class FactsNameObservation:
    """Company-Facts ``entityName``: an observation at ingestion time only."""

    name: str
    observed_at: datetime
    evidence_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required("entityName", self.name))
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(
            self, "evidence_id", normalize_unicode(str(self.evidence_id or ""))
        )


@dataclass(frozen=True)
class NameInterval:
    name: str
    valid_from: datetime
    valid_to: Optional[datetime]
    source: str
    rank: int
    evidence_id: str = ""

    def covers(self, at: datetime) -> bool:
        moment = ensure_utc(at)
        if moment < self.valid_from:
            return False
        return self.valid_to is None or moment < self.valid_to

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": None if self.valid_to is None else self.valid_to.isoformat(),
            "source": self.source,
            "rank": self.rank,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True)
class NameHistory:
    intervals: Tuple[NameInterval, ...]
    observations: Tuple[FactsNameObservation, ...] = ()

    def resolve(self, at: datetime) -> Optional[NameInterval]:
        """The applicable name at *at*, or ``None`` inside an unsupported gap."""
        moment = ensure_utc(at)
        covering = [interval for interval in self.intervals if interval.covers(moment)]
        if not covering:
            return None
        # Higher rank wins, then the smaller evidence id, then the later start.
        covering.sort(
            key=lambda interval: (
                -interval.rank,
                interval.evidence_id,
                -interval.valid_from.timestamp(),
                interval.name,
            )
        )
        return covering[0]


def build_name_history(
    submissions: SubmissionsSnapshot,
    facts_names: Iterable[FactsNameObservation] = (),
) -> NameHistory:
    """Build label intervals plus observation-only Company-Facts names."""
    intervals: List[NameInterval] = []
    for former in submissions.former_names:
        start, end = former.half_open_interval()
        intervals.append(
            NameInterval(
                name=former.name,
                valid_from=start,
                valid_to=end,
                source=NAME_SOURCE_FORMER,
                rank=RANK_FORMER,
                evidence_id=former.evidence_id,
            )
        )

    if submissions.former_names:
        last_end = max(former.to_date for former in submissions.former_names)
        current_from = day_after(last_end)
    else:
        current_from = submissions.first_observed_at
    intervals.append(
        NameInterval(
            name=submissions.current_name,
            valid_from=current_from,
            valid_to=None,
            source=NAME_SOURCE_CURRENT,
            rank=RANK_CURRENT,
            evidence_id=submissions.evidence_id,
        )
    )
    intervals.sort(
        key=lambda interval: (
            interval.valid_from,
            interval.rank,
            interval.evidence_id,
            interval.name,
        )
    )

    observations = tuple(
        FactsNameObservation(
            name=item.name,
            observed_at=item.observed_at,
            evidence_id=item.evidence_id,
        )
        for item in facts_names
    )
    return NameHistory(intervals=tuple(intervals), observations=observations)


def resolve_name(history: NameHistory, at: datetime) -> Optional[NameInterval]:
    return history.resolve(at)


def name_intervals(history: NameHistory) -> Tuple[NameInterval, ...]:
    return history.intervals


def last_former_end(snapshot: SubmissionsSnapshot) -> Optional[date]:
    """End of the last former name, used to place the current name."""
    if not snapshot.former_names:
        return None
    return max(former.to_date for former in snapshot.former_names)


def inclusive_dates_to_half_open(
    from_date: date, to_date: date
) -> Tuple[datetime, datetime]:
    """Explicit inclusive -> half-open conversion used everywhere above."""
    start = _as_date(from_date, "from_date")
    end = _as_date(to_date, "to_date")
    if end < start:
        raise NameError(f"to_date {end} precedes from_date {start}")
    return at_midnight_utc(start), day_after(end)


def observation_only_names(
    history: NameHistory,
) -> Tuple[FactsNameObservation, ...]:
    return history.observations
