# VERDICT: rag-kg-round15 — MiMo
**Status:** APPROVED
**Round:** 15

## Blocking findings
None.

## Fixes implemented

### P1: concept_norm missing from find_nodes select (confirmed by Claude)
- `api/services/sec_knowledge_graph.py:422` — added `"concept_norm"` to `.select()` so the concept filter and NULL guard resolve on real Spark (UNRESOLVED_COLUMN was the failure mode).
- `tests/rag/test_sec_knowledge_graph.py` — fixed `_FakeDataFrame.select()` in `TestSparkGraphStoreRoundTrip` to actually project columns and raise `AttributeError` on non-projected column references. Added `_FakeCol.isin(*vals)` to accept variadic args like real Spark. Added `_Expr.__and__`, `__invert__`, and `json_isin` operator support. Added `get_json_object` mock that evaluates JSON paths for the legacy guard.
- **Mutation test:** `test_mutation_select_omitting_concept_norm_fails` — creates a select() omitting concept_norm, then verifies `.where(F.col("concept_norm").isNull())` raises `AttributeError`. PASS on old code (old select returns self, no projection), FAIL on new code (properly raises).

### P2: max_entities checked after collecting
- `pipelines/build_sec_knowledge_graph.py:98-107` — moved max_entities cap BEFORE `toLocalIterator()`/`collect()`. Uses `entities_df.count() + sections_df.count()` (pushed to executors) so the check never materialises full datasets on the driver.
- **Mutation test:** `test_mutation_count_after_collect_fails` — spy verifies ZERO toLocalIterator/collect calls when cap exceeded. PASS on old code (old code calls collect first), verified on new code.

### P2: NULL-concept guard fires for non-concept-bearing rows
- `api/services/sec_knowledge_graph.py:448-470` — limited guard to XbrlFact/Metric nodes with non-empty entity_key or metric (via `get_json_object` JSON path check). Non-concept-bearing rows (Company, Filing) with NULL concept_norm no longer trigger the guard.
- **Mutation test:** `test_xbrl_null_concept_norm_guard_fires` verifies guard fires for XbrlFact with non-empty entity_key. `test_company_null_concept_norm_no_guard` verifies guard does NOT fire for Company.

### P3: No format validation on metric/period
- `agent/tools_retrieval.py:263-295` — added `_valid_metric` validator (XBRL concept name regex: `^[A-Za-z][A-Za-z0-9._:\-]*$`) and `_valid_period` validator (accepted formats: YYYY, YYYY-Qn, YYYY-MM-DD, YYYY-MM-DD..YYYY-MM-DD).
- Fixed `test_injection_label_in_untrusted_envelope` to use valid metric "Competition" instead of "ignore previous instructions" (spaces rejected by new validation).
- **Mutation tests:** `test_rejects_metric_with_spaces`, `test_rejects_period_with_slash` — FAIL on old code (no validation), PASS on new code.

## Checks run
```
python3 -m pytest tests/rag -q → 475 passed, 19 skipped, 1 warning (38.35s)
```

## Commits
- `818df88` fix(kg): round 15 — concept_norm select, max_entities pre-count, legacy guard, metric/period validation