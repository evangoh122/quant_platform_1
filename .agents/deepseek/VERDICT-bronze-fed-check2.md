===VERDICT START===
# VERDICT: bronze-fed — DeepSeek (independent re-check, round 3)

**Status:** CHANGES_REQUESTED
**Round:** 3 (re-check of round-3 SIFMA-calendar fix)
**Branch:** `slice/bronze-fed`

Checker verdict: I read and ran the code/tests but did not modify the worktree.
All scratch work happened under `/tmp` (`/tmp/sifma_check.py`, `/tmp/probe_cal2.py`,
`/tmp/regress2/`).

## Blocking findings

- [notebooks/refresh_bronze_fed.py:94-118] `_bond_market_holidays` removes
  **Columbus Day** (`:107-113`) and **Veterans Day** (`:115-117`) from the
  market-rate availability calendar, treating them as business days. That is the
  wrong publication calendar for the H.15 constant-maturity Treasury series.
  `DGS2`/`DGS10`/`T10Y2Y`/`T10Y3M` are published by the Fed/Treasury on the
  **federal** holiday calendar, and both are closed on Columbus Day and Veterans
  Day — so no constant-maturity yield is published those days even though the
  SIFMA bond market is open. Live FRED `fredgraph.csv` proves the gap:
  `DGS10`, `DGS2`, `T10Y2Y`, `T10Y3M` all have **no observation** on
  `2024-10-14` (Columbus), `2024-11-11` (Veterans), `2025-10-13`,
  `2025-11-11`, `2022-10-10`, `2022-11-11`, `2023-10-09`. Concrete failure:
  `_ny_available_ts(date(2024,10,11))` → `2024-10-14 20:30 UTC`, but the
  Friday 10-11 value is not actually available until Tuesday 2024-10-15 — a
  one-business-day **look-ahead**. This is the exact inverse of the Good Friday
  bug round 3 fixed: the fix should have been "federal + Good Friday", not
  "federal + Good Friday − Columbus − Veterans".

- [tests/bronze/test_refresh_bronze_fed.py:145-147,152-153,163-165,209-213]
  The tests now **encode** the wrong behaviour, so a passing suite does not
  catch the look-ahead:
  `test_columbus_day_is_bond_market_business_day` asserts
  `_is_ny_business_day(date(2024,10,14), "bond_market") is True`;
  `test_fri_before_columbus_day_rolls_to_monday_bond` asserts
  `_next_ny_business_day(date(2024,10,11), "bond_market") == date(2024,10,14)`;
  `test_columbus_day_bond_market_available_same_day` asserts
  `_ny_available_ts(date(2024,10,11)) == datetime(2024,10,14,20,30,0,tz=utc)`.
  These assertions are false w.r.t. actual H.15 availability.

## Non-blocking notes

- The Veterans Day removal is also internally inconsistent: it discards only the
  literal `date(year,11,11)`, so in years where Nov 11 falls on a weekend (2023)
  the *observed* holiday `2023-11-10` is left in the set (accidentally correct
  for DGS), while in 2022/2024/2025 the weekday Nov 11 is removed (wrong). The
  Columbus Day removal (computed as "2nd Monday in October") does not have this
  inconsistency. Either way the removal is the wrong call.
- Scope of impact: ~4 series (DGS2, DGS10, T10Y2Y, T10Y3M) × 7 affected days in
  the 2022–2026 window (4 Columbus + 3 weekday Veterans) ≈ 28 rows marked
  available one business day early. `DFF`/`DFEDTARU`/`DFEDTARL` carry forward on
  FRED (DFF has a value on 2024-10-14), so they are not cleanly affected the same
  way, but they share the same (wrong) calendar.
- Good Friday fix is correct and verified: `_next_ny_business_day(2024-03-28)`
  → `2024-04-01`, `_next_ny_business_day(2025-04-17)` → `2025-04-21`; DST via
  `zoneinfo` is correct (summer 20:30 UTC, winter 21:30 UTC). No other H.15 gap
  exists in 2022–2026: a full sweep of all weekdays vs. live `DGS10` found the
  only missing weekdays to be Columbus and Veterans days (plus `2026-10-01/02`,
  which are simply not yet in the live feed — the feed currently ends
  `2026-09-30`). The Jan 9 2025 national-day-of-mourning is **not** a gap:
  `DGS10` has a value (`4.68`) that day (SIFMA early close, not a full close).

