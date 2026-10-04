# VERDICT: options-right-case — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None.

## Non-blocking notes
- The silver SQL files (03_silver_options_quotes.sql, 04_silver_options_trades.sql) already normalize `right` to 'C'/'P' using `lower()`/`upper()` — no change needed.
- The etl/extract_polygon.py and etl/extract_options.py write to DuckDB tables (polygon_option_bars, option_chains), not Bronze Delta tables — out of scope.
- docs/BRONZE_REFRESH_PLAN.md line 223 confirms uppercase 'CALL'/'PUT' as canonical form.

## Sites fixed (4 total)

### gold/02_gold_options_features.sql
1. Line 73: `right = 'PUT'` → `UPPER(right) = 'PUT'`
2. Line 74: `right = 'CALL'` → `UPPER(right) = 'CALL'`
3. Line 115: `right = 'put'` → `UPPER(right) = 'PUT'`
4. Line 123: `right = 'call'` → `UPPER(right) = 'CALL'`

### notebooks/refresh_bronze_options.py
5. Line 206: `right = "call"` → `right = "CALL"` (parse_opra_symbol)
6. Lines 247-254: `_right_from_contract_type` returns 'CALL'/'PUT' instead of 'call'/'put'
7. Lines 476-477: `_shape_day` Spark when() emits 'CALL'/'PUT' instead of 'call'/'put'

## Checks run
- `python -m pytest -q tests/gold/test_options_right_case.py tests/bronze/test_refresh_bronze_options.py` → 40 passed

## Test coverage

### New tests (tests/gold/test_options_right_case.py)
1. `test_gold_sql_right_comparisons_are_case_insensitive` — regex scan of gold/02 for bare `right = '...'` not wrapped in UPPER/LOWER
2. `test_day_cte_counts_all_case_variants` — DuckDB semantic: day CTE counts PUT/put/CALL/call
3. `test_mutation_proof_revert_upper_fails` — reverting UPPER() → bare `right =` makes test miss lowercase rows
4. `test_parse_opra_symbol_emits_uppercase` — ingestion helper emits 'PUT'/'CALL'
5. `test_right_from_contract_type_emits_uppercase` — normalizer returns 'CALL'/'PUT'
6. `test_shape_quote_row_right_uppercase` — snapshot row builder emits uppercase
7. `test_repo_wide_no_case_sensitive_right_comparisons` — regex scan of silver/gold/pipelines/

### Updated tests (tests/bronze/test_refresh_bronze_options.py)
- test_parse_opra_symbol_call: `right == "call"` → `right == "CALL"`
- test_parse_opra_symbol_put: `right == "put"` → `right == "PUT"`
- test_shape_quote_row_full: `row["right"] == "call"` → `row["right"] == "CALL"`
- test_shape_quote_row_right_put: `row["right"] == "put"` → `row["right"] == "PUT"`
- test_shape_quote_row_right_normalisation: all expectations updated to uppercase

## Mutation proof output
```
Mutated SQL (reverting one UPPER to bare `right =`):
  SPY 2026-09-01: put_volume = 300 (misses 100 lowercase 'put' rows)
Correct SQL (with UPPER):
  SPY 2026-09-01: put_volume = 400 (counts all case variants)
```

## Backfill SQL
Created `sql/maintenance/2026-10-04_normalize_options_right_case.sql` — idempotent UPDATE with pre/post verification SELECTs. Do NOT run in CI; Claude runs it live on the SQL warehouse.