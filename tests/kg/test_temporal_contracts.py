"""Temporal contracts: immutable corrections and the two query modes.

Acceptance tests named by Codex Sol R4 (R3-7, S3).
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pytest

from sec_kg.contracts import temporal

ENTITY = "company:c1"
ATTRIBUTE = "name"


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0,
       second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def event(
    event_id: str,
    value: str,
    valid_from: datetime,
    valid_to,
    recorded_at: datetime,
    *,
    public=None,
    supersedes=None,
    attribute: str = ATTRIBUTE,
    entity_id: str = ENTITY,
    data_source: str = "sec_edgar",
) -> temporal.AttributeEvent:
    return temporal.AttributeEvent(
        event_id=event_id,
        entity_id=entity_id,
        attribute=attribute,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        recorded_at=recorded_at,
        data_source=data_source,
        public_available_at=public,
        supersedes_event_id=supersedes,
    )


def _split_universe():
    """Original belief plus one correction that splits it in two, plus an
    unrelated attribute that no correction touches."""
    original = event(
        "e1",
        "Old Co",
        dt(2010, 1, 1),
        dt(2020, 1, 1),
        dt(2010, 6, 1),
        public=dt(2010, 6, 1),
    )
    split_head = event(
        "c1",
        "Old Co",
        dt(2010, 1, 1),
        dt(2015, 1, 1),
        dt(2022, 3, 1),
        public=dt(2022, 3, 1),
        supersedes="e1",
    )
    split_tail = event(
        "c2",
        "Mid Co",
        dt(2015, 1, 1),
        dt(2020, 1, 1),
        dt(2022, 3, 1),
        public=dt(2022, 3, 1),
        supersedes="e1",
    )
    unrelated = event(
        "sic1",
        "3674",
        dt(2010, 1, 1),
        None,
        dt(2010, 6, 1),
        public=dt(2010, 6, 1),
        attribute="sic",
    )
    return [original, split_head, split_tail, unrelated]


# ═══════════════════════════════════════════════════════════════════════════════
# R3-7 — correction split: replay boundaries
# ═══════════════════════════════════════════════════════════════════════════════

def test_correction_split_replay_boundaries():
    events = _split_universe()
    original, split_head, split_tail, unrelated = events

    def replay(business, knowledge):
        return temporal.system_replay(
            events, ENTITY, business, knowledge, attribute=ATTRIBUTE
        )

    # Before the correction is recorded, the system still believes the original
    # single interval.
    before = replay(dt(2016, 6, 1), dt(2021, 1, 1))
    assert before is not None
    assert before.value == "Old Co"
    assert before.event_id == "e1"
    assert before.valid_to == dt(2020, 1, 1)

    # After the correction, both split pieces are beliefs.
    after_tail = replay(dt(2016, 6, 1), dt(2023, 1, 1))
    assert after_tail is not None
    assert after_tail.value == "Mid Co"
    assert after_tail.event_id == "c2"
    assert after_tail.valid_from == dt(2015, 1, 1)

    # The unaffected head piece is preserved after the correction.
    after_head = replay(dt(2012, 6, 1), dt(2023, 1, 1))
    assert after_head is not None
    assert after_head.value == "Old Co"
    assert after_head.event_id == "c1"
    # Deriving twice must not change any interval (immutability of the log).
    first = temporal.derive_system_intervals(events)
    second = temporal.derive_system_intervals(list(reversed(events)))
    assert [
        (item.event.event_id, item.system_from, item.system_to) for item in first
    ] == [(item.event.event_id, item.system_from, item.system_to) for item in second]

    # Half-open business boundaries.
    assert replay(dt(2015, 1, 1), dt(2023, 1, 1)).value == "Mid Co"
    assert replay(dt(2014, 12, 31, 23, 59, 59), dt(2023, 1, 1)).value == "Old Co"
    assert replay(dt(2020, 1, 1), dt(2023, 1, 1)) is None

    # Half-open system boundary: at exactly recorded_at the new pieces are
    # beliefs and the superseded event is not, and vice versa one second before.
    at_boundary = replay(dt(2016, 6, 1), dt(2022, 3, 1))
    assert at_boundary is not None and at_boundary.value == "Mid Co"
    just_before = replay(dt(2016, 6, 1), dt(2022, 2, 28, 23, 59, 59))
    assert just_before is not None and just_before.value == "Old Co"

    # Derived intervals are exact.
    derived = {item.event.event_id: item for item in first}
    assert derived["e1"].system_from == dt(2010, 6, 1)
    assert derived["e1"].system_to == dt(2022, 3, 1)
    assert derived["c1"].system_from == dt(2022, 3, 1)
    assert derived["c1"].system_to is None
    assert derived["c2"].system_to is None

    # An unrelated attribute is not disturbed by the correction.
    sic = temporal.system_replay(
        events, ENTITY, dt(2025, 1, 1), dt(2023, 1, 1), attribute="sic"
    )
    assert sic is not None and sic.value == "3674"

    # Equal-timestamp corrections are deterministic (input order irrelevant).
    simultaneous = [
        event(
            "x1",
            "A",
            dt(2010, 1, 1),
            dt(2020, 1, 1),
            dt(2010, 1, 1),
            public=dt(2010, 1, 1),
        ),
        event(
            "x2",
            "B",
            dt(2010, 1, 1),
            dt(2015, 1, 1),
            dt(2011, 1, 1),
            public=dt(2011, 1, 1),
            supersedes="x1",
        ),
        event(
            "x3",
            "C",
            dt(2015, 1, 1),
            dt(2020, 1, 1),
            dt(2011, 1, 1),
            public=dt(2011, 1, 1),
            supersedes="x1",
        ),
    ]
    outcomes = set()
    for permutation in itertools.permutations(simultaneous):
        resolved = temporal.system_replay(
            permutation, ENTITY, dt(2016, 6, 1), dt(2012, 1, 1), attribute=ATTRIBUTE
        )
        outcomes.add(None if resolved is None else resolved.event_id)
    assert len(outcomes) == 1

    # Half-open system intervals: a superseded event with one second of belief
    # is visible only inside that second.
    tiny = [
        event("t1", "old", dt(2010, 1, 1), dt(2020, 1, 1), dt(2010, 1, 1),
              public=dt(2010, 1, 1)),
        event("t2", "new", dt(2010, 1, 1), dt(2020, 1, 1), dt(2010, 1, 1, 0, 0, 1),
              public=dt(2010, 1, 1, 0, 0, 1), supersedes="t1"),
    ]
    assert temporal.system_replay(
        tiny, ENTITY, dt(2015, 1, 1), dt(2010, 1, 1), attribute=ATTRIBUTE
    ).event_id == "t1"
    assert temporal.system_replay(
        tiny, ENTITY, dt(2015, 1, 1), dt(2010, 1, 1, 0, 0, 1), attribute=ATTRIBUTE
    ).event_id == "t2"

    # Dangling and cyclic supersession are rejected outright.
    dangling = events + [
        event(
            "orphan",
            "X",
            dt(2010, 1, 1),
            dt(2020, 1, 1),
            dt(2023, 1, 1),
            public=dt(2023, 1, 1),
            supersedes="does-not-exist",
        )
    ]
    with pytest.raises(temporal.DanglingSupersessionError):
        temporal.derive_system_intervals(dangling)

    cycle = [
        event("a", "A", dt(2010, 1, 1), dt(2020, 1, 1), dt(2010, 1, 1),
              public=dt(2010, 1, 1), supersedes="b"),
        event("b", "B", dt(2010, 1, 1), dt(2020, 1, 1), dt(2011, 1, 1),
              public=dt(2011, 1, 1), supersedes="a"),
    ]
    with pytest.raises(temporal.SupersessionCycleError):
        temporal.derive_system_intervals(cycle)


# ═══════════════════════════════════════════════════════════════════════════════
# S3 — public supersession must not leak from the future
# ═══════════════════════════════════════════════════════════════════════════════

def test_public_view_supersession_without_future_leakage():
    original = event(
        "p1",
        "Old Co",
        dt(2010, 1, 1),
        dt(2020, 1, 1),
        dt(2010, 6, 1),
        public=dt(2010, 6, 1),
    )
    unverified = event(
        "u1",
        "Unverified Co",
        dt(2010, 1, 1),
        dt(2020, 1, 1),
        dt(2021, 6, 1),
        public=None,
        supersedes="p1",
    )
    future_correction = event(
        "p2",
        "Corrected Co",
        dt(2010, 1, 1),
        dt(2020, 1, 1),
        dt(2022, 1, 1),
        public=dt(2025, 1, 1),
        supersedes="p1",
    )
    events = [original, unverified, future_correction]

    # The correction is recorded but not yet public: the eligible predecessor
    # must still answer, and the future correction must not erase it.
    now = temporal.public_as_of(events, ENTITY, dt(2016, 6, 1), dt(2023, 1, 1),
                               attribute=ATTRIBUTE)
    assert now is not None
    assert now.value == "Old Co"
    assert now.event_id == "p1"

    # Filtering precedes supersession: at that knowledge time exactly the
    # original event is publicly eligible.
    visible = temporal.visible_intervals(events, ENTITY, "public_as_of",
                                         dt(2023, 1, 1), attribute=ATTRIBUTE)
    assert [item.event.event_id for item in visible] == ["p1"]
    # Unknown public availability is never eligible (R3-4).
    assert "u1" not in {item.event.event_id for item in visible}

    # Once the correction is public it supersedes.
    later = temporal.public_as_of(events, ENTITY, dt(2016, 6, 1), dt(2026, 1, 1),
                                 attribute=ATTRIBUTE)
    assert later is not None
    assert later.value == "Corrected Co"
    assert later.event_id == "p2"

    # The unverified-availability event is invisible in public_as_of at every
    # knowledge time, even after it was recorded.
    alone = [
        event(
            "u-only",
            "Unverified Co",
            dt(2010, 1, 1),
            dt(2020, 1, 1),
            dt(2021, 6, 1),
            public=None,
        )
    ]
    assert temporal.public_as_of(alone, ENTITY, dt(2016, 6, 1), dt(2030, 1, 1),
                                attribute=ATTRIBUTE) is None
    assert temporal.system_replay(alone, ENTITY, dt(2016, 6, 1), dt(2030, 1, 1),
                                 attribute=ATTRIBUTE).value == "Unverified Co"

    # The two modes genuinely differ for the same (business, knowledge) pair.
    replay = temporal.system_replay(events, ENTITY, dt(2016, 6, 1), dt(2023, 1, 1),
                                   attribute=ATTRIBUTE)
    assert replay is not None
    assert replay.value == "Corrected Co"
    assert replay.value != now.value

    # Business-time resolution still honours half-open intervals in the public
    # view (no leakage across the period end).
    assert temporal.public_as_of(events, ENTITY, dt(2020, 1, 1), dt(2026, 1, 1),
                                attribute=ATTRIBUTE) is None
    assert temporal.public_as_of(events, ENTITY, dt(2009, 12, 31), dt(2026, 1, 1),
                                attribute=ATTRIBUTE) is None

    # ── (a) A public correction trims an open-ended original ───────────────
    # e1 is open-ended from 2010 and was public in 2010; the correction e2
    # (public 2020) supersedes it with 2010-2015.  Inside 2015-2020 there is no
    # value any more, exactly as in system_replay: the corrected range must not
    # be resurrected just because e1's own public timestamp is older.
    opened = event(
        "q1",
        "Opened Co",
        dt(2010, 1, 1),
        None,
        dt(2010, 6, 1),
        public=dt(2010, 6, 1),
    )
    trimmed = event(
        "q2",
        "Trimmed Co",
        dt(2010, 1, 1),
        dt(2015, 1, 1),
        dt(2020, 1, 1),
        public=dt(2020, 1, 1),
        supersedes="q1",
    )
    trimmed_universe = [opened, trimmed]
    assert temporal.public_as_of(
        trimmed_universe, ENTITY, dt(2018, 6, 1), dt(2021, 1, 1),
        attribute=ATTRIBUTE,
    ) is None
    assert temporal.system_replay(
        trimmed_universe, ENTITY, dt(2018, 6, 1), dt(2021, 1, 1),
        attribute=ATTRIBUTE,
    ) is None
    # Inside the surviving range the eligible correction answers ...
    surviving = temporal.public_as_of(
        trimmed_universe, ENTITY, dt(2012, 6, 1), dt(2021, 1, 1),
        attribute=ATTRIBUTE,
    )
    assert surviving is not None and surviving.event_id == "q2"
    # ... and before the correction is public the original still answers
    # (filtering precedes supersession: no future leak in the other direction).
    before_public = temporal.public_as_of(
        trimmed_universe, ENTITY, dt(2018, 6, 1), dt(2019, 12, 31),
        attribute=ATTRIBUTE,
    )
    assert before_public is not None and before_public.event_id == "q1"

    # ── (b) The correction wins even when the corrected event was published
    # later: supersession is applied among eligible events, not by public
    # timestamp order.
    late_original = event(
        "r1",
        "Late Public Co",
        dt(2010, 1, 1),
        dt(2020, 1, 1),
        dt(2010, 6, 1),
        public=dt(2020, 9, 1),
    )
    earlier_correction = event(
        "r2",
        "Correction Wins Co",
        dt(2010, 1, 1),
        dt(2015, 1, 1),
        dt(2019, 1, 1),
        public=dt(2019, 1, 1),
        supersedes="r1",
    )
    inverted = [late_original, earlier_correction]
    correction = temporal.public_as_of(
        inverted, ENTITY, dt(2012, 6, 1), dt(2021, 1, 1), attribute=ATTRIBUTE
    )
    assert correction is not None
    assert correction.event_id == "r2"
    assert correction.value == "Correction Wins Co"
    assert [
        item.event.event_id
        for item in temporal.visible_intervals(
            inverted, ENTITY, "public_as_of", dt(2021, 1, 1), attribute=ATTRIBUTE
        )
    ] == ["r2"]
    replay_correction = temporal.system_replay(
        inverted, ENTITY, dt(2012, 6, 1), dt(2021, 1, 1), attribute=ATTRIBUTE
    )
    assert replay_correction is not None
    assert replay_correction.event_id == "r2"

    # Unknown views are rejected rather than silently defaulting.
    with pytest.raises(temporal.TemporalError):
        temporal.resolve(events, ENTITY, dt(2016, 6, 1), "latest", dt(2023, 1, 1),
                         attribute=ATTRIBUTE)


# ═══════════════════════════════════════════════════════════════════════════════
# Every event row carries a required, validated data_source
# ═══════════════════════════════════════════════════════════════════════════════

def test_attribute_event_requires_a_valid_data_source():
    with pytest.raises(TypeError):
        temporal.AttributeEvent(
            event_id="no-source",
            entity_id=ENTITY,
            attribute=ATTRIBUTE,
            value="X",
            valid_from=dt(2010, 1, 1),
            valid_to=None,
            recorded_at=dt(2010, 6, 1),
        )
    for broken in (None, "", "sec-edgar", "Massive", "edgar"):
        with pytest.raises(temporal.IntervalError):
            event("bad-source", "X", dt(2010, 1, 1), None, dt(2010, 6, 1),
                  data_source=broken)
    # A submissions-sourced name and a derived classification are both allowed
    # codes of the one vocabulary.
    assert event("ok-1", "X", dt(2010, 1, 1), None, dt(2010, 6, 1),
                 data_source="sec_edgar").data_source == "sec_edgar"
    assert event("ok-2", "X", dt(2010, 1, 1), None, dt(2010, 6, 1),
                 data_source="derived").data_source == "derived"
