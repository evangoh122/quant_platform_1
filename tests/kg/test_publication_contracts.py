"""Publication contracts: CAS state machine and subset ownership.

Acceptance tests named by Codex Sol R4 (R3-6 / S16, R2-7 / R3-5).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sec_kg.contracts import publication, registry

DT = datetime(2024, 1, 2, tzinfo=timezone.utc)


class FakePointerExecutor:
    """In-memory stand-in for the Delta pointer table + manifest writer.

    ``compare_and_set`` mirrors the MERGE in KG_DATA_MODEL_v4 §G: the update
    matches only while the pointer still names the predecessor, and the
    bootstrap insert matches only while the pointer is empty.
    """

    def __init__(self) -> None:
        self.pointer = None
        self.manifests = {}
        self.cas_calls = 0

    def read_pointer(self):
        return self.pointer

    def put_manifest(self, generation):
        existing = self.manifests.get(generation.generation_id)
        if existing is not None and existing.digest() != generation.digest():
            raise publication.ManifestConflictError(
                f"generation {generation.generation_id} already published with "
                "different content"
            )
        self.manifests[generation.generation_id] = generation

    def get_manifest(self, generation_id):
        return self.manifests.get(generation_id)

    def compare_and_set(self, *, predecessor, generation_id):
        self.cas_calls += 1
        if predecessor is None:
            if self.pointer is not None:
                return 0
        elif self.pointer != predecessor:
            return 0
        self.pointer = generation_id
        return 1


def generation(
    generation_id: str,
    predecessor,
    *,
    kind: str = publication.KIND_FULL,
    membership=(),
    output_version: int = 11,
):
    return publication.Generation(
        generation_id=generation_id,
        predecessor_generation_id=predecessor,
        kind=kind,
        membership=tuple(membership),
        input_versions={"silver_sec_sections": 7},
        output_versions={"gold_sec_kg_nodes": output_version},
        created_at=DT,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# R3-6 — bootstrap, race, stale predecessor, retry idempotence, immutability
# ═══════════════════════════════════════════════════════════════════════════════

def test_publication_bootstrap_race_stale_predecessor_retry():
    executor = FakePointerExecutor()
    first = generation("gen-1", None)

    # Bootstrap race: two publishers both see an empty pointer and both claim
    # the same (empty) predecessor.  Exactly one wins.
    winner = publication.publish(executor, first)
    loser = publication.publish(executor, generation("gen-race", None))
    assert winner.published is True
    assert winner.outcome == publication.OUTCOME_PUBLISHED
    assert winner.affected_rows == 1
    assert loser.published is False
    assert [winner.published, loser.published].count(True) == 1
    # The pointer is unchanged on failure and the losing run is marked FAILED
    # with its outputs left unpublished.
    assert executor.pointer == "gen-1"
    assert executor.get_manifest("gen-race").status == publication.STATUS_FAILED
    assert loser.pointer == "gen-1"

    # Retry of the winner is an idempotent no-op success.
    retry = publication.publish(executor, first)
    assert retry.published is True
    assert retry.outcome == publication.OUTCOME_ALREADY_CURRENT
    assert retry.affected_rows == 0
    assert executor.pointer == "gen-1"
    assert executor.get_manifest("gen-1").status == publication.STATUS_PUBLISHED

    # A successor publishes normally.
    successor = generation("gen-2", "gen-1")
    published = publication.publish(executor, successor)
    assert published.published is True
    assert published.outcome == publication.OUTCOME_PUBLISHED
    assert executor.pointer == "gen-2"

    # A publisher built on a stale predecessor fails without moving the pointer.
    stale = publication.publish(executor, generation("gen-1b", "gen-1"))
    assert stale.published is False
    assert stale.outcome == publication.OUTCOME_STALE_PREDECESSOR
    assert stale.affected_rows == 0
    assert executor.pointer == "gen-2"
    assert executor.get_manifest("gen-1b").status == publication.STATUS_FAILED

    # A published manifest is immutable: reusing the generation id with
    # different output versions is rejected and changes nothing.
    conflicting = generation("gen-2", "gen-1", output_version=99)
    conflict = publication.publish(executor, conflicting)
    assert conflict.published is False
    assert conflict.outcome == publication.OUTCOME_MANIFEST_CONFLICT
    assert conflict.pointer == "gen-2"
    stored = executor.get_manifest("gen-2")
    assert dict(stored.output_versions) == {"gold_sec_kg_nodes": 11}
    assert stored.status == publication.STATUS_PUBLISHED
    assert stored.digest() != conflicting.digest()

    # Manifest validation is explicit.
    with pytest.raises(publication.PublicationError):
        generation("gen-3", None, membership=("AAA",))
    with pytest.raises(publication.PublicationError):
        generation("gen-3", None, kind=publication.KIND_SUBSET)
    with pytest.raises(publication.PublicationError):
        publication.Generation(
            generation_id="gen-4",
            predecessor_generation_id=None,
            kind=publication.KIND_FULL,
            input_versions={},
            output_versions={"gold_sec_kg_nodes": 1},
            created_at=DT,
        )
    subset = generation("gen-5", "gen-2", kind=publication.KIND_SUBSET,
                        membership=("AAA", "BBB"))
    assert subset.membership == ("AAA", "BBB")


# ═══════════════════════════════════════════════════════════════════════════════
# S16 / R2-7, R3-5 — subset ownership equals a full build for owned rows
# ═══════════════════════════════════════════════════════════════════════════════

def _predecessor_rows():
    return [
        {"node_id": "co:A", "node_type": "Company", "company_id": "co:A", "label": "A"},
        {"node_id": "co:B", "node_type": "Company", "company_id": "co:B", "label": "B"},
        {"node_id": "metric:M", "node_type": "Metric", "label": "Revenue"},
        {"node_id": "period:P", "node_type": "Period", "label": "FY2023"},
        {"node_id": "fact:A1", "node_type": "XbrlFact", "company_id": "co:A",
         "value": "100"},
        {"node_id": "fact:B1", "node_type": "XbrlFact", "company_id": "co:B",
         "value": "200"},
        {"edge_id": "io:A", "edge_type": "INSTANCE_OF", "company_id": "co:A",
         "src_id": "fact:A1", "dst_id": "metric:M"},
        {"edge_id": "io:B", "edge_type": "INSTANCE_OF", "company_id": "co:B",
         "src_id": "fact:B1", "dst_id": "metric:M"},
        {"edge_id": "fp:A", "edge_type": "FOR_PERIOD", "company_id": "co:A",
         "src_id": "fact:A1", "dst_id": "period:P"},
        {"edge_id": "fp:B", "edge_type": "FOR_PERIOD", "company_id": "co:B",
         "src_id": "fact:B1", "dst_id": "period:P"},
        {"edge_id": "peer:AB", "edge_type": "INFERRED_PEER",
         "src_id": "co:A", "dst_id": "co:B"},
        {"evidence_id": "ev:A1", "node_id": "fact:A1", "owner_company_id": "co:A"},
        {"evidence_id": "ev:B1", "node_id": "fact:B1", "owner_company_id": "co:B"},
    ]


def _rebuilt_member_rows():
    """Member A was rebuilt: its fact has a new identity (a corrected filing)."""
    return [
        {"node_id": "co:A", "node_type": "Company", "company_id": "co:A", "label": "A"},
        {"node_id": "fact:A2", "node_type": "XbrlFact", "company_id": "co:A",
         "value": "150"},
        {"edge_id": "io:A2", "edge_type": "INSTANCE_OF", "company_id": "co:A",
         "src_id": "fact:A2", "dst_id": "metric:M"},
        {"edge_id": "fp:A2", "edge_type": "FOR_PERIOD", "company_id": "co:A",
         "src_id": "fact:A2", "dst_id": "period:P"},
        {"evidence_id": "ev:A2", "node_id": "fact:A2", "owner_company_id": "co:A"},
    ]


def _full_rows_for_members():
    rows = [
        {"node_id": "co:A", "node_type": "Company", "company_id": "co:A", "label": "A"},
        {"node_id": "co:B", "node_type": "Company", "company_id": "co:B", "label": "B"},
        {"node_id": "metric:M", "node_type": "Metric", "label": "Revenue"},
        {"node_id": "period:P", "node_type": "Period", "label": "FY2023"},
        {"node_id": "fact:A2", "node_type": "XbrlFact", "company_id": "co:A",
         "value": "150"},
        {"node_id": "fact:B1", "node_type": "XbrlFact", "company_id": "co:B",
         "value": "200"},
        {"edge_id": "io:A2", "edge_type": "INSTANCE_OF", "company_id": "co:A",
         "src_id": "fact:A2", "dst_id": "metric:M"},
        {"edge_id": "io:B", "edge_type": "INSTANCE_OF", "company_id": "co:B",
         "src_id": "fact:B1", "dst_id": "metric:M"},
        {"edge_id": "fp:A2", "edge_type": "FOR_PERIOD", "company_id": "co:A",
         "src_id": "fact:A2", "dst_id": "period:P"},
        {"edge_id": "fp:B", "edge_type": "FOR_PERIOD", "company_id": "co:B",
         "src_id": "fact:B1", "dst_id": "period:P"},
        {"edge_id": "peer:AB", "edge_type": "INFERRED_PEER",
         "src_id": "co:A", "dst_id": "co:B"},
        {"evidence_id": "ev:A2", "node_id": "fact:A2", "owner_company_id": "co:A"},
        {"evidence_id": "ev:B1", "node_id": "fact:B1", "owner_company_id": "co:B"},
    ]
    return rows


def test_subset_equals_full_for_owned_rows_and_evidence():
    # INSTANCE_OF / FOR_PERIOD belong to the source fact's company, even though
    # their targets (Metric / Period) are global nodes.
    assert publication.row_owner(
        {"edge_type": "INSTANCE_OF", "company_id": "co:A"}
    ) == "company:co:A"
    assert publication.row_owner(
        {"edge_type": "FOR_PERIOD", "company_id": "co:A"}
    ) == "company:co:A"
    assert publication.row_owner({"node_type": "Metric"}) == "global"
    assert publication.row_owner({"node_type": "Period"}) == "global"
    assert publication.row_owner({"edge_type": "INFERRED_PEER"}) == "cross-company"
    assert publication.row_owner(
        {"evidence_id": "ev:A1", "owner_company_id": "co:A"}
    ) == "company:co:A"

    predecessor = _predecessor_rows()
    rebuilt = _rebuilt_member_rows()
    subset = publication.plan_subset(predecessor, rebuilt, ["co:A"])
    expected = sorted(_full_rows_for_members(), key=publication.row_identity)
    # The subset result is exactly what a full build of the same inputs yields.
    assert subset == expected

    identities = {publication.row_identity(row) for row in subset}
    # Member-owned rows from the predecessor are gone (replaced by the rebuild).
    assert "fact:A1" not in identities
    assert "io:A" not in identities
    assert "fp:A" not in identities
    assert "ev:A1" not in identities
    # Non-member rows are untouched.
    for row in predecessor:
        if publication.row_identity(row) in ("co:B", "fact:B1", "io:B", "fp:B", "ev:B1"):
            assert row in subset
    # Global nodes survive a subset build (union of references).
    assert {"metric:M", "period:P"} <= identities
    # Cross-company edges are never rebuilt by a subset, but are preserved.
    assert "peer:AB" in identities
    # Evidence rows follow their owner.
    assert "ev:A2" in identities and "ev:B1" in identities

    # A subset may not rebuild cross-company or non-member rows.
    with pytest.raises(publication.PublicationError):
        publication.plan_subset(
            predecessor,
            rebuilt + [{"edge_id": "peer:AB", "edge_type": "INFERRED_PEER",
                        "src_id": "co:A", "dst_id": "co:B"}],
            ["co:A"],
        )
    with pytest.raises(publication.PublicationError):
        publication.plan_subset(
            predecessor,
            rebuilt + [{"node_id": "fact:B2", "node_type": "XbrlFact",
                        "company_id": "co:B", "value": "201"}],
            ["co:A"],
        )
    with pytest.raises(publication.PublicationError):
        publication.plan_subset(predecessor, rebuilt, [])

    # ── Classification staleness gate ──────────────────────────────────────
    before = [
        publication.ClassificationObservation(
            company_id="co:A", taxonomy="sic", code="3674", label="Semiconductors",
            observed_at=DT,
        ),
        publication.ClassificationObservation(
            company_id="co:B", taxonomy="sic", code="3571", label="Computers",
            observed_at=DT,
        ),
    ]
    # Unchanged member classification: the subset is allowed.
    publication.check_subset_allowed(before, list(before), ["co:A"])
    # A member classification that changed (stale + new observation) rejects it.
    changed = [
        publication.ClassificationObservation(
            company_id="co:A", taxonomy="sic", code="7372", label="Software",
            observed_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        ),
        before[1],
    ]
    with pytest.raises(publication.SubsetRejectedError):
        publication.check_subset_allowed(before, changed, ["co:A"])
    # Deleted and newly added classifications reject it too.
    with pytest.raises(publication.SubsetRejectedError):
        publication.check_subset_allowed(before, [before[1]], ["co:A"])
    added = before + [
        publication.ClassificationObservation(
            company_id="co:A", taxonomy="finviz", code="Tech", label="Technology",
            observed_at=DT,
        )
    ]
    with pytest.raises(publication.SubsetRejectedError):
        publication.check_subset_allowed(before, added, ["co:A"])
    # A non-member's classification change is not this subset's problem.
    non_member_change = [
        before[0],
        publication.ClassificationObservation(
            company_id="co:B", taxonomy="sic", code="9999", label="Other",
            observed_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        ),
    ]
    publication.check_subset_allowed(before, non_member_change, ["co:A"])
    # The registry edge scopes agree with the ownership used above.
    assert registry.get_edge_contract("INSTANCE_OF").scope == (
        registry.SCOPE_GLOBAL_TARGET
    )
    assert registry.get_edge_contract("FOR_PERIOD").scope == (
        registry.SCOPE_GLOBAL_TARGET
    )
