# VERDICT: rag-kg-round12 — MiMo
**Status:** APPROVED
**Round:** 12

## Blocking findings
None.

## Implementation summary

### Item 1: concept_norm structured column
- Added `concept_norm` column (STRING, nullable) to `gold_sec_kg_nodes` DDL and StructType in `pipelines/build_sec_knowledge_graph.py:163-170,221-231`.
- Computed in pipeline as `normalize_unicode(entity_key or metric).lower()` at `pipelines/build_sec_knowledge_graph.py:196-199`.
- `SparkGraphStore.find_nodes` now uses `F.col("concept_norm") == normalize_unicode(concept).lower()` — exact column equality, NO JSON substring (`api/services/sec_knowledge_graph.py:443-447`).
- `JsonlGraphStore.find_nodes` applies same `normalize_unicode()` to both stored and queried values for parity (`api/services/sec_knowledge_graph.py:184-186`).
- Updated `docs/DATA_SCHEMAS.md` gold_sec_kg_nodes: 6 cols → 7 cols.
- Parity harness tests (§40, 6 tests): `a"b`, backslash, full-width `Ｒｅｖｅｎｕｅ` vs `revenue`, injection `revenue","metric":"netincome` → 0 matches, `revenue` vs `revenues` → 0 matches, metric field fallback, mutation proof.

### Item 2: Fake Spark F.exists + _eval hardening
- `_eval` now raises `ValueError` on unknown expression ops instead of returning `True` (`tests/rag/test_sec_knowledge_graph.py:1539-1540`).
- `F.exists` mock now creates `_Expr("exists", col_name, lambda)` that evaluates the lambda against each provenance element (`tests/rag/test_sec_knowledge_graph.py:1582`).
- `_eval` handles `"exists"` op by iterating the array and applying the lambda (`tests/rag/test_sec_knowledge_graph.py:1535-1537`).
- `TestPredicatePushdown._eval_condition` also updated with `"exists"` handling and raise-on-unknown (`tests/rag/test_sec_knowledge_graph.py:2884-2888`).
- Spark as-of-before-LIMIT test (§41, 2 tests): future-only row + eligible row, limit=1 → returns eligible. Mutation proof: removing F.exists filter changes result.

## Non-blocking notes
- All fake node rows in `TestSparkGraphStoreRoundTrip._make_store_with_graph` and `TestPredicatePushdown._make_node_rows` now include `concept_norm` field for consistency with the new schema.

## Checks run
- `python3 -m pytest tests/rag -q` → **448 passed, 19 skipped, 1 warning**
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **448 passed, 19 skipped**