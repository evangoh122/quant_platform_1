# VERDICT: nl1-round15 — MiMo
**Status:** APPROVED
**Round:** 15

## Scope
Strengthened `test_output_availability_is_window_max` (tests/analytics_nl/test_ddl.py:674) to verify that each info_ts token in the final GREATEST is defined as `MAX(<availability_col>) OVER (...)` with a valid window frame, not just that ≥2 tokens exist.

## Changes made

### tests/analytics_nl/test_ddl.py
- Fixed `_resolve_token_to_cte` regex: was looking for `token AS (` (CTE syntax), now correctly looks for `MAX(<availability_col>) OVER (...) AS token` (column alias syntax)
- Generalized availability column pattern to accept `INFORMATION_AVAILABLE_TS` or any `*_INFO_TS` (handles `bench_max_info_ts` which is `MAX(bench_info_ts)`)
- Made `PARTITION BY` optional in window frame regex (benchmark_cumulative has no partition)
- Added `_extract_window_frame` to extract the OVER clause from a token's definition
- Added `_extract_metric_window_frame` to find the companion metric's window frame with fallback for naming mismatches (entity_info_ts → cumulative_return)
- Window frame matching: asserts info token's frame equals companion metric's frame

## Mutation proofs

| # | Mutation | Expected | Actual | Result |
|---|----------|----------|--------|--------|
| b1 | realized_vol_20d_info_ts: `MAX(information_available_ts) OVER (... ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)` → bare `information_available_ts` | FAIL | `AssertionError: SQL block 3: availability token 'realized_vol_20d_info_ts' is not a window MAX` | caught |
| b2 | drawdown_info_ts: `MAX(information_available_ts) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` → bare `information_available_ts` | FAIL | `AssertionError: SQL block 3: availability token 'drawdown_info_ts' is not a window MAX` | caught |

## Checks run
- `python -m pytest tests/analytics_nl -q` → **343 passed** (24.3s)
- `git status` → clean (working tree unchanged by this check except for the verdict file)