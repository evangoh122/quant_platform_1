"""sec_kg/contracts/facts.py — fact grain, reconciliation and linking (KG-A).

Design of record: ``KG_DATA_MODEL_v4`` §E, ``v3`` §4.

Keys::

    series_key      = (company_id, concept_id, unit, period_id, dimensions_hash)
    assertion_key   = series_key + filing_id
    observation_key = assertion_key + source + entry_hash

``entry_hash`` is the SHA-256 of the canonical JSON of the source entry
(``value_raw, unit, start, end, instant, fy, fp, form, filed, frame, accn``), so
two different values asserted by the same filing are two observations and
nothing collapses.  ``dimensions_hash`` is ``∅`` when the source carries no
XBRL context dimensions (documented in the design).

Order is fixed everywhere: **filter** by the requested view first, then
**reconcile** among the eligible rows only.  Linking follows the same rule for
its reference data: a concept -> metric mapping or evidence row that is not
visible at the requested knowledge time cannot link a fact or make it
ambiguous.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from config.data_sources import validate_data_source
from sec_kg.contracts.temporal import TemporalView, normalise_view
from sec_kg.model import deterministic_json, ensure_utc, normalize_unicode, parse_decimal

DIMENSIONS_HASH_ABSENT = "∅"

SOURCE_COMPANYFACTS = "companyfacts"
SOURCE_ENTITY_EXTRACTION = "entity_extraction"
SOURCES: Tuple[str, ...] = (SOURCE_COMPANYFACTS, SOURCE_ENTITY_EXTRACTION)

#: Provider code carried by every observation row of each source
#: (``RULE-data-source-column``): Company-Facts observations come from the SEC
#: XBRL API, entity-extraction observations are computed here from SEC text.
SOURCE_DATA_SOURCES: Mapping[str, str] = {
    SOURCE_COMPANYFACTS: "sec_companyfacts",
    SOURCE_ENTITY_EXTRACTION: "derived",
}

ENTRY_HASH_FIELDS: Tuple[str, ...] = (
    "value_raw",
    "unit",
    "start",
    "end",
    "instant",
    "fy",
    "fp",
    "form",
    "filed",
    "frame",
    "accn",
)

AMENDED_FORM_SUFFIX = "/A"

#: Link rejection reasons (stable strings, used by quality reporting).
LINK_LINKED = "linked"
LINK_NO_CANDIDATE = "no_candidate"
LINK_AMBIGUOUS = "ambiguous"
LINK_CROSS_ISSUER = "cross_issuer"
LINK_METRIC_MISMATCH = "metric_mismatch"
LINK_PERIOD_MISMATCH = "period_mismatch"
LINK_UNIT_INCOMPATIBLE = "unit_incompatible"
LINK_UNKNOWN_DIMENSIONS = "unknown_dimensions"
LINK_DIMENSIONS_MISMATCH = "dimensions_mismatch"
LINK_VALUE_MISMATCH = "value_mismatch"


class FactError(ValueError):
    """Base class for fact-contract violations."""


class ObservationConsistencyError(FactError):
    """An observation key was reused with a different payload."""


def _required(label: str, value: Any) -> str:
    text = normalize_unicode(str(value)) if value is not None else ""
    if not text:
        raise FactError(f"{label} must not be blank")
    return text


def _normalise_dimensions_hash(value: Optional[str]) -> str:
    text = normalize_unicode(str(value)) if value is not None else ""
    return text or DIMENSIONS_HASH_ABSENT


def source_data_source(source: str) -> str:
    """Provider code for an observation source (``RULE-data-source-column``)."""
    key = normalize_unicode(str(source)).lower()
    try:
        return validate_data_source(SOURCE_DATA_SOURCES[key])
    except KeyError:
        raise FactError(
            f"unknown observation source {source!r}; expected one of {SOURCES}"
        ) from None


# ── Keys ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SeriesKey:
    company_id: str
    concept_id: str
    unit: str
    period_id: str
    dimensions_hash: str = DIMENSIONS_HASH_ABSENT

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", _required("company_id", self.company_id))
        object.__setattr__(self, "concept_id", _required("concept_id", self.concept_id))
        object.__setattr__(self, "unit", _required("unit", self.unit).upper())
        object.__setattr__(self, "period_id", _required("period_id", self.period_id))
        object.__setattr__(
            self,
            "dimensions_hash",
            _normalise_dimensions_hash(self.dimensions_hash),
        )

    def as_tuple(self) -> Tuple[str, ...]:
        return (
            self.company_id,
            self.concept_id,
            self.unit,
            self.period_id,
            self.dimensions_hash,
        )


@dataclass(frozen=True)
class AssertionKey:
    series: SeriesKey
    filing_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "filing_id", _required("filing_id", self.filing_id))

    def as_tuple(self) -> Tuple[str, ...]:
        return self.series.as_tuple() + (self.filing_id,)


@dataclass(frozen=True)
class ObservationKey:
    assertion: AssertionKey
    source: str
    entry_hash: str

    def __post_init__(self) -> None:
        source = normalize_unicode(str(self.source)).lower()
        if source not in SOURCES:
            raise FactError(f"source must be one of {SOURCES}, got {self.source!r}")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "entry_hash", _required("entry_hash", self.entry_hash))

    def as_tuple(self) -> Tuple[str, ...]:
        return self.assertion.as_tuple() + (self.source, self.entry_hash)


def series_key(
    company_id: str,
    concept_id: str,
    unit: str,
    period_id: str,
    dimensions_hash: Optional[str] = None,
) -> SeriesKey:
    return SeriesKey(
        company_id=company_id,
        concept_id=concept_id,
        unit=unit,
        period_id=period_id,
        dimensions_hash=dimensions_hash,
    )


def assertion_key(series: SeriesKey, filing_id: str) -> AssertionKey:
    return AssertionKey(series=series, filing_id=filing_id)


def _canonical_entry_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return normalize_unicode(str(value))


def canonical_entry(entry: Mapping[str, Any]) -> dict:
    """Canonical, sorted-key payload that ``entry_hash`` hashes."""
    return {
        name: _canonical_entry_value(entry.get(name)) for name in ENTRY_HASH_FIELDS
    }


def entry_hash(entry: Mapping[str, Any]) -> str:
    payload = deterministic_json(canonical_entry(entry))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def observation_key(
    assertion: AssertionKey, source: str, entry: Mapping[str, Any]
) -> ObservationKey:
    return ObservationKey(
        assertion=assertion, source=source, entry_hash=entry_hash(entry)
    )


# ── Observations ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Observation:
    key: ObservationKey
    value_raw: str
    value_decimal: Optional[Decimal]
    form_type: str
    public_available_at: Optional[datetime]
    system_from: datetime
    system_to: Optional[datetime] = None
    conflict_flag: bool = False
    evidence_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "value_raw", normalize_unicode(str(self.value_raw)))
        object.__setattr__(self, "form_type", normalize_unicode(str(self.form_type or "")))
        object.__setattr__(
            self, "system_from", ensure_utc(self.system_from)
        )
        if self.system_to is not None:
            system_to = ensure_utc(self.system_to)
            if system_to <= self.system_from:
                raise FactError("system_to must be after system_from")
            object.__setattr__(self, "system_to", system_to)
        if self.public_available_at is not None:
            object.__setattr__(
                self,
                "public_available_at",
                ensure_utc(self.public_available_at),
            )

    @property
    def is_amendment(self) -> bool:
        return self.form_type.upper().endswith(AMENDED_FORM_SUFFIX)

    @property
    def data_source(self) -> str:
        """Provider of this observation row (Company-Facts -> sec_companyfacts)."""
        return source_data_source(self.key.source)

    def as_row(self) -> Dict[str, Any]:
        """Row contract, including the required ``data_source``."""
        return {
            "company_id": self.key.assertion.series.company_id,
            "concept_id": self.key.assertion.series.concept_id,
            "unit": self.key.assertion.series.unit,
            "period_id": self.key.assertion.series.period_id,
            "dimensions_hash": self.key.assertion.series.dimensions_hash,
            "filing_id": self.key.assertion.filing_id,
            "source": self.key.source,
            "entry_hash": self.key.entry_hash,
            "value_raw": self.value_raw,
            "value_decimal": (
                None if self.value_decimal is None else str(self.value_decimal)
            ),
            "form_type": self.form_type,
            "public_available_at": (
                None
                if self.public_available_at is None
                else self.public_available_at.isoformat()
            ),
            "system_from": self.system_from.isoformat(),
            "system_to": (
                None if self.system_to is None else self.system_to.isoformat()
            ),
            "conflict_flag": self.conflict_flag,
            "evidence_id": self.evidence_id,
            "data_source": self.data_source,
        }

    def with_conflict(self, flag: bool = True) -> "Observation":
        return Observation(
            key=self.key,
            value_raw=self.value_raw,
            value_decimal=self.value_decimal,
            form_type=self.form_type,
            public_available_at=self.public_available_at,
            system_from=self.system_from,
            system_to=self.system_to,
            conflict_flag=flag,
            evidence_id=self.evidence_id,
        )


def make_observation(
    assertion: AssertionKey,
    entry: Mapping[str, Any],
    *,
    source: str = SOURCE_COMPANYFACTS,
    public_available_at: Optional[datetime],
    system_from: datetime,
    system_to: Optional[datetime] = None,
    evidence_id: Optional[str] = None,
) -> Observation:
    value_raw = entry.get("value_raw")
    if value_raw is None:
        raise FactError("entry.value_raw is required for an observation")
    raw = normalize_unicode(str(value_raw))
    decimal_value = entry.get("value_decimal")
    if decimal_value is None:
        decimal_value = parse_decimal(raw)
    elif not isinstance(decimal_value, Decimal):
        decimal_value = Decimal(str(decimal_value))
    return Observation(
        key=observation_key(assertion, source, entry),
        value_raw=raw,
        value_decimal=decimal_value,
        form_type=str(entry.get("form") or ""),
        public_available_at=public_available_at,
        system_from=system_from,
        system_to=system_to,
        evidence_id=evidence_id,
    )


_UNKNOWN_AVAILABILITY = datetime.min.replace(tzinfo=timezone.utc)


def _public_rank(observation: Observation) -> datetime:
    """Sort key for public availability; ``None`` (unverified) sorts first."""
    return observation.public_available_at or _UNKNOWN_AVAILABILITY


def _dedupe_sort_key(observation: Observation) -> tuple:
    """Total order inside one observation key, so input order never decides.

    ``entry_hash`` is part of the key and is therefore constant within a group;
    every other visible column completes the order: the documented
    ``(value_raw, evidence_id)`` prefix first, then ``system_from``, the public
    availability rank, and finally form/decimal/system_to/conflict as
    last-resort discriminators for a hand-built collision.
    """
    return (
        observation.value_raw,
        observation.evidence_id or "",
        observation.system_from,
        _public_rank(observation),
        observation.form_type,
        "" if observation.value_decimal is None else str(observation.value_decimal),
        observation.system_to or _UNKNOWN_AVAILABILITY,
        observation.conflict_flag,
    )


def dedupe_observations(
    observations: Iterable[Observation],
) -> Tuple[Observation, ...]:
    """Collapse duplicate observation keys, deterministically.

    Different values inside one payload have different ``entry_hash`` values and
    therefore different keys; they are kept.  A genuine key collision with a
    different payload is reported through ``conflict_flag`` on the survivor and
    resolved by the full :func:`_dedupe_sort_key` order, so ingestion order
    never decides.  Callers that query a view must filter **before** calling
    this (see :func:`filter_observations`).
    """
    grouped: dict = {}
    for observation in observations:
        key = observation.key.as_tuple()
        grouped.setdefault(key, []).append(observation)

    survivors: List[Observation] = []
    for key in sorted(grouped):
        group = sorted(grouped[key], key=_dedupe_sort_key)
        winner = group[0]
        if any(other.value_raw != winner.value_raw for other in group[1:]):
            winner = winner.with_conflict(True)
        survivors.append(winner)
    return tuple(survivors)


# ── Filter-then-reconcile ───────────────────────────────────────────────────

class ReconciliationError(FactError):
    """Reconciliation was asked to run without an explicit view."""


@dataclass(frozen=True)
class Reconciliation:
    selected: Optional[Observation]
    conflicts: Tuple[Observation, ...]
    excluded: Tuple[Observation, ...]
    view: str

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)


def filter_observations(
    observations: Iterable[Observation], view, knowledge_time: datetime
) -> Tuple[Tuple[Observation, ...], Tuple[Observation, ...]]:
    """Return ``(eligible, excluded)`` for the requested view.

    Visibility is decided for every raw row **before** de-duplication, so a copy
    that is visible at ``knowledge_time`` always survives even when an invisible
    copy of the same key would win the tie-break.  Each partition is then
    de-duplicated independently, and a key kept as eligible is never repeated in
    ``excluded``.
    """
    mode = normalise_view(view)
    moment = ensure_utc(knowledge_time)
    visible: List[Observation] = []
    hidden: List[Observation] = []
    for observation in observations:
        if mode is TemporalView.SYSTEM_REPLAY:
            is_visible = observation.system_from <= moment and (
                observation.system_to is None or moment < observation.system_to
            )
        else:
            is_visible = (
                observation.public_available_at is not None
                and observation.public_available_at <= moment
            )
        (visible if is_visible else hidden).append(observation)
    eligible = dedupe_observations(visible)
    kept = {item.key.as_tuple() for item in eligible}
    excluded = tuple(
        item
        for item in dedupe_observations(hidden)
        if item.key.as_tuple() not in kept
    )
    return eligible, excluded


def _precedence_selection(eligible: Sequence[Observation]) -> Observation:
    """v3 §4 precedence: availability, amendment, system time, entry hash."""
    # (1) latest public_available_at; unknown availability sorts first
    best_public = max(_public_rank(item) for item in eligible)
    candidates = [
        item for item in eligible if _public_rank(item) == best_public
    ]
    # (2) an amended form outranks the original for the same asserting filing
    candidates = [item for item in candidates if item.is_amendment] or candidates
    # (3) newest system_from
    best_system = max(item.system_from for item in candidates)
    candidates = [item for item in candidates if item.system_from == best_system]
    # (4) smallest entry_hash, then evidence id, then value
    return min(
        candidates,
        key=lambda item: (
            item.key.entry_hash,
            item.evidence_id or "",
            item.value_raw,
        ),
    )


def reconcile(
    observations: Iterable[Observation],
    *,
    view,
    knowledge_time: datetime,
) -> Reconciliation:
    """Filter by *view* at *knowledge_time*, then select one assertion value."""
    mode = normalise_view(view)
    eligible, excluded = filter_observations(observations, mode, knowledge_time)
    selected = _precedence_selection(eligible) if eligible else None
    conflicts = tuple(
        item.with_conflict(True)
        for item in eligible
        if selected is None or item.key.as_tuple() != selected.key.as_tuple()
    )
    return Reconciliation(
        selected=selected,
        conflicts=conflicts,
        excluded=excluded,
        view=mode.value,
    )


def reconcile_series(
    observations: Iterable[Observation],
    *,
    view,
    knowledge_time: datetime,
) -> dict:
    """Reconcile every series independently; keys are ``series.as_tuple()``."""
    grouped: dict = {}
    for observation in observations:
        grouped.setdefault(
            observation.key.assertion.series.as_tuple(), []
        ).append(observation)
    return {
        series: reconcile(items, view=view, knowledge_time=knowledge_time)
        for series, items in sorted(grouped.items())
    }


# ── Extracted-fact linking ──────────────────────────────────────────────────

@dataclass(frozen=True)
class ExtractedFact:
    """A ``silver_sec_entities`` fact: no taxonomy, no XBRL dimensions."""

    company_id: str
    metric_id: str
    period_id: str
    unit: str
    value_raw: str
    dimensions_hash: str = DIMENSIONS_HASH_ABSENT
    evidence_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", _required("company_id", self.company_id))
        object.__setattr__(self, "metric_id", _required("metric_id", self.metric_id))
        object.__setattr__(self, "period_id", _required("period_id", self.period_id))
        object.__setattr__(self, "unit", _required("unit", self.unit).upper())
        object.__setattr__(
            self,
            "dimensions_hash",
            _normalise_dimensions_hash(self.dimensions_hash),
        )

    @property
    def data_source(self) -> str:
        """Extracted from SEC narrative, i.e. computed in this project."""
        return "derived"


@dataclass(frozen=True)
class LinkCandidate:
    """One Company-Facts assertion that an extracted fact could link to.

    ``metric_id`` is the *mapped* metric for the assertion's concept (the
    concept -> metric mapping is versioned separately); a candidate whose
    mapping is unknown cannot compete.

    A candidate also carries the **visibility** of the mapping/evidence row
    that produced it, because a mapping that is not visible in the requested
    view must not influence linking (Opus R4 MAJOR 3 / Sol R4 P2):

    ``public_available_at``
        when the mapping became public; ``None`` means unverified, which is
        never eligible in ``public_as_of``;
    ``system_from``/``system_to``
        the derived system interval of the mapping row, used by
        ``system_replay``.  An unknown ``system_from`` is never eligible.
    """

    assertion: AssertionKey
    value_raw: str
    metric_id: str
    decimals: int = 0
    public_available_at: Optional[datetime] = None
    system_from: Optional[datetime] = None
    system_to: Optional[datetime] = None

    def __post_init__(self) -> None:
        _required("metric_id", self.metric_id)
        _required("value_raw", self.value_raw)
        if self.public_available_at is not None:
            object.__setattr__(
                self,
                "public_available_at",
                ensure_utc(self.public_available_at),
            )
        if self.system_from is not None:
            object.__setattr__(self, "system_from", ensure_utc(self.system_from))
        if self.system_to is not None:
            system_to = ensure_utc(self.system_to)
            if self.system_from is not None and system_to <= self.system_from:
                raise FactError(
                    "candidate system_to must be after system_from"
                )
            object.__setattr__(self, "system_to", system_to)

    @property
    def company_id(self) -> str:
        return self.assertion.series.company_id

    @property
    def concept_id(self) -> str:
        return self.assertion.series.concept_id

    @property
    def period_id(self) -> str:
        return self.assertion.series.period_id

    @property
    def unit(self) -> str:
        return self.assertion.series.unit

    @property
    def dimensions_hash(self) -> str:
        return self.assertion.series.dimensions_hash

    def visible_in(self, view, knowledge_time: datetime) -> bool:
        """Is this candidate's mapping/evidence row visible in *view* at *T*?"""
        mode = normalise_view(view)
        moment = ensure_utc(knowledge_time)
        if mode is TemporalView.SYSTEM_REPLAY:
            if self.system_from is None:
                return False
            return self.system_from <= moment and (
                self.system_to is None or moment < self.system_to
            )
        return (
            self.public_available_at is not None
            and self.public_available_at <= moment
        )


