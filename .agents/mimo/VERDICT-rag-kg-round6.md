# VERDICT: rag-kg-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
- None.

## Non-blocking notes
- Added `validate_and_raise()` shared function in `sec_kg/build.py:865` — single validation path for offline script and Databricks pipeline.
- Pipeline (`pipelines/build_sec_knowledge_graph.py:102`) now calls `validate_and_raise()` before any table writes. Undocumented rejection reasons → `ValueError`, no writes, exit non-zero.
- Run manifest written to `gold_sec_kg_build_runs` Delta table with exact stats: input rows by entity_type, accepted, rejected by reason, node/edge counts.
- Schema added to `docs/DATA_SCHEMAS.md` for `gold_sec_kg_build_runs` (9 cols).
- Offline script (`scripts/build_sec_knowledge_graph.py:128`) updated to use shared `validate_and_raise()`.
- Exact-value assertion for `neighbors()` edge timestamps added: `test_neighbor_edge_timestamps_exact` verifies `valid_from` and `accepted_ts` match `2023-11-14T22:13:20Z` (epoch 1700000000). `test_neighbor_timestamp_mutation_detectable` proves +28800s mutation fails.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag` → 390 passed, 19 skipped
- `python3 -m pytest -q -p no:cacheprovider tests/rag -k "TestRejectionReporting or TestValidateAndRaise or TestNeighborEdgeTimestampsExact or TestPipelineValidation"` → 13 passed