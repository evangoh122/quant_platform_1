"""sec_kg/contracts/identity.py — stable ids, encoders, aliases, migration.

Two encoders coexist (KG_DATA_MODEL_v4 §C, §D):

* **v1** — ``sec_kg/model.py``'s length-delimited ``v1|kind|...`` canonical
  tuple.  It is reused *unchanged*, by delegating to the model helpers, for
  every kind whose identity definition did not change: Company, Filing,
  Section, Chunk, Metric and Concept.
* **v2** — a null-safe encoder (``kgid:v2``) where every field is written as
  ``<presence:0|1><len:8-hex><utf8 bytes>``.  ``None`` is presence ``0`` with no
  length, which distinguishes ``None`` from ``""`` unambiguously.  It is used
  only for the new or changed kinds: Security (issuer + share class),
  Instrument (venue contract), CryptoAsset, Period (explicit type) and Fact
  (a Fact id embeds its Period id, so it migrates with Period).

``Concept`` is the one deliberate deviation from the ``KG_DATA_MODEL_v4`` §C
list of null-safe kinds: its identity already existed as a v1 tuple
(``taxonomy`` + ``concept``, both required and case-preserved), it has **no
nullable field**, and re-encoding it would re-mint every Concept id for no
identity gain.  It therefore stays on the v1 encoder and is listed in
``V1_KINDS``.  A future kind that gains a nullable component must not follow
this precedent.

Importing this module has no side effects and needs no third-party package.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)

from config.data_sources import DERIVED, validate_data_source
from sec_kg.model import (
    chunk_id_from_parts,
    company_id as _v1_company_id,
    filing_id as _v1_filing_id,
    make_node_id,
    metric_id as _v1_metric_id,
    normalize_accession,
    normalize_cik,
    normalize_unicode,
    period_id as _v1_period_id,
    section_id as _v1_section_id,
    xbrl_fact_id as _v1_xbrl_fact_id,
)

# ── Identity versions ───────────────────────────────────────────────────────

IDENTITY_VERSION_V1 = "v1"
IDENTITY_VERSION_V2 = "kgid:v2"

# ── Kinds ───────────────────────────────────────────────────────────────────

KIND_COMPANY = "company"
KIND_FILING = "filing"
KIND_SECTION = "section"
KIND_CHUNK = "chunk"
KIND_METRIC = "metric"
KIND_CONCEPT = "concept"
KIND_SECURITY = "security"
KIND_INSTRUMENT = "instrument"
KIND_CRYPTO_ASSET = "crypto_asset"
KIND_PERIOD = "period"
KIND_FACT = "xbrl_fact"

V1_KINDS: Tuple[str, ...] = (
    KIND_COMPANY,
    KIND_FILING,
    KIND_SECTION,
    KIND_CHUNK,
    KIND_METRIC,
    KIND_CONCEPT,
)
V2_KINDS: Tuple[str, ...] = (
    KIND_SECURITY,
    KIND_INSTRUMENT,
    KIND_CRYPTO_ASSET,
    KIND_PERIOD,
    KIND_FACT,
)

IDENTITY_VERSION_BY_KIND: Mapping[str, str] = {
    **{kind: IDENTITY_VERSION_V1 for kind in V1_KINDS},
    **{kind: IDENTITY_VERSION_V2 for kind in V2_KINDS},
}

#: Marker that prefixes a provisional share-class code.
PROVISIONAL_PREFIX = "PROV:"

PERIOD_TYPES: Tuple[str, ...] = ("instant", "duration")


class IdentityError(ValueError):
    """Base class for identity-contract violations."""


class AliasError(IdentityError):
    """Invalid alias registration."""


class AliasConflictError(AliasError):
    """An append-only alias mapping was rewritten."""


class AliasCycleError(AliasError):
    """An alias chain cycles."""


class MigrationError(IdentityError):
    """An identity migration cannot be applied."""


# ── Normalisation ───────────────────────────────────────────────────────────

def _normalise_kind(kind: str) -> str:
    text = normalize_unicode(str(kind)).lower()
    if not text:
        raise IdentityError("identity kind must not be blank")
    return text


def _normalise_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return normalize_unicode(str(value))


def _normalise_required(label: str, value: Optional[str]) -> str:
    text = _normalise_text(value)
    if not text:
        raise IdentityError(f"{label} must not be blank")
    return text


def identity_version(kind: str) -> str:
    """Return the encoder version for *kind*."""
    kind = _normalise_kind(kind)
    try:
        return IDENTITY_VERSION_BY_KIND[kind]
    except KeyError:  # pragma: no cover - defensive
        raise IdentityError(f"unknown identity kind: {kind!r}") from None


def normalise_share_class(code: Optional[str]) -> str:
    """Share-class codes are upper-case, whitespace-normalised."""
    return _normalise_required("share_class_code", code).upper()


def normalise_period_type(period_type: str) -> str:
    text = _normalise_kind(period_type)
    if text not in PERIOD_TYPES:
        raise IdentityError(
            f"period_type must be one of {PERIOD_TYPES}, got {period_type!r}"
        )
    return text


def normalise_iso_date(value: Optional[str], label: str) -> str:
    """Validate a canonical ``YYYY-MM-DD`` date that really exists.

    A well-shaped but impossible date (``2024-13-45``, ``2024-02-30``) is
    rejected here rather than silently minting an unreachable Period id.
    """
    text = _normalise_required(label, value)
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise IdentityError(f"{label} must be an ISO date (YYYY-MM-DD): {value!r}")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise IdentityError(
            f"{label} is not a real calendar date: {value!r}"
        ) from None
    return text


# ── v1 encoder (delegating to sec_kg.model, unchanged) ──────────────────────

def _v1_entity_id(kind: str, fields: Sequence[Optional[str]]) -> str:
    """Reuse the existing v1 helpers verbatim — do not re-implement."""
    if kind == KIND_COMPANY and len(fields) == 1:
        return _v1_company_id(str(fields[0]))
    if kind == KIND_FILING and len(fields) == 2:
        return _v1_filing_id(str(fields[0]), str(fields[1]))
    if kind == KIND_SECTION and len(fields) == 2:
        return _v1_section_id(str(fields[0]), str(fields[1]))
    if kind == KIND_CHUNK and len(fields) == 1:
        return chunk_id_from_parts(str(fields[0]))
    if kind == KIND_METRIC and len(fields) == 1:
        return _v1_metric_id(str(fields[0]))
    if kind == KIND_CONCEPT and len(fields) == 2:
        # New kind, v1 encoder: taxonomy and concept are case-preserved.
        return make_node_id(
            "v1",
            KIND_CONCEPT,
            _normalise_required("taxonomy", fields[0]),
            _normalise_required("concept", fields[1]),
        )
    raise IdentityError(
        f"{kind!r} has no v1 encoder for {len(fields)} field(s); "
        "use the v2 helpers"
    )


# ── v2 encoder ──────────────────────────────────────────────────────────────

def _encode_v2_field(value: Optional[Any]) -> str:
    """``<presence><len:8 hex><utf8>``; ``None`` is presence ``0`` only."""
    if value is None:
        return "0"
    text = str(value)
    raw = text.encode("utf-8")
    return "1" + format(len(raw), "08x") + text


def canonical_v2_payload(kind: str, fields: Sequence[Optional[Any]]) -> str:
    """Expose the exact bytes hashed for a v2 id (debugging and tests)."""
    segments = [IDENTITY_VERSION_V2, _normalise_kind(kind)]
    segments.extend(_encode_v2_field(field) for field in fields)
    return "|".join(segments)


def make_id_v2(kind: str, *fields: Optional[Any]) -> str:
    """Deterministic lowercase SHA-256 id under the ``kgid:v2`` encoder."""
    payload = canonical_v2_payload(kind, fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Natural keys and ids per kind ───────────────────────────────────────────

NaturalKey = Tuple[Optional[str], ...]


def company_key(cik: str) -> NaturalKey:
    return (KIND_COMPANY, normalize_cik(cik))


def filing_key(cik: str, accession: str) -> NaturalKey:
    return (KIND_FILING, normalize_cik(cik), normalize_accession(accession))


def section_key(accession: str, filing_section: str) -> NaturalKey:
    return (
        KIND_SECTION,
        normalize_accession(accession),
        normalize_unicode(filing_section).lower(),
    )


def chunk_key(chunk_id: str) -> NaturalKey:
    return (KIND_CHUNK, _normalise_required("chunk_id", chunk_id))


def metric_key(metric_code: str) -> NaturalKey:
    return (KIND_METRIC, normalize_unicode(metric_code).lower())


def concept_key(taxonomy: str, concept: str) -> NaturalKey:
    """Case-preserved (v2 §1); normalised only for whitespace."""
    return (
        KIND_CONCEPT,
        _normalise_required("taxonomy", taxonomy),
        _normalise_required("concept", concept),
    )


def security_key(issuer_company_id: str, share_class_code: str) -> NaturalKey:
    return (
        KIND_SECURITY,
        _normalise_required("issuer_company_id", issuer_company_id),
        normalise_share_class(share_class_code),
    )


def provisional_security_key(
    issuer_company_id: str, evidence_ids: Iterable[str]
) -> NaturalKey:
    """Provisional security key from the *first* (smallest) evidence id.

    Ordering evidence ids — never timestamps — keeps the provisional id stable
    under shuffled ingestion (v4 §H).
    """
    normalised = sorted(
        {_normalise_required("evidence_id", e) for e in evidence_ids}
    )
    if not normalised:
        raise IdentityError("provisional security id requires at least one evidence_id")
    return (
        KIND_SECURITY,
        _normalise_required("issuer_company_id", issuer_company_id),
        PROVISIONAL_PREFIX + normalised[0],
    )


def is_provisional_key(key: Sequence[Optional[str]]) -> bool:
    return (
        len(key) == 3
        and _normalise_kind(str(key[0])) == KIND_SECURITY
        and str(key[2] or "").startswith(PROVISIONAL_PREFIX)
    )


def crypto_asset_key(asset_code: str) -> NaturalKey:
    return (KIND_CRYPTO_ASSET, _normalise_required("asset_code", asset_code).upper())


def instrument_key(
    venue: str, dex_or_market: Optional[str], contract_symbol: str
) -> NaturalKey:
    """Venue contract; ``dex_or_market`` is ``None`` for central-limit venues."""
    return (
        KIND_INSTRUMENT,
        _normalise_required("venue", venue).lower(),
        _normalise_text(dex_or_market),
        _normalise_required("contract_symbol", contract_symbol).upper(),
    )


def period_key(
    period_type: str, start: Optional[str], end: Optional[str]
) -> NaturalKey:
    """``("period", type, start, end)``; an instant has ``start = None`` (v4 §B).

    A blank legacy start (``""`` or whitespace, as the v1 encoder stores an
    instant) is treated as ``None`` here, so a KG-B migration can pass the
    legacy ``period_start`` column through unchanged.  The v2 key still encodes
    ``None``; only a real start on an instant is rejected.
    """
    kind_type = normalise_period_type(period_type)
    end_iso = normalise_iso_date(end, "period end")
    if kind_type == "instant":
        if start is not None and _normalise_text(start):
            raise IdentityError("instant periods must not carry a start date")
        return (KIND_PERIOD, kind_type, None, end_iso)
    start_iso = normalise_iso_date(start, "period start")
    if start_iso > end_iso:
        raise IdentityError(
            f"duration period start {start_iso} is after end {end_iso}"
        )
    return (KIND_PERIOD, kind_type, start_iso, end_iso)


def fact_key(
    issuer_company_id: str,
    concept_id: str,
    unit: str,
    period_id_v2: str,
    dimensions_hash: Optional[str],
    filing_id: str,
) -> NaturalKey:
    """Assertion-grain fact identity: it embeds the v2 Period id."""
    return (
        KIND_FACT,
        _normalise_required("issuer_company_id", issuer_company_id),
        _normalise_required("concept_id", concept_id),
        _normalise_required("unit", unit).upper(),
        _normalise_required("period_id", period_id_v2),
        _normalise_text(dimensions_hash),
        _normalise_required("filing_id", filing_id),
    )


def entity_id(natural_key: Sequence[Optional[str]]) -> str:
    """Derive the stable id for a natural key, using its kind's encoder."""
    if not natural_key:
        raise IdentityError("natural key must not be empty")
    kind = _normalise_kind(str(natural_key[0]))
    fields = list(natural_key[1:])
    version = identity_version(kind)
    if version == IDENTITY_VERSION_V1:
        return _v1_entity_id(kind, fields)
    return make_id_v2(kind, *fields)


