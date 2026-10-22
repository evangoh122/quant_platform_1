"""sec_kg/contracts/publication.py — generations, CAS and subset ownership.

Design of record: ``KG_DATA_MODEL_v4`` §G, ``v3`` §8.

Publication is a compare-and-swap on a single-row pointer table::

    gold_sec_kg_current(pointer_id = 'current', generation_id, updated_at)

The swap succeeds only when the pointer still names the generation's
``predecessor_generation_id``; bootstrap inserts only while the pointer is
empty.  Affected rows = 1 means published.  Affected rows = 0 means this call
did not move the pointer, which is **not** the same as failure: the pointer is
re-read after the CAS and the outcome is decided from the *stored* manifest.

The manifest table is written **only** through two atomic operations, so the
state machine is correct under any interleaving of concurrent invocations:

* ``insert_manifest_if_absent`` is a ``WHEN NOT MATCHED THEN INSERT`` MERGE: it
  can create a run row but never overwrites one, whatever its status.  A retry
  therefore cannot resurrect a published (or failed) manifest as ``pending``;
* ``transition_status`` is a ``WHEN MATCHED AND status IN (...) THEN UPDATE``
  MERGE, i.e. a compare-and-set on ``status``.  ``published`` is terminal: no
  transition may move a row out of it, so a concurrent ``pending -> failed``
  write can never downgrade a published generation.

The outcomes are decided from those two operations alone —

* the pointer already names **this** generation (a concurrent identical retry
  published it first) -> idempotent success, ``already_current``; the stored
  status is published, and only a still-``pending`` row is repaired;
* this generation was published earlier and has since been superseded ->
  no-op success, ``already_published_superseded``;
* otherwise the generation was never published -> the run is marked FAILED and
  its outputs stay unpublished, ``cas_failed``.

A run status is therefore never downgraded from ``published`` to ``failed``
(Opus R4 MAJOR 2).  The production executor is injected, so the state machine
is tested without a warehouse.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple

from config.data_sources import validate_data_source
from sec_kg.contracts import identity
from sec_kg.contracts.instruments import (
    INSTRUMENT_ONLY_NODE_FIELDS,
    NODE_TYPE_INSTRUMENT,
    SECURITY_ONLY_NODE_FIELDS,
    UNDERLYING_KIND_CRYPTO_ASSET,
    UNDERLYING_KIND_SECURITY,
    Instrument,
    InstrumentError,
    underlying_kind as _underlying_kind,
)
from sec_kg.contracts.registry import (
    COMPANY_SCOPED_NODE_KINDS,
    CONTRACT_NODE_KINDS,
    EVIDENCE_DATA_SOURCES,
    GLOBAL_NODE_KINDS,
    SCOPE_CROSS_COMPANY,
    SCOPE_GLOBAL_TARGET,
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
OUTCOME_ALREADY_PUBLISHED_SUPERSEDED = "already_published_superseded"
OUTCOME_STALE_PREDECESSOR = "stale_predecessor"
OUTCOME_CAS_FAILED = "cas_failed"
OUTCOME_MANIFEST_CONFLICT = "manifest_conflict"

OWNER_GLOBAL = "global"
OWNER_CROSS_COMPANY = "cross-company"
OWNER_COMPANY_PREFIX = "company:"

#: The one ``SCOPE_GLOBAL_TARGET`` edge that has no owning company.
EDGE_UNDERLIES = "UNDERLIES"


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
    """Injected persistence: a pointer CAS plus two atomic manifest writes.

    The real executor is Delta SQL.  The publisher may only *write* manifests
    through the two compare-and-set operations below — there is deliberately no
    unconditional "put" that could overwrite an existing row (Opus R4 MINOR 2 /
    Sol R4 P1):

    ``insert_manifest_if_absent(generation_id, manifest) -> bool``
        ``MERGE INTO <manifests> AS t USING (<row>) AS s
        ON t.generation_id = s.generation_id
        WHEN NOT MATCHED THEN INSERT (...) VALUES (...)``

        True when this call inserted the row; False when a row for that id
        already exists, **whatever its status**.  An existing row is never
        overwritten, so a retry can never replace a published or failed
        manifest with a pending one.

    ``transition_status(generation_id, from_statuses, to_status) -> int``
        ``MERGE INTO <manifests> AS t USING (<generation_id>) AS s
        ON t.generation_id = s.generation_id
        WHEN MATCHED AND t.status IN (<from_statuses>)
                     AND t.status <> 'published'
        THEN UPDATE SET status = <to_status>``

        Affected rows.  This is a compare-and-set on ``status``: a losing
        writer sees 0, and ``published`` is terminal — no transition may move a
        row out of it.  ``pending -> published`` is the publish transition;
        ``failed -> published`` lets the pointer-CAS winner repair a failure
        mark written in the gap between its pointer swap and its status write.

    ``read_pointer``, ``compare_and_set`` and ``get_manifest`` are reads (plus
    the pointer CAS); they never rewrite manifest content.
    """

    def read_pointer(self) -> Optional[str]: ...

    def compare_and_set(
        self, *, predecessor: Optional[str], generation_id: str
    ) -> int: ...

    def insert_manifest_if_absent(
        self, generation_id: str, manifest: Generation
    ) -> bool: ...

    def transition_status(
        self,
        generation_id: str,
        from_statuses: Tuple[str, ...],
        to_status: str,
    ) -> int: ...

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

    ``published`` is True whenever the generation's manifest is ``published``
    after the call — including the no-op outcomes — and ``outcome`` states
    whether *this* call performed the swap.  Manifests are written only through
    ``insert_manifest_if_absent`` and ``transition_status`` (see
    :class:`PointerExecutor`), so a manifest that is already ``published`` is
    never rewritten to ``pending`` or ``failed`` under any interleaving: a
    zero-row CAS is resolved by re-reading the pointer and the stored status.
    """
    gid = generation.generation_id
    existing = executor.get_manifest(gid)
    if existing is not None and existing.digest() != generation.digest():
        return PublishResult(
            published=False,
            outcome=OUTCOME_MANIFEST_CONFLICT,
            affected_rows=0,
            pointer=executor.read_pointer(),
            generation=existing,
        )
    if existing is None:
        # Create the run row once, as pending.  An existing row — whatever its
        # status — is never overwritten; if it appeared concurrently it must
        # still describe this generation's content.
        inserted = executor.insert_manifest_if_absent(
            gid, generation.with_status(STATUS_PENDING)
        )
        if not inserted:
            existing = executor.get_manifest(gid)
            if existing is None:
                raise PublicationError(
                    f"executor reported generation {gid!r} as present but "
                    "returned no manifest"
                )
            if existing.digest() != generation.digest():
                return PublishResult(
                    published=False,
                    outcome=OUTCOME_MANIFEST_CONFLICT,
                    affected_rows=0,
                    pointer=executor.read_pointer(),
                    generation=existing,
                )

    current = executor.read_pointer()
    if current == gid:
        # The pointer already names this generation: it is published, and a
        # still-pending (or gap-failed) row is repaired — never downgraded.
        return _already_current(
            executor, generation, affected_rows=0, pointer=current
        )
    if current != generation.predecessor_generation_id:
        # The pointer moved away from our predecessor.  If this generation was
        # published before that move it is only superseded, never failed.
        return _not_our_turn(
            executor,
            generation,
            pointer=current,
            affected_rows=0,
            outcome=OUTCOME_STALE_PREDECESSOR,
        )

    affected = executor.compare_and_set(
        predecessor=generation.predecessor_generation_id,
        generation_id=gid,
    )
    if affected == 1:
        # This call moved the pointer, so this generation is published.  A
        # duplicate invocation may have marked it failed in the gap between the
        # pointer swap and this write; the CAS winner repairs that mark.
        executor.transition_status(
            gid, (STATUS_PENDING, STATUS_FAILED), STATUS_PUBLISHED
        )
        return PublishResult(
            published=True,
            outcome=OUTCOME_PUBLISHED,
            affected_rows=affected,
            pointer=executor.read_pointer(),
            generation=_stored_or(executor, generation, STATUS_PUBLISHED),
        )

    # The CAS lost.  Decide from the pointer and the stored manifest instead of
    # assuming failure: a concurrent identical invocation may have published
    # this very generation, and a published manifest is never downgraded.
    pointer_after = executor.read_pointer()
    if pointer_after == gid:
        return _already_current(
            executor, generation, affected_rows=affected, pointer=pointer_after
        )
    return _not_our_turn(
        executor,
        generation,
        pointer=pointer_after,
        affected_rows=affected,
        outcome=OUTCOME_CAS_FAILED,
    )