def filter_candidates(
    candidates: Iterable[LinkCandidate], view, knowledge_time: datetime
) -> Tuple[LinkCandidate, ...]:
    """Keep only the candidates whose mapping/evidence is visible at *T*.

    Filtering happens **before** any dimension matching, so a future or
    unverified mapping can neither link a fact nor make it ambiguous, in either
    query mode.
    """
    mode = normalise_view(view)
    moment = ensure_utc(knowledge_time)
    return tuple(
        candidate
        for candidate in candidates
        if candidate.visible_in(mode, moment)
    )


@dataclass(frozen=True)
class LinkResult:
    assertion: Optional[AssertionKey]
    reason: str
    matched: Tuple[AssertionKey, ...] = ()

    @property
    def linked(self) -> bool:
        return self.assertion is not None


def values_match(left: Any, right: Any, decimals: int = 0) -> bool:
    """Match two decimals at the assertion's stated scale.

    ``decimals`` is the XBRL ``decimals`` attribute and **may be negative**:
    ``-3`` states the value in thousands and ``-6`` in millions, exactly like a
    positive value states it in tenths/hundredths.  The tolerance is half a unit
    of that stated scale (``10 ** -decimals / 2``), i.e. the rounding interval
    of the assertion, so ``-3`` accepts a 400 difference and rejects 600.
    ``decimals == 0`` keeps the exact comparison: an assertion precise to the
    unit must not absorb a sub-unit difference (Opus R4 MINOR 8).
    """
    if not isinstance(decimals, int) or isinstance(decimals, bool):
        raise FactError(
            f"decimals must be an int (XBRL decimals may be negative), got "
            f"{decimals!r}"
        )
    left_value = _as_decimal(left)
    right_value = _as_decimal(right)
    if left_value is None or right_value is None:
        return False
    if decimals == 0:
        return left_value == right_value
    tolerance = (Decimal(10) ** -decimals) / 2
    return abs(left_value - right_value) <= tolerance


