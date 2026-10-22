"""sec_kg/contracts/registry.py — join contracts and the edge registry (KG-A).

Two registries, both executable rather than documentation:

``JOIN_CONTRACTS``
    One row per external table the graph joins to: grain (unique key),
    symbol namespace, the **business-time column**, the **stored availability
    column** (use it, never re-derive it), the AS-OF predicate and the
    cardinality to a security (``KG_DATA_MODEL_v3`` §7, ``v4`` §H).

``EDGE_CONTRACTS``
    One row per edge type with explicit source/destination node types,
    identity rule, required evidence and ownership scope (``v3`` §6).

Requirements are anchored to the SQL that produces each column through
``availability_evidence``; a test asserts the anchor really contains it.

Every produced row also declares its provider through the one vocabulary in
``config/data_sources.py``: join contracts list the providers of the external
table, edge contracts the provider(s) that may stamp an edge, and every
evidence row carries its own validated ``data_source``
(``.agents/requests/RULE-data-source-column.md``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from config.data_sources import (
    BINANCE_UM,
    CONFIG,
    DERIVED,
    HYPERLIQUID,
    MASSIVE,
    SEC_COMPANYFACTS,
    SEC_EDGAR,
    validate_data_source,
)
from sec_kg.model import (
    EDGE_TYPES,
    NODE_TYPES,
    deterministic_json,
    ensure_utc,
    normalize_unicode,
)

# ── Node kinds known to the contracts (superset of the v1 graph) ────────────

CONTRACT_NODE_KINDS: frozenset = frozenset(
    set(NODE_TYPES) | {"Security", "Instrument", "CryptoAsset"}
)

#: Node kinds whose rows belong to one company (subset builds replace them).
COMPANY_SCOPED_NODE_KINDS: frozenset = frozenset(
    {
        "Company",
        "Filing",
        "Section",
        "Chunk",
        "XbrlFact",
        "RiskFactor",
        "Event",
        "Segment",
        "Product",
        "Customer",
        "Security",
    }
)

#: Node kinds that are recomputed as the union of references (never deleted by
#: a subset build).  v4 §G names exactly these four.
GLOBAL_NODE_KINDS: frozenset = frozenset(
    {"Metric", "Period", "Concept", "CryptoAsset"}
)

#: Venue contracts are shared by every issuer that lists on the venue; their
#: ownership is *not* blanket-global: ``publication.row_owner`` derives it from
#: the underlying (a contract on a Security belongs to that security's company,
#: a contract on a CryptoAsset is global).  Kept here as the documented set of
#: venue product kinds.
VENUE_NODE_KINDS: frozenset = frozenset({"Instrument"})

NAMESPACES: frozenset = frozenset(
    {
        "massive",
        "sec_corpus",
        "hyperliquid",
        "binance_um",
        "config_universe",
        "perps",
    }
)

CARDINALITIES: frozenset = frozenset({"n:1", "1:1", "1:n"})

AVAILABILITY_STORED = "stored"
AVAILABILITY_STORED_SAME_AS_BUSINESS = "stored_same_as_business"
AVAILABILITY_VIA_JOIN = "via_join"
AVAILABILITY_DERIVED_BAR_CLOSE = "derived_bar_close"

AVAILABILITY_KINDS: frozenset = frozenset(
    {
        AVAILABILITY_STORED,
        AVAILABILITY_STORED_SAME_AS_BUSINESS,
        AVAILABILITY_VIA_JOIN,
        AVAILABILITY_DERIVED_BAR_CLOSE,
    }
)

EVIDENCE_KINDS: frozenset = frozenset(
    {
        "filing",
        "chunk",
        "xbrl_observation",
        "mapping_observation",
        "classification",
        "calendar",
    }
)

SCOPE_COMPANY = "company"
SCOPE_GLOBAL_TARGET = "global-target"
SCOPE_CROSS_COMPANY = "cross-company"

SCOPES: frozenset = frozenset(
    {SCOPE_COMPANY, SCOPE_GLOBAL_TARGET, SCOPE_CROSS_COMPANY}
)

#: Providers an evidence row of each kind may come from
#: (``RULE-data-source-column``: filing/section/chunk -> SEC EDGAR, XBRL facts
#: -> Company-Facts, symbol/listing bridges -> hand-maintained config, peer
#: classification -> derived).  A row that mixes providers is two rows.
EVIDENCE_DATA_SOURCES: Mapping[str, Tuple[str, ...]] = {
    "filing": (SEC_EDGAR,),
    "chunk": (SEC_EDGAR,),
    "xbrl_observation": (SEC_COMPANYFACTS,),
    "mapping_observation": (CONFIG,),
    "classification": (DERIVED,),
    "calendar": (CONFIG,),
}


def _validated_data_sources(values: Iterable[str], label: str) -> Tuple[str, ...]:
    """Validate and canonicalise a provider-code collection."""
    sources = tuple(values)
    if not sources:
        raise RegistryError(f"{label}: data_sources must not be empty")
    for value in sources:
        try:
            validate_data_source(value)
        except ValueError as error:
            raise RegistryError(f"{label}: {error}") from error
    return tuple(sorted(set(sources)))


class RegistryError(ValueError):
    """Base class for registry-contract violations."""


class UnknownTableError(RegistryError, KeyError):
    """The table is not registered."""


class UnknownEdgeTypeError(RegistryError, KeyError):
    """The edge type is not registered."""


class GrainViolation(RegistryError):
    """Rows violate the declared grain."""


class CardinalityViolation(RegistryError):
    """Rows violate the declared cardinality."""


class BridgeViolation(RegistryError):
    """A symbol bridge is ambiguous, overlapping or not yet observed."""


class EdgeContractError(RegistryError):
    """An edge violates its registered contract."""


# ── Join contracts ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class JoinContract:
    table: str
    grain: Tuple[str, ...]
    namespace: str
    business_time: str
    availability: str
    availability_kind: str
    as_of_predicate: str
    cardinality: str
    bridge: str
    data_sources: Tuple[str, ...]
    availability_evidence: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.table:
            raise RegistryError("table must not be blank")
        if not self.grain:
            raise RegistryError(f"{self.table}: grain must not be empty")
        if self.namespace not in NAMESPACES:
            raise RegistryError(
                f"{self.table}: unknown namespace {self.namespace!r}"
            )
        object.__setattr__(
            self,
            "data_sources",
            _validated_data_sources(self.data_sources, self.table),
        )
        if not self.business_time:
            raise RegistryError(f"{self.table}: business_time is required")
        if not self.availability:
            raise RegistryError(f"{self.table}: availability is required")
        if self.availability_kind not in AVAILABILITY_KINDS:
            raise RegistryError(
                f"{self.table}: unknown availability_kind {self.availability_kind!r}"
            )
        if self.cardinality not in CARDINALITIES:
            raise RegistryError(
                f"{self.table}: unknown cardinality {self.cardinality!r}"
            )
        if not self.as_of_predicate:
            raise RegistryError(f"{self.table}: as_of_predicate is required")
        if self.as_of_predicate.count("?") > 1:
            raise RegistryError(
                f"{self.table}: as_of_predicate must contain at most one placeholder"
            )

    @property
    def stored_availability(self) -> bool:
        return self.availability_kind in (
            AVAILABILITY_STORED,
            AVAILABILITY_STORED_SAME_AS_BUSINESS,
        )

    def columns(self) -> Tuple[str, ...]:
        ordered = list(self.grain)
        for column in (self.business_time, self.availability):
            if column not in ordered:
                ordered.append(column)
        return tuple(ordered)


JOIN_CONTRACTS: Dict[str, JoinContract] = {
    "gold_ohlcv_features": JoinContract(
        table="gold_ohlcv_features",
        grain=("symbol", "feature_ts"),
        namespace="massive",
        business_time="feature_ts",
        availability="information_available_ts",
        availability_kind=AVAILABILITY_STORED,
        as_of_predicate="information_available_ts <= ?",
        cardinality="n:1",
        bridge="bridge_security_symbol(provider='massive', symbol)",
        data_sources=(MASSIVE,),
        availability_evidence="gold/01_gold_ohlcv_features.sql",
        notes=(
            "information_available_ts is stored (bar start + bar interval); "
            "never re-derive it from feature_ts"
        ),
    ),
    "gold_options_features": JoinContract(
        table="gold_options_features",
        grain=("symbol", "feature_ts"),
        namespace="massive",
        business_time="feature_ts",
        availability="information_available_ts",
        availability_kind=AVAILABILITY_STORED,
        as_of_predicate="information_available_ts <= ?",
        cardinality="n:1",
        bridge="bridge_security_symbol(provider='massive', symbol)",
        data_sources=(MASSIVE,),
        availability_evidence="gold/02_gold_options_features.sql",
    ),
    "gold_model_features": JoinContract(
        table="gold_model_features",
        grain=("symbol", "prediction_ts"),
        namespace="massive",
        business_time="prediction_ts",
        availability="prediction_ts",
        availability_kind=AVAILABILITY_STORED_SAME_AS_BUSINESS,
        as_of_predicate="prediction_ts <= ?",
        cardinality="n:1",
        bridge="bridge_security_symbol(provider='massive', symbol)",
        data_sources=(MASSIVE, DERIVED),
        availability_evidence="gold/05_gold_model_features.sql",
        notes=(
            "prediction_ts is the availability timestamp of the last bar of the "
            "spine (last bar's feature_ts + 1 minute)"
        ),
    ),
    "gold_tradable_universe": JoinContract(
        table="gold_tradable_universe",
        grain=("trade_date", "symbol"),
        namespace="massive",
        business_time="trade_date",
        availability="information_available_ts",
        availability_kind=AVAILABILITY_STORED,
        as_of_predicate="information_available_ts <= ?",
        cardinality="n:1",
        bridge="bridge_security_symbol(provider='massive', symbol)",
        data_sources=(MASSIVE, CONFIG),
        availability_evidence="gold/06_gold_tradable_universe.sql",
        notes=(
            "information_available_ts = previous session close 16:00 New York "
            "+ pub_buffer_minutes"
        ),
    ),
    "silver_sec_sections": JoinContract(
        table="silver_sec_sections",
        grain=("chunk_id",),
        namespace="sec_corpus",
        business_time="accepted_ts",
        availability="accepted_ts",
        availability_kind=AVAILABILITY_STORED_SAME_AS_BUSINESS,
        as_of_predicate="accepted_ts <= ?",
        cardinality="1:1",
        bridge="Chunk node by source chunk_id",
        data_sources=(SEC_EDGAR,),
        availability_evidence="silver/05_silver_sec_sections.sql",
    ),
    "gold_sec_chunk_embeddings": JoinContract(
        table="gold_sec_chunk_embeddings",
        grain=("chunk_id",),
        namespace="sec_corpus",
        business_time="accepted_ts",
        availability="accepted_ts",
        availability_kind=AVAILABILITY_VIA_JOIN,
        as_of_predicate="accepted_ts <= ?",
        cardinality="1:1",
        bridge="Chunk node by source chunk_id",
        data_sources=(SEC_EDGAR, DERIVED),
        notes=(
            "embeddings carry no availability column; accepted_ts is joined from "
            "silver_sec_sections on chunk_id"
        ),
    ),
    "silver_sec_xbrl_facts": JoinContract(
        table="silver_sec_xbrl_facts",
        grain=("observation_key",),
        namespace="sec_corpus",
        business_time="filed_date",
        availability="public_available_at",
        availability_kind=AVAILABILITY_VIA_JOIN,
        as_of_predicate="public_available_at <= ?",
        cardinality="n:1",
        bridge="assertion/observation keys (no symbol join)",
        data_sources=(SEC_COMPANYFACTS, SEC_EDGAR),
        notes=(
            "public_available_at comes from dim_filing.accepted_ts; when it cannot "
            "be verified the observation is unverified and never eligible in "
            "public_as_of"
        ),
    ),
    "bridge_security_symbol": JoinContract(
        table="bridge_security_symbol",
        grain=("provider", "symbol", "valid_from"),
        namespace="config_universe",
        business_time="valid_from",
        availability="observed_at",
        availability_kind=AVAILABILITY_STORED,
        as_of_predicate="observed_at <= ?",
        cardinality="n:1",
        bridge="security_id (this table *is* the bridge)",
        data_sources=(CONFIG,),
        notes="half-open [valid_from, valid_to); intervals never overlap per (provider, symbol)",
    ),
    "perps_bars": JoinContract(
        table="perps_bars",
        grain=("instrument_id", "bar_ts"),
        namespace="perps",
        business_time="bar_ts",
        availability="bar_close",
        availability_kind=AVAILABILITY_DERIVED_BAR_CLOSE,
        as_of_predicate="bar_close <= ?",
        cardinality="n:1",
        bridge=(
            "bridge_security_symbol(provider IN ('hyperliquid','binance_um'), "
            "symbol) -> instrument -> underlying"
        ),
        data_sources=(HYPERLIQUID, BINANCE_UM),
        notes="bar_close = bar_ts + bar interval; perps ingestion is P1+",
    ),
}


def table_names() -> Tuple[str, ...]:
    return tuple(sorted(JOIN_CONTRACTS))


def get_contract(table: str) -> JoinContract:
    key = normalize_unicode(str(table))
    try:
        return JOIN_CONTRACTS[key]
    except KeyError:
        raise UnknownTableError(
            f"{table!r} has no join contract; registered: {table_names()}"
        ) from None


def business_time_column(table: str) -> str:
    return get_contract(table).business_time


def availability_column(table: str) -> str:
    return get_contract(table).availability


def availability_kind(table: str) -> str:
    return get_contract(table).availability_kind


def as_of_predicate(table: str, param: str = "T") -> str:
    contract = get_contract(table)
    predicate = contract.as_of_predicate
    if "?" in predicate:
        return predicate.replace("?", param)
    return predicate


def is_available(
    table: str, availability_value: Optional[datetime], query_time: datetime
) -> bool:
    """PIT eligibility: a NULL/unknown availability is never eligible.

    The table must have a registered join contract: an unregistered table has
    no declared availability column, so eligibility cannot be evaluated for it
    and is rejected rather than silently answered (Sol R4 P2).
    """
    get_contract(table)
    if availability_value is None:
        return False
    return ensure_utc(availability_value) <= ensure_utc(query_time)


def check_grain(table: str, rows: Iterable[Mapping[str, Any]]) -> int:
    """Verify the declared grain is unique; returns the row count."""
    contract = get_contract(table)
    seen: Dict[Tuple[Any, ...], int] = {}
    count = 0
    for index, row in enumerate(rows):
        key: list = []
        for column in contract.grain:
            if column not in row:
                raise GrainViolation(
                    f"{table}: row {index} is missing grain column {column!r}"
                )
            value = row[column]
            if value is None:
                raise GrainViolation(
                    f"{table}: row {index} has NULL grain column {column!r}"
                )
            key.append(value)
        tuple_key = tuple(key)
        if tuple_key in seen:
            raise GrainViolation(
                f"{table}: duplicate grain {tuple_key!r} at rows "
                f"{seen[tuple_key]} and {index}"
            )
        seen[tuple_key] = index
        count += 1
    return count


def _interval_bounds(
    row: Mapping[str, Any], label: str, columns: Tuple[str, str]
) -> Tuple[datetime, Optional[datetime]]:
    """Half-open ``[from, to)`` bounds of a row; ``None`` *to* is open-ended."""
    start_column, end_column = columns
    for column in (start_column, end_column):
        if column not in row:
            raise CardinalityViolation(
                f"{label}: row is missing interval column {column!r}"
            )
    start = ensure_utc(row[start_column])
    end = row[end_column]
    if end is None:
        return start, None
    end = ensure_utc(end)
    if end <= start:
        raise CardinalityViolation(
            f"{label}: interval {start_column}={start.isoformat()} must precede "
            f"{end_column}={end.isoformat()}"
        )
    return start, end


def _overlaps(
    left: Tuple[datetime, Optional[datetime]],
    right: Tuple[datetime, Optional[datetime]],
) -> bool:
    """Half-open interval overlap; an open end extends to infinity."""
    left_start, left_end = left
    right_start, right_end = right
    if left_end is not None and right_start >= left_end:
        return False
    if right_end is not None and left_start >= right_end:
        return False
    return True


def check_cardinality(
    table: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    left_column: str,
    right_column: str,
    interval_columns: Optional[Tuple[str, str]] = None,
) -> None:
    """Verify the declared cardinality between ``left_column`` and ``right``.

    For ``n:1`` every left value must map to exactly one right value (many rows
    per security is fine, two securities for one symbol is not).

    With ``interval_columns=(from, to)`` the cardinality is evaluated **per
    time**: a left value may map to several right values as long as their
    half-open validity intervals never overlap, so a ticker that is reused at
    non-overlapping times is allowed while an overlap at one instant is still a
    violation.  Without ``interval_columns`` every row is treated as
    concurrent, which is the strict reading (Sol R4 P2).
    """
    contract = get_contract(table)
    if contract.cardinality not in ("n:1", "1:1"):
        raise RegistryError(
            f"{table}: declared cardinality {contract.cardinality!r} cannot be "
            "validated with check_cardinality"
        )
    entries: List[Tuple[Any, Any, Tuple[datetime, Optional[datetime]]]] = []
    forward: Dict[Any, List[int]] = {}
    reverse: Dict[Any, List[int]] = {}
    for index, row in enumerate(rows):
        for column in (left_column, right_column):
            if column not in row:
                raise CardinalityViolation(
                    f"{table}: row {index} is missing column {column!r}"
                )
        left = row[left_column]
        right = row[right_column]
        if left is None or right is None:
            continue
        if interval_columns is None:
            window: Tuple[Any, Any] = (None, None)
        else:
            window = _interval_bounds(row, table, interval_columns)
        entries.append((left, right, window))
        forward.setdefault(left, []).append(len(entries) - 1)
        reverse.setdefault(right, []).append(len(entries) - 1)

    def _violations(indices: List[int], varying: int) -> List[Tuple[int, int]]:
        """Pairs inside ``indices`` whose *varying* value differs and overlaps.

        ``varying`` is 0 for the left column and 1 for the right column: the
        forward check varies ``right_column`` and the 1:1 reverse check varies
        ``left_column``.
        """
        clashing = []
        for position, first in enumerate(indices):
            for second in indices[position + 1:]:
                if entries[first][varying] == entries[second][varying]:
                    continue
                if interval_columns is None or _overlaps(
                    entries[first][2], entries[second][2]
                ):
                    clashing.append((first, second))
        return clashing

    for left, indices in sorted(forward.items(), key=lambda item: str(item[0])):
        rights = {entries[index][1] for index in indices}
        if len(rights) < 2:
            continue
        if _violations(indices, 1):
            raise CardinalityViolation(
                f"{table}: {left_column}={left!r} maps to {len(rights)} "
                f"{right_column} values {sorted(str(r) for r in rights)} but "
                f"cardinality is {contract.cardinality}"
                + ("" if interval_columns is None else " at overlapping times")
            )
    if contract.cardinality == "1:1":
        for right, indices in sorted(reverse.items(), key=lambda item: str(item[0])):
            lefts = {entries[index][0] for index in indices}
            if len(lefts) < 2:
                continue
            if _violations(indices, 0):
                raise CardinalityViolation(
                    f"{table}: {right_column}={right!r} maps to {len(lefts)} "
                    f"{left_column} values {sorted(str(l) for l in lefts)} but "
                    "cardinality is 1:1"
                    + ("" if interval_columns is None else " at overlapping times")
                )


# ── Provider-symbol bridge ──────────────────────────────────────────────────

@dataclass(frozen=True)
class SecuritySymbolBridge:
    """One provider-symbol -> security row (the ``bridge_security_symbol`` table).

    ``data_source`` is required and validated (``RULE-data-source-column``).  A
    bridge is hand-maintained repository config, so the registry's own join
    contract declares the only provider that may stamp it (``config``).

    ``provider`` (lower-cased) and ``symbol`` (whitespace-normalised, case
    preserved because provider symbols are not guaranteed case-insensitive) are
    normalised once here, so ``validate_bridge_rows`` and
    ``resolve_security_symbol`` operate on the same key.
    """

    provider: str
    symbol: str
    security_id: str
    valid_from: datetime
    valid_to: Optional[datetime]
    observed_at: datetime
    data_source: str
    mapping_status: str = "verified"
    evidence_id: Optional[str] = None

    def __post_init__(self) -> None:
        for label, value in (
            ("provider", self.provider),
            ("symbol", self.symbol),
            ("security_id", self.security_id),
        ):
            if not normalize_unicode(str(value)):
                raise BridgeViolation(f"{label} must not be blank")
        try:
            data_source = validate_data_source(self.data_source)
        except ValueError as error:
            raise BridgeViolation(f"bridge: {error}") from error
        allowed = get_contract("bridge_security_symbol").data_sources
        if data_source not in allowed:
            raise BridgeViolation(
                f"bridge: data_source {data_source!r} is not one of "
                f"{list(allowed)}"
            )
        object.__setattr__(self, "data_source", data_source)
        object.__setattr__(self, "provider", normalize_unicode(str(self.provider)).lower())
        object.__setattr__(self, "symbol", normalize_unicode(str(self.symbol)))
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        start = ensure_utc(self.valid_from)
        object.__setattr__(self, "valid_from", start)
        if self.valid_to is not None:
            end = ensure_utc(self.valid_to)
            if end <= start:
                raise BridgeViolation("bridge valid_to must be after valid_from")
            object.__setattr__(self, "valid_to", end)
        if self.mapping_status not in ("verified", "inferred", "unknown"):
            raise BridgeViolation(
                f"unknown mapping_status {self.mapping_status!r}"
            )

    def covers(self, business_time: datetime) -> bool:
        moment = ensure_utc(business_time)
        if moment < self.valid_from:
            return False
        return self.valid_to is None or moment < self.valid_to


def validate_bridge_rows(bridges: Iterable[SecuritySymbolBridge]) -> None:
    """Reject overlapping validity intervals per ``(provider, symbol)``."""
    grouped: Dict[Tuple[str, str], list] = {}
    for bridge in bridges:
        grouped.setdefault((bridge.provider, bridge.symbol), []).append(bridge)
    for (provider, symbol), rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda row: row.valid_from)
        for previous, current in zip(rows, rows[1:]):
            previous_end = previous.valid_to
            if previous_end is None or current.valid_from < previous_end:
                raise BridgeViolation(
                    f"{provider}/{symbol}: bridge intervals overlap "
                    f"({previous.valid_from.isoformat()}.."
                    f"{None if previous_end is None else previous_end.isoformat()}) and "
                    f"{current.valid_from.isoformat()}"
                )


def resolve_security_symbol(
    bridges: Iterable[SecuritySymbolBridge],
    *,
    provider: str,
    symbol: str,
    business_time: datetime,
    query_time: datetime,
) -> Optional[str]:
    """Resolve ``(provider, symbol)`` to a security as of *business_time*.

    The bridge row is selected by the **business** time (a ticker change after
    the business time must not rewrite history) and must already have been
    observed at *query_time*; future observations are not usable.
    """
    provider_key = normalize_unicode(str(provider)).lower()
    symbol_key = normalize_unicode(str(symbol))
    moment = ensure_utc(business_time)
    observed_by = ensure_utc(query_time)

    matches = [
        bridge
        for bridge in bridges
        if bridge.provider == provider_key
        and bridge.symbol == symbol_key
        and bridge.covers(moment)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise BridgeViolation(
            f"{provider_key}/{symbol_key} at {moment.isoformat()}: "
            f"{len(matches)} bridge rows match"
        )
    bridge = matches[0]
    if bridge.observed_at > observed_by:
        return None
    return bridge.security_id


# ── Edge contracts ──────────────────────────────────────────────────────────

REQUIRED_EDGE_FIELDS: Tuple[str, ...] = (
    "edge_id",
    "src_id",
    "edge_type",
    "dst_id",
    "data_source",
    "valid_from",
    "valid_to",
    "system_from",
    "system_to",
    "public_available_at",
    "system_observed_at",
    "confidence",
    "extraction_method",
    "evidence_count",
    "build_generation_id",
)


@dataclass(frozen=True)
class EdgeContract:
    edge_type: str
    src_types: Tuple[str, ...]
    dst_types: Tuple[str, ...]
    identity: Tuple[str, ...]
    evidence: Tuple[str, ...]
    scope: str
    data_sources: Tuple[str, ...]
    directional: bool = True
    symmetric: bool = False
    temporal: bool = True

    def __post_init__(self) -> None:
        if not self.edge_type:
            raise RegistryError("edge_type must not be blank")
        if self.scope not in SCOPES:
            raise RegistryError(
                f"{self.edge_type}: unknown scope {self.scope!r}"
            )
        object.__setattr__(
            self,
            "data_sources",
            _validated_data_sources(self.data_sources, self.edge_type),
        )
        if not self.src_types or not self.dst_types:
            raise RegistryError(f"{self.edge_type}: endpoints are required")
        for node_kind in self.src_types + self.dst_types:
            if node_kind not in CONTRACT_NODE_KINDS:
                raise RegistryError(
                    f"{self.edge_type}: unknown node kind {node_kind!r}"
                )
        if not self.identity:
            raise RegistryError(f"{self.edge_type}: identity rule is required")
        if not self.evidence:
            raise RegistryError(f"{self.edge_type}: evidence is required")
        for kind in self.evidence:
            if kind not in EVIDENCE_KINDS:
                raise RegistryError(
                    f"{self.edge_type}: unknown evidence kind {kind!r}"
                )
        if self.symmetric and not self.directional:
            raise RegistryError(
                f"{self.edge_type}: an undirected edge is stored once, once only"
            )


def _edge(
    edge_type: str,
    src_types: Sequence[str],
    dst_types: Sequence[str],
    identity: Sequence[str],
    evidence: Sequence[str],
    scope: str,
    *,
    data_sources: Sequence[str],
    symmetric: bool = False,
) -> EdgeContract:
    return EdgeContract(
        edge_type=edge_type,
        src_types=tuple(src_types),
        dst_types=tuple(dst_types),
        identity=tuple(identity),
        evidence=tuple(evidence),
        scope=scope,
        data_sources=tuple(data_sources),
        symmetric=symmetric,
    )


#: Edges derived from SEC filings (filings, sections, chunks, mentions).
_EDGAR_EDGE_SOURCES: Tuple[str, ...] = (SEC_EDGAR,)
#: Edges derived from XBRL Company-Facts observations.
_COMPANYFACTS_EDGE_SOURCES: Tuple[str, ...] = (SEC_COMPANYFACTS,)
#: Edges from hand-maintained symbol/listing/identity bridges.
_CONFIG_EDGE_SOURCES: Tuple[str, ...] = (CONFIG,)
#: Edges computed in this project from other rows.
_DERIVED_EDGE_SOURCES: Tuple[str, ...] = (DERIVED,)


EDGE_CONTRACTS: Dict[str, EdgeContract] = {
    "FILED": _edge(
        "FILED", ["Company"], ["Filing"], ["company_id", "filing_id"],
        ["filing"], SCOPE_COMPANY, data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "HAS_SECTION": _edge(
        "HAS_SECTION", ["Filing"], ["Section"], ["filing_id", "section_code"],
        ["chunk"], SCOPE_COMPANY, data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "HAS_CHUNK": _edge(
        "HAS_CHUNK", ["Section"], ["Chunk"], ["section_id", "source_chunk_id"],
        ["chunk"], SCOPE_COMPANY, data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "REPORTED_FACT": _edge(
        "REPORTED_FACT", ["Filing"], ["XbrlFact"], ["filing_id", "assertion_key"],
        ["xbrl_observation"], SCOPE_COMPANY,
        data_sources=_COMPANYFACTS_EDGE_SOURCES,
    ),
    "INSTANCE_OF": _edge(
        "INSTANCE_OF", ["XbrlFact"], ["Metric"],
        ["assertion_key", "metric_id", "mapping_version"],
        ["mapping_observation"], SCOPE_GLOBAL_TARGET,
        data_sources=(SEC_COMPANYFACTS, CONFIG),
    ),
    "FOR_PERIOD": _edge(
        "FOR_PERIOD", ["XbrlFact"], ["Period"],
        ["assertion_key", "period_id"], ["xbrl_observation"], SCOPE_GLOBAL_TARGET,
        data_sources=_COMPANYFACTS_EDGE_SOURCES,
    ),
    "SOURCED_FROM": _edge(
        "SOURCED_FROM", ["XbrlFact", "RiskFactor", "Event"], ["Chunk"],
        ["evidence_id", "source_chunk_id"], ["chunk"], SCOPE_COMPANY,
        data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "SUPERSEDES": _edge(
        "SUPERSEDES", ["XbrlFact"], ["XbrlFact"],
        ["new_assertion_key", "old_assertion_key"], ["xbrl_observation"],
        SCOPE_COMPANY, data_sources=_COMPANYFACTS_EDGE_SOURCES,
    ),
    "AMENDS": _edge(
        "AMENDS", ["Filing"], ["Filing"],
        ["amending_accession", "amended_accession"], ["filing"], SCOPE_COMPANY,
        data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "DISCLOSED_RISK": _edge(
        "DISCLOSED_RISK", ["Filing"], ["RiskFactor"],
        ["filing_id", "mention_key"], ["chunk"], SCOPE_COMPANY,
        data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "REPORTED_EVENT": _edge(
        "REPORTED_EVENT", ["Filing"], ["Event"],
        ["filing_id", "mention_key"], ["chunk"], SCOPE_COMPANY,
        data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "HAS_SEGMENT": _edge(
        "HAS_SEGMENT", ["Company"], ["Segment"],
        ["company_id", "segment_key"], ["chunk"], SCOPE_COMPANY,
        data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "HAS_PRODUCT": _edge(
        "HAS_PRODUCT", ["Company"], ["Product"],
        ["company_id", "product_key"], ["chunk"], SCOPE_COMPANY,
        data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "HAS_CUSTOMER": _edge(
        "HAS_CUSTOMER", ["Company"], ["Customer"],
        ["company_id", "customer_key"], ["chunk"], SCOPE_COMPANY,
        data_sources=_EDGAR_EDGE_SOURCES,
    ),
    "HAS_SECURITY": _edge(
        "HAS_SECURITY", ["Company"], ["Security"],
        ["company_id", "security_id"], ["mapping_observation"], SCOPE_COMPANY,
        data_sources=_CONFIG_EDGE_SOURCES,
    ),
    "LISTED_AS": _edge(
        "LISTED_AS", ["Security"], ["Instrument"],
        ["security_id", "instrument_id"], ["mapping_observation"], SCOPE_COMPANY,
        data_sources=_CONFIG_EDGE_SOURCES,
    ),
    "UNDERLIES": _edge(
        "UNDERLIES", ["CryptoAsset"], ["Instrument"],
        ["asset_id", "instrument_id"], ["mapping_observation"], SCOPE_GLOBAL_TARGET,
        data_sources=_CONFIG_EDGE_SOURCES,
    ),
    "INFERRED_PEER": _edge(
        "INFERRED_PEER", ["Company"], ["Company"],
        ["pair", "taxonomy", "code", "basis_date"], ["classification"],
        SCOPE_CROSS_COMPANY, data_sources=_DERIVED_EDGE_SOURCES, symmetric=True,
    ),
}


def get_edge_contract(edge_type: str) -> EdgeContract:
    key = normalize_unicode(str(edge_type)).upper()
    try:
        return EDGE_CONTRACTS[key]
    except KeyError:
        raise UnknownEdgeTypeError(
            f"{edge_type!r} has no edge contract; registered: "
            f"{tuple(sorted(EDGE_CONTRACTS))}"
        ) from None


def unregistered_v1_edge_types() -> Tuple[str, ...]:
    """v1 model edge types that the registry does not cover (must be empty)."""
    return tuple(sorted(set(EDGE_TYPES) - set(EDGE_CONTRACTS)))


def validate_evidence_row(
    evidence: Mapping[str, Any],
    contract: Optional[EdgeContract] = None,
) -> str:
    """Validate one evidence row; returns its evidence kind.

    Every evidence row carries its own validated ``data_source`` and that code
    must be one its kind can come from (``EVIDENCE_DATA_SOURCES``); when an edge
    contract is supplied the code must also be one the contract allows.
    """
    if not isinstance(evidence, Mapping):
        raise EdgeContractError(
            f"evidence row must be a mapping, got {type(evidence).__name__}"
        )
    kind = evidence.get("kind")
    if kind not in EVIDENCE_KINDS:
        raise EdgeContractError(f"unknown evidence kind {kind!r}")
    try:
        data_source = validate_data_source(evidence.get("data_source"))
    except ValueError as error:
        raise EdgeContractError(f"evidence {kind!r}: {error}") from error
    allowed = EVIDENCE_DATA_SOURCES[kind]
    if data_source not in allowed:
        raise EdgeContractError(
            f"evidence {kind!r}: data_source {data_source!r} is not one of "
            f"{list(allowed)}"
        )
    if contract is not None:
        if data_source not in contract.data_sources:
            raise EdgeContractError(
                f"{contract.edge_type}: evidence data_source {data_source!r} is "
                f"not one of {list(contract.data_sources)}"
            )
    return kind


def validate_edge(
    edge: Mapping[str, Any], endpoints: Mapping[str, str]
) -> EdgeContract:
    """Validate an edge row against its contract and the endpoint node types."""
    contract = get_edge_contract(str(edge.get("edge_type", "")))
    for field_name in ("src_id", "dst_id", "edge_type"):
        if not edge.get(field_name):
            raise EdgeContractError(f"edge is missing {field_name!r}")
    try:
        data_source = validate_data_source(edge.get("data_source"))
    except ValueError as error:
        raise EdgeContractError(f"{contract.edge_type}: {error}") from error
    if data_source not in contract.data_sources:
        raise EdgeContractError(
            f"{contract.edge_type}: data_source {data_source!r} is not one of "
            f"{list(contract.data_sources)}"
        )
    src_id = str(edge["src_id"])
    dst_id = str(edge["dst_id"])
    if src_id == dst_id:
        raise EdgeContractError(
            f"{contract.edge_type}: self edge is not allowed ({src_id})"
        )
    for label, node_id, allowed in (
        ("src", src_id, contract.src_types),
        ("dst", dst_id, contract.dst_types),
    ):
        node_kind = endpoints.get(node_id)
        if node_kind is None:
            raise EdgeContractError(
                f"{contract.edge_type}: unknown {label} endpoint {node_id}"
            )
        if node_kind not in allowed:
            raise EdgeContractError(
                f"{contract.edge_type}: {label} endpoint type {node_kind!r} is not "
                f"one of {allowed}"
            )
    if contract.symmetric and src_id > dst_id:
        raise EdgeContractError(
            f"{contract.edge_type}: symmetric edges are stored once with the "
            f"lower id first (got {src_id} -> {dst_id})"
        )
    evidence = edge.get("evidence") or ()
    if not evidence:
        raise EdgeContractError(
            f"{contract.edge_type}: evidence is required ({contract.evidence})"
        )
    for item in evidence:
        kind = validate_evidence_row(item, contract)
        if kind not in contract.evidence:
            raise EdgeContractError(
                f"{contract.edge_type}: evidence kind {kind!r} is not one of "
                f"{contract.evidence}"
            )
    identity_fields = edge.get("identity") or {}
    for name in contract.identity:
        if identity_fields.get(name) in (None, ""):
            raise EdgeContractError(
                f"{contract.edge_type}: identity field {name!r} is required"
            )
    if contract.temporal:
        for name in ("valid_from", "system_from"):
            if edge.get(name) in (None, ""):
                raise EdgeContractError(
                    f"{contract.edge_type}: temporal field {name!r} is required"
                )
    return contract


def edge_identity_values(
    edge: Mapping[str, Any], contract: Optional[EdgeContract] = None
) -> Tuple[Any, ...]:
    contract = contract or get_edge_contract(str(edge.get("edge_type", "")))
    identity = edge.get("identity") or {}
    missing = [name for name in contract.identity if name not in identity]
    if missing:
        raise EdgeContractError(
            f"{contract.edge_type}: identity is missing {missing}"
        )
    return tuple(identity[name] for name in contract.identity)


def serialize_edge(edge: Mapping[str, Any]) -> str:
    """Canonical edge serialization: sorted keys, decimals as strings, nulls.

    Every required field must be present — a missing field is a contract
    violation, not an implicit ``null`` — and ``data_source`` must be one known
    provider code, so an untyped edge can never be exported.
    """
    missing = [name for name in REQUIRED_EDGE_FIELDS if name not in edge]
    if missing:
        raise EdgeContractError(f"edge is missing required fields {missing}")
    try:
        validate_data_source(edge["data_source"])
    except ValueError as error:
        raise EdgeContractError(f"edge data_source: {error}") from error
    payload = {name: edge[name] for name in REQUIRED_EDGE_FIELDS}
    properties = edge.get("properties")
    payload["properties"] = dict(properties) if properties is not None else {}
    return deterministic_json(payload)