# ── Convenience id helpers ──────────────────────────────────────────────────

def company_id(cik: str) -> str:
    return entity_id(company_key(cik))


def filing_id(cik: str, accession: str) -> str:
    return entity_id(filing_key(cik, accession))


def section_id(accession: str, filing_section: str) -> str:
    return entity_id(section_key(accession, filing_section))


def chunk_id(chunk_id_value: str) -> str:
    return entity_id(chunk_key(chunk_id_value))


def metric_id(metric_code: str) -> str:
    return entity_id(metric_key(metric_code))


def concept_id(taxonomy: str, concept: str) -> str:
    return entity_id(concept_key(taxonomy, concept))


def security_id(issuer_company_id: str, share_class_code: str) -> str:
    return entity_id(security_key(issuer_company_id, share_class_code))


def provisional_security_id(
    issuer_company_id: str, evidence_ids: Iterable[str]
) -> str:
    return entity_id(provisional_security_key(issuer_company_id, evidence_ids))


def crypto_asset_id(asset_code: str) -> str:
    return entity_id(crypto_asset_key(asset_code))


def instrument_id(
    venue: str, dex_or_market: Optional[str], contract_symbol: str
) -> str:
    return entity_id(instrument_key(venue, dex_or_market, contract_symbol))


def period_id_v2(
    period_type: str, start: Optional[str], end: Optional[str]
) -> str:
    return entity_id(period_key(period_type, start, end))


