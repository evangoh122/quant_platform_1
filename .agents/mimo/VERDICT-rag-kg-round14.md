# VERDICT: rag-kg round 14 — MiMo
**Status:** APPROVED
**Round:** 14

## Summary
Both tasks completed successfully:
1. **Wiring test**: Renamed `test_mutation_skip_alter_test_fails` → `test_ensure_concept_norm_column_issues_alter` (honest function test name). Added `test_build_issues_alter_before_merge` wiring test that runs `build()` against a fake Spark whose `gold_sec_kg_nodes` lacks `concept_norm` and asserts ALTER TABLE is issued BEFORE MERGE (call order recorded in one list).
2. **CRLF fix**: Converted `pipelines/build_sec_knowledge_graph.py` from CRLF to LF line endings. Added `TestLineEndings::test_no_crlf_in_python_files` to enforce no CRLF in `sec_kg/`, `pipelines/`, `api/services/`, `tests/rag/`.

## Mutation verification
- Commented out `ensure_concept_norm_column(spark, nodes_table)` in `build()` → `test_build_issues_alter_before_merge` FAILS as expected (ALTER TABLE not found in call order).
- Restored the call → test PASSES again.

## Blocking findings
(none)

## Non-blocking notes
- Added `.columns` property to `_FakeDataFrame` in `_setup_pyspark_mocks` to support `ensure_concept_norm_column` which reads `spark.table(fqn).columns`. This was needed because the existing fake DataFrame didn't expose columns.

## Checks run
- `python -m pytest tests/rag/test_sec_knowledge_graph.py::TestConceptNormMigration -xvs` → 6 passed
- `python -m pytest tests/rag/test_sec_knowledge_graph.py::TestLineEndings -xvs` → 1 passed
- `python -m pytest tests/rag/test_sec_knowledge_graph.py -q` → 149 passed, 2 skipped
- Mutation test (remove call → wiring test fails) → confirmed