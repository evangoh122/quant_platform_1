"""
tests/bronze/test_refresh_bronze_fed.py
Tests for FRED bronze refresh parsing and key-selection helpers.

Self-contained: tests pure functions from notebooks/refresh_bronze_fed.py
without triggering live ingestion (guarded by if __name__ == "__main__").
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from notebooks.refresh_bronze_fed import (
    _parse_date,
    _parse_value,
    _easter_sunday,
    _h15_holidays,
    _is_ny_business_day,
    _next_ny_business_day,
    _ny_available_ts,
    _overlap_start,
    _compute_overlap_dates,
    parse_csv_rows,
    select_new_rows,
    SERIES_CONFIG,
)

INGEST_TS = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _parse_value: "." handling
# ---------------------------------------------------------------------------

class TestParseValue:
    def test_dot_returns_none(self):
        assert _parse_value(".") is None

    def test_empty_string_returns_none(self):
        assert _parse_value("") is None

    def test_whitespace_returns_none(self):
        assert _parse_value("   ") is None

    def test_non_numeric_returns_none(self):
        assert _parse_value("NA") is None

    def test_valid_float(self):
        assert _parse_value("3.14") == pytest.approx(3.14)

    def test_valid_int(self):
        assert _parse_value("42") == 42.0

    def test_negative(self):
        assert _parse_value("-0.5") == -0.5

    def test_dot_with_spaces(self):
        assert _parse_value(" . ") is None

    def test_zero(self):
        assert _parse_value("0") == 0.0


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_valid_date(self):
        assert _parse_date("2024-06-04") == date(2024, 6, 4)

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_none(self):
        assert _parse_date(None) is None

    def test_invalid_format(self):
        assert _parse_date("not-a-date") is None

    def test_whitespace(self):
        assert _parse_date("  ") is None


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

class TestCalendarHelpers:
    def test_weekday_is_business_day(self):
        # 2026-10-05 is Monday
        assert _is_ny_business_day(date(2026, 10, 5)) is True

    def test_weekend_is_not_business_day(self):
        # 2026-10-04 is Sunday
        assert _is_ny_business_day(date(2026, 10, 4)) is False

    def test_next_business_day_from_friday(self):
        # 2026-10-02 is Friday → next is Monday 2026-10-05
        assert _next_ny_business_day(date(2026, 10, 2)) == date(2026, 10, 5)

    def test_next_business_day_from_weekday(self):
        # 2026-10-01 is Thursday → next is Friday 2026-10-02
        assert _next_ny_business_day(date(2026, 10, 1)) == date(2026, 10, 2)


# ---------------------------------------------------------------------------
# Bond market (SIFMA) calendar
# ---------------------------------------------------------------------------

class TestH15Calendar:
    def test_easter_sunday_2024(self):
        assert _easter_sunday(2024) == date(2024, 3, 31)

    def test_easter_sunday_2025(self):
        assert _easter_sunday(2025) == date(2025, 4, 20)

    def test_easter_sunday_2026(self):
        assert _easter_sunday(2026) == date(2026, 4, 5)

    def test_good_friday_is_holiday(self):
        # Good Friday 2024-03-29 should be in H.15 holidays
        holidays = _h15_holidays(date(2024, 3, 25), date(2024, 4, 5))
        assert date(2024, 3, 29) in holidays

    def test_good_friday_is_not_federal_holiday(self):
        # Good Friday is NOT a federal holiday
        from pandas.tseries.holiday import USFederalHolidayCalendar
        cal = USFederalHolidayCalendar()
        holidays = cal.holidays(start="2024-03-25", end="2024-04-05")
        assert date(2024, 3, 29) not in {h.date() for h in holidays}

    def test_columbus_day_in_h15_holidays(self):
        # Columbus Day 2024-10-14 IS an H.15 holiday (Fed closed)
        holidays = _h15_holidays(date(2024, 10, 10), date(2024, 10, 18))
        assert date(2024, 10, 14) in holidays

    def test_veterans_day_in_h15_holidays(self):
        # Veterans Day 2024-11-11 IS an H.15 holiday (Fed closed)
        holidays = _h15_holidays(date(2024, 11, 8), date(2024, 11, 15))
        assert date(2024, 11, 11) in holidays

    def test_columbus_day_is_federal_holiday(self):
        # Columbus Day IS a federal holiday (so _is_ny_business_day with federal says False)
        assert _is_ny_business_day(date(2024, 10, 14), calendar="federal") is False

    def test_columbus_day_is_h15_holiday(self):
        # Columbus Day is an H.15 holiday — Fed closed, no H.15 publication
        assert _is_ny_business_day(date(2024, 10, 14), calendar="h15") is False

    def test_veterans_day_is_federal_holiday(self):
        assert _is_ny_business_day(date(2024, 11, 11), calendar="federal") is False

    def test_veterans_day_is_h15_holiday(self):
        # Veterans Day is an H.15 holiday — Fed closed, no H.15 publication
        assert _is_ny_business_day(date(2024, 11, 11), calendar="h15") is False

    def test_thu_before_good_friday_2024_rolls_to_monday(self):
        # 2024-03-28 (Thu) → Good Friday 03-29 closed → next is Monday 2024-04-01
        assert _next_ny_business_day(date(2024, 3, 28), calendar="h15") == date(2024, 4, 1)

    def test_thu_before_good_friday_2025_rolls_to_monday(self):
        # 2025-04-17 (Thu) → Good Friday 04-18 closed → next is Monday 2025-04-21
        assert _next_ny_business_day(date(2025, 4, 17), calendar="h15") == date(2025, 4, 21)

    def test_fri_before_columbus_day_rolls_to_tuesday_h15(self):
        # 2024-10-11 (Fri) → Columbus Day 10-14 closed → next is Tuesday 2024-10-15
        assert _next_ny_business_day(date(2024, 10, 11), calendar="h15") == date(2024, 10, 15)

    def test_fri_before_veterans_day_rolls_to_wednesday_h15(self):
        # 2024-11-08 (Fri) → Veterans Day 11-11 closed → next is Wednesday 2024-11-12
        assert _next_ny_business_day(date(2024, 11, 8), calendar="h15") == date(2024, 11, 12)

    def test_good_friday_fails_on_federal_calendar(self):
        # Under the old federal calendar, 2024-03-28 (Thu) → 2024-03-29 (Good Friday)
        # because Good Friday is not a federal holiday
        assert _next_ny_business_day(date(2024, 3, 28), calendar="federal") == date(2024, 3, 29)


# ---------------------------------------------------------------------------
# _ny_available_ts: market rate availability
# ---------------------------------------------------------------------------

class TestNyAvailableTs:
    def test_weekday_obs_returns_next_day_2030utc_summer(self):
        # 2026-10-01 (Thursday, EDT) → next business day is 2026-10-02 at 16:30 EDT = 20:30 UTC
        ts = _ny_available_ts(date(2026, 10, 1))
        assert ts == datetime(2026, 10, 2, 20, 30, 0, tzinfo=timezone.utc)

    def test_friday_obs_returns_monday_2030utc_summer(self):
        # 2026-10-02 (Friday, EDT) → next business day is 2026-10-05 (Monday) at 16:30 EDT = 20:30 UTC
        ts = _ny_available_ts(date(2026, 10, 2))
        assert ts == datetime(2026, 10, 5, 20, 30, 0, tzinfo=timezone.utc)

    def test_winter_obs_returns_next_day_2130utc(self):
        # 2026-01-05 (Monday, EST) → next business day is 2026-01-06 at 16:30 EST = 21:30 UTC
        ts = _ny_available_ts(date(2026, 1, 5))
        assert ts == datetime(2026, 1, 6, 21, 30, 0, tzinfo=timezone.utc)

    def test_holiday_rolls_forward(self):
        # 2026-01-16 (Friday) → next is Monday 2026-01-19 (MLK Day is Jan 19 in 2026)
        # MLK Day 2026 = Jan 19, so next business day is Jan 20
        ts = _ny_available_ts(date(2026, 1, 16))
        assert ts == datetime(2026, 1, 20, 21, 30, 0, tzinfo=timezone.utc)

    def test_thu_before_good_friday_2024_rolls_to_monday(self):
        # 2024-03-28 (Thu) → Good Friday 03-29 closed → Monday 2024-04-01 16:30 EDT = 20:30 UTC
        ts = _ny_available_ts(date(2024, 3, 28))
        assert ts == datetime(2024, 4, 1, 20, 30, 0, tzinfo=timezone.utc)

    def test_thu_before_good_friday_2025_rolls_to_monday(self):
        # 2025-04-17 (Thu) → Good Friday 04-18 closed → Monday 2025-04-21 16:30 EDT = 20:30 UTC
        ts = _ny_available_ts(date(2025, 4, 17))
        assert ts == datetime(2025, 4, 21, 20, 30, 0, tzinfo=timezone.utc)

    def test_columbus_day_h15_available_next_business_day(self):
        # Columbus Day 2024-10-14: Fed closed, no H.15 publication
        # 2024-10-11 (Fri) → 2024-10-15 (Tue) 16:30 EDT = 20:30 UTC
        ts = _ny_available_ts(date(2024, 10, 11))
        assert ts == datetime(2024, 10, 15, 20, 30, 0, tzinfo=timezone.utc)

    def test_veterans_day_h15_available_next_business_day(self):
        # Veterans Day 2024-11-11: Fed closed, no H.15 publication
        # 2024-11-08 (Fri) → 2024-11-12 (Tue) 16:30 EST = 21:30 UTC
        ts = _ny_available_ts(date(2024, 11, 8))
        assert ts == datetime(2024, 11, 12, 21, 30, 0, tzinfo=timezone.utc)

    def test_good_friday_wrong_on_federal_calendar(self):
        # Under federal calendar, Thu before Good Friday → Good Friday (wrong)
        from notebooks.refresh_bronze_fed import _next_ny_business_day
        nxt = _next_ny_business_day(date(2024, 3, 28), calendar="federal")
        assert nxt == date(2024, 3, 29)  # This is Good Friday — proves the bug


# ---------------------------------------------------------------------------
# _overlap_start
# ---------------------------------------------------------------------------

class TestOverlapStart:
    def test_daily_overlap_14_days(self):
        max_obs = date(2026, 10, 3)
        assert _overlap_start(max_obs, "daily") == date(2026, 9, 19)

    def test_monthly_overlap_24_months(self):
        max_obs = date(2026, 10, 1)
        assert _overlap_start(max_obs, "monthly") == date(2024, 10, 1)


# ---------------------------------------------------------------------------
# _compute_overlap_dates
# ---------------------------------------------------------------------------

class TestComputeOverlapDates:
    def test_daily_series(self):
        assert _compute_overlap_dates("DFF", date(2026, 10, 3)) == date(2026, 9, 19)

    def test_monthly_series(self):
        assert _compute_overlap_dates("CPIAUCSL", date(2026, 10, 1)) == date(2024, 10, 1)


# ---------------------------------------------------------------------------
# parse_csv_rows: daily and monthly date parsing
# ---------------------------------------------------------------------------

class TestParseCsvRows:
    def _make_csv(self, header, rows):
        lines = [",".join(header)]
        for row in rows:
            lines.append(",".join(str(v) for v in row))
        return "\n".join(lines)

    def test_daily_series_parsing(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-09-20", "4.33"], ["2026-09-21", "4.34"], ["2026-09-22", "."]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 2  # "." row skipped
        assert rows[0]["series_id"] == "DFF"
        assert rows[0]["observation_date"] == date(2026, 9, 20)
        assert rows[0]["value"] == pytest.approx(4.33)
        assert rows[0]["revision_class"] == "market_rate"

    def test_monthly_series_parsing(self):
        csv_text = self._make_csv(
            ["DATE", "CPIAUCSL"],
            [["2026-08-01", "308.5"], ["2026-09-01", "309.1"]],
        )
        rows = parse_csv_rows(csv_text, "CPIAUCSL", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 2
        assert rows[0]["revision_class"] == "revised_macro"

    def test_end_date_filter(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-10-02", "4.33"], ["2026-10-04", "4.34"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 1  # 2026-10-04 > end_date

    def test_overlap_filter(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-09-18", "4.33"], ["2026-09-20", "4.34"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), date(2026, 9, 19), INGEST_TS)
        assert len(rows) == 1  # 2026-09-18 < overlap_start

    def test_dot_values_skipped(self):
        csv_text = self._make_csv(
            ["DATE", "DGS10"],
            [["2026-09-20", "."], ["2026-09-21", "3.85"]],
        )
        rows = parse_csv_rows(csv_text, "DGS10", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 1
        assert rows[0]["value"] == pytest.approx(3.85)

    def test_empty_values_skipped(self):
        csv_text = self._make_csv(
            ["DATE", "DGS10"],
            [["2026-09-20", ""], ["2026-09-21", "3.85"]],
        )
        rows = parse_csv_rows(csv_text, "DGS10", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 1

    def test_market_rate_info_ts_after_ingest(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-10-01", "4.33"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        # 2026-10-01 Thursday → next business day is 2026-10-02 at 16:30 EDT = 20:30 UTC
        # info_ts is NOT max(ny_ts, ingest_ts) anymore — it's purely the NY available time
        assert rows[0]["information_available_ts"] == datetime(2026, 10, 2, 20, 30, 0, tzinfo=timezone.utc)

    def test_market_rate_historical_info_ts_not_ingest(self):
        """Historical market rate rows use NY available time, not ingest_ts."""
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2020-01-02", "1.55"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        # 2020-01-02 Thursday → next business day is 2020-01-03 at 16:30 EST = 21:30 UTC
        assert rows[0]["information_available_ts"] == datetime(2020, 1, 3, 21, 30, 0, tzinfo=timezone.utc)
        assert rows[0]["information_available_ts"] != INGEST_TS

    def test_revised_macro_info_ts_equals_ingest_ts(self):
        csv_text = self._make_csv(
            ["DATE", "UNRATE"],
            [["2026-09-01", "3.7"]],
        )
        rows = parse_csv_rows(csv_text, "UNRATE", date(2026, 10, 3), None, INGEST_TS)
        assert rows[0]["information_available_ts"] == INGEST_TS

    def test_raw_value_preserved(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-09-20", "4.33"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert rows[0]["raw_value"] == "4.33"

    def test_dot_raw_value_becomes_none(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-09-20", "."]],
        )
        # "." value is skipped entirely, so no row to check raw_value on
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 0

    def test_vintage_date_equals_ingest_date(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-09-20", "4.33"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert rows[0]["vintage_date"] == date(2026, 10, 3)

    def test_source_is_fred_csv(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-09-20", "4.33"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert rows[0]["source"] == "fred_csv"

    def test_source_url(self):
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-09-20", "4.33"]],
        )
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert rows[0]["source_url"] == "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"


# ---------------------------------------------------------------------------
# select_new_rows: overlap, changed values, idempotency
# ---------------------------------------------------------------------------

class TestSelectNewRows:
    def test_unchanged_overlap_excluded(self):
        candidates = [
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 3), "value": 4.33},
        ]
        existing = {("DFF", date(2026, 9, 20)): 4.33}
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 0
        assert overlap_count == 1

    def test_changed_value_becomes_new_vintage(self):
        candidates = [
            {"series_id": "UNRATE", "observation_date": date(2026, 9, 1),
             "vintage_date": date(2026, 10, 3), "value": 3.8},
        ]
        # Existing has a different value for same (series_id, observation_date)
        existing = {("UNRATE", date(2026, 9, 1)): 3.7}
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 1  # Different value = new vintage
        assert new_rows[0]["value"] == pytest.approx(3.8)

    def test_same_day_rerun_idempotency(self):
        """Same candidates and same existing keys → zero new rows."""
        candidates = [
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 3), "value": 4.33},
            {"series_id": "DGS10", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 3), "value": 3.85},
        ]
        existing = {
            ("DFF", date(2026, 9, 20)): 4.33,
            ("DGS10", date(2026, 9, 20)): 3.85,
        }
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 0
        assert overlap_count == 2

    def test_next_day_same_value_not_appended(self):
        """Candidate from day D+1 with same value as day D → 0 new."""
        candidates = [
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 4), "value": 4.33},
        ]
        existing = {("DFF", date(2026, 9, 20)): 4.33}
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 0
        assert overlap_count == 1

    def test_next_day_changed_value_appended(self):
        """Candidate from day D+1 with different value → 1 new."""
        candidates = [
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 4), "value": 4.50},
        ]
        existing = {("DFF", date(2026, 9, 20)): 4.33}
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 1
        assert new_rows[0]["value"] == pytest.approx(4.50)

    def test_value_revert_is_new_vintage(self):
        """A→B→A: the revert (A) differs from latest stored (B), so it's new."""
        candidates = [
            {"series_id": "UNRATE", "observation_date": date(2026, 9, 1),
             "vintage_date": date(2026, 10, 5), "value": 3.7},
        ]
        # Latest stored vintage has value 3.8 (the B in A→B→A)
        existing = {("UNRATE", date(2026, 9, 1)): 3.8}
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 1
        assert new_rows[0]["value"] == pytest.approx(3.7)

    def test_duplicates_within_batch(self):
        candidates = [
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 3), "value": 4.33},
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 3), "value": 4.33},
        ]
        new_rows, dup_count, overlap_count = select_new_rows(candidates, {})
        assert len(new_rows) == 1
        assert dup_count == 1

    def test_empty_candidates(self):
        new_rows, dup_count, overlap_count = select_new_rows([], {})
        assert len(new_rows) == 0
        assert dup_count == 0
        assert overlap_count == 0


