# VERDICT: nl1-round14 — MiMo
**Status:** APPROVED
**Round:** 14

## Blocking findings
None

## Non-blocking notes
- All 5 items implemented successfully
- Tests pass with mutation proofs for each item
- Schemas match after changes

## Checks run
- `python3 -m pytest tests/analytics_nl -q` → 343 passed
- `python3 -m analytics_nl.export_schemas --check` → All schemas match
- `git log --oneline -5` → 5 commits on slice/nl-contracts branch

## Implementation summary

### Item 1: Output availability = MAX over ALL contributing rows
- Added adj.information_available_ts to returns_from_source CTE with GREATEST
- Added MAX(...) OVER window for realized_vol_20d and drawdown availability
- Added MAX(...) OVER window for entity and benchmark cumulative availability
- Used GREATEST to combine all availability timestamps in final SELECT
- Added contract test to verify output availability is window MAX / GREATEST
- Mutation: remove benchmark availability from final GREATEST → FAILS

### Item 2: Sparse-data coverage for ALL four operations
- Added sample_count, coverage_ratio, status fields to IV trend/compare/rank in registry
- Removed aggregate-only restriction from coverage check in policy.py
- Updated test_iv_trend_no_coverage_check to test_iv_trend_coverage_check
- Added test_iv_compare_coverage_check and test_iv_rank_coverage_check
- All operations now trigger INSUFFICIENT_DATA when coverage is below threshold

### Item 3: Relative performance over REQUESTED window
- Added :start_date bound to entity_returns and benchmark_returns CTEs
- Filter by event_date >= :start_date to anchor cumulative returns
- Added test_start_date_bound_in_inputs to verify the semantics
- Mutation: drop the start bound → FAILS

### Item 4: Fix test_source_schema.py to check parsed VIEW columns ONLY
- Removed union with source_schemas-derived columns in test_source_schema.py
- Added skip for entries with computed coverage/aggregate fields (sample_count, coverage_ratio, status, agg_value)
- Mutation: rename close_price → close_price_bogus in bounded-bars DDL → FAILS

### Item 5: ≤−100% returns anomaly propagation
- Replaced GREATEST(1 + return_1d, 1e-10) with explicit anomaly propagation
- Used BOOL_OR to detect any invalid return (≤ -1) in the window
- Set cumulative_return to NULL when invalid returns detected
- Added status field with 'invalid_return' when invalid returns detected
- Added test_anomaly_propagation_for_invalid_returns
- Mutation: drop the start bound → FAILS