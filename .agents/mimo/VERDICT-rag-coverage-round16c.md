# VERDICT: rag-coverage-round16c — MiMo
**Status:** APPROVED
**Round:** 16c

## Blocking findings
- None remaining.

## Non-blocking notes
- `tests/bronze/test_refresh_bronze_options.py::test_shape_day_emits_uppercase_right` has a pre-existing ordering-dependent failure (passes alone, fails in full suite). Out of scope for this round.
- Unused variable `original_spark` was cleaned up before final commit.

## What was fixed
1. **`test_generic_exception_returns_retrieval_unavailable`** (test_hybrid_retriever.py:1329) — After the merge restored main's substring fallback, a generic `RuntimeError` from the retriever fell through to the `except Exception` handler which called `_spark()` without mocking, attempting a real Databricks connection that timed out (>30s). Fixed by mocking `agent.tools_retrieval._spark` to raise `RuntimeError` → fallback also fails → `retrieval_unavailable` returned.
2. **`test_databricks_connect_not_polluted`** (test_zz_isolation.py:11) — Cascaded from #1: the timeout left `databricks.connect` SDK in a dirty `sys.modules` state. Fixed by preventing the network call entirely.
3. **Added `test_generic_exception_fallback_succeeds_with_pit_filter`** — Sibling test: mock `_spark()` returns a fake Spark table → `retrieval_mode == "substring_fallback"`, PIT filter verified.
4. **Added `test_no_coverage_never_reaches_fallback`** — Asserts `NoCoverageError` returns `no_coverage` without invoking the substring fallback (spy on `_spark()`).

## Checks run
- `python3 -m pytest tests/rag -q` → 862 passed, 19 skipped, 0 failed
- `python3 -m pytest tests/rag/test_hybrid_retriever.py::TestSearchSecFilingsError -xvs` → 12 passed
- `python3 -m pytest tests/rag tests/bronze -q` → 1126 passed, 36 skipped, 1 failed (pre-existing bronze ordering issue)