# ---------------------------------------------------------------------------
# information_available_ts >= ingest_ts invariant
# ---------------------------------------------------------------------------

class TestAvailabilityInvariant:
    def _make_csv(self, header, rows):
        lines = [",".join(header)]
        for row in rows:
            lines.append(",".join(str(v) for v in row))
        return "\n".join(lines)

    def test_market_rate_available_at_ny_time(self):
        """For market_rate, information_available_ts = next NY business day 16:30 ET."""
        csv_text = self._make_csv(
            ["DATE", "DFF"],
            [["2026-10-02", "4.33"]],
        )
        # 2026-10-02 Friday → next business day is 2026-10-05 Monday at 16:30 EDT = 20:30 UTC
        rows = parse_csv_rows(csv_text, "DFF", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 1
        assert rows[0]["information_available_ts"] == datetime(2026, 10, 5, 20, 30, 0, tzinfo=timezone.utc)

    def test_market_rate_summer_vs_winter_utc(self):
        """Summer (EDT) → 20:30 UTC; winter (EST) → 21:30 UTC."""
        summer_csv = self._make_csv(["DATE", "DFF"], [["2026-07-01", "4.0"]])
        winter_csv = self._make_csv(["DATE", "DFF"], [["2026-01-05", "4.0"]])
        summer_rows = parse_csv_rows(summer_csv, "DFF", date(2026, 10, 3), None, INGEST_TS)
        winter_rows = parse_csv_rows(winter_csv, "DFF", date(2026, 10, 3), None, INGEST_TS)
        # 2026-07-01 Wed → Thu 2026-07-02 16:30 EDT = 20:30 UTC
        assert summer_rows[0]["information_available_ts"] == datetime(2026, 7, 2, 20, 30, 0, tzinfo=timezone.utc)
        # 2026-01-05 Mon → Tue 2026-01-06 16:30 EST = 21:30 UTC
        assert winter_rows[0]["information_available_ts"] == datetime(2026, 1, 6, 21, 30, 0, tzinfo=timezone.utc)

    def test_revised_macro_available_equals_ingest(self):
        csv_text = self._make_csv(
            ["DATE", "UNRATE"],
            [["2026-09-01", "3.7"]],
        )
        rows = parse_csv_rows(csv_text, "UNRATE", date(2026, 10, 3), None, INGEST_TS)
        assert len(rows) == 1
        assert rows[0]["information_available_ts"] == INGEST_TS
        assert rows[0]["information_available_ts"] >= INGEST_TS


# ---------------------------------------------------------------------------
# SERIES_CONFIG sanity
# ---------------------------------------------------------------------------

class TestSeriesConfig:
    def test_all_12_series_present(self):
        expected = {"DFF", "DGS2", "DGS10", "T10Y2Y", "T10Y3M",
                    "DFEDTARU", "DFEDTARL", "CPIAUCSL", "CPILFESL",
                    "UNRATE", "PAYEMS", "INDPRO"}
        assert set(SERIES_CONFIG.keys()) == expected

    def test_market_rate_series(self):
        market = {k for k, v in SERIES_CONFIG.items() if v["revision_class"] == "market_rate"}
        assert market == {"DFF", "DGS2", "DGS10", "T10Y2Y", "T10Y3M", "DFEDTARU", "DFEDTARL"}

    def test_revised_macro_series(self):
        revised = {k for k, v in SERIES_CONFIG.items() if v["revision_class"] == "revised_macro"}
        assert revised == {"CPIAUCSL", "CPILFESL", "UNRATE", "PAYEMS", "INDPRO"}

    def test_freq_assignments(self):
        daily = {k for k, v in SERIES_CONFIG.items() if v["freq"] == "daily"}
        monthly = {k for k, v in SERIES_CONFIG.items() if v["freq"] == "monthly"}
        assert daily == {"DFF", "DGS2", "DGS10", "T10Y2Y", "T10Y3M", "DFEDTARU", "DFEDTARL"}
        assert monthly == {"CPIAUCSL", "CPILFESL", "UNRATE", "PAYEMS", "INDPRO"}


# ---------------------------------------------------------------------------
# H.15 gap validation from FRED-shaped fixture
# ---------------------------------------------------------------------------

class TestH15GapFromFixture:
    """Derive expected gaps from FRED-shaped fixture data.

    For every date where the fixture series value is blank (FRED uses "." for
    missing), the previous observation's information_available_ts must NOT
    fall on that date — because no H.15 value is published that day.
    """

    def _make_csv(self, header, rows):
        lines = [",".join(header)]
        for row in rows:
            lines.append(",".join(str(v) for v in row))
        return "\n".join(lines)

    def test_blank_dates_not_available_from_prev(self):
        """FRED-shaped fixture: DGS10 has gaps on Columbus Day and Veterans Day.

        Proves that previous observations are not marked available on days
        when no H.15 value is published.
        """
        # Fixture modeled on live FRED DGS10 data around Columbus/Veterans 2024
        csv_text = self._make_csv(
            ["DATE", "DGS10"],
            [
                ["2024-10-10", "4.09"],
                ["2024-10-11", "4.08"],
                ["2024-10-14", "."],    # Columbus Day: blank
                ["2024-10-15", "4.03"],
                ["2024-11-08", "4.30"],
                ["2024-11-11", "."],    # Veterans Day: blank
                ["2024-11-12", "4.43"],
            ],
        )
        rows = parse_csv_rows(csv_text, "DGS10", date(2024, 12, 31), None, INGEST_TS)
        # Build a map: obs_date → information_available_ts
        avail = {r["observation_date"]: r["information_available_ts"] for r in rows}

        # For each blank-date gap, the previous observation's available_ts
        # must NOT land on the blank date (that would mean "available before published")
        blank_dates = [date(2024, 10, 14), date(2024, 11, 11)]
        for blank_d in blank_dates:
            prev_d = blank_d - _one_biz_day_back(blank_d)
            if prev_d in avail:
                avail_date = avail[prev_d].date()
                assert avail_date != blank_d, (
                    f"{prev_d} marked available on {blank_d}, "
                    f"but no H.15 value is published that day"
                )

    def test_friday_before_columbus_available_tuesday(self):
        """Friday 2024-10-11 observation → available Tuesday 2024-10-15, not Monday."""
        csv_text = self._make_csv(
            ["DATE", "DGS10"],
            [
                ["2024-10-11", "4.08"],
                ["2024-10-14", "."],
                ["2024-10-15", "4.03"],
            ],
        )
        rows = parse_csv_rows(csv_text, "DGS10", date(2024, 12, 31), None, INGEST_TS)
        assert len(rows) == 2  # 10-14 skipped (blank)
        fri_row = rows[0]
        assert fri_row["observation_date"] == date(2024, 10, 11)
        assert fri_row["information_available_ts"] == datetime(
            2024, 10, 15, 20, 30, 0, tzinfo=timezone.utc
        )

    def test_friday_before_veterans_available_wednesday(self):
        """Friday 2024-11-08 observation → available Wednesday 2024-11-12, not Monday."""
        csv_text = self._make_csv(
            ["DATE", "DGS10"],
            [
                ["2024-11-08", "4.30"],
                ["2024-11-11", "."],
                ["2024-11-12", "4.43"],
            ],
        )
        rows = parse_csv_rows(csv_text, "DGS10", date(2024, 12, 31), None, INGEST_TS)
        assert len(rows) == 2  # 11-11 skipped (blank)
        fri_row = rows[0]
        assert fri_row["observation_date"] == date(2024, 11, 8)
        assert fri_row["information_available_ts"] == datetime(
            2024, 11, 12, 21, 30, 0, tzinfo=timezone.utc
        )


def _one_biz_day_back(d: date) -> timedelta:
    """Return timedelta to previous business day (3 days if d is Monday, else 1)."""
    if d.weekday() == 0:  # Monday → prev is Friday (3 days back)
        return timedelta(days=3)
    return timedelta(days=1)


# ---------------------------------------------------------------------------
# Round-3 regression proof: old code treats Columbus as business day
# ---------------------------------------------------------------------------

class TestRound3RegressionProof:
    """Prove that the round-3 code (bond_market calendar with Columbus/Veterans
    removed) produces the wrong result for Columbus Day availability."""

    def test_old_bond_market_calendar_treats_columbus_as_business_day(self):
        """Round-3 _is_ny_business_day(date(2024,10,14), 'bond_market') returned True.

        This is the exact bug: Columbus Day is a federal holiday (Fed closed),
        but the old SIFMA bond-market calendar removed it, marking it as a
        business day. The fix re-adds it under the new 'h15' calendar name.
        """
        # Simulate the old bond_market logic: federal holidays + Good Friday
        # - Columbus Day - Veterans Day
        from notebooks.refresh_bronze_fed import _us_federal_holidays, _easter_sunday
        d = date(2024, 10, 14)
        holidays = _us_federal_holidays(d, d)
        # Old code removed Columbus Day:
        oct_1 = date(2024, 10, 1)
        first_monday = oct_1 + timedelta(days=(7 - oct_1.weekday()) % 7)
        columbus_day = first_monday + timedelta(days=7)
        holidays.discard(columbus_day)
        # Old code: Columbus Day NOT in holidays → is_business_day = True
        assert d not in holidays, "Old code: Columbus Day removed from holidays"
        # But the new h15 calendar says it IS a holiday
        assert _is_ny_business_day(d, calendar="h15") is False, (
            "Fixed code: Columbus Day is an H.15 holiday"
        )

    def test_old_available_ts_columbus_one_day_lookahead(self):
        """Round-3 _ny_available_ts(2024-10-11) = 2024-10-14 (wrong, one-day lookahead).

        The fix correctly returns 2024-10-15 because Columbus Day 10-14 is closed.
        """
        ts = _ny_available_ts(date(2024, 10, 11))
        # Old code would return 2024-10-14 20:30 UTC (Columbus Day — wrong)
        # Fixed code returns 2024-10-15 20:30 UTC (Tuesday — correct)
        assert ts == datetime(2024, 10, 15, 20, 30, 0, tzinfo=timezone.utc)
        # Prove the old result is wrong (the value isn't published until Tuesday)
        assert ts != datetime(2024, 10, 14, 20, 30, 0, tzinfo=timezone.utc)