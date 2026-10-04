# VERDICT: corporate-actions-round8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
(none)

## Non-blocking notes
- `_deduped_daily` fixture table schema expanded from 2 columns to 10 to support break-detection CTEs. Existing factor tests unaffected (INSERT with explicit column list).
- Bronze tests timeout is pre-existing (Databricks serverless connectivity issue), unrelated to round 8 changes.

## Checks run
- `python -m pytest -q tests/silver/test_silver_sql_semantics.py` → **14 passed** (10 original + 4 new)
- `python -m pytest -q tests/silver tests/test_security.py` → **92 passed, 3 skipped**
- `python -m pytest -q tests/silver/test_silver_sql_semantics.py -k "mutation" -v` → **3 passed** (test_mutation_dedupe_removal_fails, test_mutation_drop_source_filter_fails, test_mutation_break_candidate_predicate_required)

## What was built

### Task 1: Rewrite `test_mutation_drop_source_filter_fails`
- Fixture: massive AMZN 20:1 (fetched_ts 2026-01-01) + yfinance AMZN 15.0 (fetched_ts 2026-02-01, LATER)
- Positive test: real SQL (with `WHERE source = 'massive'`) → factor exactly 20.0
- Mutation test: source filter removed → dedup picks yfinance (later fetched_ts) → factor exactly 15.0
- Proves the `source = 'massive'` filter is load-bearing

### Task 2: Break detection against real SQL
- Extracted `_adjusted`, `_break_candidates`, `_classified_breaks` CTEs from `silver/08_silver_ohlcv_day_adjusted.sql`
- Ran full pipeline in DuckDB on fixtures via `_run_break_ctes()` helper
- (a) MEME -50% drop, no split → 1 break row: `UNEXPLAINED_PENDING`, `is_masked=True`, `split_error=0.5`
- (b) AMZN 20:1 split, ~+2% adjusted move → 1 break row: `SPLIT_EXPLAINED`, `is_masked=False`, `split_error≈0.02`
- (c) SPLITBAD: 20:1 split but raw move doesn't match → 1 break row: `UNEXPLAINED_PENDING`, `is_masked=True`, `split_error≈0.20`
- Mutation: remove `abs(raw_gross_return - 1) >= 0.40` predicate → AMZN small ~2% daily moves become false break candidates
- Existing `_compute_break` Python reference tests preserved unchanged

### Task 3: duckdb in requirements
- Added `duckdb>=0.10.0` to `requirements.txt`

## Commit
- `eb5cacb` on `slice/corporate-actions`: "round8: rewrite source-filter mutation test, add break-detection SQL tests, add duckdb to requirements"