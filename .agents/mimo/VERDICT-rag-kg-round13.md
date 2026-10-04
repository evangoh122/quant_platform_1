===VERDICT START===
# VERDICT: rag-kg-round13 — MiMo (builder)
**Status:** APPROVED
**Round:** 13
**Range:** c85169f (HEAD, branch slice/rag-kg)

## Blocking findings
- None

## Non-blocking notes
- The NULL concept_norm guard uses a `.limit(1).count()` probe query before the actual concept filter. This adds one extra Spark query per concept search, but only when concept filtering is requested. Acceptable latency trade-off for correctness.
- The `ensure_concept_norm_column` function follows the established pattern from `run_silver_gold.py:ensure_model_availability_columns` exactly.

## Checks run
- `python3 -m pytest tests/rag -q` → **455 passed, 19 skipped, 1 warning**
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **455 passed, 19 skipped, 1 warning**
- Mutation proof: `test_mutation_skip_alter_test_fails` → PASSED (verifies ALTER is issued when column missing)

## Files modified
- `pipelines/build_sec_knowledge_graph.py` — added `ensure_concept_norm_column()` and call before MERGE
- `api/services/sec_knowledge_graph.py` — added NULL concept_norm guard in `find_nodes()`
- `tests/rag/test_sec_knowledge_graph.py` — added `TestConceptNormMigration` (4 tests), `TestConceptNormNullGuard` (3 tests), extended `_FakeCol` with `isNull()`, `_FakeDataFrame`/`_SpyDataFrame` with `count()`
- `docs/DEPLOYMENT.md` — added concept_norm migration section

## Commit
c85169f round 13: concept_norm migration + NULL guard
===VERDICT END===