===VERDICT START===
# VERDICT: bronze-fed — DeepSeek (independent re-check, round 4)

**Status:** APPROVED
**Round:** 4 (re-check of the round-4 H.15-calendar fix, `98af9a0..HEAD`)
**Branch:** `slice/bronze-fed`

Checker verdict: I read and ran the code/tests but did not modify the worktree.
All scratch work happened under `/tmp` (`/tmp/check_fed_calendar2.py`,
`/tmp/prove_regression.py`).

## Blocking findings

None. The round-4 change is correct and resolves the Columbus/Veterans
look-ahead that `check2` flagged.

## Non-blocking notes

- [notebooks/refresh_bronze_fed.py:94-108] The H.15 calendar (federal + Good
  Friday) is **over-strict by 3 weekdays** for the DGS series. FRED actually
  published `DGS2`/`DGS10`/`T10Y2Y`/`T10Y3M` on `2023-04-07` (Good Friday),
  `2023-11-10` (Veterans Day observed), and `2026-04-03` (Good Friday), while
  the code treats those as holidays. Consequence: availability for the preceding
  observation is delayed to the following Monday/Tuesday. This is the safe
  direction (never early), so it is not blocking, but it shows Good-Friday
  publication is inconsistent in FRED across years (published 2023/2026, missing
  2024/2025) and the fixed calendar cannot be exact in both directions.

- [notebooks/refresh_bronze_fed.py:361-386] `_get_existing_keys` performs the
  "anti-join" by `.collect()`ing the full `(series_id, observation_date,
  vintage_date, value)` key set to the driver. Functionally correct for
  idempotency, but it is not the Spark left anti-join the BUILD spec literally
  requests and will not scale with table size (a performance lane concern, not
  a correctness defect).

- The original BUILD spec's `unsafe_rows` check (`information_available_ts <
  ingest_ts` → must be 0) is now stale: the round-2 amendment deliberately
  removed `max(next_business_day, ingest_ts)`, so historical `market_rate` rows
  are *intended* to have `information_available_ts < ingest_ts`. Anyone reusing
  that SQL verbatim will see ~90k "unsafe" rows that are in fact correct.

## Answers to the four check questions

1. **Next-business-day correctness / calendar completeness.** Correct in the
   only direction that matters. Weekends: correct (`_next_ny_business_day`
   skips `weekday() >= 5`). DST: correct (`notebooks/refresh_bronze_fed.py:84`
   `_NY_TZ = ZoneInfo("America/New_York")` → 16:30 EDT = 20:30 UTC, 16:30 EST =
   21:30 UTC). Federal holidays: correct (pandas `USFederalHolidayCalendar`),
   and Good Friday is added via `_easter_sunday - 2` (`:104-107`). A full
   data-driven sweep of all 7 `market_rate` series over 2022-01-01..2026-10-03
   against live `fredgraph.csv` found **0 dates** where FRED has a missing (`.`)
   value but the code treats it as a business day (`missing_but_business_day=0`
   for DFF, DGS2, DGS10, T10Y2Y, T10Y3M, DFEDTARU, DFEDTARL). So there is no
   remaining bond-market-only / special closure that would make a rate available
   a day early. The 2025-01-09 national-day-of-mourning is **not** a gap: all 7
   series carry a value that day (e.g. DGS10=4.68, DFF=4.33). Early-close days
   are irrelevant: H.15 publishes 16:15 ET and availability is 16:30 ET.

2. **Available before published?** No. `avail <= obs` is 0 for all 7 series,
   and `_ny_available_ts` always returns a strictly-later calendar day. Combined
   with (1), no `market_rate` row can be available on a day its series was not
   published.

3. **Append-only + anti-join.** Correct. The only write is
   `notebooks/refresh_bronze_fed.py:418`
   `df.write.format("delta").mode("append").saveAsTable(fqn)` — no
   `UPDATE`/`DELETE`/`MERGE`/`OVERWRITE`/`replaceWhere`. `select_new_rows`
   (`:302-328`) de-dups within batch and skips keys already in the target on
   `(series_id, observation_date, vintage_date, value)`. `vintage_date =
   ingest_ts.date()` (`:284`) means a revised value is a new 4-column key →
   appended as a new vintage, never an update of the old row. Same-day re-runs
   cannot duplicate.

4. **Tests call production functions and catch a `max()` regression.** Yes.
   `tests/bronze/test_refresh_bronze_fed.py` imports the production module
   (`from notebooks.refresh_bronze_fed import ...`). I proved the regression with
   a scratch copy under `/tmp` (worktree never edited): patching
   `info_ts = max(_ny_available_ts(...), ingest_ts)` makes
   `test_market_rate_info_ts_after_ingest` and
   `test_market_rate_historical_info_ts_not_ingest` **fail** (expected
   `2026-10-02 20:30` and `2020-01-03 21:30` become `ingest_ts`). Current code
   passes both.

## Checks run

```
$ python3 -m pytest tests/bronze/test_refresh_bronze_fed.py -q
78 passed in 1.30s
```

```
$ python3 /tmp/check_fed_calendar2.py     # full 2022-2026 sweep vs live FRED
DFF:     missing_but_business_day=0  avail<=obs=0
DGS2:    missing_but_business_day=0  avail<=obs=0
DGS10:   missing_but_business_day=0  avail<=obs=0   (over-conservative: 2023-04-07, 2023-11-10, 2026-04-03)
T10Y2Y:  missing_but_business_day=0  avail<=obs=0
T10Y3M:  missing_but_business_day=0  avail<=obs=0
DFEDTARU:missing_but_business_day=0  avail<=obs=0
DFEDTARL:missing_but_business_day=0  avail<=obs=0
2025-01-09 (national mourning): DFF=4.33 DGS2=4.27 DGS10=4.68 T10Y2Y=0.41 T10Y3M=0.33 DFEDTARU=4.50 DFEDTARL=4.25
```

```
$ python3 /tmp/prove_regression.py       # scratch copy, worktree untouched
[current]   after_ingest PASS, historical PASS
[regressed] after_ingest FAIL (got 2026-10-03 12:00, exp 2026-10-02 20:30)
            historical FAIL (got 2026-10-03 12:00, exp 2020-01-03 21:30)
PROOF: tests DO catch the max(next_business_day, ingest_ts) regression.
```
===VERDICT END===
