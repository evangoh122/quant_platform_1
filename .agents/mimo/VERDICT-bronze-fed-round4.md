===VERDICT START===
# VERDICT: bronze-fed — MiMo

**Status:** APPROVED
**Round:** 4 (H.15 publication calendar fix)
**Branch:** `slice/bronze-fed`
**Commit:** `21dee91`

Builder verdict: Fixed the H.15 publication calendar for market_rate availability.

## What was done

- **`notebooks/refresh_bronze_fed.py`:**
  - Renamed `_bond_market_holidays` → `_h15_holidays` (says what it is: Fed/Treasury H.15 publication calendar)
  - Removed Columbus Day and Veterans Day subtraction (lines 106-117 of round-3 code)
  - Calendar is now federal holidays + Good Friday (no SIFMA bond-market framing)
  - Updated all internal references: `"bond_market"` → `"h15"` in `_is_ny_business_day`, `_next_ny_business_day`, `_ny_available_ts`

- **`tests/bronze/test_refresh_bronze_fed.py`:**
  - Updated import: `_bond_market_holidays` → `_h15_holidays`
  - Renamed `TestBondMarketCalendar` → `TestH15Calendar`
  - Fixed 6 test assertions that encoded wrong round-3 behaviour:
    - `test_columbus_day_in_h15_holidays`: Columbus Day IS an H.15 holiday (was "not in bond_market")
    - `test_veterans_day_in_h15_holidays`: Veterans Day IS an H.15 holiday (was "not in bond_market")
    - `test_columbus_day_is_h15_holiday`: `_is_ny_business_day(2024-10-14, "h15")` = False (was True with "bond_market")
    - `test_veterans_day_is_h15_holiday`: `_is_ny_business_day(2024-11-11, "h15")` = False (was True with "bond_market")
    - `test_fri_before_columbus_day_rolls_to_tuesday_h15`: `_next_ny_business_day(2024-10-11, "h15")` = 2024-10-15 (was 2024-10-14)
    - `test_fri_before_veterans_day_rolls_to_wednesday_h15`: `_next_ny_business_day(2024-11-08, "h15")` = 2024-11-12 (was 2024-11-11)
    - `test_columbus_day_h15_available_next_business_day`: `_ny_available_ts(2024-10-11)` = 2024-10-15 20:30 UTC (was 2024-10-14)
    - `test_veterans_day_h15_available_next_business_day`: `_ny_available_ts(2024-11-08)` = 2024-11-12 21:30 UTC (new test)
  - Added `TestH15GapFromFixture` (3 tests):
    - `test_blank_dates_not_available_from_prev`: FRED-shaped fixture with blank dates on Columbus/Veterans → previous observation not available on those dates
    - `test_friday_before_columbus_available_tuesday`: 2024-10-11 → 2024-10-15 20:30 UTC
    - `test_friday_before_veterans_available_wednesday`: 2024-11-08 → 2024-11-12 21:30 UTC
  - Added `TestRound3RegressionProof` (2 tests):
    - `test_old_bond_market_calendar_treats_columbus_as_business_day`: proves old code removes Columbus Day from holidays
    - `test_old_available_ts_columbus_one_day_lookahead`: proves old code returns 2024-10-14 not 2024-10-15

## Non-blocking notes

- DST handling is correct: summer (EDT) → 20:30 UTC, winter (EST) → 21:30 UTC. Verified by existing `test_market_rate_summer_vs_winter_utc`.
- Good Friday handling unchanged and correct: `_next_ny_business_day(2024-03-28, "h15")` → 2024-04-01.
- Veterans Day 2024-11-08 (Fri) → 2024-11-12 (Wed) because 11-09 is Saturday, 11-10 is Sunday, 11-11 is Veterans Day.
- No `--write` or truncate operations performed. Coordinator rebuilds the table.

## Checks run

```
$ python3 -m pytest tests/bronze/test_refresh_bronze_fed.py -v
78 passed in 1.90s
```

```
$ python3 /tmp/round3_columbus_fail.py
=== Round-3 code results (WRONG) ===
_is_ny_biz(2024-10-14, bond_market) = True
_next_ny_biz(2024-10-11, bond_market) = 2024-10-14
_ny_avail(2024-10-11) = 2024-10-14 20:30:00+00:00

=== Proving old code FAILS new assertions ===
PASS: old _is_ny_biz(2024-10-14) = True (fails new assertion)
PASS: old _next_ny_biz(2024-10-11) = 2024-10-14 (fails, expected 2024-10-15)
PASS: old _ny_avail(2024-10-11) = 2024-10-14 20:30:00+00:00 (fails, expected 2024-10-15 20:30 UTC)

3/3 assertions failed against round-3 code (all expected to fail)
```

```
$ file notebooks/refresh_bronze_fed.py tests/bronze/test_refresh_bronze_fed.py
notebooks/refresh_bronze_fed.py:         Python script, Unicode text, UTF-8 text executable
tests/bronze/test_refresh_bronze_fed.py: Python script, Unicode text, UTF-8 text executable
```
===VERDICT END===