def _stored_or(
    executor: PointerExecutor, generation: Generation, status: str
) -> Generation:
    """Read the stored run row, falling back to *generation* with *status*."""
    return executor.get_manifest(generation.generation_id) or generation.with_status(
        status
    )


def _already_current(
    executor: PointerExecutor,
    generation: Generation,
    *,
    affected_rows: int,
    pointer: Optional[str],
) -> PublishResult:
    """The pointer names this generation: published, repairing a stale row."""
    gid = generation.generation_id
    # A pointer that names this generation is authoritative: a pending row (the
    # status write never landed) or a gap-failed row is repaired.  Published is
    # terminal, so this can never downgrade a row that already published.
    executor.transition_status(
        gid, (STATUS_PENDING, STATUS_FAILED), STATUS_PUBLISHED
    )
    return PublishResult(
        published=True,
        outcome=OUTCOME_ALREADY_CURRENT,
        affected_rows=affected_rows,
        pointer=pointer,
        generation=_stored_or(executor, generation, STATUS_PUBLISHED),
    )


def _not_our_turn(
    executor: PointerExecutor,
    generation: Generation,
    *,
    pointer: Optional[str],
    affected_rows: int,
    outcome: str,
) -> PublishResult:
    """This call did not move the pointer; classify from the stored status."""
    gid = generation.generation_id
    stored = _stored_or(executor, generation, STATUS_PENDING)
    if stored.status != STATUS_PUBLISHED:
        # Conditional on ``pending`` only: if another invocation published this
        # row after we read it, the CAS affects 0 rows and leaves it published.
        executor.transition_status(gid, (STATUS_PENDING,), STATUS_FAILED)
        stored = _stored_or(executor, generation, STATUS_FAILED)
    if stored.status == STATUS_PUBLISHED:
        return PublishResult(
            published=True,
            outcome=OUTCOME_ALREADY_PUBLISHED_SUPERSEDED,
            affected_rows=affected_rows,
            pointer=pointer,
            generation=stored,
        )
    return PublishResult(
        published=False,
        outcome=outcome,
        affected_rows=affected_rows,
        pointer=pointer,
        generation=stored,
    )


