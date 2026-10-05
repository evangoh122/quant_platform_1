===VERDICT START===
# VERDICT: nl1-round18 — MiMo (builder)
**Status:** APPROVED
**Round:** 18

## Summary

Reverted the round-17 semantic change that interpolated NULL returns as 0%. Restored `WHERE return_1d IS NOT NULL` / `WHERE bench_return IS NOT NULL` filters in `serve_relative_performance_v1`. Fixed the DuckDB-only eager `LN(0)` error in the `to_duckdb()` shim. Added 3 new tests closing both blocking findings from DeepSeek round-17 verdict.

## Changes made

1. **`docs/NL1_PROPOSED_SERVING_VIEWS.md`** (reverted):
   - Restored `AND return_1d IS NOT NULL` in `entity_returns` CTE (`:398`)
   - Restored `AND return_1d IS NOT NULL` in `benchmark_returns` CTE (`:409`)
   - Removed `COALESCE(return_1d, 0)` → `return_1d` in entity cumulative (`:433`)
   - Removed `COALESCE(bench_return, 0)` → `bench_return` in benchmark cumulative (`:460`)
   - Fixed false comment at `:425-426`: now correctly states NULLs are excluded upstream

2. **`tests/analytics_nl/_ddl_extract.py`** (shim fix):
   - Added regex for `LN(1 + <col>)` → `LN(GREATEST(1 + <col>, 1e-10))` in `to_duckdb()` shim
   - Kept legacy `LN(1 + COALESCE(col, 0))` pattern for backward compatibility
   - Documented as DuckDB evaluation-order workaround; production keeps CASE/NULL semantics

3. **`tests/analytics_nl/test_ddl.py`** (3 new tests):
   - `test_null_return_day_is_excluded`: NULL-return day produces NO output row; not silently interpolated as 0%
   - `test_mutation_coalesce_zero_in_doc_breaks_null_exclusion`: re-add COALESCE(...,0) + remove WHERE IS NOT NULL → NULL day appears as 0% (mutation proof)
   - `test_adjusted_momentum_lag_before_null_filter`: adjusted-mode with_momentum CTE does NOT filter return_1d before LAG; adding the filter is a mutation

4. **`tests/analytics_nl/test_extract_helper.py`** (updated):
   - Updated `test_relative_performance_full_extraction` assertion: no COALESCE in reverted DOC, GREATEST from shim

## Blocking findings from DeepSeek round 17 — resolution

1. **[High] COALESCE(return_1d, 0) masked NULL returns as 0%** → RESOLVED: reverted COALESCE, restored WHERE IS NOT NULL. Mutation proof: `test_mutation_coalesce_zero_in_doc_breaks_null_exclusion` catches the regression.
2. **[Medium] adjusted-mode LAG-before-null-filter not enforced** → RESOLVED: `test_adjusted_momentum_lag_before_null_filter` catches mutation of adding WHERE IS NOT NULL to adjusted with_momentum.

## Mutation proof table

| Mutation | Expected catch | Result |
|---|---|---|
| Re-add COALESCE(...,0) + remove WHERE IS NOT NULL in DOC | `test_null_return_day_is_excluded` | **1 failed** — caught (NULL day appears as 0%) |
| Add WHERE return_1d IS NOT NULL to adjusted with_momentum (:198) | `test_adjusted_momentum_lag_before_null_filter` | **1 failed** — caught |

## Checks run

- `PYTHONPATH=.../nps python3 -m pytest tests/analytics_nl -q` → **386 passed** (14.5s)
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- Mutation 1 (`/tmp/r18m1`): COALESCE mutation → `test_null_return_day_is_excluded` **FAILED** as expected
- Mutation 2 (`/tmp/r18m2`): adjusted momentum filter mutation → `test_adjusted_momentum_lag_before_null_filter` **FAILED** as expected
- Existing -100% test on mutated copy (`/tmp/r18m1`): still **PASSES** (COALESCE doesn't affect -100% detection)
===VERDICT END===