def fact_id_v2(
    issuer_company_id: str,
    concept_id_value: str,
    unit: str,
    period_id_value: str,
    dimensions_hash: Optional[str],
    filing_id_value: str,
) -> str:
    return entity_id(
        fact_key(
            issuer_company_id,
            concept_id_value,
            unit,
            period_id_value,
            dimensions_hash,
            filing_id_value,
        )
    )


def legacy_period_id(start: Optional[str], end: Optional[str]) -> str:
    """The frozen v1 Period id (``sec_kg/model.py``), kept for migration."""
    return _v1_period_id(start or "", end or "")


def legacy_fact_id(
    cik: str,
    accession: str,
    metric_concept: str,
    period_start: Optional[str],
    period_end: str,
    unit: str,
    canonical_value: str,
    source_chunk_id: str,
) -> str:
    """The frozen v1 Fact id (``sec_kg/model.py``), kept for migration."""
    return _v1_xbrl_fact_id(
        cik,
        accession,
        metric_concept,
        period_start or "",
        period_end,
        unit,
        canonical_value,
        source_chunk_id,
    )


# ── Collision detection (both directions, per kind + version) ───────────────

COLLISION_KEY_TO_MANY_IDS = "natural_key_to_multiple_ids"
COLLISION_ID_TO_MANY_KEYS = "id_to_multiple_natural_keys"


