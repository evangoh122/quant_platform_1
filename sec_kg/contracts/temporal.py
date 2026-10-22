"""sec_kg/contracts/temporal.py — bitemporal contract (KG-A).

Design of record: ``KG_DATA_MODEL_v4`` §F, ``v3`` §2.

Base tables are **insert-only event logs**::

    *_events(entity_id, attribute, value, valid_from, valid_to,
              recorded_at, supersedes_event_id)

``system_from``/``system_to`` are never written; they are *derived* from
``recorded_at`` and supersession.  A late arrival that splits an interval is
one correction event per split piece, each superseding the earlier event.

Both query modes filter first and resolve business time second:

``system_replay``
    keep the beliefs held by the system at ``T`` (``system_from <= T <
    system_to``), then resolve the requested business time.
``public_as_of``
    keep every event that was public at ``T`` (known ``public_available_at <=
    T``), then drop any eligible event that another **eligible** event
    supersedes, then resolve.  Filtering deliberately does **not** require the
    row to be the current belief: a correction that only becomes public in the
    future must not erase an eligible predecessor (Sol R3 S3).  Supersession is
    applied among the eligible events, so a correction that is public at ``T``
    always beats the event it corrects, whichever of the two was published
    first (Opus R4 MAJOR 1).  The supersession chain is followed through
    events that are not (yet) public, so a public correction also corrects the
    older eligible event behind a never-public link (Opus R4 MINOR 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Iterable, List, Mapping, Optional, Tuple

from config.data_sources import validate_data_source
from sec_kg.model import ensure_utc, normalize_unicode

UTC = timezone.utc


class TemporalView(str, Enum):
    PUBLIC_AS_OF = "public_as_of"
    SYSTEM_REPLAY = "system_replay"


class TemporalError(ValueError):
    """Base class for temporal-contract violations."""


class DanglingSupersessionError(TemporalError):
    """A correction supersedes an event that is not in the log."""


class SupersessionCycleError(TemporalError):
    """Supersession links form a cycle."""


class IntervalError(TemporalError):
    """Invalid business or system interval."""


def _as_datetime(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise TemporalError(f"{label} must be a datetime, got {type(value).__name__}")
    return ensure_utc(value)


def _as_business_time(value) -> datetime:
    """Accept ``datetime`` (any tz) or ``date`` (interpreted as UTC midnight)."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0), tzinfo=UTC)
    raise TemporalError(
        f"business time must be a date or datetime, got {type(value).__name__}"
    )


def normalise_view(view) -> TemporalView:
    """Coerce ``view`` to :class:`TemporalView` or raise."""
    if isinstance(view, TemporalView):
        return view
    try:
        return TemporalView(str(view))
    except ValueError:
        raise TemporalError(
            "view must be 'public_as_of' or 'system_replay', got "
            f"{view!r}"
        ) from None


