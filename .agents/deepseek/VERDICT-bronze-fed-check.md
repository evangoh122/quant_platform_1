===VERDICT START===
# VERDICT: bronze-fed — DeepSeek (independent check)

**Status:** CHANGES_REQUESTED
**Round:** 3 (check of round-2 market-rate availability fix)
**Branch:** `slice/bronze-fed`

This is a checker verdict: I read and ran the code/tests but did not modify the
worktree. All scratch work happened under `/tmp/regress`.

## Blocking findings

- [notebooks/refresh_bronze_fed.py:23,68-72,83-90] The "next business day" is
  computed with `pandas.tseries.holiday.USFederalHolidayCalendar`, which **omits
  Good Friday**. Good Friday is a full SIFMA bond-market close and no H.15
  Treasury constant-maturity yield is published that day — FRED `DGS10` has no
  observation on `2024-03-29` or `2025-04-18` (verified live via
  `fredgraph.csv`). The calendar is therefore the wrong one for the Treasury
  yield series. Concrete failure:
  `_next_ny_business_day(date(2024,3,28))` → `2024-03-29` (Good Friday), so
  `_ny_available_ts(date(2024,3,28))` → `2024-03-29 20:30 UTC`. Under the
  amendment's "next business day" rule the Thursday observation must roll to
  **Monday 2024-04-01**, not Good Friday. A Thursday-before-Good-Friday row for
  `DGS2`/`DGS10`/`T10Y2Y`/`T10Y3M` is thus marked available one business day
  early — a look-ahead in the 2022–2026 backtest. Five Good Fridays fall in that
  window (2022-04-15, 2023-04-07, 2024-03-29, 2025-04-18, 2026-04-03), so the
  mislabel affects ~4 series × ~5 Thursdays ≈ 20 rows.

  Fix direction: use a bond-market/H.15 publication calendar (SIFMA: includes
  Good Friday, excludes Columbus/Veterans Day) for the market-rate availability
  roll, not `USFederalHolidayCalendar`. The requirement in the amendment is
  "next NY business day" where a business day is a day the rate is actually
  published; Good Friday is not one.

## Non-blocking notes

- Inverse calendar mismatch (conservative, not a leak): the federal calendar
  **includes** Columbus Day and Veterans Day, but the bond market is **open** on
  those days, so availability is computed one business day **late**.
  `_is_ny_business_day(date(2024,10,14))` → `False`,
  `_is_ny_business_day(date(2024,11,11))` → `False`. This loses data for the
  backtest but does not create look-ahead.
- DST handling is correct: `zoneinfo` (`America/New_York`) with
  `.astimezone(utc)`; summer → 20:30 UTC, winter → 21:30 UTC (tests confirm).
  The round-2 hardcoded-EST defect is fixed.
- Weekend handling is correct (`weekday >= 5` skipped); 16:30 ET is always after
  the 02:00 DST transition, so no transition ambiguity.
- Honesty note on severity: the live FRED/Treasury docs describe constant-maturity
  yields as same-day (~3:30 PM trading quotes, H.15 posted 4:15 PM), which would
  make "next business day" conservative and Good Friday non-leaking in reality.
  I could not resolve same-day vs next-day from the frozen test snapshot. The
  calendar defect itself is objective and unambiguous, and it violates the
  amendment's stated "next business day" contract either way.

## Answers to the four check questions

1. **Next-business-day correctness.** Weekends: correct. DST: correct
   (zoneinfo). Federal holidays the calendar knows: correct (e.g.
   `2025-07-03` → `2025-07-07`, matching Claude's live check). But it uses the
   wrong holiday set: Good Friday (bond-market close) is absent → marks a
   Thursday rate available on Good Friday (one business day early); Columbus Day
   and Veterans Day (bond-market open) are present → marks availability one
   business day late. See blocking finding.
2. **Available before published?** Under the amendment's "next business day"
   rule, yes: a Thursday Treasury-yield observation before Good Friday is
   assigned `information_available_ts` on Good Friday, a day no H.15 Treasury
   yield is published. Concrete: `_ny_available_ts(date(2024,3,28))` =
   `2024-03-29 20:30 UTC` but the next published DGS10 value is Monday
   2024-04-01.
3. **Append-only + anti-join.** Correct. `notebooks/refresh_bronze_fed.py:371`
   is the only write: `df.write.format("delta").mode("append").saveAsTable(fqn)`.
   No `UPDATE`/`DELETE`/`MERGE`/`OVERWRITE`/`replaceWhere` anywhere (grep
   confirmed). `select_new_rows` (`:255-281`) anti-joins candidates against the
   natural key `(series_id, observation_date, vintage_date, value)` and
   de-dups within batch via `seen`. Same-day re-runs cannot duplicate (same
   `vintage_date`); a changed `value` is a distinct key → appended as a new
   vintage, never an update of the old row.
4. **Do tests call production code / catch a `max()` regression?** Yes.
   `tests/bronze/test_refresh_bronze_fed.py` imports the production functions
   (`parse_csv_rows`, `_ny_available_ts`, …) directly. I patched a scratch copy
   under `/tmp/regress` to `info_ts = max(_ny_available_ts(obs_date), ingest_ts)`
   and re-ran the suite: **3 tests failed** (the exact market-rate availability
   assertions), proving the tests regress to red if the availability rule falls
   back to `max(..., ingest_ts)`. The worktree was never edited.

## Checks run

```
$ python3 -m pytest tests/bronze/test_refresh_bronze_fed.py -q
52 passed in 1.26s
```

```
$ cd /tmp/regress && PYTHONPATH=/tmp/regress python3 -m pytest test_refresh_bronze_fed.py -q
# after patching line 233 to info_ts = max(_ny_available_ts(obs_date), ingest_ts)
FAILED ...::test_market_rate_info_ts_after_ingest
FAILED ...::test_market_rate_historical_info_ts_not_ingest
FAILED ...::test_market_rate_summer_vs_winter_utc
3 failed, 49 passed in 1.54s
```

```
$ python3 /tmp/probe_cal.py
2024-03-28 Thursday -> next 2024-03-29 Friday available 2024-03-29 20:30:00+00:00   # Good Friday (WRONG)
2025-04-17 Thursday -> next 2025-04-18 Friday available 2025-04-18 20:30:00+00:00   # Good Friday (WRONG)
2025-07-03 Thursday -> next 2025-07-07 Monday available 2025-07-07 20:30:00+00:00   # correct
2024-10-11 Friday  -> next 2024-10-15 Tuesday available 2024-10-15 20:30:00+00:00   # Columbus Day (1 day late)
Good Friday 2024-03-29 is biz day? True
Columbus 2024-10-14 is biz day? False
Veterans 2024-11-11 is biz day? False
```

```
$ curl -s 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10' | grep -E '2024-03-2[789]|2024-04-01|2025-04-1[7-9]|2025-04-21'
2024-03-27,4.20
2024-03-28,4.20
2024-03-29,            # Good Friday: no DGS10 published
2024-04-01,4.33
2025-04-17,4.34
2025-04-18,            # Good Friday: no DGS10 published
2025-04-21,4.42
```

```
$ grep -nE 'UPDATE|DELETE|MERGE|overwrite|replaceWhere|mode\(' notebooks/refresh_bronze_fed.py
371:    df.write.format("delta").mode("append").saveAsTable(fqn)
```
===VERDICT END===