# ── Ownership ──────────────────────────────────────────────────────────────

def row_owner(row: Mapping[str, Any]) -> str:
    """Return ``global``, ``cross-company`` or ``company:<company_id>``.

    ``owner_company_id`` (evidence rows) always wins.  Otherwise ownership is
    derived from the row kind (``KG_DATA_MODEL_v4`` §G, refined by review item
    O3 which is implemented here):

    * ``Metric`` / ``Period`` / ``Concept`` / ``CryptoAsset`` nodes are global;
    * ``Instrument`` nodes are **derivatives** and inherit their underlying's
      ownership: a contract on an equity/ETF/fund/preferred ``Security`` is
      owned by that security's company (the row's ``company_id``), a contract
      on a ``CryptoAsset`` is global, and a commodity-underlying contract must
      carry an explicit ``owner_company_id`` until KG-F defines a commodity
      node — it is never silently global;
    * the other node kinds and company-scoped edges belong to ``company_id``;
    * ``INFERRED_PEER`` edges are cross-company.

    A subset build therefore replaces a member's Instruments together with its
    securities, while crypto contracts survive as global rows.
    """
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
            # (v4 §G) even though the target node is global; only UNDERLIES has
            # no company at all and belongs to the global union, so a company
            # edge without one is an error rather than a silent global row.
            company = row.get("company_id")
            if company is None or not normalize_unicode(str(company)):
                if contract.edge_type == EDGE_UNDERLIES:
                    return OWNER_GLOBAL
                raise PublicationError(
                    f"{contract.edge_type}: a {contract.scope} edge is owned by "
                    "its source company; company_id is required"
                )
            return OWNER_COMPANY_PREFIX + normalize_unicode(str(company))
        company = row.get("company_id")
        if company is None:
            raise PublicationError(
                f"{edge_type}: company-scoped edge is missing company_id"
            )
        return OWNER_COMPANY_PREFIX + normalize_unicode(str(company))

    node_kind = row.get("node_type")
    if node_kind is not None:
        if node_kind == NODE_TYPE_INSTRUMENT:
            return _instrument_row_owner(row)
        if node_kind in GLOBAL_NODE_KINDS:
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


