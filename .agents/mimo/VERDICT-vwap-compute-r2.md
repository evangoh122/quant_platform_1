# VERDICT: vwap-compute-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
- None.

## Non-blocking notes
- `tests/silver/test_ohlcv_day_adjusted.py::TestApplyOnceSemantics::test_silver_merge_deletes_rows_no_longer_in_source` is a pre-existing bug (standalone function inside a class, receives unexpected `self`). Not related to this change.

## Checks run
- `pytest tests/pipelines/test_run_silver_gold.py -v` → 6/6 pass
- `pytest tests/gold/test_gold_vwap_sql.py -v` → 9/9 pass
- `pytest tests/silver/test_ohlcv_day_adjusted.py -v` → 61/62 pass (1 pre-existing failure)
- Mutation: ALTER TABLE re-added to SQL → `test_sql_has_no_add_columns` FAILS ✓
- Mutation: `if not missing: return` removed from `ensure_day_adjusted_columns` → `test_column_present_no_alter` FAILS ✓
- Mutation: gold SQL `(close - session_vwap) / NULLIF(session_vwap, 0)` changed to `close - session_vwap` → `test_vwap_deviation_from_session_vwap` FAILS (bar2: 0.25 vs expected 0.023) ✓

## Changes made

### 1. Removed unconditional ALTER TABLE from SQL
`silver/08_silver_ohlcv_day_adjusted.sql:82-84` — deleted the unconditional `ALTER TABLE ... ADD COLUMNS (vwap_source STRING)`. This was idempotent but ran every execution regardless of whether the column already existed.

### 2. Added `ensure_day_adjusted_columns()` to pipeline
`pipelines/run_silver_gold.py` — new function modeled exactly on `ensure_model_availability_columns`:
- Reads existing columns from `silver_ohlcv_day_adjusted` via `spark.table().columns`
- Adds only the missing `vwap_source STRING` column via `ALTER TABLE ... ADD COLUMNS`
- Skips silently if table is unreadable (no raise)
- Called before the silver step loop (unconditionally when not `--counts`)

### 3. Tests for `ensure_day_adjusted_columns`
`tests/pipelines/test_run_silver_gold.py` — new test file with 6 tests using a fake Spark:
- Column missing → one ALTER issued
- Column present → no ALTER
- Table unreadable → no ALTER, no raise
- Mutation proof (always ALTER → present test fails)
- ALTER targets correct table name
- Multiple missing columns handled

### 4. SQL contract test: no ADD COLUMNS
`tests/silver/test_ohlcv_day_adjusted.py` — new `test_sql_has_no_add_columns` asserts the SQL file contains no `ADD COLUMNS` (enforces the column addition is done via `ensure_day_adjusted_columns()`).

### 5. vwap_deviation uses real SQL expression
`tests/gold/test_gold_vwap_sql.py` — `test_vwap_deviation_from_session_vwap` now executes the REAL `(close - session_vwap) / NULLIF(session_vwap, 0)` expression from `gold/01_gold_ohlcv_features.sql` through the full CTE chain (`lagged` → `returns` → `feats`) via the DuckDB shim. Python re-computation deleted. New `test_mutation_vwap_deviation_uses_session_vwap_not_vwap` mutation test proves changing the expression to absolute diff (`close - session_vwap`) produces different output (0.25 vs 0.023).