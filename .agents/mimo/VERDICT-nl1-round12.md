# VERDICT: nl1-round12 — MiMo
**Status:** APPROVED
**Round:** 12

## Blocking findings
None.

## Non-blocking notes
- The `_extract_view_select_columns` parser in test_source_schema.py is regex-based and may need refinement if DDL structure changes significantly. Currently handles all 5 views correctly.
- Coverage stats injection is opt-in (coverage_stats=None skips the check). Consumers must supply stats for sparse metrics to trigger INSUFFICIENT_DATA rejection.
- Relative performance cumulative return uses `EXP(SUM(LN(1+r)))` which requires return_1d > -1 (no -100% days). NULL return_1d rows are excluded before computation.

## Changes made
1. **Finding 1 (High) — PIT safety:** Restructured all 5 serving view DDLs to add `as_of_filtered` CTE that applies `information_available_ts <= :as_of` BEFORE any window/aggregate computation. Each CTE explicitly lists columns (no SELECT *). Added contract test `TestDDLPITSafetyAsOfBeforeWindow` with mutation proof (removing as_of filter → test fails).

2. **Finding 2 (High) — close → close_price:** Renamed `close` to `close_price` in all 4 price registry entries' `input_columns`, `output_fields`, and `allowed_ordering`. Added `TestRegistryColumnsMatchViewOutput` that validates registry output_fields against DDL SELECT list. Implemented SQL-column checker (was empty pass-through).

3. **Finding 3 (High) — Insufficient-data honesty:** Added `CoverageStatus` enum (ok, INSUFFICIENT_DATA), `CoverageMeta` dataclass to registry, `INSUFFICIENT_DATA` reason code. IV entries get `coverage: {availability: snapshot_only, min_coverage_ratio: 0.001}`. IV aggregate output_fields gain `sample_count` (int), `coverage_ratio` (number), `status` (string); `agg_value` nullable. Policy rejects aggregate when `coverage_stats[pair_key]` ratio < threshold. 4 new tests.

4. **Finding 4 (Medium) — Entity count/kind enforcement:** Entity-type validation now checks each entity against `entry.allowed_entity_types` (was no-op). `TOO_FEW_ENTITIES` reason code added; `entry.min_entities` enforced. `allowed_entity_types: [ticker]` on IV, PCR, rel_perf entries. `min_entities: 2` on all compare entries. 7 new tests with mutation proofs.

5. **Finding 5 (Medium) — Relative performance:** View takes `:benchmark` parameter (SPY/QQQ/RSP, not hardcoded). Computes cumulative return via `EXP(SUM(LN(1+return_1d)))` over window. Relative perf = entity cumulative − benchmark cumulative. Output `information_available_ts = GREATEST(entity_ts, bench_ts)`. DDL contract test verifies parameterized benchmark and cumulative return.

## Checks run
- `python3 -m pytest tests/analytics_nl -q` → 329 passed
- `python3 -m analytics_nl.export_schemas --check` → All schemas match
- Mutation: remove as_of filter from CTE → PIT test fails (1 failed, 328 passed)
- Mutation: entity type no-op → sector IV accepted instead of rejected (test catches)
- Mutation: min_entities no-op → 1-entity compare accepted instead of rejected (test catches)