@dataclass(frozen=True)
class IdentityCollision:
    direction: str
    kind: str
    identity_version: str
    natural_key: Optional[NaturalKey]
    entity_id: Optional[str]
    entity_ids: Tuple[str, ...]
    natural_keys: Tuple[NaturalKey, ...]

    def describe(self) -> str:
        if self.direction == COLLISION_KEY_TO_MANY_IDS:
            return (
                f"{self.kind}@{self.identity_version}: one natural key "
                f"{self.natural_key!r} -> {len(self.entity_ids)} ids "
                f"{self.entity_ids!r}"
            )
        return (
            f"{self.kind}@{self.identity_version}: one id {self.entity_id} -> "
            f"{len(self.natural_keys)} natural keys {self.natural_keys!r}"
        )


def _key_sort_value(key: Sequence[Optional[str]]) -> Tuple[Tuple[bool, str], ...]:
    """Total sort key for a natural key that keeps ``None`` distinct from ``""``.

    A plain ``str(part)`` (or ``part or ""``) collapses a typed NULL into the
    empty string, which both hides a real collision and, once the raw tuples
    are sorted, can compare ``None`` with ``str`` and raise ``TypeError``.  The
    pair ``(part is None, "" if part is None else str(part))`` is a total order
    over typed parts and keeps the two distinct (Sol R4 P2).
    """
    return tuple(
        (part is None, "" if part is None else str(part)) for part in key
    )