## Answers to the four check questions

1. **Next-business-day correctness.** Weekends: correct. DST: correct
   (`zoneinfo`). Good Friday: now correct. **Columbus Day and Veterans Day:
   wrong** — removed from the calendar, but no H.15 Treasury yield is published
   on those days (Fed/Treasury closed). The SIFMA "bond-market open" framing is
   the wrong model: H.15 publication follows the **federal** calendar plus Good
   Friday, not the bond-market calendar. This makes the rate available a day
   early for the preceding business-day observation (blocking finding above).
2. **Available before published?** Yes. A Thursday/Friday `DGS2`/`DGS10`/
   `T10Y2Y`/`T10Y3M` observation before a Columbus or Veterans Day is assigned
   `information_available_ts` on that holiday, a day the value is not published.
   Concrete: `_ny_available_ts(date(2024,10,11))` = `2024-10-14 20:30 UTC` but
   the next published DGS10 value is Tuesday 2024-10-15.
3. **Append-only + anti-join.** Correct and unchanged from round 1.
   `notebooks/refresh_bronze_fed.py:428` is the only write:
   `df.write.format("delta").mode("append").saveAsTable(fqn)`. No
   `UPDATE`/`DELETE`/`MERGE`/`OVERWRITE`/`replaceWhere` (grep confirmed).
   `select_new_rows` (`:312-338`) anti-joins candidates against the natural key
   `(series_id, observation_date, vintage_date, value)` and de-dups within batch;
   a changed `value` is a distinct key → appended as a new vintage, never an
   update of the old row. Same-day re-runs cannot duplicate.
4. **Tests call production code / catch a `max()` regression?** Yes to both.
   `tests/bronze/test_refresh_bronze_fed.py` imports the production functions
   directly. I patched a scratch copy under `/tmp/regress2` to
   `info_ts = max(_ny_available_ts(...), ingest_ts)` and re-ran: **3 failed**
   (`test_market_rate_info_ts_after_ingest`,
   `test_market_rate_historical_info_ts_not_ingest`,
   `test_market_rate_summer_vs_winter_utc`). The worktree was never edited.
   (But note: the tests do *not* catch the new Columbus/Veterans look-ahead,
   because they assert it as expected behaviour.)

## Checks run

```
$ python3 -m pytest tests/bronze/test_refresh_bronze_fed.py -q
71 passed in 1.78s
```

```
$ python3 /tmp/patch_regress2.py && cd /tmp/regress2 && PYTHONPATH=/tmp/regress2 python3 -m pytest test_refresh_bronze_fed.py -q
# after patching info_ts = max(_ny_available_ts(...), ingest_ts)
FAILED test_market_rate_info_ts_after_ingest
FAILED test_market_rate_historical_info_ts_not_ingest
FAILED test_market_rate_summer_vs_winter_utc
3 failed, 68 passed in 2.12s
```

```
$ python3 /tmp/probe_cal2.py
Columbus 2024-10-14 biz(bond_market)? True      # WRONG: no H.15 that day
Veterans 2024-11-11 biz(bond_market)? True      # WRONG: no H.15 that day
ny_available_ts 2024-10-11 -> 2024-10-14 20:30:00+00:00
ny_available_ts 2024-11-08 -> 2024-11-11 21:30:00+00:00
next federal day after 2024-10-11 -> 2024-10-15  # correct
next federal day after 2024-11-08 -> 2024-11-12  # correct
```

```
$ python3 /tmp/sifma_check.py
weekdays NOT in code bond_market holiday set but MISSING DGS10:
2022-10-10, 2022-11-11, 2023-10-09, 2024-10-14, 2024-11-11,
2025-10-13, 2025-11-11   (+ 2026-10-01/02 = data-lag artifacts)
```

```
$ curl -s 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10' | grep -E '2024-10-1[0-6]'
2024-10-10,4.09
2024-10-11,4.08
2024-10-14,          # Columbus Day: no DGS10
2024-10-15,4.03
```

```
$ grep -nE 'UPDATE|DELETE|MERGE|overwrite|replaceWhere|mode\(' notebooks/refresh_bronze_fed.py
428:    df.write.format("delta").mode("append").saveAsTable(fqn)
```
===VERDICT END===
