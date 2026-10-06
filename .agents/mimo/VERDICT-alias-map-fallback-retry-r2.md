# VERDICT: alias-map-fallback-retry-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Non-blocking notes
- The cache-forever mutation (`_alias_map_loaded = True` in the MISSING-COLUMN branch) breaks `test_a_unresolved_column_with_suggestion` — exactly as intended. The test proves the retry deadline is load-bearing for that branch.
- Branches (b) and (c) are unaffected by the mutation because they hit different code paths (no-rows and generic-exception branches respectively), which still correctly schedule retries.
- Existing tests (`TestAliasMapFallbackRetry`) cover the TABLE_OR_VIEW_NOT_FOUND generic path; the new tests cover the UNRESOLVED_COLUMN and no-rows paths specifically.

## Checks run
- `python3 -m pytest tests/api/test_hybrid_retriever.py::TestAliasMapFallbackRetryAllBranches -v` → 3 passed (0.83s)
- `python3 -m pytest tests/api/test_hybrid_retriever.py -v` → 24 passed (1.06s)
- Cache-forever mutation applied → `test_a_unresolved_column_with_suggestion` FAILED (assert hr._alias_map_loaded is False), `test_b_no_rows` PASSED, `test_c_generic_exception` PASSED
- Cache-forever mutation reverted → all 3 new tests pass again

## Files modified
- `tests/api/test_hybrid_retriever.py` — added `TestAliasMapFallbackRetryAllBranches` class with 3 tests