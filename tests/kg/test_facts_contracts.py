"""Fact contracts: keys, filter-then-reconcile, extracted-fact linking.

Acceptance tests named by Codex Sol R4 (R3-3, R3-4, S6 / R2-1).
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pytest

from sec_kg.contracts import facts, identity

COMPANY_A = identity.company_id("0001045810")
COMPANY_B = identity.company_id("0000320193")
CONCEPT = identity.concept_id("us-gaap", "Revenues")
METRIC = identity.metric_id("revenues")
PERIOD = identity.period_id_v2("duration", "2023-01-29", "2024-01-28")
PERIOD_OTHER = identity.period_id_v2("duration", "2022-01-30", "2023-01-28")
FILING = identity.filing_id(COMPANY_A, "0001045810-24-000001")
FILING_AMENDED = identity.filing_id(COMPANY_A, "0001045810-24-000002")
FILING_B = identity.filing_id(COMPANY_B, "0000320193-24-000001")
ACCESSION = "0001045810-24-000001"


def dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def entry(value: str, *, unit: str = "USD", form: str = "10-K",
          accn: str = ACCESSION, start: str = "2023-01-29",
          end: str = "2024-01-28") -> dict:
    return {
        "value_raw": value,
        "unit": unit,
        "start": start,
        "end": end,
        "instant": None,
        "fy": "2023",
        "fp": "FY",
        "form": form,
        "filed": "2024-01-28",
        "frame": None,
        "accn": accn,
    }


def series(**overrides):
    values = {
        "company_id": COMPANY_A,
        "concept_id": CONCEPT,
        "unit": "USD",
        "period_id": PERIOD,
        "dimensions_hash": None,
    }
    values.update(overrides)
    return facts.series_key(**values)


def candidate(
    value: str,
    *,
    company: str = COMPANY_A,
    concept: str = CONCEPT,
    metric: str = METRIC,
    period: str = PERIOD,
    unit: str = "USD",
    dimensions: str = facts.DIMENSIONS_HASH_ABSENT,
    filing: str = FILING,
    decimals: int = 0,
) -> facts.LinkCandidate:
    key = facts.series_key(company, concept, unit, period, dimensions)
    return facts.LinkCandidate(
        assertion=facts.assertion_key(key, filing),
        value_raw=value,
        metric_id=metric,
        decimals=decimals,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# R3-3 — extracted-fact linking needs a unique assertion match
# ═══════════════════════════════════════════════════════════════════════════════

def test_extracted_link_requires_unique_company_metric_period_unit_dimensions_value():
    extracted = facts.ExtractedFact(
        company_id=COMPANY_A,
        metric_id=METRIC,
        period_id=PERIOD,
        unit="USD",
        value_raw="100",
        dimensions_hash=facts.DIMENSIONS_HASH_ABSENT,
        evidence_id="ev-extracted-1",
    )

    same_issuer = candidate("100")
    other_issuer = candidate("100", company=COMPANY_B, filing=FILING_B)
    different_unit = candidate("100", unit="shares", filing=FILING)
    other_dimensions = candidate("100", dimensions="dim-hash-1")
    second_same_issuer = candidate("100", concept=CONCEPT, filing=FILING_AMENDED)

    # Cross-issuer and incompatible-unit candidates are rejected, so the match
    # is unique and links to the same-issuer assertion.
    linked = facts.link_extracted_fact(
        extracted, [same_issuer, other_issuer, different_unit]
    )
    assert linked.linked
    assert linked.reason == facts.LINK_LINKED
    assert linked.assertion == same_issuer.assertion
    assert linked.matched == (same_issuer.assertion,)

    # The fixture really does share company/metric/period/unit with the decoy.
    assert other_issuer.company_id != extracted.company_id
    assert other_issuer.metric_id == extracted.metric_id
    assert other_issuer.period_id == extracted.period_id
    assert other_issuer.unit == extracted.unit

    cross = facts.link_extracted_fact(extracted, [other_issuer])
    assert not cross.linked
    assert cross.reason == facts.LINK_CROSS_ISSUER

    unit = facts.link_extracted_fact(extracted, [different_unit])
    assert not unit.linked
    assert unit.reason == facts.LINK_UNIT_INCOMPATIBLE

    # Two matching dimensions blocks means the extracted fact cannot know which
    # XBRL context it belongs to.
    unknown = facts.link_extracted_fact(extracted, [same_issuer, other_dimensions])
    assert not unknown.linked
    assert unknown.reason == facts.LINK_UNKNOWN_DIMENSIONS

    dimensions = facts.link_extracted_fact(extracted, [other_dimensions])
    assert not dimensions.linked
    assert dimensions.reason == facts.LINK_DIMENSIONS_MISMATCH

    # Two otherwise identical assertions are ambiguous, never silently picked.
    ambiguous = facts.link_extracted_fact(extracted, [same_issuer, second_same_issuer])
    assert not ambiguous.linked
    assert ambiguous.reason == facts.LINK_AMBIGUOUS
    assert len(ambiguous.matched) == 2

    # Period and metric mismatches are distinguished from a missing candidate.
    period = facts.link_extracted_fact(extracted, [candidate("100", period=PERIOD_OTHER)])
    assert period.reason == facts.LINK_PERIOD_MISMATCH
    metric = facts.link_extracted_fact(
        extracted, [candidate("100", metric=identity.metric_id("assets"))]
    )
    assert metric.reason == facts.LINK_METRIC_MISMATCH
    assert facts.link_extracted_fact(extracted, []).reason == facts.LINK_NO_CANDIDATE

    # A value that differs at the stated decimals never links; the tolerance is
    # explicit.
    mismatch = facts.link_extracted_fact(extracted, [candidate("100.4")])
    assert mismatch.reason == facts.LINK_VALUE_MISMATCH
    assert facts.link_extracted_fact(extracted, [candidate("100.04", decimals=1)]).linked
    assert not facts.link_extracted_fact(
        extracted, [candidate("100.04", decimals=2)]
    ).linked
    assert facts.values_match("100", "100.0", 0)
    assert not facts.values_match("100", "120", 0)
    assert facts.values_match("100.0", "100.04", 1)
    assert not facts.values_match("100.0", "100.04", 2)


# ═══════════════════════════════════════════════════════════════════════════════
# R3-4 — filter before reconcile, in both query modes
# ═══════════════════════════════════════════════════════════════════════════════

def test_filter_before_reconcile_amendment_T1_T2():
    s = series()
    assertion_original = facts.assertion_key(s, FILING)
    assertion_amended = facts.assertion_key(s, FILING_AMENDED)

    original = facts.make_observation(
        assertion_original,
        entry("100", form="10-K"),
        public_available_at=dt(2024, 2, 1),
        system_from=dt(2024, 2, 2),
        evidence_id="ev-original",
    )
    amended = facts.make_observation(
        assertion_amended,
        entry("120", form="10-K/A", accn="0001045810-24-000002"),
        public_available_at=dt(2024, 5, 1),
        system_from=dt(2024, 5, 2),
        evidence_id="ev-amended",
    )
    unverified = facts.make_observation(
        assertion_amended,
        entry("999", form="10-K/A", accn="0001045810-24-000003"),
        public_available_at=None,
        system_from=dt(2024, 6, 1),
        evidence_id="ev-unverified",
    )

    observations = [original, amended, unverified]

    # T1: the amendment is not public yet, so filtering must happen first even
    # though an amended form outranks an original at reconciliation.
    at_t1 = facts.reconcile(
        observations, view="public_as_of", knowledge_time=dt(2024, 3, 1)
    )
    assert at_t1.selected is not None
    assert at_t1.selected.value_raw == "100"
    assert at_t1.selected.key.assertion.filing_id == FILING
    # Nothing else is even eligible before the amendment is public.
    assert at_t1.conflicts == ()
    assert {item.key.assertion.filing_id for item in at_t1.excluded} == {
        FILING_AMENDED
    }
    assert len(at_t1.excluded) == 2

    # T2: after the amendment became public it wins, and the older eligible
    # observation is retained as a conflict.
    at_t2 = facts.reconcile(
        observations, view="public_as_of", knowledge_time=dt(2024, 6, 1)
    )
    assert at_t2.selected is not None
    assert at_t2.selected.value_raw == "120"
    assert at_t2.selected.key.assertion.filing_id == FILING_AMENDED
    assert at_t2.conflicts and all(item.conflict_flag for item in at_t2.conflicts)
    assert {item.value_raw for item in at_t2.conflicts} == {"100"}

    # Unknown public availability is excluded in public_as_of at every T, so it
    # can never win on system time alone.
    late = facts.reconcile(
        observations, view="public_as_of", knowledge_time=dt(2030, 1, 1)
    )
    assert late.selected.value_raw == "120"
    assert all(
        item.public_available_at is None for item in late.excluded
    )

    # The second mode is verified independently, on its own clock.
    replay_t1 = facts.reconcile(
        observations, view="system_replay", knowledge_time=dt(2024, 2, 15)
    )
    assert replay_t1.selected.value_raw == "100"
    replay_t2 = facts.reconcile(
        observations, view="system_replay", knowledge_time=dt(2024, 5, 5)
    )
    assert replay_t2.selected.value_raw == "120"
    # In replay the unverified observation is eligible but loses on precedence:
    # its public availability is unknown, which sorts before a known one.
    replay_late = facts.reconcile(
        observations, view="system_replay", knowledge_time=dt(2024, 6, 2)
    )
    assert replay_late.selected.value_raw == "120"
    assert unverified.key in {item.key for item in replay_late.conflicts}

    # A view is mandatory: there is no implicit default mode.
    with pytest.raises(ValueError, match="view"):
        facts.reconcile(observations, view="latest", knowledge_time=dt(2024, 6, 1))


# ═══════════════════════════════════════════════════════════════════════════════
# S6 / R2-1 — conflicting observations survive de-duplication and shuffling
# ═══════════════════════════════════════════════════════════════════════════════

def test_observation_conflicts_survive_dedup_and_shuffle():
    s = series()
    assertion = facts.assertion_key(s, FILING)
    at = dt(2024, 2, 1)

    first = facts.make_observation(
        assertion,
        entry("100"),
        public_available_at=at,
        system_from=at,
        evidence_id="ev-1",
    )
    # Same assertion, different value text: two observations, never one.
    second = facts.make_observation(
        assertion,
        entry("120"),
        public_available_at=at,
        system_from=at,
        evidence_id="ev-2",
    )
    duplicate = facts.make_observation(
        assertion,
        entry("100"),
        public_available_at=at,
        system_from=at,
        evidence_id="ev-1",
    )
    assert first.key.as_tuple() != second.key.as_tuple()
    assert first.key.as_tuple() == duplicate.key.as_tuple()
    assert first.key.source == facts.SOURCE_COMPANYFACTS

    deduped = facts.dedupe_observations([first, second, duplicate])
    assert len(deduped) == 2
    assert {item.value_raw for item in deduped} == {"100", "120"}

    # The same numeric value written differently is a different entry: the key
    # hashes the exact source text, not the parsed decimal.
    textual = facts.make_observation(
        assertion,
        entry("100.0"),
        public_available_at=at,
        system_from=at,
        evidence_id="ev-3",
    )
    assert textual.key.as_tuple() != first.key.as_tuple()
    assert textual.value_decimal == first.value_decimal
    assert len(facts.dedupe_observations([first, textual])) == 2

    # Selection is deterministic under every ingestion permutation and the
    # smallest entry hash wins the final tie-break.
    expected_hash = min(
        first.key.entry_hash, second.key.entry_hash, textual.key.entry_hash
    )
    outcomes = set()
    conflict_sets = set()
    for permutation in itertools.permutations([first, second, textual, duplicate]):
        result = facts.reconcile(
            permutation, view="public_as_of", knowledge_time=at
        )
        assert result.selected is not None
        outcomes.add(result.selected.key.as_tuple())
        conflict_sets.add(
            tuple(sorted(item.key.as_tuple() for item in result.conflicts))
        )
        assert all(item.conflict_flag for item in result.conflicts)
    assert len(outcomes) == 1
    assert len(conflict_sets) == 1
    assert next(iter(outcomes))[7] == expected_hash
    assert len(conflict_sets.pop()) == 2

    # Series grouping reconciles each grain independently.
    other_period = facts.make_observation(
        facts.assertion_key(series(period_id=PERIOD_OTHER), FILING),
        entry("7", start="2022-01-30", end="2023-01-28"),
        public_available_at=at,
        system_from=at,
        evidence_id="ev-4",
    )
    grouped = facts.reconcile_series(
        [first, second, other_period], view="public_as_of", knowledge_time=at
    )
    assert len(grouped) == 2
    assert grouped[s.as_tuple()].selected is not None
    assert grouped[s.as_tuple()].selected.value_raw in {"100", "120"}

    # A genuine key collision with different payloads is flagged, never hidden.
    collided = facts.Observation(
        key=first.key,
        value_raw="999",
        value_decimal=None,
        form_type="10-K",
        public_available_at=at,
        system_from=at,
        evidence_id="ev-collision",
    )
    survivors = facts.dedupe_observations([first, collided])
    assert len(survivors) == 1
    assert survivors[0].conflict_flag is True
