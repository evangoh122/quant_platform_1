"""Identity contracts: encoders, provisional ids, aliases and migration.

Acceptance tests named by Codex Sol R4 (S1, S15 / R2-6).  Production functions
only — no logic is copied into the test.
"""
from __future__ import annotations

import hashlib
import itertools

import pytest

from sec_kg.contracts import identity
from sec_kg.model import (
    chunk_id_from_parts,
    company_id as model_company_id,
    filing_id as model_filing_id,
    make_node_id,
    metric_id as model_metric_id,
    section_id as model_section_id,
)

CIK = "0001045810"
OTHER_CIK = "0000320193"
ACCESSION = "0001045810-24-000001"
GENERATION = "kg-mig-0001"


def _issuer(cik: str = CIK) -> str:
    return identity.company_id(cik)


# ═══════════════════════════════════════════════════════════════════════════════
# S1 — security identity: permutation, aliases, cycles, ticker reuse
# ═══════════════════════════════════════════════════════════════════════════════

def test_security_identity_permutation_alias_cycle_and_ticker_reuse():
    issuer = _issuer()
    other_issuer = _issuer(OTHER_CIK)

    # Share classes are separate securities; normalisation is benign.
    class_a = identity.security_id(issuer, "CL_A")
    class_c = identity.security_id(issuer, "CL_C")
    assert class_a != class_c
    assert identity.security_id(issuer, "  cl_a  ") == class_a
    assert identity.identity_version("security") == identity.IDENTITY_VERSION_V2

    # Ticker reuse: the same ticker under a different issuer is a different
    # security (identity is issuer + share class, never the raw ticker).
    assert identity.security_id(issuer, "NVDA") != identity.security_id(
        other_issuer, "NVDA"
    )
    # The natural key keeps issuer and class separate in the hash.
    assert identity.security_key(issuer, "CL_A") != identity.security_key(
        other_issuer, "CL_A"
    )

    # A provisional id hashes the *first evidence id* (not a timestamp), so it
    # is identical under every ingestion permutation.
    evidence = ["ev:9", "ev:2", "ev:5"]
    provisional_ids = {
        identity.provisional_security_id(issuer, perm)
        for perm in itertools.permutations(evidence)
    }
    assert len(provisional_ids) == 1
    provisional = identity.provisional_security_id(issuer, evidence)
    assert provisional == identity.provisional_security_id(issuer, sorted(evidence))
    assert provisional != class_a
    # It is exactly the *smallest* evidence id that is hashed into the key, so a
    # different first id (not merely a different set) yields another id below.
    assert identity.provisional_security_key(issuer, evidence)[2] == (
        identity.PROVISIONAL_PREFIX + "ev:2"
    )
    assert provisional == identity.entity_id(
        (
            identity.KIND_SECURITY,
            issuer,
            identity.PROVISIONAL_PREFIX + "ev:2",
        )
    )
    # A different first evidence id yields a different provisional security.
    assert identity.provisional_security_id(
        issuer, ["ev:1", "ev:2"]
    ) != identity.provisional_security_id(issuer, ["ev:2", "ev:9"])
    assert identity.is_provisional_key(
        identity.provisional_security_key(issuer, evidence)
    )
    assert not identity.is_provisional_key(identity.security_key(issuer, "CL_A"))
    # Provisional ids are deterministic under shuffle at the key level too.
    assert len(
        {
            identity.provisional_security_key(issuer, perm)
            for perm in itertools.permutations(evidence)
        }
    ) == 1

    # Alias chains resolve transitively; history is append-only.
    direct = identity.alias_map([(provisional, class_a)])
    assert identity.resolve_alias(direct, provisional) == class_a
    chained = identity.alias_map([(provisional, "mid-id"), ("mid-id", class_a)])
    assert identity.resolve_alias(chained, provisional) == class_a
    assert identity.resolve_alias(chained, class_a) == class_a
    with pytest.raises(identity.AliasConflictError):
        identity.add_alias(direct, provisional, class_c)
    with pytest.raises(identity.AliasError):
        identity.add_alias({}, "same", "same")
    with pytest.raises(identity.AliasCycleError):
        identity.alias_map([("a", "b"), ("b", "a")])
    with pytest.raises(identity.AliasCycleError):
        identity.alias_map([("a", "b"), ("b", "c"), ("c", "a")])
    # A chain that only *reaches* the new id from itself must also be rejected.
    with pytest.raises(identity.AliasCycleError):
        identity.add_alias({"b": "c", "c": "a"}, "a", "b")

    # Collisions are detected in both directions, per kind and version.
    records = [
        (identity.security_key(issuer, "CL_A"), class_a),
        (identity.security_key(issuer, "CL_A"), class_c),
        (identity.security_key(issuer, "CL_B"), class_a),
    ]
    collisions = identity.check_collisions(records)
    directions = {collision.direction for collision in collisions}
    assert directions == {
        identity.COLLISION_KEY_TO_MANY_IDS,
        identity.COLLISION_ID_TO_MANY_KEYS,
    }
    assert all(collision.kind == "security" for collision in collisions)
    assert all(
        collision.identity_version == identity.IDENTITY_VERSION_V2
        for collision in collisions
    )
    # One natural key -> one id is not a collision.
    assert identity.check_collisions(
        [(identity.company_key(CIK), identity.company_id(CIK))]
    ) == []
    # Descriptions are stable and mention the offending identity.
    key_collision = next(
        collision for collision in collisions
        if collision.direction == identity.COLLISION_KEY_TO_MANY_IDS
    )
    assert "one natural key" in key_collision.describe()
    id_collision = next(
        collision for collision in collisions
        if collision.direction == identity.COLLISION_ID_TO_MANY_KEYS
    )
    assert "one id" in id_collision.describe()