def _as_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if value is None:
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def link_extracted_fact(
    fact: ExtractedFact,
    candidates: Iterable[LinkCandidate],
    *,
    view,
    knowledge_time: datetime,
    decimals: Optional[int] = None,
) -> LinkResult:
    """Link an extracted fact to a unique Company-Facts assertion or reject.

    Candidates are first filtered by visibility in *view* at *knowledge_time*:
    a concept -> metric mapping (or its evidence row) that is not yet public, or
    whose availability is unknown, does not exist for this query and therefore
    cannot influence the result.  Every dimension of the surviving assertions
    must then agree — company, metric, period (including its type), unit, XBRL
    dimensions — and the value must match at the stated decimal scale.  Anything
    ambiguous stays unlinked.
    """
    mode = normalise_view(view)
    moment = ensure_utc(knowledge_time)
    pool = list(filter_candidates(candidates, mode, moment))
    if not pool:
        return LinkResult(None, LINK_NO_CANDIDATE)

    by_company = [item for item in pool if item.company_id == fact.company_id]
    if not by_company:
        return LinkResult(None, LINK_CROSS_ISSUER, tuple(item.assertion for item in pool))

    by_metric = [item for item in by_company if item.metric_id == fact.metric_id]
    if not by_metric:
        return LinkResult(
            None, LINK_METRIC_MISMATCH, tuple(item.assertion for item in by_company)
        )

    by_period = [item for item in by_metric if item.period_id == fact.period_id]
    if not by_period:
        return LinkResult(
            None, LINK_PERIOD_MISMATCH, tuple(item.assertion for item in by_metric)
        )

    by_unit = [item for item in by_period if item.unit == fact.unit]
    if not by_unit:
        return LinkResult(
            None, LINK_UNIT_INCOMPATIBLE, tuple(item.assertion for item in by_period)
        )

    dimension_hashes = {item.dimensions_hash for item in by_unit}
    if len(dimension_hashes) > 1:
        return LinkResult(
            None, LINK_UNKNOWN_DIMENSIONS, tuple(item.assertion for item in by_unit)
        )
    if dimension_hashes != {fact.dimensions_hash}:
        return LinkResult(
            None, LINK_DIMENSIONS_MISMATCH, tuple(item.assertion for item in by_unit)
        )

    matched = [
        item
        for item in by_unit
        if values_match(
            fact.value_raw,
            item.value_raw,
            item.decimals if decimals is None else decimals,
        )
    ]
    if not matched:
        return LinkResult(
            None, LINK_VALUE_MISMATCH, tuple(item.assertion for item in by_unit)
        )
    if len(matched) > 1:
        return LinkResult(
            None, LINK_AMBIGUOUS, tuple(item.assertion for item in matched)
        )
    return LinkResult(matched[0].assertion, LINK_LINKED, (matched[0].assertion,))
