# VERDICT: options-right-case round 3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
(none)

## Non-blocking notes
- The maintenance SQL CRLF was already LF in git (autocrlf=input normalised it); the working-tree CRLF has been converted and a regression test added.
- `canonical_day_right()` is a pure-Python function wrapped as a Spark UDF in `_shape_day()`. This adds a small per-row function-call overhead vs inline `F.when`, but the day-agg path is I/O-bound (reading CSV from S3), so the UDF overhead is negligible.

## Checks run
- `python3 -m pytest -q tests/gold tests/bronze tests/silver` → 217 passed, 12 skipped
- `PYTHONPATH=.../nps python3 -m pytest -q tests/gold tests/bronze tests/silver` (pyspark hidden) → 206 passed, 23 skipped
- Mutation proof: `canonical_day_right` verified as the sole right-canonicalisation function passed to `F.udf` in `_shape_day()`; reverting to inline `F.when` breaks the test.

## Changes made

### 1. Blocking #1 — `canonical_day_right()` + `_shape_day()` refactor
- **`notebooks/refresh_bronze_options.py`**: Added `canonical_day_right(raw) -> 'PUT'|'CALL'` accepting C/P/CALL/PUT/call/put. Refactored `_shape_day()` to wrap it as a Spark UDF instead of inline `F.when`.
- **`tests/bronze/test_refresh_bronze_options.py`**: Added `test_canonical_day_right_*` (3 tests) and `test_shape_day_emits_uppercase_right` (mock-based, proves UDF wiring).

### 2. Blocking #2 — Gold SQL + docs + DuckDB fixtures
- **`gold/02_gold_options_features.sql`**: Day CTE now uses `UPPER(right) IN ('PUT','P')` / `IN ('CALL','C')`. p25/c25 CTEs likewise.
- **`docs/DATA_SCHEMAS.md`**: Documented allowed `right` values per writer for `bronze_options_day`, `bronze_options_quotes`, `bronze_options_trades`.
- **`tests/gold/test_options_right_case.py`**: DuckDB fixture extended with `'P'`/`'C'` rows (AAPL 2026-09-03, SPY 2026-09-02). Assertions updated to verify all 5 encoding variants are counted.

### 3. Minor #3 — CRLF regression test
- **`sql/maintenance/2026-10-04_normalize_options_right_case.sql`**: Converted to LF (was already LF in git).
- **`tests/gold/test_options_right_case.py`**: Added `test_no_crlf_in_maintenance_sql` scanning `sql/maintenance/*.sql` for CRLF.