# ── Events ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AttributeEvent:
    """One insert-only row of an ``*_events`` log.

    ``data_source`` is required and validated against the one provider
    vocabulary (``RULE-data-source-column``): a submissions-sourced name is
    ``sec_edgar``, a Company-Facts ``entityName`` is ``sec_companyfacts`` and a
    classification derived here is ``derived``.
    """

    event_id: str
    entity_id: str
    attribute: str
    value: str
    valid_from: datetime
    valid_to: Optional[datetime]
    recorded_at: datetime
    data_source: str
    public_available_at: Optional[datetime] = None
    supersedes_event_id: Optional[str] = None
    evidence_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not normalize_unicode(str(self.event_id)):
            raise IntervalError("event_id must not be blank")
        if not normalize_unicode(str(self.entity_id)):
            raise IntervalError("entity_id must not be blank")
        if not normalize_unicode(str(self.attribute)):
            raise IntervalError("attribute must not be blank")
        try:
            data_source = validate_data_source(self.data_source)
        except ValueError as error:
            raise IntervalError(f"event {self.event_id}: {error}") from error
        object.__setattr__(self, "data_source", data_source)
        object.__setattr__(self, "event_id", normalize_unicode(str(self.event_id)))
        object.__setattr__(self, "entity_id", normalize_unicode(str(self.entity_id)))
        object.__setattr__(self, "attribute", normalize_unicode(str(self.attribute)))
        start = _as_datetime(self.valid_from, "valid_from")
        object.__setattr__(self, "valid_from", start)
        if self.valid_to is not None:
            end = _as_datetime(self.valid_to, "valid_to")
            if end <= start:
                raise IntervalError(
                    f"event {self.event_id}: valid_to {end.isoformat()} must be "
                    f"after valid_from {start.isoformat()}"
                )
            object.__setattr__(self, "valid_to", end)
        object.__setattr__(
            self, "recorded_at", _as_datetime(self.recorded_at, "recorded_at")
        )
        if self.public_available_at is not None:
            object.__setattr__(
                self,
                "public_available_at",
                _as_datetime(self.public_available_at, "public_available_at"),
            )

    def covers(self, business_time) -> bool:
        moment = _as_business_time(business_time)
        if moment < self.valid_from:
            return False
        return self.valid_to is None or moment < self.valid_to


@dataclass(frozen=True)
class DerivedInterval:
    """An event paired with the system interval derived for it."""

    event: AttributeEvent
    system_from: datetime
    system_to: Optional[datetime]

    def visible_in_system(self, knowledge_time: datetime) -> bool:
        moment = _as_datetime(knowledge_time, "knowledge_time")
        if moment < self.system_from:
            return False
        return self.system_to is None or moment < self.system_to


# ── Derived system intervals ────────────────────────────────────────────────

def derive_system_intervals(
    events: Iterable[AttributeEvent],
) -> Tuple[DerivedInterval, ...]:
    """Derive ``system_from``/``system_to`` from ``recorded_at`` + supersession.

    ``system_to`` is the ``recorded_at`` of the earliest event that directly
    supersedes this one, ``None`` while it is the current belief.  An interval
    may be empty when a correction is recorded at the same instant as the
    original; empty intervals are never visible, which keeps equal-time events
    deterministic.
    """
    log: dict = {}
    for event in events:
        if not isinstance(event, AttributeEvent):
            raise TemporalError(
                f"expected AttributeEvent, got {type(event).__name__}"
            )
        if event.event_id in log:
            raise TemporalError(f"duplicate event_id: {event.event_id}")
        log[event.event_id] = event

    superseders: dict = {}
    for event in log.values():
        target = event.supersedes_event_id
        if target is None:
            continue
        if target not in log:
            raise DanglingSupersessionError(
                f"event {event.event_id} supersedes unknown event {target}"
            )
        superseders.setdefault(target, []).append(event)

    # Cycle detection over the supersession graph (iterative DFS).
    _reject_supersession_cycles(log)

    derived: List[DerivedInterval] = []
    for event in log.values():
        system_from = event.recorded_at
        later = superseders.get(event.event_id, [])
        system_to = min((other.recorded_at for other in later), default=None)
        if system_to is not None and system_to < system_from:
            raise IntervalError(
                f"event {event.event_id}: superseding event recorded before it "
                f"({system_to.isoformat()} < {system_from.isoformat()})"
            )
        derived.append(
            DerivedInterval(event=event, system_from=system_from, system_to=system_to)
        )
    derived.sort(key=lambda interval: (interval.system_from, interval.event.event_id))
    return tuple(derived)


def _reject_supersession_cycles(log: Mapping[str, AttributeEvent]) -> None:
    state: dict = {}
    for start in sorted(log):
        if state.get(start) == "done":
            continue
        path: List[str] = []
        current: Optional[str] = start
        while current is not None:
            status = state.get(current)
            if status == "done":
                break
            if status == "visiting":
                cycle_start = path.index(current)
                raise SupersessionCycleError(
                    "supersession cycle: "
                    + " -> ".join(path[cycle_start:] + [current])
                )
            state[current] = "visiting"
            path.append(current)
            event = log.get(current)
            current = None if event is None else event.supersedes_event_id
        for node in path:
            state[node] = "done"