def _instrument_row_owner(row: Mapping[str, Any]) -> str:
    """Ownership of an Instrument node: derived from what it tracks."""
    underlying_type = row.get("underlying_type")
    if underlying_type is None:
        raise PublicationError(
            "Instrument: underlying_type is required to determine ownership"
        )
    try:
        kind = _underlying_kind(str(underlying_type))
    except InstrumentError as error:
        raise PublicationError(f"Instrument: {error}") from error
    if kind == UNDERLYING_KIND_SECURITY:
        company = row.get("company_id")
        if company is None or not normalize_unicode(str(company)):
            raise PublicationError(
                "Instrument: a contract on a Security belongs to that "
                "security's company; company_id is required"
            )
        return OWNER_COMPANY_PREFIX + normalize_unicode(str(company))
    if kind == UNDERLYING_KIND_CRYPTO_ASSET:
        return OWNER_GLOBAL
    raise PublicationError(
        "Instrument: ownership of an "
        f"{normalize_unicode(str(underlying_type))!r} underlying is not defined "
        "yet; supply owner_company_id"
    )


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


# ── Node-row contract (typed nodes, never cross-kind) ──────────────────────

def _row_data_source(row: Mapping[str, Any], label: str) -> str:
    """Validate a row's required ``data_source`` (``RULE-data-source-column``)."""
    try:
        return validate_data_source(row.get("data_source"))
    except ValueError as error:
        raise PublicationError(f"{label}: {error}") from error


def validate_node_row(row: Mapping[str, Any]) -> str:
    """Validate one node row before publication; return its ``node_type``.

    Every node row must carry a valid ``data_source``.  ``Instrument`` rows are
    re-validated as typed perpetual futures and re-derive their id from the
    venue natural key ``(venue, dex_or_market, contract_symbol)``, so a contract
    can never be published under a Security id; ``Security`` rows refuse
    Instrument-only attributes and re-derive their issuer+class id, so a perp
    can never be published as the equity it tracks (``KG_DATA_MODEL_v4`` §J).

    A **provisional** Security id (``identity.provisional_security_id``, whose
    share-class component is the deterministic ``PROV:`` evidence key) and a
    legacy **v1** ``v1|security|...`` id cannot pass this check, and therefore
    cannot pass :func:`merge_node_rows` either: the row's ``node_id`` must equal
    the v2 id re-derived from ``issuer_company_id`` + ``share_class_code`` and
    neither old form reproduces it.  That is intended until the KG-B identity
    migration rewrites those ids; it is not a licence to trust an asserted id.
    """
    if not isinstance(row, Mapping):
        raise PublicationError(
            f"node row must be a mapping, got {type(row).__name__}"
        )
    node_type = row.get("node_type")
    if node_type not in CONTRACT_NODE_KINDS:
        raise PublicationError(f"unknown node_type {node_type!r}")
    node_type = str(node_type)
    node_id = normalize_unicode(str(row.get("node_id") or ""))
    if not node_id:
        raise PublicationError(f"{node_type}: node_id is required")
    _row_data_source(row, node_type)
    if node_type == NODE_TYPE_INSTRUMENT:
        _validate_instrument_node(row, node_id)
    elif node_type == "Security":
        _validate_security_node(row, node_id)
    elif node_type in COMPANY_SCOPED_NODE_KINDS:
        if not normalize_unicode(str(row.get("company_id") or "")):
            raise PublicationError(
                f"{node_type}: company-scoped node is missing company_id"
            )
    return node_type


def _validate_instrument_node(row: Mapping[str, Any], node_id: str) -> None:
    for field_name in SECURITY_ONLY_NODE_FIELDS:
        if row.get(field_name) not in (None, ""):
            raise PublicationError(
                f"Instrument rows must not carry Security identity field "
                f"{field_name!r}: a perpetual future is never the equity "
                "it tracks"
            )
    try:
        instrument = Instrument(
            venue=row.get("venue"),
            dex_or_market=row.get("dex_or_market"),
            contract_symbol=row.get("contract_symbol"),
            instrument_type=row.get("instrument_type"),
            underlying_type=row.get("underlying_type"),
            underlying=row.get("underlying"),
            data_source=row.get("data_source"),
        )
    except (InstrumentError, ValueError) as error:
        raise PublicationError(f"Instrument: {error}") from error
    if instrument.node_id != node_id:
        raise PublicationError(
            f"Instrument: node_id {node_id!r} does not match its venue identity "
            f"{instrument.node_id!r}; an Instrument can never take a Security id"
        )
    if instrument.underlying_kind == UNDERLYING_KIND_SECURITY:
        if not normalize_unicode(str(row.get("company_id") or "")):
            raise PublicationError(
                "Instrument: a Security-underlying contract requires the "
                "underlying security's company_id"
            )


