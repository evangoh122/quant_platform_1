===VERDICT START===
# VERDICT: bronze-fed round 3 — MiMo

**Status:** APPROVED
**Round:** 3
**Branch:** `slice/bronze-fed`
**Commit:** `d00727d`

## What changed

Replaced `USFederalHolidayCalendar` with a SIFMA-style bond-market calendar for
`market_rate` (Treasury H.15) series availability. The new calendar includes
federal holidays **plus Good Friday**, **minus Columbus Day and Veterans Day**.

New pure functions:
- `_easter_sunday(year)` — Anonymous Gregorian algorithm, no external dependency
- `_bond_market_holidays(start, end)` — SIFMA holiday set
- `_is_ny_business_day(d, calendar="federal")` — calendar-aware
- `_next_ny_business_day(d, calendar="federal")` — calendar-aware
- `_ny_available_ts(obs_date, revision_class="market_rate")` — routes to bond_market calendar for market_rate

Non-market-rate series (`revised_macro`) continue to use the federal calendar.

## Blocking findings

None.

## Non-blocking notes

- The `_easter_sunday` implementation uses the Anonymous Gregorian algorithm (valid 1583–4099). FRED data range is well within this.
- Columbus Day and Veterans Day removal is conservative: the bond market is open on those days, so using the federal calendar made availability one day late (not a look-ahead). The fix is still correct — it matches actual H.15 publication dates.
- `dateutil.easter` was available but a pure function was preferred per the request. No new dependency introduced.

## Checks run

```
$ python3 -m pytest tests/bronze/test_refresh_bronze_fed.py -v
71 passed in 1.89s
```

```
$ python3 scratch_gf_test.py  (in /tmp only, not committed)
=== Scratch regression test (federal calendar) ===
  2022: Thu 2022-04-14 Good Friday 2022-04-15
    federal -> 2022-04-15 (WRONG: lands on Good Friday)
    bond    -> 2022-04-18 (correct: skips to Monday)
  2023: Thu 2023-04-06 Good Friday 2023-04-07
    federal -> 2023-04-07 (WRONG: lands on Good Friday)
    bond    -> 2023-04-10 (correct: skips to Monday)
  2024: Thu 2024-03-28 Good Friday 2024-03-29
    federal -> 2024-03-29 (WRONG: lands on Good Friday)
    bond    -> 2024-04-01 (correct: skips to Monday)
  2025: Thu 2025-04-17 Good Friday 2025-04-18
    federal -> 2025-04-18 (WRONG: lands on Good Friday)
    bond    -> 2025-04-21 (correct: skips to Monday)
  2026: Thu 2026-04-02 Good Friday 2026-04-03
    federal -> 2026-04-03 (WRONG: lands on Good Friday)
    bond    -> 2026-04-06 (correct: skips to Monday)
All Good Fridays verified: federal calendar is wrong, bond calendar is correct.
```

```
$ xxd notebooks/refresh_bronze_fed.py | head -3
00000000: 2222 220a ...
(LF line endings confirmed)
```

```
$ git diff --cached --stat
 notebooks/refresh_bronze_fed.py         | 77 +++++++++++++++++++++++----
 tests/bronze/test_refresh_bronze_fed.py | 93 +++++++++++++++++++++++++++++++++
 2 files changed, 160 insertions(+), 10 deletions(-)
```
===VERDICT END===