# ── Visibility ──────────────────────────────────────────────────────────────

def _publicly_eligible(
    interval: DerivedInterval, knowledge_time: datetime
) -> bool:
    """Known public availability at or before *T*; unknown is never eligible."""
    available = interval.event.public_available_at
    return available is not None and available <= knowledge_time


def _drop_publicly_superseded(
    intervals: Iterable[DerivedInterval],
    supersedes_by_event: Mapping[str, Optional[str]],
) -> Tuple[DerivedInterval, ...]:
    """Remove every eligible event an *also eligible* event supersedes.

    Supersession is applied **among the events visible in the requested view**,
    before business time is resolved (Opus R4 MAJOR 1).  Otherwise a superseded
    event whose correction became public later keeps winning on its own public
    timestamp and the public view leaks a value the record had already
    corrected.  A correction that is not yet eligible is not in the set, so it
    still cannot erase an eligible predecessor (Sol R3 S3).

    The correction chain is followed **transitively through events that are not
    (yet) public** (Opus R4 MINOR 1).  If public ``e3`` supersedes
    never-public ``e2``, which superseded public ``e1``, then ``e1`` is
    corrected and must not answer either: the public view must agree with
    ``system_replay`` at the same business time.  ``supersedes_by_event`` is
    the *whole* log's ``event_id -> supersedes_event_id`` map, so the walk can
    pass through ineligible links.
    """
    kept = tuple(intervals)
    superseded: set = set()
    for interval in kept:
        target = supersedes_by_event.get(interval.event.event_id)
        seen: set = set()
        while target is not None and target not in seen:
            seen.add(target)
            superseded.add(target)
            target = supersedes_by_event.get(target)
    return tuple(
        interval for interval in kept if interval.event.event_id not in superseded
    )


def visible_intervals(
    events: Iterable[AttributeEvent],
    entity_id: str,
    view,
    knowledge_time: datetime,
    attribute: Optional[str] = None,
) -> Tuple[DerivedInterval, ...]:
    """Belief rows visible in *view* at *knowledge_time*, before business time.

    ``public_as_of`` filters on public availability first and then applies
    supersession among the surviving events, so a public correction beats the
    event it corrects regardless of which of the two became public first.  The
    correction chain is followed through events that are not eligible, so a
    public correction still corrects an older eligible event when the link
    between them is a never-public one.
    """
    mode = normalise_view(view)
    moment = _as_datetime(knowledge_time, "knowledge_time")
    wanted_entity = normalize_unicode(str(entity_id))
    wanted_attribute = (
        normalize_unicode(str(attribute)) if attribute is not None else None
    )
    intervals = derive_system_intervals(events)
    supersedes_by_event = {
        interval.event.event_id: interval.event.supersedes_event_id
        for interval in intervals
    }
    selected = []
    for interval in intervals:
        event = interval.event
        if event.entity_id != wanted_entity:
            continue
        if wanted_attribute is not None and event.attribute != wanted_attribute:
            continue
        if mode is TemporalView.SYSTEM_REPLAY:
            if interval.visible_in_system(moment):
                selected.append(interval)
        else:
            if _publicly_eligible(interval, moment):
                selected.append(interval)
    if mode is TemporalView.PUBLIC_AS_OF:
        selected = list(
            _drop_publicly_superseded(selected, supersedes_by_event)
        )
    selected.sort(key=lambda interval: (interval.event.valid_from, interval.event.event_id))
    return tuple(selected)


