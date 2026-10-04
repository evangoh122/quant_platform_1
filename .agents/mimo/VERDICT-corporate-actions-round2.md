# VERDICT: corporate-actions-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none — all 3 blocking issues from Round 1 DeepSeek verdict resolved)

## Fixes applied

1. **[silver/08_silver_ohlcv_day_adjusted.sql:338-341] Daily `information_available_ts` — FIXED.**
   Changed `from_utc_timestamp(..., ' 16:00:00')` → `to_utc_timestamp(..., ' 16:30:00')`.
   DST verification (Python `zoneinfo` reference):
   - 2022-06-06 (EDT): `to_utc_timestamp('2022-06-06 16:30:00', 'America/New_York')` = 20:30 UTC ✓
   - 2022-12-05 (EST): `to_utc_timestamp('2022-12-05 16:30:00', 'America/New_York')` = 21:30 UTC ✓
   SQL-text tests assert `to_utc_timestamp` with `16:30` present, `from_utc_timestamp` absent.

2. **[silver/08_silver_ohlcv_day_adjusted.sql:296] `data_quality_breaks` MERGE INSERT — FIXED.**
   Replaced `INSERT *` with explicit 16-column `INSERT (…) VALUES (…)` list.
   `reviewed_by`/`reviewed_ts` set to `NULL` in VALUES. Tests parse target DDL and
   assert INSERT lists every target column exactly once.

3. **[notebooks/refresh_bronze_corporate_actions.py:135-176] CLI flags — FIXED.**
   Added `argparse.ArgumentParser` with `--mode`, `--source`, `--symbol-start`,
   `--symbol-end`, `--delay-seconds`, `--max-retries`, `--run-id`. Uses
   `parse_known_args` (unknown flags ignored). Args take precedence over
   `dbutils.widgets` (interactive fallback preserved). Tests verify `--mode write`
   sets write mode and omitting it keeps dry-run default.

## Other refresh notebooks (not edited, noted only)
- `notebooks/refresh_bronze_equities.py` — uses `dbutils.widgets` only (no argparse). Same pattern as the pre-fix corporate_actions notebook. Not in scope for this round.
- `notebooks/refresh_bronze_fed.py` — already uses argparse ✓
- `notebooks/refresh_bronze_options.py` — already uses argparse ✓
- `notebooks/refresh_bronze_cot.py` — already uses argparse ✓

## Non-blocking notes
- (from DeepSeek Round 1) Dedup `ROW_NUMBER` partitions on `(symbol, event_ts)` not `(symbol, event_date)` — correct only because daily provider stamps single time-of-day.
- (from DeepSeek Round 1) `self._delay` stored but never used in `etl/corporate_actions.py`.
- (from DeepSeek Round 1) `matched_split_ratio` stores `1.0` (not `NULL`) for non-split candidates.
- (from DeepSeek Round 1) `silver/08_silver_ohlcv_day_adjusted.sql` registered twice in `pipelines/run_silver_gold.py` — idempotent but wasteful.

## Checks run
```
$ python3 -m pytest -q -p no:cacheprovider tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py
87 passed in 0.68s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py
87 passed in 0.68s            # pyspark import-blocked — proves no pyspark/network needed

$ python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
625 passed, 67 skipped in 118.39s

$ git diff --check && git status --porcelain
(clean diff, no whitespace errors, 4 files modified)
```

All LF line endings. No secrets committed. No edits to `.agents/dispatch.sh`.