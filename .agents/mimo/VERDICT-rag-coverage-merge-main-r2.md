# VERDICT: rag-coverage-merge-main-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
- None

## Non-blocking notes
- The original test file had 3 failures due to loguru's default sink not being captured by pytest's `capsys`. Fixed by implementing a `LoguruCapture` helper that adds a temporary loguru sink during test execution.
- `check_ticker_coverage` was leaking raw `RuntimeError` for TABLE_OR_VIEW_NOT_FOUND instead of converting to `NoCoverageError`. Fixed the code to catch this specific error pattern and raise `NoCoverageError` instead.

## Checks run
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks" tests/api/test_hybrid_retriever.py` → 12 passed (2.31s)

## Implementation details

### Tests added (tests/api/test_hybrid_retriever.py)
1. **TestFetchTickerRowsWarehouse** (2 tests)
   - `test_returns_rows_from_warehouse`: Verifies chunk and embedding rows returned correctly
   - `test_ticker_bound_as_param_not_in_sql`: Ensures ticker is in params, not f-stringed into SQL

2. **TestCheckTickerCoverageWarehouse** (3 tests)
   - `test_returns_coverage_from_warehouse`: Returns (n_chunks, cik) for covered ticker
   - `test_ticker_bound_as_param_in_coverage_query`: Param binding verification
   - `test_raises_no_coverage_error_when_empty`: Empty result raises NoCoverageError

3. **TestLoadAliasMapWarehouse** (1 test)
   - `test_alias_map_built_from_warehouse_rows`: Groups by CIK, alphabetically-first is canonical

4. **TestMissingCoverageTableAliasMap** (2 tests)
   - `test_alias_map_empty_on_table_not_found`: TABLE_OR_VIEW_NOT_FOUND → empty map + WARNING
   - `test_alias_map_empty_on_spark_analysis_exception`: Spark AnalysisException → empty map + WARNING

5. **TestMissingCoverageTableCheckTicker** (1 test)
   - `test_raises_no_coverage_not_driver_error`: TABLE_OR_VIEW_NOT_FOUND → NoCoverageError (not raw RuntimeError)

6. **TestStartupWarmupMissingTable** (1 test)
   - `test_warm_up_does_not_crash_on_missing_table`: _load_alias_map degrades gracefully, marks loaded

7. **TestFallbackMutationProof** (2 tests)
   - `test_remove_fallback_in_fetch_ticker_rows_breaks`: Removing except ImportError breaks tests
   - `test_fstring_ticker_in_sql_is_detected`: F-string ticker in SQL is caught by param checks

### Code change (api/services/hybrid_retriever.py)
- Line 585-587: Added conversion of TABLE_OR_VIEW_NOT_FOUND RuntimeError to NoCoverageError
```python
if "TABLE_OR_VIEW_NOT_FOUND" in str(e):
    raise NoCoverageError(ticker) from e
```

## Commit
- `efa3446` feat(coverage): warehouse fallback tests + TABLE_OR_VIEW_NOT_FOUND handling