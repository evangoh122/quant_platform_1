"""Tests for the static NYSE calendar and weekend-window helpers."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from config.market_calendar import (
    CALENDAR_END,
    CALENDAR_START,
    MarketCalendarError,
    check_calendar_file,
    early_close_dates,
    full_closure_dates,
    is_trading_day,
    last_close_before,
    next_open_after,
    weekend_window,
)

NY = ZoneInfo("America/New_York")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CALENDAR_YAML = _REPO_ROOT / "config" / "xnys_holidays.yaml"


def _et(value: datetime) -> datetime:
    return value.astimezone(NY)


def _assert_et(value: datetime, *parts: int) -> None:
    assert _et(value) == datetime(*parts, tzinfo=NY)


def test_good_friday_window_starts_thursday_close():
    # 2026-04-03 is Good Friday (NYSE closed); the break starts with the
    # Thursday 2026-04-02 16:00 ET close and ends Monday 2026-04-06 09:30 ET.
    start, end = weekend_window(date(2026, 4, 3))
    _assert_et(start, 2026, 4, 2, 16, 0)
    _assert_et(end, 2026, 4, 6, 9, 30)
    assert start == datetime(2026, 4, 2, 20, 0, tzinfo=timezone.utc)


def test_labor_day_window_ends_tuesday_open():
    # Friday 2026-09-04 -> Monday 2026-09-07 is Labor Day -> Tuesday open.
    start, end = weekend_window(date(2026, 9, 4))
    _assert_et(start, 2026, 9, 4, 16, 0)
    _assert_et(end, 2026, 9, 8, 9, 30)
    assert end == datetime(2026, 9, 8, 13, 30, tzinfo=timezone.utc)


def test_regular_weekend_window():
    start, end = weekend_window(date(2026, 1, 9))
    _assert_et(start, 2026, 1, 9, 16, 0)
    _assert_et(end, 2026, 1, 12, 9, 30)


def test_dst_spring_forward_uses_est_then_edt():
    # DST starts Sunday 2026-03-08: Friday close is EST, Monday open is EDT.
    start, end = weekend_window(date(2026, 3, 6))
    _assert_et(start, 2026, 3, 6, 16, 0)
    _assert_et(end, 2026, 3, 9, 9, 30)
    assert _et(start).utcoffset().total_seconds() == -5 * 3600
    assert _et(end).utcoffset().total_seconds() == -4 * 3600
    assert start == datetime(2026, 3, 6, 21, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 3, 9, 13, 30, tzinfo=timezone.utc)


def test_dst_fall_back_uses_edt_then_est():
    # DST ends Sunday 2026-11-01: Friday close is EDT, Monday open is EST.
    start, end = weekend_window(date(2026, 10, 30))
    _assert_et(start, 2026, 10, 30, 16, 0)
    _assert_et(end, 2026, 11, 2, 9, 30)
    assert _et(start).utcoffset().total_seconds() == -4 * 3600
    assert _et(end).utcoffset().total_seconds() == -5 * 3600
    assert start == datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)


def test_day_after_thanksgiving_is_1300_early_close():
    start, end = weekend_window(date(2026, 11, 27))
    _assert_et(start, 2026, 11, 27, 13, 0)
    _assert_et(end, 2026, 11, 30, 9, 30)
    assert start == datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)


def test_christmas_eve_early_close_then_monday_open():
    # Christmas Day 2026 is Friday; Dec 24 is a 13:00 early close and the next
    # open is Monday 2026-12-28.
    start, end = weekend_window(date(2026, 12, 25))
    _assert_et(start, 2026, 12, 24, 13, 0)
    _assert_et(end, 2026, 12, 28, 9, 30)


def test_observed_friday_holiday_uses_thursday_close():
    # July 4 2026 is Saturday, so Friday 2026-07-03 is the observed full
    # closure; the window must start on Thursday 2026-07-02.
    assert date(2026, 7, 3) in full_closure_dates()
    assert date(2026, 7, 3) not in early_close_dates()
    start, end = weekend_window(date(2026, 7, 3))
    _assert_et(start, 2026, 7, 2, 16, 0)
    _assert_et(end, 2026, 7, 6, 9, 30)


def test_new_years_day_on_saturday_is_not_observed():
    assert date(2021, 12, 31) not in full_closure_dates()
    assert date(2022, 1, 1) not in full_closure_dates()
    assert is_trading_day(date(2021, 12, 31)) is True
    start, end = weekend_window(date(2021, 12, 31))
    _assert_et(start, 2021, 12, 31, 16, 0)
    _assert_et(end, 2022, 1, 3, 9, 30)


def test_juneteenth_rules():
    # First observed by the NYSE in 2022; 2022-06-19 was a Sunday.
    assert date(2022, 6, 20) in full_closure_dates()
    assert is_trading_day(date(2021, 6, 18)) is True
    assert date(2027, 6, 18) in full_closure_dates()  # Saturday -> Friday


def test_special_closures_are_included():
    for closed in (
        date(2001, 9, 11),
        date(2001, 9, 14),
        date(2004, 6, 11),
        date(2007, 1, 2),
        date(2012, 10, 30),
        date(2018, 12, 5),
        date(2025, 1, 9),
    ):
        assert closed in full_closure_dates()
        assert is_trading_day(closed) is False
    assert is_trading_day(date(2001, 9, 17)) is True


def test_static_calendar_matches_rule_derivation():
    assert check_calendar_file() == []


def test_calendar_yaml_covers_range_and_cites_rules():
    document = yaml.safe_load(_CALENDAR_YAML.read_text(encoding="utf-8"))
    assert document["coverage"]["start"] == CALENDAR_START.isoformat()
    assert document["coverage"]["end"] == CALENDAR_END.isoformat()
    rules = {rule["id"]: rule for rule in document["rules"]}
    for rule_id in (
        "good_friday",
        "day_after_thanksgiving",
        "independence_day_eve",
        "christmas_eve",
    ):
        assert rule_id in rules
        assert rules[rule_id]["source"]
    good_friday = [
        entry
        for entry in document["full_closures"]
        if entry["date"] == "2026-04-03"
    ]
    assert good_friday and good_friday[0]["rule"] == "good_friday"


def test_weekend_window_rejects_non_friday():
    with pytest.raises(MarketCalendarError, match="Friday"):
        weekend_window(date(2026, 1, 10))


def test_out_of_coverage_is_rejected():
    with pytest.raises(MarketCalendarError, match="outside calendar coverage"):
        last_close_before(date(1999, 12, 31))
    with pytest.raises(MarketCalendarError, match="outside calendar coverage"):
        next_open_after(date(2036, 1, 4))


def test_last_close_before_is_strict():
    assert last_close_before("2026-01-09T16:00:00-05:00") == datetime(
        2026, 1, 8, 21, 0, tzinfo=timezone.utc
    )
    assert last_close_before("2026-01-09T16:00:01-05:00") == datetime(
        2026, 1, 9, 21, 0, tzinfo=timezone.utc
    )


def test_next_open_after_is_strict():
    assert next_open_after("2026-01-12T09:30:00-05:00") == datetime(
        2026, 1, 13, 14, 30, tzinfo=timezone.utc
    )
    assert next_open_after("2026-01-12T09:29:59-05:00") == datetime(
        2026, 1, 12, 14, 30, tzinfo=timezone.utc
    )


def test_naive_datetime_is_interpreted_as_new_york():
    start = last_close_before(datetime(2026, 4, 3, 0, 0))
    _assert_et(start, 2026, 4, 2, 16, 0)


def test_weekend_has_no_session():
    assert is_trading_day(date(2026, 1, 10)) is False
    assert is_trading_day(date(2026, 1, 11)) is False


def test_early_close_date_is_a_trading_day():
    assert is_trading_day(date(2026, 11, 27)) is True
    assert is_trading_day(date(2026, 12, 24)) is True