def check_collisions(
    records: Iterable[Tuple[Sequence[Optional[str]], str]],
) -> List[IdentityCollision]:
    """Return every id collision in both directions.

    ``records`` are ``(natural_key, entity_id)`` pairs.  Grouping is per
    ``(kind, identity_version)`` so a v1 id and a v2 id never "collide" merely
    because the hex digests were produced by different encoders.  Natural keys
    are compared as **typed** tuples: ``("instrument", "hl", None, "BTC")`` and
    ``("instrument", "hl", "", "BTC")`` are two different keys that happen to
    render alike, so mapping them to one id is still a collision, and sorting
    them never compares ``None`` with ``str``.
    """
    by_key: Dict[Tuple[str, str, Tuple[str, ...]], List[str]] = {}
    by_id: Dict[Tuple[str, str, str], List[Tuple[str, ...]]] = {}
    for natural_key, entity in records:
        kind = _normalise_kind(str(natural_key[0]))
        version = identity_version(kind)
        key_tuple = tuple(natural_key)
        by_key.setdefault((kind, version, key_tuple), []).append(entity)
        by_id.setdefault((kind, version, entity), []).append(key_tuple)

    collisions: List[IdentityCollision] = []
    for (kind, version, key_tuple), ids in by_key.items():
        unique = sorted(set(ids))
        if len(unique) > 1:
            collisions.append(
                IdentityCollision(
                    direction=COLLISION_KEY_TO_MANY_IDS,
                    kind=kind,
                    identity_version=version,
                    natural_key=key_tuple,
                    entity_id=None,
                    entity_ids=tuple(unique),
                    natural_keys=(key_tuple,),
                )
            )
    for (kind, version, entity), keys in by_id.items():
        unique = sorted({_key_sort_value(k) for k in keys})
        if len(unique) > 1:
            collisions.append(
                IdentityCollision(
                    direction=COLLISION_ID_TO_MANY_KEYS,
                    kind=kind,
                    identity_version=version,
                    natural_key=None,
                    entity_id=entity,
                    entity_ids=(entity,),
                    natural_keys=tuple(sorted(keys, key=_key_sort_value)),
                )
            )
    collisions.sort(
        key=lambda c: (
            c.direction,
            c.kind,
            tuple(_key_sort_value(c.natural_key or ())),
            str(c.entity_id),
        )
    )
    return collisions


# ── Append-only alias chains ────────────────────────────────────────────────

def _alias_chain(aliases: Mapping[str, str], start: str) -> List[str]:
    chain: List[str] = []
    seen = set()
    current = start
    while current in aliases:
        if current in seen:
            raise AliasCycleError(
                f"alias cycle detected at {current!r}: {chain + [current]!r}"
            )
        seen.add(current)
        chain.append(current)
        current = aliases[current]
    return chain


def _would_cycle(aliases: Mapping[str, str], old_id: str, new_id: str) -> bool:
    """True when ``old -> new`` would close a cycle (transitively)."""
    current = new_id
    seen = set()
    while True:
        if current == old_id:
            return True
        if current in seen:
            raise AliasCycleError(
                f"pre-existing alias cycle through {current!r}"
            )
        seen.add(current)
        if current not in aliases:
            return False
        current = aliases[current]


def add_alias(
    aliases: MutableMapping[str, str], old_id: str, new_id: str
) -> None:
    """Register ``old_id -> new_id`` in an append-only alias map.

    Rejects blank ids, self-aliases, rewritten mappings and any chain that
    would cycle (transitively, not just ``a -> b -> a``).
    """
    old = _normalise_required("old_id", old_id)
    new = _normalise_required("new_id", new_id)
    if old == new:
        raise AliasError(f"self alias is not allowed: {old}")
    if old in aliases:
        raise AliasConflictError(
            f"alias for {old} already exists -> {aliases[old]} (append-only)"
        )
    if _would_cycle(aliases, old, new):
        raise AliasCycleError(f"alias {old} -> {new} would create a cycle")
    aliases[old] = new


