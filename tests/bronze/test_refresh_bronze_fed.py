"""
tests/bronze/test_refresh_bronze_fed.py
Tests for FRED bronze refresh parsing and key-selection helpers.

Self-contained: tests pure functions from notebooks/refresh_bronze_fed.py
without triggering live ingestion (guarded by if __name__ == "__main__").
"""
import pytest
from datetime import date, datetime, timezone
from notebooks.refresh_bronze_fed import (
    _parse_date,
    _parse_value,
    _easter_sunday,
    _bond_market_holidays,
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

class TestBondMarketCalendar:
    def test_easter_sunday_2024(self):
        assert _easter_sunday(2024) == date(2024, 3, 31)

    def test_easter_sunday_2025(self):
        assert _easter_sunday(2025) == date(2025, 4, 20)

    def test_easter_sunday_2026(self):
        assert _easter_sunday(2026) == date(2026, 4, 5)

    def test_good_friday_is_holiday(self):
        # Good Friday 2024-03-29 should be in bond market holidays
        holidays = _bond_market_holidays(date(2024, 3, 25), date(2024, 4, 5))
        assert date(2024, 3, 29) in holidays

    def test_good_friday_is_not_federal_holiday(self):
        # Good Friday is NOT a federal holiday
        fed = _bond_market_holidays.__wrapped__ if hasattr(_bond_market_holidays, '__wrapped__') else None
        from pandas.tseries.holiday import USFederalHolidayCalendar
        cal = USFederalHolidayCalendar()
        holidays = cal.holidays(start="2024-03-25", end="2024-04-05")
        assert date(2024, 3, 29) not in {h.date() for h in holidays}

    def test_columbus_day_not_in_bond_market(self):
        # Columbus Day 2024-10-14 should NOT be a bond market holiday
        holidays = _bond_market_holidays(date(2024, 10, 10), date(2024, 10, 18))
        assert date(2024, 10, 14) not in holidays

    def test_veterans_day_not_in_bond_market(self):
        # Veterans Day 2024-11-11 should NOT be a bond market holiday
        holidays = _bond_market_holidays(date(2024, 11, 8), date(2024, 11, 15))
        assert date(2024, 11, 11) not in holidays

    def test_columbus_day_is_federal_holiday(self):
        # Columbus Day IS a federal holiday (so _is_ny_business_day with federal says False)
        assert _is_ny_business_day(date(2024, 10, 14), calendar="federal") is False

    def test_columbus_day_is_bond_market_business_day(self):
        # Columbus Day is a bond market business day
        assert _is_ny_business_day(date(2024, 10, 14), calendar="bond_market") is True

    def test_veterans_day_is_federal_holiday(self):
        assert _is_ny_business_day(date(2024, 11, 11), calendar="federal") is False

    def test_veterans_day_is_bond_market_business_day(self):
        assert _is_ny_business_day(date(2024, 11, 11), calendar="bond_market") is True

    def test_thu_before_good_friday_2024_rolls_to_monday(self):
        # 2024-03-28 (Thu) → Good Friday 03-29 closed → next is Monday 2024-04-01
        assert _next_ny_business_day(date(2024, 3, 28), calendar="bond_market") == date(2024, 4, 1)

    def test_thu_before_good_friday_2025_rolls_to_monday(self):
        # 2025-04-17 (Thu) → Good Friday 04-18 closed → next is Monday 2025-04-21
        assert _next_ny_business_day(date(2025, 4, 17), calendar="bond_market") == date(2025, 4, 21)

    def test_fri_before_columbus_day_rolls_to_monday_bond(self):
        # 2024-10-11 (Fri) → Columbus Day 10-14 is OPEN → next is Monday 2024-10-14
        assert _next_ny_business_day(date(2024, 10, 11), calendar="bond_market") == date(2024, 10, 14)

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

    def test_columbus_day_bond_market_available_same_day(self):
        # Columbus Day 2024-10-14: bond market OPEN
        # 2024-10-11 (Fri) → 2024-10-14 (Mon) 16:30 EDT = 20:30 UTC
        ts = _ny_available_ts(date(2024, 10, 11))
        assert ts == datetime(2024, 10, 14, 20, 30, 0, tzinfo=timezone.utc)

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
        existing = {("DFF", date(2026, 9, 20), date(2026, 10, 3), 4.33)}
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 0
        assert overlap_count == 1

    def test_changed_value_becomes_new_vintage(self):
        candidates = [
            {"series_id": "UNRATE", "observation_date": date(2026, 9, 1),
             "vintage_date": date(2026, 10, 3), "value": 3.8},
        ]
        # Existing has a different value for same key prefix
        existing = {("UNRATE", date(2026, 9, 1), date(2026, 10, 3), 3.7)}
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
            ("DFF", date(2026, 9, 20), date(2026, 10, 3), 4.33),
            ("DGS10", date(2026, 9, 20), date(2026, 10, 3), 3.85),
        }
        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing)
        assert len(new_rows) == 0
        assert overlap_count == 2

    def test_duplicates_within_batch(self):
        candidates = [
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 3), "value": 4.33},
            {"series_id": "DFF", "observation_date": date(2026, 9, 20),
             "vintage_date": date(2026, 10, 3), "value": 4.33},
        ]
        new_rows, dup_count, overlap_count = select_new_rows(candidates, set())
        assert len(new_rows) == 1
        assert dup_count == 1

    def test_empty_candidates(self):
        new_rows, dup_count, overlap_count = select_new_rows([], set())
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