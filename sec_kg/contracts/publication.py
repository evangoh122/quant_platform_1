"""sec_kg/contracts/publication.py — generations, CAS and subset ownership.

Design of record: ``KG_DATA_MODEL_v4`` §G, ``v3`` §8.

Publication is a compare-and-swap on a single-row pointer table::

    gold_sec_kg_current(pointer_id = 'current', generation_id, updated_at)

The swap succeeds only when the pointer still names the generation's
``predecessor_generation_id``; bootstrap inserts only while the pointer is
empty.  Affected rows = 1 means published, 0 means the CAS lost and the run is
marked FAILED with its outputs left unpublished.  A retry reuses the same
``generation_id`` and is a no-op success when that generation is already
current.  The production executor is injected, so the state machine is tested
without a warehouse.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple

from sec_kg.contracts.registry import (
    COMPANY_SCOPED_NODE_KINDS,
    GLOBAL_NODE_KINDS,
    SCOPE_CROSS_COMPANY,
    SCOPE_GLOBAL_TARGET,
    VENUE_NODE_KINDS,
    get_edge_contract,
)
from sec_kg.model import deterministic_json, ensure_utc, normalize_unicode

POINTER_ID = "current"

KIND_FULL = "full"
KIND_SUBSET = "subset"
GENERATION_KINDS: Tuple[str, ...] = (KIND_FULL, KIND_SUBSET)

STATUS_PENDING = "pending"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"
STATUSES: Tuple[str, ...] = (STATUS_PENDING, STATUS_PUBLISHED, STATUS_FAILED)

OUTCOME_PUBLISHED = "published"
OUTCOME_ALREADY_CURRENT = "already_current"
OUTCOME_STALE_PREDECESSOR = "stale_predecessor"
OUTCOME_CAS_FAILED = "cas_failed"
OUTCOME_MANIFEST_CONFLICT = "manifest_conflict"

OWNER_GLOBAL = "global"
OWNER_CROSS_COMPANY = "cross-company"
OWNER_COMPANY_PREFIX = "company:"


class PublicationError(ValueError):
    """Base class for publication-contract violations."""


class ManifestConflictError(PublicationError):
    """A generation id was reused for different content."""


class SubsetRejectedError(PublicationError):
    """A subset build would stale cross-company state."""


# ── Generation manifest ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Generation:
    generation_id: str
    predecessor_generation_id: Optional[str]
    kind: str
    input_versions: Mapping[str, int]
    output_versions: Mapping[str, int]
    created_at: datetime
    membership: Tuple[str, ...] = ()
    status: str = STATUS_PENDING

    def __post_init__(self) -> None:
        if not normalize_unicode(str(self.generation_id)):
            raise PublicationError("generation_id must not be blank")
        if self.kind not in GENERATION_KINDS:
            raise PublicationError(
                f"kind must be one of {GENERATION_KINDS}, got {self.kind!r}"
            )
        if self.status not in STATUSES:
            raise PublicationError(
                f"status must be one of {STATUSES}, got {self.status!r}"
            )
        if self.predecessor_generation_id is not None and not normalize_unicode(
            str(self.predecessor_generation_id)
        ):
            raise PublicationError("predecessor_generation_id must not be blank")
        if not self.input_versions:
            raise PublicationError("input_versions must not be empty")
        if not self.output_versions:
            raise PublicationError("output_versions must not be empty")
        for label, versions in (
            ("input_versions", self.input_versions),
            ("output_versions", self.output_versions),
        ):
            for table, version in versions.items():
                if not normalize_unicode(str(table)):
                    raise PublicationError(f"{label} has a blank table name")
                if not isinstance(version, int) or version < 0:
                    raise PublicationError(
                        f"{label}[{table!r}] must be a non-negative int"
                    )
        object.__setattr__(self, "input_versions", MappingProxyType(dict(self.input_versions)))
        object.__setattr__(self, "output_versions", MappingProxyType(dict(self.output_versions)))
        object.__setattr__(self, "created_at", ensure_utc(self.created_at))
        membership = tuple(sorted({normalize_unicode(str(m)) for m in self.membership}))
        if any(not member for member in membership):
            raise PublicationError("membership must not contain blank tickers")
        if self.kind == KIND_FULL and membership:
            raise PublicationError("a full generation must not declare membership")
        if self.kind == KIND_SUBSET and not membership:
            raise PublicationError("a subset generation must declare membership")
        object.__setattr__(self, "membership", membership)

    def with_status(self, status: str) -> "Generation":
        return Generation(
            generation_id=self.generation_id,
            predecessor_generation_id=self.predecessor_generation_id,
            kind=self.kind,
            input_versions=self.input_versions,
            output_versions=self.output_versions,
            created_at=self.created_at,
            membership=self.membership,
            status=status,
        )

    def content(self) -> Dict[str, Any]:
        """Content that defines the generation; ``status`` is a run column."""
        return {
            "generation_id": self.generation_id,
            "predecessor_generation_id": self.predecessor_generation_id,
            "kind": self.kind,
            "membership": list(self.membership),
            "input_versions": dict(self.input_versions),
            "output_versions": dict(self.output_versions),
            "created_at": self.created_at.isoformat(),
        }

    def digest(self) -> str:
        return hashlib.sha256(
            deterministic_json(self.content()).encode("utf-8")
        ).hexdigest()

    def as_row(self) -> Dict[str, Any]:
        row = self.content()
        row["status"] = self.status
        return row


class PointerExecutor(Protocol):
    """Injected persistence; the real one is a Delta MERGE + manifest table."""

    def read_pointer(self) -> Optional[str]: ...

    def compare_and_set(
        self, *, predecessor: Optional[str], generation_id: str
    ) -> int: ...

    def put_manifest(self, generation: Generation) -> None: ...

    def get_manifest(self, generation_id: str) -> Optional[Generation]: ...


@dataclass(frozen=True)
class PublishResult:
    published: bool
    outcome: str
    affected_rows: int
    pointer: Optional[str]
    generation: Generation


def publish(executor: PointerExecutor, generation: Generation) -> PublishResult:
    """Publish *generation* with compare-and-swap semantics.

    Idempotent: retrying an already-current generation is a successful no-op
    and never moves the pointer.  Reusing a generation id with different
    content is rejected as an immutable-manifest conflict.
    """
    existing = executor.get_manifest(generation.generation_id)
    if existing is not None and existing.digest() != generation.digest():
        return PublishResult(
            published=False,
            outcome=OUTCOME_MANIFEST_CONFLICT,
            affected_rows=0,
            pointer=executor.read_pointer(),
            generation=existing,
        )
    if existing is None:
        try:
            executor.put_manifest(generation)
        except ManifestConflictError:
            return PublishResult(
                published=False,
                outcome=OUTCOME_MANIFEST_CONFLICT,
                affected_rows=0,
                pointer=executor.read_pointer(),
                generation=generation,
            )

    current = executor.read_pointer()
    if current == generation.generation_id:
        stored = executor.get_manifest(generation.generation_id) or generation
        return PublishResult(
            published=True,
            outcome=OUTCOME_ALREADY_CURRENT,
            affected_rows=0,
            pointer=current,
            generation=stored,
        )
    if current != generation.predecessor_generation_id:
        failed = generation.with_status(STATUS_FAILED)
        _replace_manifest(executor, failed)
        return PublishResult(
            published=False,
            outcome=OUTCOME_STALE_PREDECESSOR,
            affected_rows=0,
            pointer=current,
            generation=failed,
        )

    affected = executor.compare_and_set(
        predecessor=generation.predecessor_generation_id,
        generation_id=generation.generation_id,
    )
    if affected == 1:
        published = generation.with_status(STATUS_PUBLISHED)
        _replace_manifest(executor, published)
        return PublishResult(
            published=True,
            outcome=OUTCOME_PUBLISHED,
            affected_rows=affected,
            pointer=executor.read_pointer(),
            generation=published,
        )
    failed = generation.with_status(STATUS_FAILED)
    _replace_manifest(executor, failed)
    return PublishResult(
        published=False,
        outcome=OUTCOME_CAS_FAILED,
        affected_rows=affected,
        pointer=executor.read_pointer(),
        generation=failed,
    )


def _replace_manifest(executor: PointerExecutor, generation: Generation) -> None:
    """Rewrite the run status of the same generation (content is unchanged)."""
    try:
        executor.put_manifest(generation)
    except ManifestConflictError as error:  # pragma: no cover - defensive
        raise PublicationError(
            f"status update changed manifest content: {error}"
        ) from error


# ── Ownership ──────────────────────────────────────────────────────────────

def row_owner(row: Mapping[str, Any]) -> str:
    """Return ``global``, ``cross-company`` or ``company:<company_id>``."""
    explicit = row.get("owner_company_id")
    if explicit is not None:
        owner = normalize_unicode(str(explicit))
        if not owner:
            raise PublicationError("owner_company_id must not be blank")
        return OWNER_COMPANY_PREFIX + owner

    edge_type = row.get("edge_type")
    if edge_type is not None:
        contract = get_edge_contract(str(edge_type))
        if contract.scope == SCOPE_CROSS_COMPANY:
            return OWNER_CROSS_COMPANY
        if contract.scope == SCOPE_GLOBAL_TARGET:
            # INSTANCE_OF / FOR_PERIOD are owned by the source fact's company
            # (v4 §G) even though the target node is global; UNDERLIES has no
            # company and belongs to the global union.
            company = row.get("company_id")
            if company is None:
                return OWNER_GLOBAL
            return OWNER_COMPANY_PREFIX + normalize_unicode(str(company))
        company = row.get("company_id")
        if company is None:
            raise PublicationError(
                f"{edge_type}: company-scoped edge is missing company_id"
            )
        return OWNER_COMPANY_PREFIX + normalize_unicode(str(company))

    node_kind = row.get("node_type")
    if node_kind is not None:
        if node_kind in GLOBAL_NODE_KINDS:
            return OWNER_GLOBAL
        if node_kind in VENUE_NODE_KINDS:
            return OWNER_GLOBAL
        if node_kind in COMPANY_SCOPED_NODE_KINDS:
            company = row.get("company_id")
            if company is None:
                raise PublicationError(
                    f"{node_kind}: company-scoped node is missing company_id"
                )
            return OWNER_COMPANY_PREFIX + normalize_unicode(str(company))
        raise PublicationError(f"unknown node_type {node_kind!r}")

    raise PublicationError("row has neither node_type nor edge_type")


def _row_identity(row: Mapping[str, Any]) -> str:
    """Stable identity of a graph row, by row kind.

    Node rows are keyed by ``node_id`` and edge rows by ``edge_id``; evidence
    links carry their own ``evidence_id`` even though they also reference a
    node, so they never collide with the node they point at.
    """
    if row.get("node_type") is not None and row.get("node_id"):
        return normalize_unicode(str(row["node_id"]))
    if row.get("edge_type") is not None and row.get("edge_id"):
        return normalize_unicode(str(row["edge_id"]))
    for field_name in ("evidence_id", "edge_id", "node_id", "row_id"):
        value = row.get(field_name)
        if value:
            return normalize_unicode(str(value))
    return deterministic_json(dict(row))


def row_identity(row: Mapping[str, Any]) -> str:
    """Public name for the row identity used to merge subset and full builds."""
    return _row_identity(row)


def plan_subset(
    predecessor_rows: Iterable[Mapping[str, Any]],
    rebuilt_rows: Iterable[Mapping[str, Any]],
    member_company_ids: Iterable[str],
) -> List[Dict[str, Any]]:
    """Subset = predecessor minus member-owned rows, plus the rebuilt rows.

    Global rows from the predecessor are retained (union of references) unless
    the rebuild supplies them again; cross-company rows are never rebuilt by a
    subset.  Ordering is deterministic by row identity.
    """
    members = {
        OWNER_COMPANY_PREFIX + normalize_unicode(str(company))
        for company in member_company_ids
    }
    if not members:
        raise PublicationError("a subset needs at least one member company")

    kept: Dict[str, Dict[str, Any]] = {}
    for row in predecessor_rows:
        owner = row_owner(row)
        if owner in members:
            continue
        kept.setdefault(_row_identity(row), dict(row))

    for row in rebuilt_rows:
        owner = row_owner(row)
        if owner == OWNER_CROSS_COMPANY:
            raise PublicationError(
                "cross-company rows are rebuilt only by full generations"
            )
        if owner.startswith(OWNER_COMPANY_PREFIX) and owner not in members:
            raise PublicationError(
                f"rebuilt row {_row_identity(row)} belongs to {owner}, "
                f"outside the subset members {sorted(members)}"
            )
        kept[_row_identity(row)] = dict(row)
    return [kept[key] for key in sorted(kept)]


# ── Subset eligibility (classification staleness) ──────────────────────────

@dataclass(frozen=True)
class ClassificationObservation:
    company_id: str
    taxonomy: str
    code: str
    label: str
    observed_at: datetime
    source: str = ""

    def __post_init__(self) -> None:
        for label, value in (
            ("company_id", self.company_id),
            ("taxonomy", self.taxonomy),
            ("code", self.code),
        ):
            if not normalize_unicode(str(value)):
                raise PublicationError(f"{label} must not be blank")
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))

    def as_row(self) -> Tuple[str, str, str, str, str]:
        return (
            self.company_id,
            self.taxonomy,
            self.code,
            self.label,
            self.observed_at.isoformat(),
        )


def _latest_by_company_taxonomy(
    observations: Iterable[ClassificationObservation],
) -> Dict[Tuple[str, str], ClassificationObservation]:
    latest: Dict[Tuple[str, str], ClassificationObservation] = {}
    for observation in observations:
        key = (normalize_unicode(observation.company_id), normalize_unicode(observation.taxonomy))
        current = latest.get(key)
        if current is None or observation.observed_at > current.observed_at:
            latest[key] = observation
    return latest


def check_subset_allowed(
    predecessor: Iterable[ClassificationObservation],
    current: Iterable[ClassificationObservation],
    member_company_ids: Iterable[str],
) -> None:
    """Reject a subset when a member's classification observation changed.

    Stale (superseded), deleted and newly added classifications all count as a
    change, because cross-company ``INFERRED_PEER`` edges would go stale; a
    full generation is then required.
    """
    members = {normalize_unicode(str(company)) for company in member_company_ids}
    before = _latest_by_company_taxonomy(predecessor)
    after = _latest_by_company_taxonomy(current)
    changed: List[str] = []
    for key in sorted(set(before) | set(after)):
        company, taxonomy = key
        if company not in members:
            continue
        old = before.get(key)
        new = after.get(key)
        if old is None:
            changed.append(f"{company}/{taxonomy}: added {new.as_row()!r}")
        elif new is None:
            changed.append(f"{company}/{taxonomy}: deleted {old.as_row()!r}")
        elif old.as_row() != new.as_row():
            changed.append(
                f"{company}/{taxonomy}: {old.as_row()!r} -> {new.as_row()!r}"
            )
    if changed:
        raise SubsetRejectedError(
            "subset build rejected: member classification observations changed "
            f"since the predecessor generation: {changed}"
        )
