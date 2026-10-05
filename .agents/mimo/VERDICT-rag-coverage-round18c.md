# VERDICT: rag-coverage-round18c — MiMo
**Status:** APPROVED
**Round:** 18c

## Blocking findings
- None.

## Non-blocking notes
- The original `_resolve_canonical_ticker` issued two Spark queries (CIK lookup + all-tickers-for-CIK) on every `get_ticker_corpus` call. This is now a single cached read from `gold_sec_coverage`, loaded lazily on first use and reused thereafter.
- The alias map shares the same `COVERAGE_TABLE` as `check_ticker_coverage` — one read, two purposes.
- `_get_spark` guard in conftest.py ensures any future Spark-leakage fails fast with a clear message instead of hanging on Databricks Connect.

## Design decisions
1. **Cached alias map** (`_alias_map`, `_alias_map_loaded`, `_alias_map_lock`): mirrors the corpus cache pattern. Loaded once from `gold_sec_coverage` via a single `SELECT ticker, cik` query. Grouped by CIK, canonical = alphabetically-first ticker. On failure, logs once and falls back to identity (ticker → ticker).
2. **`_get_spark` autouse guard**: raises `RuntimeError` immediately so any test that accidentally reaches `_get_spark()` fails fast instead of hanging on a Databricks Connect network timeout.
3. **`_resolve_canonical_ticker` mock**: identity by default in `_mock_check_ticker_coverage` fixture. Tests that need real alias resolution override it.
4. **Mutation proof**: `TestAliasResolutionMutationProof.test_mutation_drop_alias_resolution_fails` — dropping alias resolution causes GOOGL query to raise `NoCoverageError` (no corpus for GOOGL without alias → GOOG).

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q --timeout 60` → **1144 passed, 36 skipped, 10 warnings in 50.87s**
- Mutation proof: drop `_resolve_canonical_ticker` → `test_mutation_drop_alias_resolution_fails` FAILS with `NoCoverageError`
- No pyspark required for test run (CI-safe)

## Files changed
- `api/services/hybrid_retriever.py`: +`_alias_map`/`_alias_map_lock`/`_alias_map_loaded`, +`_load_alias_map()`, rewrote `_resolve_canonical_ticker()` to use cached map, updated `reload_corpus()` to clear alias map
- `tests/rag/conftest.py`: +`_guard_spark` autouse fixture, updated `_mock_check_ticker_coverage` to mock `_resolve_canonical_ticker`, +alias map reset in `_reset_retriever_singletons`
- `tests/rag/test_hybrid_retriever.py`: fixed `TestSessionSelection` tests to restore real `_get_spark`, +`TestAliasResolutionMutationProof` class (GOOGL→GOOG alias resolution + mutation proof)