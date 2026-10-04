# VERDICT: rag-kg-round7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
- None

## Non-blocking notes
- Item 1 implemented: 4 new tests in `TestPipelineValidation` exercising `pipelines/build_sec_knowledge_graph.build()` with fake Spark session and write spy
  - (a) `test_undocumented_rejection_raises_and_no_writes`: undocumented reason → ValueError, zero write/create/sql calls
  - (b) `test_documented_reasons_writes_after_validation`: documented reasons → writes happen, validate_and_raise called before any write
  - (c) `test_manifest_row_has_exact_counts`: manifest has exact accepted_rows=2, rejected_rows=0, node_count=4, edge_count=3, input_rows_by_entity_type={"company":1,"filing":1}
  - (d) `test_manifest_schema_explicit_9_columns`: explicit StructType with 9 fields, exact column name order matches docs/DATA_SCHEMAS.md
- Item 2 implemented: explicit `StructType` manifest schema in `pipelines/build_sec_knowledge_graph.py:236-248` matching docs/DATA_SCHEMAS.md exactly (9 columns: run_id, build_version, run_ts, input_rows_by_entity_type, accepted_rows, rejected_rows, rejection_reasons, node_count, edge_count)
- `_FakeRow` class at module level, `_setup_pyspark_mocks` helper with pyspark+delta mock installation, suffix-based table name matching
- Pre-existing failures: 8 tests in `TestTypedArgumentRejection` fail due to missing `psycopg` module (not related to this change)

## Checks run
- `python -m pytest tests/rag/test_sec_knowledge_graph.py::TestPipelineValidation -q` → 4 passed
- `python -m pytest tests/rag/test_sec_knowledge_graph.py -q` → 78 passed, 8 failed (pre-existing psycopg)
- pyspark hidden: `PYTHONPATH="" python -m pytest tests/rag/test_sec_knowledge_graph.py -q` → 73 passed, 13 deselected

## Mutation proofs
- Mutation A: replace `validate_and_raise(stats, entity_type_counts)` with plain dict at line 103 → 3 tests FAILED (test_undocumented_rejection_raises_and_no_writes, test_documented_reasons_writes_after_validation, test_manifest_row_has_exact_counts)
- Mutation B: move `validate_and_raise` call after table writes (after edges MERGE) → 1 test FAILED (test_undocumented_rejection_raises_and_no_writes — validation-before-writes check)

## Files modified
- `pipelines/build_sec_knowledge_graph.py`: +15/-2 (explicit manifest schema with StructType)
- `tests/rag/test_sec_knowledge_graph.py`: +463/-21 (4 new pipeline tests replacing vacuous TestPipelineValidation)