def _rank(interval: DerivedInterval, mode: TemporalView):
    event = interval.event
    if mode is TemporalView.PUBLIC_AS_OF:
        return (
            event.public_available_at,
            event.valid_from,
            event.recorded_at,
            event.event_id,
        )
    return (event.valid_from, event.recorded_at, event.event_id)


# ── Resolution ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Resolution:
    entity_id: str
    attribute: str
    value: str
    event_id: str
    valid_from: datetime
    valid_to: Optional[datetime]
    recorded_at: datetime
    public_available_at: Optional[datetime]
    view: str
    knowledge_time: datetime
    business_time: datetime

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "attribute": self.attribute,
            "value": self.value,
            "event_id": self.event_id,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": None if self.valid_to is None else self.valid_to.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "public_available_at": (
                None
                if self.public_available_at is None
                else self.public_available_at.isoformat()
            ),
            "view": self.view,
            "knowledge_time": self.knowledge_time.isoformat(),
            "business_time": self.business_time.isoformat(),
        }


def resolve(
    events: Iterable[AttributeEvent],
    entity_id: str,
    business_time,
    view,
    knowledge_time: datetime,
    attribute: Optional[str] = None,
) -> Optional[Resolution]:
    """Filter by ``knowledge_time`` first, then resolve ``business_time``.

    With ``attribute=None`` the log for the entity must contain exactly one
    attribute (two attributes are independent series and must be resolved
    separately).
    """
    mode = normalise_view(view)
    moment = _as_datetime(knowledge_time, "knowledge_time")
    business = _as_business_time(business_time)
    wanted_entity = normalize_unicode(str(entity_id))

    entity_events = [
        event for event in events if event.entity_id == wanted_entity
    ]
    if attribute is None:
        attributes = {event.attribute for event in entity_events}
        if len(attributes) > 1:
            raise TemporalError(
                f"entity {wanted_entity!r} has several attributes {sorted(attributes)}; "
                "pass attribute= to disambiguate"
            )
        if attributes:
            attribute = next(iter(attributes))

    eligible = visible_intervals(
        entity_events, wanted_entity, mode, moment, attribute=attribute
    )
    matches = [interval for interval in eligible if interval.event.covers(business)]
    if not matches:
        return None
    best = max(matches, key=lambda interval: _rank(interval, mode))
    event = best.event
    return Resolution(
        entity_id=event.entity_id,
        attribute=event.attribute,
        value=event.value,
        event_id=event.event_id,
        valid_from=event.valid_from,
        valid_to=event.valid_to,
        recorded_at=event.recorded_at,
        public_available_at=event.public_available_at,
        view=mode.value,
        knowledge_time=moment,
        business_time=business,
    )


def public_as_of(
    events: Iterable[AttributeEvent],
    entity_id: str,
    business_time,
    knowledge_time: datetime,
    attribute: Optional[str] = None,
) -> Optional[Resolution]:
    return resolve(
        events,
        entity_id,
        business_time,
        TemporalView.PUBLIC_AS_OF,
        knowledge_time,
        attribute=attribute,
    )


def system_replay(
    events: Iterable[AttributeEvent],
    entity_id: str,
    business_time,
    knowledge_time: datetime,
    attribute: Optional[str] = None,
) -> Optional[Resolution]:
    return resolve(
        events,
        entity_id,
        business_time,
        TemporalView.SYSTEM_REPLAY,
        knowledge_time,
        attribute=attribute,
    )


# ── Date helpers ────────────────────────────────────────────────────────────

def at_midnight_utc(day: date) -> datetime:
    """Start-of-day UTC for an inclusive source date."""
    return datetime.combine(day, time(0, 0), tzinfo=UTC)


def day_after(day: date) -> datetime:
    """Exclusive end of an inclusive source date (``to`` + 1 day)."""
    return at_midnight_utc(day + timedelta(days=1))


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO timestamp and require an explicit offset."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise IntervalError(f"timestamp {value!r} must carry a UTC offset")
    return ensure_utc(parsed)
