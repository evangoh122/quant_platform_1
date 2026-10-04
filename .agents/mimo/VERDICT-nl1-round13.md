===VERDICT START===
# VERDICT: nl1-round13 — MiMo
**Status:** APPROVED
**Round:** 13

## Blocking findings

None.

## Non-blocking notes

- CoverageStatus was imported but unused in policy.py — removed in this round.
- The `_parse_sql_ctes_and_final_select` parser uses simple whitespace-split for CTE name matching. This is adequate for the current DDL but would need refinement if CTE names appeared as substrings of other identifiers (not the case today).

## Checks run

- `python3 -m pytest tests/analytics_nl -q` → 338 passed (14.5s)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → 338 passed (pyspark hidden)
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- `git diff HEAD~3..HEAD -- tests` → additions only; no tests deleted/weakened

## Changes made

### Item 1 — Fix _has_as_of_filter_before_window (test_ddl.py)
- Rewrote `_has_as_of_filter_before_window` to split SQL into CTE list and final SELECT using parenthesis depth tracking (`_parse_sql_ctes_and_final_select`).
- Old regex approach attributed the final SELECT to the last CTE body, making the test vacuous.
- Added BFS-based transitive dependency check: for each window CTE, verify some ancestor CTE contains `information_available_ts <= :as_of`.
- Added second mutation proof for serve_daily_equity_metrics_v1.
- Mutation proof (serve_options_metrics_v1): remove as_of from CTE, add to final WHERE → test FAILS.
- Mutation proof (serve_daily_equity_metrics_v1): remove as_of from daily_prices CTE → test FAILS.

### Item 2 — Fix _extract_view_select_columns (test_source_schema.py)
- Rewrote `_extract_view_select_columns` with CTE-aware final-SELECT extraction (same depth-tracking parser).
- Changed `^\s*SELECT\s` regex to `^\s*SELECT(?:\s|$)` to handle SELECT alone on a line.
- Added `_extract_column_aliases_from_select` helper: handles `AS x`, `t.col`, functions with commas in parens.
- Empty extraction is now an assertion FAILURE (never `continue`).
- Added explicit expected columns test for serve_daily_prices_v1: `{symbol, event_date, open_price, high_price, low_price, close_price, volume, information_available_ts}`.
- Mutation proof: rename close_price → close_price_bogus in registry → test FAILS.

### Item 3 — Enforce CoverageStatus enum
- Added `CoverageResult` model in contracts.py with `model_validator`: agg_value nullable ONLY when status == INSUFFICIENT_DATA.
- Added registry validation: aggregate entries with `status` output_field must use type `coverage_status`, agg_value must be nullable.
- Updated semantic_registry_v1.yaml: `implied_volatility.aggregate` status type changed from `string` to `coverage_status`.
- Removed unused CoverageStatus import from policy.py.
- 6 new tests: ok+value valid, INSUFFICIENT_DATA+null valid, ok+null rejected, INSUFFICIENT_DATA+value rejected, string rejected (strict mode), enum count check.

### Item 4 — Guard return_1d > -1 in DDL
- Added `GREATEST(1 + return_1d, 1e-10)` before LN in entity_cumulative and benchmark_cumulative CTEs.
- Documented assumption: daily returns on positive-priced equities bounded above -1; guard is defensive.
- Updated window pattern regex in test to match `EXP(SUM(LN(GREATEST...)))`.

## Test count delta

Before: 329 passed. After: 338 passed (+9 new tests).
===VERDICT END===