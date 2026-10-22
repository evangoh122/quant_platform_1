"""NYSE trading calendar and weekend-window helpers.

The calendar is **static data** (``config/xnys_holidays.yaml``) covering
2000-01-01 through 2035-12-31.  The file is generated from the published NYSE
rules below (``python -m config.market_calendar --write``) and checked for
drift in CI/maintenance (``python -m config.market_calendar --check``).

Rules implemented (NYSE Rule 7.2 "Trading Days" and the NYSE trading-hours
calendar at https://www.nyse.com/markets/hours-calendars):

* New Year's Day — January 1.  When it falls on Sunday the market is closed
  Monday; when it falls on Saturday there is **no** holiday (the preceding
  Friday is a full session).
* Martin Luther King, Jr. Day — third Monday in January.
* Washington's Birthday — third Monday in February.
* Good Friday — the Friday before Easter Sunday.
* Memorial Day — last Monday in May.
* Juneteenth National Independence Day — June 19, first observed by the NYSE
  in 2022; Saturday to Friday, Sunday to Monday.
* Independence Day — July 4; Saturday to Friday, Sunday to Monday.
* Labor Day — first Monday in September.
* Thanksgiving Day — fourth Thursday in November.
* Christmas Day — December 25; Saturday to Friday, Sunday to Monday.

Recurring early closes (13:00 America/New_York):

* the day after Thanksgiving;
* July 3, when it is a trading day (the eve of Independence Day);
* December 24, when it is a trading day (Christmas Eve).

Ad-hoc full closures in the covered window (NYSE announcements) are listed
separately in the YAML and are never derived from a rule: the September 11
attacks (2001-09-11..14), national days of mourning (2004-06-11, 2007-01-02,
2018-12-05, 2025-01-09) and Hurricane Sandy (2012-10-29..30).

Public API
----------
``last_close_before(ts)`` and ``next_open_after(ts)`` return timezone-aware
UTC ``datetime`` values.  ``weekend_window(friday)`` returns
``(start_utc, end_utc)``: the last regular-session close before the weekend
break and the next regular-session open after it.

Inputs must carry a timezone: a naive ``datetime`` or an ISO-8601 string
without a UTC offset raises :class:`MarketCalendarError` (a ``ValueError``)
instead of being silently interpreted in some zone.  A ``date`` is the one
exception and means 00:00 America/New_York on that date, because "the
weekend beginning on this Friday" has no clock time.

Rule provenance, coverage and known limits
------------------------------------------
Full closures are derived from NYSE Rule 7.2 for the whole 2000-2035 window and
drift-checked against the static file.  The recurring early-close rules
(day after Thanksgiving, Independence Day eve, Christmas Eve) are the modern
NYSE trading-hours rules; this module asserts them from **2013-01-01 onward**.

For 2000-2012 the file applies one documented historical July rule: when July 4
falls on a Thursday the 13:00 close is the following **Friday, July 5**, not
Wednesday July 3 (2002 is the only such year inside the coverage).  The
pre-2013 Christmas behaviour could **not** be verified offline against the
calendar's cited source (the NYSE trading-hours page does not publish the
pre-2013 session schedule), so this module makes no claim about it: the
December-24 early closes before 2013 stay in the file as best-effort entries
and are flagged in the YAML rule list as unverified.  Treat a weekend window
in 2000-2012 whose start or end depends on a December early close as
approximate until an owner verifies the primary source (for example whether
2003-12-26 rather than 2003-12-24 was the 13:00 session).

The module is pure: no network, no pandas, no DuckDB.  It only reads the
checked-in YAML (via ``zoneinfo`` for DST).
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union
from zoneinfo import ZoneInfo

import yaml

DEFAULT_PATH = Path(__file__).with_name("xnys_holidays.yaml")

NY = ZoneInfo("America/New_York")
UTC = timezone.utc

OPEN_TIME = time(9, 30)
CLOSE_TIME = time(16, 0)
EARLY_CLOSE_TIME = time(13, 0)

CALENDAR_START = date(2000, 1, 1)
CALENDAR_END = date(2035, 12, 31)

#: Maximum number of calendar days scanned by the forward/backward searches.
_MAX_SCAN_DAYS = 40

#: NYSE ad-hoc closures inside the covered window (press releases).
SPECIAL_CLOSURES: Tuple[Tuple[date, str, str], ...] = (
    (
        date(2001, 9, 11),
        "September 11 attacks (day 1)",
        "NYSE closed 2001-09-11 through 2001-09-14; reopened 2001-09-17",
    ),
    (
        date(2001, 9, 12),
        "September 11 attacks (day 2)",
        "NYSE closed 2001-09-11 through 2001-09-14; reopened 2001-09-17",
    ),
    (
        date(2001, 9, 13),
        "September 11 attacks (day 3)",
        "NYSE closed 2001-09-11 through 2001-09-14; reopened 2001-09-17",
    ),
    (
        date(2001, 9, 14),
        "September 11 attacks (day 4)",
        "NYSE closed 2001-09-11 through 2001-09-14; reopened 2001-09-17",
    ),
    (
        date(2004, 6, 11),
        "National day of mourning for Ronald Reagan",
        "NYSE announcement, 2004-06-09",
    ),
    (
        date(2007, 1, 2),
        "National day of mourning for Gerald Ford",
        "NYSE announcement, 2006-12-29",
    ),
    (
        date(2012, 10, 29),
        "Hurricane Sandy (day 1)",
        "NYSE closed 2012-10-29 and 2012-10-30",
    ),
    (
        date(2012, 10, 30),
        "Hurricane Sandy (day 2)",
        "NYSE closed 2012-10-29 and 2012-10-30",
    ),
    (
        date(2018, 12, 5),
        "National day of mourning for George H. W. Bush",
        "NYSE announcement, 2018-12-02",
    ),
    (
        date(2025, 1, 9),
        "National day of mourning for Jimmy Carter",
        "NYSE announcement, 2024-12-30",
    ),
)

_RULES: Tuple[Tuple[str, str, str], ...] = (
    (
        "new_years_day",
        "January 1; Sunday to Monday, Saturday not observed",
        "NYSE Rule 7.2",
    ),
    ("martin_luther_king_day", "third Monday in January", "NYSE Rule 7.2"),
    ("washingtons_birthday", "third Monday in February", "NYSE Rule 7.2"),
    ("good_friday", "Friday before Easter Sunday", "NYSE Rule 7.2"),
    ("memorial_day", "last Monday in May", "NYSE Rule 7.2"),
    (
        "juneteenth",
        "June 19 from 2022; Saturday to Friday, Sunday to Monday",
        "NYSE Rule 7.2 (2022 amendment)",
    ),
    (
        "independence_day",
        "July 4; Saturday to Friday, Sunday to Monday",
        "NYSE Rule 7.2",
    ),
    ("labor_day", "first Monday in September", "NYSE Rule 7.2"),
    ("thanksgiving_day", "fourth Thursday in November", "NYSE Rule 7.2"),
    (
        "christmas_day",
        "December 25; Saturday to Friday, Sunday to Monday",
        "NYSE Rule 7.2",
    ),
    (
        "day_after_thanksgiving",
        "early close 13:00 the Friday after Thanksgiving",
        "NYSE Rule 7.2; NYSE trading hours",
    ),
    (
        "independence_day_eve",
        "early close 13:00 on July 3 when it is a trading day (from 2013; "
        "before 2013 a Thursday July 4 moved the early close to Friday July 5)",
        "NYSE trading hours",
    ),
    (
        "christmas_eve",
        "early close 13:00 on December 24 when it is a trading day "
        "(2013+; pre-2013 entries are unverified best-effort)",
        "NYSE trading hours",
    ),
)


class MarketCalendarError(ValueError):
    """Raised for malformed calendar data or out-of-coverage queries."""


TimestampLike = Union[datetime, date, str]


@dataclass(frozen=True)
class _Calendar:
    coverage_start: date
    coverage_end: date
    rule_closures: Mapping[date, str]
    special_closures: Mapping[date, str]
    early_closes: Mapping[date, str]
    path: Path

    @property
    def full_closures(self) -> Mapping[date, str]:
        merged: Dict[date, str] = dict(self.rule_closures)
        merged.update(self.special_closures)
        return merged


# ---------------------------------------------------------------------------
# Rule derivation (used to build/check the static YAML; not used at runtime)
# ---------------------------------------------------------------------------

def easter_sunday(year: int) -> date:
    """Return Easter Sunday for *year* (anonymous Gregorian algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed_fixed(
    year: int, month: int, day: int, *, saturday_observed: bool
) -> Optional[date]:
    fixed = date(year, month, day)
    if fixed.weekday() == 5:  # Saturday
        if not saturday_observed:
            return None
        return fixed - timedelta(days=1)
    if fixed.weekday() == 6:  # Sunday
        return fixed + timedelta(days=1)
    return fixed


def derive_full_closures(
    start: date = CALENDAR_START, end: date = CALENDAR_END
) -> Dict[date, str]:
    """Derive recurring NYSE full closures for ``[start, end]``.

    Ad-hoc closures are intentionally excluded; they are static data.
    """
    if end < start:
        raise MarketCalendarError(f"end {end} precedes start {start}")
    out: Dict[date, str] = {}
    for year in range(start.year, end.year + 1):
        candidates: List[Tuple[Optional[date], str]] = [
            (
                _observed_fixed(year, 1, 1, saturday_observed=False),
                "New Year's Day",
            ),
            (_nth_weekday(year, 1, 0, 3), "Martin Luther King, Jr. Day"),
            (_nth_weekday(year, 2, 0, 3), "Washington's Birthday"),
            (easter_sunday(year) - timedelta(days=2), "Good Friday"),
            (_last_weekday(year, 5, 0), "Memorial Day"),
            (
                _observed_fixed(year, 6, 19, saturday_observed=True)
                if year >= 2022
                else None,
                "Juneteenth National Independence Day",
            ),
            (
                _observed_fixed(year, 7, 4, saturday_observed=True),
                "Independence Day",
            ),
            (_nth_weekday(year, 9, 0, 1), "Labor Day"),
            (_nth_weekday(year, 11, 3, 4), "Thanksgiving Day"),
            (
                _observed_fixed(year, 12, 25, saturday_observed=True),
                "Christmas Day",
            ),
        ]
        for observed, name in candidates:
            if observed is not None and start <= observed <= end:
                out[observed] = name
    for closed, name, _source in SPECIAL_CLOSURES:
        if start <= closed <= end:
            out[closed] = name
    return out


def derive_early_closes(
    start: date = CALENDAR_START, end: date = CALENDAR_END
) -> Dict[date, str]:
    """Derive recurring 13:00 NYSE early closes for ``[start, end]``.

    July rule: from 2013 the early close is July 3 (the eve).  Before 2013,
    when July 4 fell on a Thursday the 13:00 close was the following Friday,
    July 5 — see the module docstring for the documented range and the
    unverified pre-2013 December behaviour.
    """
    if end < start:
        raise MarketCalendarError(f"end {end} precedes start {start}")
    closures = derive_full_closures(start, end)
    out: Dict[date, str] = {}
    for year in range(start.year, end.year + 1):
        thanksgiving = _nth_weekday(year, 11, 3, 4)
        july_fourth = date(year, 7, 4)
        if year < 2013 and july_fourth.weekday() == 3:  # Thursday
            july_eve = date(year, 7, 5)
        else:
            july_eve = date(year, 7, 3)
        candidates = [
            (thanksgiving + timedelta(days=1), "Day after Thanksgiving"),
            (july_eve, "Independence Day eve"),
            (date(year, 12, 24), "Christmas Eve"),
        ]
        for day, name in candidates:
            if not (start <= day <= end):
                continue
            if day.weekday() >= 5:
                continue
            if day in closures:
                continue
            out[day] = name
    return out


# ---------------------------------------------------------------------------
# Static calendar loading
# ---------------------------------------------------------------------------

def _parse_date(value: object, source: Path, key: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise MarketCalendarError(f"{source}: {key} must be a 'YYYY-MM-DD' string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MarketCalendarError(
            f"{source}: {key} must be a valid date, got {value!r}"
        ) from exc


def _parse_time(value: object, source: Path, key: str, expected: time) -> time:
    if not isinstance(value, str):
        raise MarketCalendarError(f"{source}: {key} must be an 'HH:MM' string")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise MarketCalendarError(
            f"{source}: {key} must be a valid time, got {value!r}"
        ) from exc
    if parsed != expected:
        raise MarketCalendarError(
            f"{source}: {key} must be {expected.strftime('%H:%M')}, got {value!r}"
        )
    return parsed


@lru_cache(maxsize=8)
def _load_calendar_cached(path_text: str) -> _Calendar:
    path = Path(path_text)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MarketCalendarError(
            f"cannot read NYSE calendar at {path}: {exc.strerror or exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise MarketCalendarError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(document, Mapping):
        raise MarketCalendarError(f"{path}: document must be a mapping")

    coverage = document.get("coverage")
    if not isinstance(coverage, Mapping):
        raise MarketCalendarError(f"{path}: 'coverage' must be a mapping")
    coverage_start = _parse_date(coverage.get("start"), path, "coverage.start")
    coverage_end = _parse_date(coverage.get("end"), path, "coverage.end")
    if coverage_end < coverage_start:
        raise MarketCalendarError(f"{path}: coverage end precedes coverage start")

    regular = document.get("regular_session")
    if not isinstance(regular, Mapping):
        raise MarketCalendarError(f"{path}: 'regular_session' must be a mapping")
    _parse_time(regular.get("open"), path, "regular_session.open", OPEN_TIME)
    _parse_time(regular.get("close"), path, "regular_session.close", CLOSE_TIME)
    early = document.get("early_close")
    if not isinstance(early, Mapping):
        raise MarketCalendarError(f"{path}: 'early_close' must be a mapping")
    _parse_time(early.get("close"), path, "early_close.close", EARLY_CLOSE_TIME)

    def parse_entries(section: str, *, require_close: bool) -> Dict[date, str]:
        raw = document.get(section)
        if raw is None:
            return {}
        if not isinstance(raw, list):
            raise MarketCalendarError(f"{path}: '{section}' must be a list")
        parsed: Dict[date, str] = {}
        for index, entry in enumerate(raw):
            key = f"{section}[{index}]"
            if not isinstance(entry, Mapping):
                raise MarketCalendarError(f"{path}: {key} must be a mapping")
            day = _parse_date(entry.get("date"), path, f"{key}.date")
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                raise MarketCalendarError(f"{path}: {key}.name must be a non-empty string")
            if not (coverage_start <= day <= coverage_end):
                raise MarketCalendarError(
                    f"{path}: {key}.date {day} is outside the declared coverage"
                )
            if day in parsed:
                raise MarketCalendarError(f"{path}: {key}.date duplicates {day}")
            parsed[day] = name.strip()
            if require_close:
                _parse_time(
                    entry.get("close"), path, f"{key}.close", EARLY_CLOSE_TIME
                )
        return parsed

    rule_closures = parse_entries("full_closures", require_close=False)
    special_closures = parse_entries("special_closures", require_close=False)
    early_closes = parse_entries("early_closes", require_close=True)

    overlap = set(rule_closures) & set(special_closures)
    if overlap:
        raise MarketCalendarError(
            f"{path}: date(s) listed as both rule and special closure: {sorted(overlap)}"
        )
    for day in early_closes:
        if day in rule_closures or day in special_closures:
            raise MarketCalendarError(
                f"{path}: {day} is both a full closure and an early close"
            )

    return _Calendar(
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        rule_closures=rule_closures,
        special_closures=special_closures,
        early_closes=early_closes,
        path=path,
    )


def _calendar(path: str | Path | None = None) -> _Calendar:
    if path is None:
        configured = os.getenv("XNYS_HOLIDAYS_YAML")
        resolved = Path(configured) if configured else DEFAULT_PATH
    else:
        resolved = Path(path)
    return _load_calendar_cached(str(resolved))


def full_closure_dates(path: str | Path | None = None) -> frozenset[date]:
    """Return every full-closure date (rules + ad-hoc) in the static file."""
    return frozenset(_calendar(path).full_closures)


def early_close_dates(path: str | Path | None = None) -> frozenset[date]:
    """Return every 13:00 early-close date in the static file."""
    return frozenset(_calendar(path).early_closes)


def _ensure_coverage(day: date, calendar: _Calendar) -> None:
    if not (calendar.coverage_start <= day <= calendar.coverage_end):
        raise MarketCalendarError(
            f"{day} is outside calendar coverage "
            f"{calendar.coverage_start}..{calendar.coverage_end} ({calendar.path})"
        )


def is_trading_day(day: date, path: str | Path | None = None) -> bool:
    """Return True when *day* is a regular or early-close NYSE session."""
    calendar = _calendar(path)
    _ensure_coverage(day, calendar)
    return day.weekday() < 5 and day not in calendar.full_closures


def _session_open(day: date, calendar: _Calendar) -> Optional[datetime]:
    if not is_trading_day(day, calendar.path):
        return None
    return datetime.combine(day, OPEN_TIME, tzinfo=NY)


def _session_close(day: date, calendar: _Calendar) -> Optional[datetime]:
    if not is_trading_day(day, calendar.path):
        return None
    close = EARLY_CLOSE_TIME if day in calendar.early_closes else CLOSE_TIME
    return datetime.combine(day, close, tzinfo=NY)


def _coerce_to_ny(ts: TimestampLike) -> datetime:
    if isinstance(ts, datetime):
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise MarketCalendarError(
                f"naive datetime {ts!r} is rejected; pass a timezone-aware "
                "datetime or a date"
            )
        return ts.astimezone(NY)
    if isinstance(ts, date):
        return datetime.combine(ts, time(0, 0), tzinfo=NY)
    if isinstance(ts, str):
        raw = ts.strip()
        if not raw:
            raise MarketCalendarError("empty timestamp string")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise MarketCalendarError(
                f"cannot parse timestamp {ts!r}; use ISO-8601 with a UTC offset"
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise MarketCalendarError(
                f"timestamp {ts!r} has no UTC offset; append one (for example "
                "'-05:00', '+00:00' or 'Z') or pass a date"
            )
        return parsed.astimezone(NY)
    raise TypeError(
        f"ts must be a datetime, date or ISO-8601 string, got {type(ts).__name__}"
    )


def last_close_before(
    ts: TimestampLike, path: str | Path | None = None
) -> datetime:
    """Return the most recent regular-session close strictly before *ts* (UTC)."""
    calendar = _calendar(path)
    moment_ny = _coerce_to_ny(ts)
    moment_utc = moment_ny.astimezone(UTC)
    _ensure_coverage(moment_ny.date(), calendar)
    day = moment_ny.date()
    for _ in range(_MAX_SCAN_DAYS):
        close_ny = _session_close(day, calendar)
        if close_ny is not None:
            close_utc = close_ny.astimezone(UTC)
            if close_utc < moment_utc:
                return close_utc
        day -= timedelta(days=1)
        if day < calendar.coverage_start:
            break
    raise MarketCalendarError(
        f"no regular-session close within {_MAX_SCAN_DAYS} days before {ts!r}"
    )


def next_open_after(
    ts: TimestampLike, path: str | Path | None = None
) -> datetime:
    """Return the earliest regular-session open strictly after *ts* (UTC)."""
    calendar = _calendar(path)
    moment_ny = _coerce_to_ny(ts)
    moment_utc = moment_ny.astimezone(UTC)
    _ensure_coverage(moment_ny.date(), calendar)
    day = moment_ny.date()
    for _ in range(_MAX_SCAN_DAYS):
        open_ny = _session_open(day, calendar)
        if open_ny is not None:
            open_utc = open_ny.astimezone(UTC)
            if open_utc > moment_utc:
                return open_utc
        day += timedelta(days=1)
        if day > calendar.coverage_end:
            break
    raise MarketCalendarError(
        f"no regular-session open within {_MAX_SCAN_DAYS} days after {ts!r}"
    )


def weekend_window(
    friday: TimestampLike, path: str | Path | None = None
) -> Tuple[datetime, datetime]:
    """Return ``(start_utc, end_utc)`` for the weekend beginning on *friday*.

    ``start_utc`` is the last regular-session close before the break and
    ``end_utc`` is the next regular-session open after it.  A Friday holiday
    (Good Friday, July 4 observed, Christmas observed) therefore starts the
    window on Thursday; a Monday holiday ends it on Tuesday.
    """
    calendar = _calendar(path)
    day = _coerce_to_ny(friday).date()
    if day.weekday() != 4:
        raise MarketCalendarError(
            f"weekend_window expects a Friday date, got {day} ({day.strftime('%A')})"
        )
    anchor = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=NY)
    start = last_close_before(anchor, calendar.path)
    end = next_open_after(start, calendar.path)
    return start, end


def check_calendar_file(path: str | Path | None = None) -> List[str]:
    """Compare the static file with the rule-derived calendar.

    Returns a list of human-readable discrepancies (empty means consistent).
    Ad-hoc special closures are excluded from the comparison because they
    cannot be derived from a rule.
    """
    calendar = _calendar(path)
    special = set(calendar.special_closures)
    derived_closures = {
        day: name
        for day, name in derive_full_closures(
            calendar.coverage_start, calendar.coverage_end
        ).items()
        if day not in special
    }
    derived_early = derive_early_closes(
        calendar.coverage_start, calendar.coverage_end
    )

    problems: List[str] = []
    static_days = set(calendar.rule_closures)
    derived_days = set(derived_closures)
    for day in sorted(derived_days - static_days):
        problems.append(
            f"missing from full_closures: {day} ({derived_closures[day]})"
        )
    for day in sorted(static_days - derived_days):
        problems.append(
            f"not produced by any rule: {day} ({calendar.rule_closures[day]})"
        )
    for day in sorted(static_days & derived_days):
        if calendar.rule_closures[day] != derived_closures[day]:
            problems.append(
                f"name mismatch on {day}: static {calendar.rule_closures[day]!r} "
                f"vs derived {derived_closures[day]!r}"
            )

    static_early = set(calendar.early_closes)
    derived_early_days = set(derived_early)
    for day in sorted(derived_early_days - static_early):
        problems.append(
            f"missing from early_closes: {day} ({derived_early[day]})"
        )
    for day in sorted(static_early - derived_early_days):
        problems.append(
            f"not produced by any early-close rule: "
            f"{day} ({calendar.early_closes[day]})"
        )
    return problems


# ---------------------------------------------------------------------------
# YAML rendering / CLI
# ---------------------------------------------------------------------------

def render_calendar_yaml(
    start: date = CALENDAR_START, end: date = CALENDAR_END
) -> str:
    """Render the complete static calendar YAML for ``[start, end]``."""
    closures = derive_full_closures(start, end)
    special = {day for day, _name, _source in SPECIAL_CLOSURES}
    rule_closures = {day: name for day, name in closures.items() if day not in special}
    early = derive_early_closes(start, end)

    def quoted(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines: List[str] = []
    lines.append("# config/xnys_holidays.yaml — static NYSE calendar, 2000-2035.")
    lines.append("#")
    lines.append("# GENERATED FILE — do not edit by hand. Regenerate with:")
    lines.append("#   python -m config.market_calendar --write")
    lines.append("# and verify with:")
    lines.append("#   python -m config.market_calendar --check")
    lines.append("#")
    lines.append("# Full closures are rule-derived from NYSE Rule 7.2 and the NYSE")
    lines.append("# trading-hours calendar (https://www.nyse.com/markets/hours-calendars):")
    for rule_id, description, source in _RULES:
        lines.append(f"#   {rule_id}: {description} [{source}]")
    lines.append("#")
    lines.append("# Ad-hoc closures (attacks, weather, national days of mourning) are")
    lines.append("# listed under special_closures with their announcement citation and")
    lines.append("# are NOT rule-derived.")
    lines.append("version: 1")
    lines.append("timezone: America/New_York")
    lines.append("coverage:")
    lines.append(f"  start: {quoted(start.isoformat())}")
    lines.append(f"  end: {quoted(end.isoformat())}")
    lines.append("regular_session:")
    lines.append(f"  open: {quoted('09:30')}")
    lines.append(f"  close: {quoted('16:00')}")
    lines.append("early_close:")
    lines.append(f"  close: {quoted('13:00')}")
    lines.append("")
    lines.append("rules:")
    for rule_id, description, source in _RULES:
        lines.append(f"  - id: {rule_id}")
        lines.append(f"    description: {quoted(description)}")
        lines.append(f"    source: {quoted(source)}")
    lines.append("")
    lines.append("full_closures:")
    for day in sorted(rule_closures):
        lines.append(
            "  - {date: %s, name: %s, rule: %s}"
            % (
                quoted(day.isoformat()),
                quoted(rule_closures[day]),
                _rule_id_for(day),
            )
        )
    lines.append("")
    lines.append("early_closes:")
    for day in sorted(early):
        lines.append(
            "  - {date: %s, name: %s, rule: %s, close: %s}"
            % (
                quoted(day.isoformat()),
                quoted(early[day]),
                _early_rule_id(early[day]),
                quoted("13:00"),
            )
        )
    lines.append("")
    lines.append("special_closures:")
    for day, name, source in SPECIAL_CLOSURES:
        if start <= day <= end:
            lines.append(
                "  - {date: %s, name: %s, source: %s}"
                % (quoted(day.isoformat()), quoted(name), quoted(source))
            )
    lines.append("")
    return "\n".join(lines)


def _rule_id_for(day: date) -> str:
    """Best-effort rule id for a derived closure date (documentation only)."""
    for rule_id, description, _source in _RULES:
        if rule_id in {
            "day_after_thanksgiving",
            "independence_day_eve",
            "christmas_eve",
        }:
            continue
        # The description is human text; match by deriving each rule alone.
        if day in _derive_single_rule(rule_id, day.year):
            return rule_id
    return "unknown"


def _derive_single_rule(rule_id: str, year: int) -> set[date]:
    mapping = {
        "new_years_day": _observed_fixed(year, 1, 1, saturday_observed=False),
        "martin_luther_king_day": _nth_weekday(year, 1, 0, 3),
        "washingtons_birthday": _nth_weekday(year, 2, 0, 3),
        "good_friday": easter_sunday(year) - timedelta(days=2),
        "memorial_day": _last_weekday(year, 5, 0),
        "juneteenth": (
            _observed_fixed(year, 6, 19, saturday_observed=True)
            if year >= 2022
            else None
        ),
        "independence_day": _observed_fixed(year, 7, 4, saturday_observed=True),
        "labor_day": _nth_weekday(year, 9, 0, 1),
        "thanksgiving_day": _nth_weekday(year, 11, 3, 4),
        "christmas_day": _observed_fixed(year, 12, 25, saturday_observed=True),
    }
    value = mapping.get(rule_id)
    return {value} if value is not None else set()


def _early_rule_id(name: str) -> str:
    return {
        "Day after Thanksgiving": "day_after_thanksgiving",
        "Independence Day eve": "independence_day_eve",
        "Christmas Eve": "christmas_eve",
    }.get(name, "unknown")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--path",
        default=None,
        help=f"calendar YAML (default: {DEFAULT_PATH})",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="verify the static YAML against the rule-derived calendar",
    )
    group.add_argument(
        "--write",
        action="store_true",
        help="regenerate the static YAML from the rules",
    )
    group.add_argument(
        "--summary",
        action="store_true",
        help="print coverage and counts",
    )
    args = parser.parse_args(argv)

    target = Path(args.path) if args.path else DEFAULT_PATH
    if args.write:
        target.write_text(render_calendar_yaml(), encoding="utf-8")
        print(f"wrote {target}")
        return 0
    if args.check:
        problems = check_calendar_file(target)
        if problems:
            print(f"{target}: {len(problems)} discrepancy(ies)", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"{target}: OK (rules match static calendar)")
        return 0
    calendar = _calendar(target)
    print(
        f"coverage {calendar.coverage_start}..{calendar.coverage_end}; "
        f"{len(calendar.full_closures)} full closures "
        f"({len(calendar.special_closures)} ad-hoc), "
        f"{len(calendar.early_closes)} early closes ({calendar.path})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