# ═══════════════════════════════════════════════════════════════════════════════
# S15 / R2-6 — unchanged v1 ids, complete v2 reference migration
# ═══════════════════════════════════════════════════════════════════════════════

def test_unchanged_v1_ids_and_complete_v2_reference_migration():
    issuer = _issuer()

    # Unchanged kinds still use the frozen v1 encoder, byte for byte.
    assert identity.company_id(CIK) == model_company_id(CIK)
    assert identity.filing_id(CIK, ACCESSION) == model_filing_id(CIK, ACCESSION)
    assert identity.metric_id("Revenues") == model_metric_id("Revenues")
    assert identity.section_id(ACCESSION, "item1_business") == model_section_id(
        ACCESSION, "item1_business"
    )
    assert identity.chunk_id("chunk-1") == chunk_id_from_parts("chunk-1")
    assert identity.company_id(CIK) == hashlib.sha256(
        "2:v1|7:company|10:0001045810".encode("utf-8")
    ).hexdigest()
    for kind in ("company", "filing", "section", "chunk", "metric"):
        assert identity.identity_version(kind) == identity.IDENTITY_VERSION_V1

    # Period identity changed: explicit type, instant start is null, and a
    # same-day duration is a different period.
    legacy_period = identity.legacy_period_id(None, "2024-01-28")
    assert legacy_period == identity.legacy_period_id("", "2024-01-28")
    instant = identity.period_id_v2("instant", None, "2024-01-28")
    same_day_duration = identity.period_id_v2("duration", "2024-01-28", "2024-01-28")
    assert instant != same_day_duration
    assert instant != legacy_period
    assert identity.period_id_v2("instant", None, "2024-01-28") == instant
    with pytest.raises(identity.IdentityError):
        identity.period_id_v2("instant", "2024-01-28", "2024-01-28")
    with pytest.raises(identity.IdentityError):
        identity.period_id_v2("duration", None, "2024-01-28")
    # Null-safe encoding distinguishes null from the empty string.
    assert identity.canonical_v2_payload("period", [None, "2024-01-28"]) != (
        identity.canonical_v2_payload("period", ["", "2024-01-28"])
    )

    # ── A document referencing the changed ids in nodes, edges, evidence and
    # the export ────────────────────────────────────────────────────────────
    company = identity.company_id(CIK)
    filing = identity.filing_id(CIK, ACCESSION)
    concept = identity.concept_id("us-gaap", "Revenues")
    old_period = identity.legacy_period_id("2023-01-29", "2024-01-28")
    new_period = identity.period_id_v2("duration", "2023-01-29", "2024-01-28")
    old_security = make_node_id("v1", "security", CIK, "NVDA")
    new_security = identity.security_id(issuer, "CL_A")
    old_fact = identity.legacy_fact_id(
        CIK, ACCESSION, "Revenues", "2023-01-29", "2024-01-28", "USD", "100", "c1"
    )

    fact_row = {
        "node_id": old_fact,
        "company_id": company,
        "concept_id": concept,
        "unit": "USD",
        "period_id": old_period,
        "dimensions_hash": None,
        "filing_id": filing,
    }
    new_fact = identity.fact_id_v2(
        company, concept, "USD", new_period, None, filing
    )

    document = {
        "nodes": [
            {"node_id": old_period, "node_type": "Period", "period_id": old_period},
            {
                "node_id": old_fact,
                "node_type": "XbrlFact",
                "company_id": company,
                "period_id": old_period,
            },
            {"node_id": old_security, "node_type": "Security"},
            {"node_id": company, "node_type": "Company"},
        ],
        "edges": [
            {"edge_id": "edge-1", "src_id": old_fact, "dst_id": old_period},
            {"edge_id": "edge-2", "src_id": company, "dst_id": old_security},
        ],
        "evidence": [
            {"evidence_id": "ev-1", "entity_id": old_security, "source_id": old_period}
        ],
        "export": {
            "generation": GENERATION,
            "rows": [
                {
                    "security_id": old_security,
                    "period_id": old_period,
                    "fact_id": old_fact,
                }
            ],
        },
    }

    migrations = [
        identity.migrate_period(GENERATION, "duration", "2023-01-29", "2024-01-28"),
        identity.migrate_security(
            GENERATION, ("security", CIK, "NVDA"), issuer, "CL_A"
        ),
    ]
    result = identity.apply_migration(
        document, migrations, fact_rows=[fact_row], generation_id=GENERATION
    )

    old_ids = [old_period, old_security, old_fact]
    assert identity.find_reference_paths(result.document, old_ids) == []
    # Every reference site was rewritten, not just node/edge endpoints.
    assert identity.find_reference_paths(result.document, [new_period]) == [
        ("edges", "0", "dst_id"),
        ("evidence", "0", "source_id"),
        ("export", "rows", "0", "period_id"),
        ("nodes", "0", "node_id"),
        ("nodes", "0", "period_id"),
        ("nodes", "1", "period_id"),
    ]
    assert identity.find_reference_paths(result.document, [new_security]) == [
        ("edges", "1", "dst_id"),
        ("evidence", "0", "entity_id"),
        ("export", "rows", "0", "security_id"),
        ("nodes", "2", "node_id"),
    ]
    assert identity.find_reference_paths(result.document, [new_fact]) == [
        ("edges", "0", "src_id"),
        ("export", "rows", "0", "fact_id"),
        ("nodes", "1", "node_id"),
    ]
    # Unchanged ids are untouched.
    assert identity.find_reference_paths(result.document, [company]) == [
        ("edges", "1", "src_id"),
        ("nodes", "1", "company_id"),
        ("nodes", "3", "node_id"),
    ]
    assert result.changed > 0

    # Migration rows: one per changed id, with the generation and version.
    kinds = {migration.kind for migration in result.migrations}
    assert kinds == {"period", "security", "xbrl_fact"}
    rows = [migration.as_row() for migration in result.migrations]
    for row in rows:
        assert row["generation_id"] == GENERATION
        assert row["old_id"] != row["new_id"]
        assert row["identity_version"] in ("v1", identity.IDENTITY_VERSION_V2)
        assert row["data_source"] == "derived"
        assert set(row) == {
            "old_id",
            "new_id",
            "kind",
            "identity_version",
            "generation_id",
            "data_source",
            "reason",
        }
    fact_migration = next(row for row in rows if row["kind"] == "xbrl_fact")
    assert fact_migration["old_id"] == old_fact
    assert fact_migration["new_id"] == new_fact
    assert fact_migration["reason"] == "fact_embeds_period"

    # Idempotent: re-applying the same migration changes nothing.
    again = identity.apply_migration(
        result.document, migrations, fact_rows=[fact_row], generation_id=GENERATION
    )
    assert again.changed == 0
    assert again.document == result.document

    # A migration may not silently rewrite an id to itself.
    with pytest.raises(identity.MigrationError):
        identity.IdentityMigration(
            kind="period",
            old_id=new_period,
            new_id=new_period,
            generation_id=GENERATION,
            identity_version=identity.IDENTITY_VERSION_V2,
            data_source="derived",
        )
    # The migration row's provider code is required and validated.
    with pytest.raises(TypeError):
        identity.IdentityMigration(
            kind="period",
            old_id="old",
            new_id="new",
            generation_id=GENERATION,
            identity_version=identity.IDENTITY_VERSION_V2,
        )
    with pytest.raises(identity.MigrationError):
        identity.IdentityMigration(
            kind="period",
            old_id="old",
            new_id="new",
            generation_id=GENERATION,
            identity_version=identity.IDENTITY_VERSION_V2,
            data_source="edgar",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# R4 — typed NULLs in collision detection, real calendar dates
# ═══════════════════════════════════════════════════════════════════════════════

def test_collision_detection_keeps_typed_nulls_and_never_crashes():
    null_market = (identity.KIND_INSTRUMENT, "hyperliquid", None, "BTC-PERP")
    empty_market = (identity.KIND_INSTRUMENT, "hyperliquid", "", "BTC-PERP")
    other_market = (identity.KIND_INSTRUMENT, "hyperliquid", "dex", "BTC-PERP")

    # ``None`` and ``""`` are different natural keys: mapping both to one id is
    # a collision even though they render alike.
    collisions = identity.check_collisions(
        [(null_market, "shared-id"), (empty_market, "shared-id")]
    )
    assert len(collisions) == 1
    assert collisions[0].direction == identity.COLLISION_ID_TO_MANY_KEYS
    assert collisions[0].entity_id == "shared-id"
    assert collisions[0].natural_keys == (empty_market, null_market)
    assert len(collisions[0].natural_keys) == 2

    # A typed NULL next to a real string sorts by a total key; it never raises
    # TypeError by comparing None with str.
    mixed = identity.check_collisions(
        [(other_market, "shared-id"), (null_market, "shared-id")]
    )
    assert len(mixed) == 1
    assert mixed[0].natural_keys == (other_market, null_market)
    # The description lists both typed keys and stays readable.
    assert "2 natural keys" in mixed[0].describe()

    # One natural key with one id is still clean.
    assert identity.check_collisions([(null_market, "shared-id")]) == []
    assert identity.check_collisions([(empty_market, "shared-id")]) == []


def test_period_dates_must_be_real_calendar_dates():
    for impossible in ("2024-13-45", "2024-02-30", "2023-02-29", "2024-00-10"):
        with pytest.raises(identity.IdentityError):
            identity.period_id_v2("instant", None, impossible)
    with pytest.raises(identity.IdentityError):
        identity.period_id_v2("duration", "2024-01-01", "2024-13-01")
    with pytest.raises(identity.IdentityError):
        identity.period_id_v2("instant", None, "2024-1-01")
    # A real leap day is accepted.
    assert identity.period_id_v2("instant", None, "2024-02-29")


# ═══════════════════════════════════════════════════════════════════════════════
# CodeRabbit full review (PR #76) item 4 — a blank legacy instant start is None
# ═══════════════════════════════════════════════════════════════════════════════

def test_instant_period_normalises_the_blank_legacy_start():
    canonical = identity.period_id_v2("instant", None, "2024-01-28")
    # The v1 encoder stores an instant start as "" (sec_kg/model.py), so a KG-B
    # migration that passes `period_start` verbatim must still mint the v2 id.
    assert identity.period_id_v2("instant", "", "2024-01-28") == canonical
    assert identity.period_id_v2("instant", "   ", "2024-01-28") == canonical
    # The v2 key still encodes None, never the blank string.
    assert identity.period_key("instant", "", "2024-01-28") == (
        "period",
        "instant",
        None,
        "2024-01-28",
    )
    # A real start on an instant remains an error; only blank is normalised.
    with pytest.raises(identity.IdentityError):
        identity.period_id_v2("instant", "2024-01-27", "2024-01-28")
