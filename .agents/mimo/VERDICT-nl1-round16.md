# VERDICT: nl1-round16 — MiMo
**Status:** APPROVED
**Round:** 16

## Blocking findings
None.

## Non-blocking notes
- All 7 items implemented and verified.
- 361 tests pass (up from 343 baseline — 18 new tests added).
- Schema check passes (`export_schemas --check`).
- DuckDB shim uses GREATEST guard for LN(0) safety (Spark handles this natively).

## Items completed

### 1 (High). GREATEST assertions for multi-source availability
- Strengthened `test_output_availability_is_window_max` to require GREATEST when ≥2 CTEs define availability via MAX(...) OVER.
- Added mutation proofs: remove benchmark from GREATEST → FAILS; replace GREATEST with single column → FAILS.
- Commit: `03f222b`

### 2 (High). DuckDB semantic tests for relative-performance -100% handling
- Added `TestRelativePerformanceDuckDB` class with 4 tests:
  - `test_normal_window_returns_numeric_value` → numeric rel_perf, status='ok'
  - `test_minus_100_percent_day_gives_null_and_invalid_return` → NULL cumulative, status='invalid_return'
  - `test_mutation_replace_null_arm_with_computed_value_fails` → mutation proof
  - `test_mutation_disable_invalid_return_status_fails` → mutation proof
- Commit: `df6ea45`

### 3 (Medium). momentum_20d availability term and LAG counting
- Added `with_momentum` CTE that computes LAG on full date-ordered series (before null-return filter).
- Added `momentum_20d_info_ts = MAX(information_available_ts) OVER (20 PRECEDING)`.
- Added `momentum_20d_info_ts` to final GREATEST in both adjusted and fallback DDL.
- Updated test to handle LAG-based metrics with `_detect_lag_offset` method.
- Commit: `a75ebb4`

### 4 (Medium). Bronze fallback ingest_ts bound
- Added `AND ingest_ts <= :as_of` to both serve_daily_prices_v1 and serve_bounded_daily_bars_v1 fallback DDL.
- Added `test_bronze_fallback_has_ingest_ts_bound` and `test_mutation_bronze_without_ingest_ts_fails`.
- Commit: `2c07797`

### 5 (Medium). Bounded-bars dedup before LAG
- Split `deduped` CTE into `deduped` (rn only) + `with_splits` (LAG after rn=1 filter).
- Added `TestBoundedBarsDuckDB` with 4 tests including split detection and dedup ordering.
- Commit: `d27cbb5`

### 6 (Medium). Ticker/Index/Sector validators use re.fullmatch
- Changed all `.match()` to `.fullmatch()` in contracts.py (5 validators) and registry.py (1 validator).
- Added trailing newline rejection tests for Ticker, Sector, and Index entities.
- Commit: `f0204a9`

### 7 (Medium). Policy.py fail-closed on missing coverage_stats
- When `entry.coverage is not None` and `coverage_stats is None` → INSUFFICIENT_DATA (fail closed).
- Tightened IV min_coverage_ratio from 0.001 to 0.5 in registry YAML.
- Updated tests: `test_no_coverage_stats_fails_closed`, `test_coverage_stats_with_sufficient_ratio_accepted`.
- Commit: `223c28f`

## Checks run
- `python3 -m pytest tests/analytics_nl -q` → 361 passed (13.85s)
- `python3 -m analytics_nl.export_schemas --check` → All schemas match
- `git archive HEAD | tar -x -C /tmp/mutation-proof-r16` → archive created, all 361 tests pass from archive
- Mutation tests (6 total): all pass from archive