def _validate_security_node(row: Mapping[str, Any], node_id: str) -> None:
    for field_name in INSTRUMENT_ONLY_NODE_FIELDS:
        if row.get(field_name) not in (None, ""):
            raise PublicationError(
                f"Security rows must not carry Instrument attribute "
                f"{field_name!r}: perpetual futures are derivatives, never "
                "equities"
            )
    try:
        expected = identity.security_id(
            str(row.get("issuer_company_id") or ""),
            str(row.get("share_class_code") or ""),
        )
    except identity.IdentityError as error:
        raise PublicationError(f"Security: {error}") from error
    if expected != node_id:
        raise PublicationError(
            f"Security: node_id {node_id!r} does not match its issuer+class "
            f"identity {expected!r}; an Instrument id can never be published "
            "as a Security"
        )
    if not normalize_unicode(str(row.get("company_id") or "")):
        raise PublicationError("Security: company_id (owner) is required")


def merge_node_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    aliases: Optional[Mapping[str, str]] = None,
) -> Tuple[Dict[str, Any], ...]:
    """Merge node rows for publication, keyed by ``(node_type, node_id)``.

    Rows are never merged across kinds: an id alias that would fold an
    Instrument id into a Security id (or the reverse) is rejected, because a
    perpetual future is a derivative and must stay a separate node from the
    equity it tracks (``KG_DATA_MODEL_v4`` §J).  A duplicate row of the same
    kind is a contract violation, not a silent overwrite.

    Aliases are validated **after** resolution, on the resolved identity: a
    kind whose id is derived from its natural key (``Instrument`` from the
    venue contract, ``Security`` from issuer + share class) must still carry
    exactly that id once the alias is applied.  The target row therefore does
    not have to appear in the same batch — an Instrument can never be
    republished under a Security id (or the reverse) merely because the
    Security row is absent (Sol R4 P1).
    """
    alias_map = dict(aliases or {})
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    kind_by_id: Dict[str, str] = {}
    for row in rows:
        node_type = validate_node_row(row)
        original = normalize_unicode(str(row["node_id"]))
        resolved = identity.resolve_alias(alias_map, original)
        if resolved != original:
            try:
                validate_node_row(dict(row, node_id=resolved))
            except PublicationError as error:
                raise PublicationError(
                    f"node id {original!r} aliases to {resolved!r}, which is not "
                    f"a valid {node_type} identity: {error}"
                ) from error
        previous_kind = kind_by_id.setdefault(resolved, node_type)
        if previous_kind != node_type:
            raise PublicationError(
                f"node id {resolved!r} is both {previous_kind} and {node_type}: "
                "an Instrument is never merged into the Security it tracks"
            )
        key = (node_type, resolved)
        if key in merged:
            raise PublicationError(
                f"duplicate {node_type} node row for {resolved!r}"
            )
        merged[key] = dict(row, node_id=resolved)
    return tuple(merged[key] for key in sorted(merged))


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
    """One classification evidence row (``EVIDENCE_KINDS = 'classification'``).

    ``data_source`` is required and validated against the one vocabulary
    (``RULE-data-source-column``); a classification row is computed in this
    project, so it must carry a code the registry allows for classification
    evidence (``derived``).
    """

    company_id: str
    taxonomy: str
    code: str
    label: str
    observed_at: datetime
    data_source: str

    def __post_init__(self) -> None:
        for label, value in (
            ("company_id", self.company_id),
            ("taxonomy", self.taxonomy),
            ("code", self.code),
        ):
            if not normalize_unicode(str(value)):
                raise PublicationError(f"{label} must not be blank")
        try:
            data_source = validate_data_source(self.data_source)
        except ValueError as error:
            raise PublicationError(f"classification: {error}") from error
        allowed = EVIDENCE_DATA_SOURCES["classification"]
        if data_source not in allowed:
            raise PublicationError(
                f"classification: data_source {data_source!r} is not one of "
                f"{list(allowed)}"
            )
        object.__setattr__(self, "data_source", data_source)
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))

    def as_row(self) -> Tuple[str, str, str, str, str, str]:
        return (
            self.company_id,
            self.taxonomy,
            self.code,
            self.label,
            self.observed_at.isoformat(),
            self.data_source,
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
