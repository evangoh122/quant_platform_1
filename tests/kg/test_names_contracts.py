"""Company-name precedence from SEC submissions (Sol R4 S5 / v4 §A)."""
from __future__ import annotations

import itertools
from datetime import date, datetime, timezone

import pytest

from sec_kg.contracts import names


def d(year: int, month: int, day: int) -> date:
    return date(year, month, day)


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0,
       second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def former(name: str, start: date, end: date, evidence: str) -> names.FormerName:
    return names.FormerName(
        name=name, from_date=start, to_date=end, evidence_id=evidence
    )


def snapshot(former_names=(), current="Gamma Corp", first_observed=None):
    return names.SubmissionsSnapshot(
        current_name=current,
        former_names=tuple(former_names),
        first_observed_at=first_observed or dt(2018, 1, 1),
        observed_at=dt(2018, 1, 1),
        evidence_id="ev-current",
    )


def test_submissions_name_intervals_gaps_overlap_date_boundaries():
    former_names = (
        former("Alpha Corp", d(2010, 1, 1), d(2012, 12, 31), "ev-1"),
        former("Beta Corp", d(2015, 1, 1), d(2017, 6, 30), "ev-2"),
    )
    facts_names = [
        names.FactsNameObservation(
            name="Gamma Holdings", observed_at=dt(2019, 5, 1), evidence_id="ev-facts"
        )
    ]
    history = names.build_name_history(snapshot(former_names), facts_names)

    by_name = {interval.name: interval for interval in history.intervals}
    # Inclusive source dates become half-open intervals: the last included day
    # is covered, the day after is not.
    assert by_name["Alpha Corp"].valid_from == dt(2010, 1, 1)
    assert by_name["Alpha Corp"].valid_to == dt(2013, 1, 1)
    assert by_name["Beta Corp"].valid_from == dt(2015, 1, 1)
    assert by_name["Beta Corp"].valid_to == dt(2017, 7, 1)
    # The current name starts exactly at the end of the last former name.
    assert by_name["Gamma Corp"].valid_from == dt(2017, 7, 1)
    assert by_name["Gamma Corp"].valid_to is None
    assert by_name["Alpha Corp"].source == names.NAME_SOURCE_FORMER
    assert by_name["Gamma Corp"].source == names.NAME_SOURCE_CURRENT

    # Boundary resolution, second precision on both sides of every edge.
    assert history.resolve(dt(2009, 12, 31, 23, 59, 59)) is None
    assert history.resolve(dt(2010, 1, 1)).name == "Alpha Corp"
    assert history.resolve(dt(2012, 12, 31, 23, 59, 59)).name == "Alpha Corp"
    # A gap between former names stays a gap: the current name is not
    # back-filled across it (S5: no unsupported coverage).
    assert history.resolve(dt(2013, 1, 1)) is None
    assert history.resolve(dt(2014, 12, 31)) is None
    assert history.resolve(dt(2015, 1, 1)).name == "Beta Corp"
    assert history.resolve(dt(2017, 6, 30, 23, 59, 59)).name == "Beta Corp"
    assert history.resolve(dt(2017, 7, 1)).name == "Gamma Corp"
    assert history.resolve(dt(2030, 1, 1)).name == "Gamma Corp"

    # Company-Facts entityName is observation-only: never a reconciled label.
    assert [item.name for item in history.observations] == ["Gamma Holdings"]
    assert history.observations[0].observed_at == dt(2019, 5, 1)
    for moment in (
        dt(2009, 12, 31),
        dt(2012, 6, 1),
        dt(2016, 1, 1),
        dt(2019, 5, 1),
        dt(2030, 1, 1),
    ):
        resolved = history.resolve(moment)
        assert resolved is None or resolved.name != "Gamma Holdings"
    assert names.observation_only_names(history) == history.observations

    # Overlapping former names resolve by rank then by smaller evidence id,
    # deterministically under every input permutation.
    overlapping = former_names + (
        former("Alpha LLC", d(2012, 1, 1), d(2012, 12, 31), "ev-0"),
    )
    outcomes = set()
    interval_orders = set()
    for permutation in itertools.permutations(overlapping):
        candidate = names.build_name_history(snapshot(permutation), facts_names)
        resolved = candidate.resolve(dt(2012, 6, 1))
        outcomes.add(None if resolved is None else resolved.name)
        interval_orders.add(
            tuple(
                (item.name, item.valid_from, item.valid_to)
                for item in candidate.intervals
            )
        )
    assert outcomes == {"Alpha LLC"}
    assert len(interval_orders) == 1
    # With a larger evidence id on the overlapping name the original wins.
    larger = former_names + (
        former("Alpha LLC", d(2012, 1, 1), d(2012, 12, 31), "ev-9"),
    )
    assert names.build_name_history(
        snapshot(larger), facts_names
    ).resolve(dt(2012, 6, 1)).name == "Alpha Corp"

    # Current name with no former names is valid from first observation only.
    no_former = names.build_name_history(
        snapshot((), current="Solo Inc", first_observed=dt(2020, 5, 1))
    )
    assert no_former.resolve(dt(2020, 4, 30)) is None
    assert no_former.resolve(dt(2020, 5, 1)).name == "Solo Inc"

    # Rank 1 is the strongest: when a former-name interval and the current name
    # overlap, the former name wins (v4 §A list order), and the resolution is
    # not decided by which interval happens to be listed first.
    overlapping_ranks = names.NameHistory(
        intervals=(
            names.NameInterval(
                name="Former Strong",
                valid_from=dt(2012, 1, 1),
                valid_to=dt(2013, 1, 1),
                source=names.NAME_SOURCE_FORMER,
                rank=names.RANK_FORMER,
                data_source="sec_edgar",
                evidence_id="ev-2",
            ),
            names.NameInterval(
                name="Current Weak",
                valid_from=dt(2012, 1, 1),
                valid_to=dt(2013, 1, 1),
                source=names.NAME_SOURCE_CURRENT,
                rank=names.RANK_CURRENT,
                data_source="sec_edgar",
                evidence_id="ev-1",
            ),
        )
    )
    assert names.resolve_name(overlapping_ranks, dt(2012, 6, 1)).name == (
        "Former Strong"
    )
    assert names.RANK_FORMER < names.RANK_CURRENT < names.RANK_OBSERVATION

    # Explicit inclusive -> half-open conversion, and invalid ranges rejected.
    start, end = names.inclusive_dates_to_half_open(d(2010, 1, 1), d(2012, 12, 31))
    assert (start, end) == (dt(2010, 1, 1), dt(2013, 1, 1))
    with pytest.raises(names.NameError):
        names.FormerName(
            name="Bad", from_date=d(2020, 1, 1), to_date=d(2019, 1, 1)
        )
    with pytest.raises(names.NameError):
        names.inclusive_dates_to_half_open(d(2020, 1, 1), d(2019, 12, 31))
    with pytest.raises(names.NameError):
        names.SubmissionsSnapshot(
            current_name="  ",
            former_names=(),
            first_observed_at=dt(2020, 1, 1),
            observed_at=dt(2020, 1, 1),
        )