def alias_map(pairs: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    """Build a validated alias map from ``(old, new)`` pairs."""
    aliases: Dict[str, str] = {}
    for old, new in pairs:
        add_alias(aliases, old, new)
    return aliases


def resolve_alias(aliases: Mapping[str, str], entity_id: str) -> str:
    """Follow an alias chain transitively to its canonical id."""
    chain = _alias_chain(aliases, entity_id)
    if not chain:
        return entity_id
    return aliases[chain[-1]]


# ── Identity migrations ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class IdentityMigration:
    """One row of ``kg_identity_migration(old_id, new_id, kind, generation_id)``.

    ``data_source`` is required and validated (``RULE-data-source-column``); an
    identity migration is computed in this project from the two id encoders, so
    it carries ``derived``.
    """

    kind: str
    old_id: str
    new_id: str
    generation_id: str
    identity_version: str
    data_source: str
    reason: str = "identity_change"

    def __post_init__(self) -> None:
        if not self.old_id or not self.new_id:
            raise MigrationError("migration ids must not be blank")
        if self.old_id == self.new_id:
            raise MigrationError(
                f"migration {self.kind}: old_id equals new_id ({self.old_id})"
            )
        if not self.generation_id:
            raise MigrationError("migration requires a generation_id")
        if self.kind not in IDENTITY_VERSION_BY_KIND:
            raise MigrationError(f"unknown migration kind: {self.kind!r}")
        try:
            data_source = validate_data_source(self.data_source)
        except ValueError as error:
            raise MigrationError(f"migration {self.kind}: {error}") from error
        object.__setattr__(self, "data_source", data_source)

    def as_row(self) -> Dict[str, str]:
        return {
            "old_id": self.old_id,
            "new_id": self.new_id,
            "kind": self.kind,
            "identity_version": self.identity_version,
            "generation_id": self.generation_id,
            "data_source": self.data_source,
            "reason": self.reason,
        }


def migrate_period(
    generation_id: str,
    period_type: str,
    start: Optional[str],
    end: Optional[str],
) -> IdentityMigration:
    """v1 Period id -> v2 Period id (explicit type, null instant start)."""
    new_key = period_key(period_type, start, end)
    return IdentityMigration(
        kind=KIND_PERIOD,
        old_id=legacy_period_id(start, end),
        new_id=entity_id(new_key),
        generation_id=generation_id,
        identity_version=IDENTITY_VERSION_V2,
        data_source=DERIVED,
        reason="period_type_explicit",
    )


def migrate_security(
    generation_id: str,
    legacy_natural_key: Sequence[Optional[str]],
    issuer_company_id: str,
    share_class_code: str,
) -> IdentityMigration:
    """Legacy (cik, ticker) Security id -> v2 (issuer + class) id."""
    new_key = security_key(issuer_company_id, share_class_code)
    return IdentityMigration(
        kind=KIND_SECURITY,
        old_id=make_node_id("v1", *[str(part) for part in legacy_natural_key]),
        new_id=entity_id(new_key),
        generation_id=generation_id,
        identity_version=IDENTITY_VERSION_V2,
        data_source=DERIVED,
        reason="security_issuer_and_class",
    )


def derive_fact_migration(
    generation_id: str,
    fact_row: Mapping[str, Any],
    period_migrations: Sequence[IdentityMigration],
) -> Optional[IdentityMigration]:
    """Recompute a Fact id whose Period reference was migrated.

    ``fact_row`` carries ``node_id`` (the old fact id), ``period_id`` (the old
    Period id) plus the other assertion-key columns.  Returns ``None`` when the
    row does not reference a migrated Period.
    """
    old_period = fact_row.get("period_id")
    replacement = {
        migration.old_id: migration.new_id
        for migration in period_migrations
        if migration.kind == KIND_PERIOD
    }
    if old_period not in replacement:
        return None
    new_fact = fact_id_v2(
        str(fact_row["company_id"]),
        str(fact_row["concept_id"]),
        str(fact_row["unit"]),
        replacement[old_period],
        fact_row.get("dimensions_hash"),
        str(fact_row["filing_id"]),
    )
    return IdentityMigration(
        kind=KIND_FACT,
        old_id=str(fact_row["node_id"]),
        new_id=new_fact,
        generation_id=generation_id,
        identity_version=IDENTITY_VERSION_V2,
        data_source=DERIVED,
        reason="fact_embeds_period",
    )


@dataclass(frozen=True)
class MigrationRewrite:
    path: Tuple[str, ...]
    old_id: str
    new_id: str


@dataclass(frozen=True)
class MigrationResult:
    document: Any
    migrations: Tuple[IdentityMigration, ...]
    rewrites: Tuple[MigrationRewrite, ...]

    @property
    def changed(self) -> int:
        return len(self.rewrites)


def _walk_and_rewrite(
    node: Any,
    path: Tuple[str, ...],
    replacements: Mapping[str, str],
    rewrites: List[MigrationRewrite],
) -> Any:
    if isinstance(node, Mapping):
        rebuilt: Dict[str, Any] = {}
        for key, value in node.items():
            rebuilt[key] = _walk_and_rewrite(
                value, path + (str(key),), replacements, rewrites
            )
        return rebuilt
    if isinstance(node, (list, tuple)):
        return [
            _walk_and_rewrite(value, path + (str(index),), replacements, rewrites)
            for index, value in enumerate(node)
        ]
    if isinstance(node, str) and node in replacements:
        rewrites.append(
            MigrationRewrite(path=path, old_id=node, new_id=replacements[node])
        )
        return replacements[node]
    return node


def apply_migration(
    document: Any,
    migrations: Sequence[IdentityMigration],
    *,
    fact_rows: Optional[Iterable[Mapping[str, Any]]] = None,
    generation_id: Optional[str] = None,
) -> MigrationResult:
    """Rewrite every reference to a migrated id inside ``document``.

    Nodes, edges, evidence links and exports are all covered: any string value
    equal to an ``old_id`` is replaced, wherever it appears, and every rewrite
    is reported with its path.  Identifiers used as *mapping keys* are not
    rewritable without renaming columns, so exports must carry explicit id
    values (documented contract).

    ``fact_rows`` are rows whose Fact id embeds a migrated Period id; their
    derived migrations are appended to the returned migration set.
    """
    collected: List[IdentityMigration] = list(migrations)
    by_old: Dict[str, str] = {}
    for migration in collected:
        if migration.old_id in by_old:
            raise MigrationError(
                f"duplicate migration source id {migration.old_id}"
            )
        by_old[migration.old_id] = migration.new_id

    generation = generation_id or (collected[0].generation_id if collected else "")
    if fact_rows is not None:
        if not generation:
            raise MigrationError("fact migration requires a generation_id")
        period_migrations = [
            migration for migration in collected if migration.kind == KIND_PERIOD
        ]
        for row in fact_rows:
            derived = derive_fact_migration(generation, row, period_migrations)
            if derived is None:
                continue
            if derived.old_id in by_old and by_old[derived.old_id] != derived.new_id:
                raise MigrationError(
                    f"conflicting migration for {derived.old_id}"
                )
            by_old[derived.old_id] = derived.new_id
            collected.append(derived)

    rewrites: List[MigrationRewrite] = []
    rewritten = _walk_and_rewrite(document, (), by_old, rewrites)
    rewrites.sort(key=lambda item: item.path)
    return MigrationResult(
        document=rewritten,
        migrations=tuple(collected),
        rewrites=tuple(rewrites),
    )


def find_reference_paths(
    document: Any, ids: Iterable[str]
) -> List[Tuple[str, ...]]:
    """Return every path whose string value is one of ``ids``."""
    targets = set(ids)
    found: List[Tuple[str, ...]] = []

    def _walk(node: Any, path: Tuple[str, ...]) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                _walk(value, path + (str(key),))
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                _walk(value, path + (str(index),))
        elif isinstance(node, str) and node in targets:
            found.append(path)

    _walk(document, ())
    found.sort()
    return found
