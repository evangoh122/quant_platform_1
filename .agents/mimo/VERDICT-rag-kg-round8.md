# VERDICT: rag-kg round 8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None — all 3 items completed.

## Changes made
1. **Test (b) validate ordering** (test_sec_knowledge_graph.py:2277-2304): Wrapped validate_and_raise with spy that records into write_spy.calls (kind="validate"). Asserts validate_idx < write_indices[0]. Previously the loop ended in `pass` and order was never checked.
2. **Test (c) Mutation A guard** (test_sec_knowledge_graph.py:2314-2319,2379-2381): Added spy on validate_and_raise and assertion `len(validate_called) >= 1`. Now Mutation A (validate replaced by dict) causes test (c) to fail in addition to tests (a) and (b).
3. **Schema test per-field types** (test_sec_knowledge_graph.py:2412-2450): Added _dt_repr helper that serializes MapType with valueContainsNull. Asserts dataType and nullable for all 9 fields against docs/DATA_SCHEMAS.md:498-507. Fixed fake _MapType to preserve valueContainsNull.

## Mutation proofs

### Mutation A — validate_and_raise replaced by dict
```
FAILED test_undocumented_rejection_raises_and_no_writes  (a) — no ValueError raised
FAILED test_documented_reasons_writes_after_validation   (b) — validate_and_raise never called
FAILED test_manifest_row_has_exact_counts                (c) — validate_and_raise never called
PASSED test_manifest_schema_explicit_9_columns           (d) — schema unaffected
3 failed, 1 passed
```

### Mutation B — validate_and_raise moved after table writes
```
FAILED test_undocumented_rejection_raises_and_no_writes  (a) — writes happen before validation
FAILED test_documented_reasons_writes_after_validation   (b) — validate_idx > write_indices[0]
PASSED test_manifest_row_has_exact_counts                (c) — counts correct, validate still called
PASSED test_manifest_schema_explicit_9_columns           (d) — schema unaffected
2 failed, 2 passed
```

### Mutation C — IntegerType → LongType for accepted_rows
```
FAILED test_manifest_schema_explicit_9_columns — Field 4 (accepted_rows) dataType mismatch: LongType != IntegerType
1 failed
```

## Checks run
- `python -m pytest tests/rag/test_sec_knowledge_graph.py -q -k TestPipelineValidation` → 4 passed
- `python -m pytest tests/rag/test_sec_knowledge_graph.py -q` → 78 passed, 8 failed (pre-existing psycopg import errors in TestTypedArgumentRejection, unrelated to round 8 changes)
- Mutation A (validate=dict) → 3 FAILED (a,b,c)
- Mutation B (validate after writes) → 2 FAILED (a,b)
- Mutation C (LongType) → 1 FAILED (schema test)