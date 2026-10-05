# VERDICT: rag-coverage-round18 — MiMo
**Status:** APPROVED
**Round:** 18

## Blocking findings
None.

## Fixes implemented

### 1. SEC history file parsing (pipelines/sec_rag_ingest.py:867-878)
- History overflow files (`CIK##########-submissions-001.json`) store filing arrays at the TOP level, not nested under `filings.recent`.
- Updated `discover_filings` to parse both shapes.
- Fixed fixture `tests/rag/fixtures/sec/submissions_history.json` to real top-level shape.
- Added test `test_history_top_level_shape_discovered`.

### 2. Share-class alias resolution (pipelines/sec_rag_ingest.py:1396)
- Added `resolve_canonical_tickers()` — first ticker alphabetically per CIK is canonical.
- Anti-join uses canonical ticker + deduplicates within batch via `planned_accessions` set.
- Coverage SQL (`gold/07_gold_sec_coverage.sql`) resolves aliases via `canonical_per_cik` CTE.
- `_resolve_canonical_ticker()` in `hybrid_retriever.py` resolves aliases for corpus lookup.
- Tests: `TestResolveCanonicalTickers`, `TestGoldCoverageAliases`.

### 3. Silver-only tickers in coverage universe (gold/07_gold_sec_coverage.sql:16)
- Added `UNION` with `silver_sec_sections` in the `universe` CTE.
- Tickers with silver chunks but absent from `gold_tradable_universe` now get coverage rows.
- Test: `TestGoldCoverageAliases.test_silver_only_ticker_included`.

### 4. Offline hybrid evals Spark-free (evals/rag_eval/corpus.py:462)
- Bypasses LRU size limit: direct insert into `hr._ticker_cache` instead of `_insert_ticker_corpus`.
- Monkey-patches `check_ticker_coverage` to answer from offline ticker groups.
- Saves/restores original checker + cache on exit.
- Tests: `TestOfflineCoverageCheck` (3 tests).

### 5. Runbook `--` replaces parameters (docs/SEC_RAG_COVERAGE_RUNBOOK.md:53)
- Documented that `databricks bundle run <job> -- <args>` replaces task parameters.
- All commands now repeat `--catalog`, `--schema`, `--user-agent-secret-scope`, `--user-agent-secret-key`.

### 6. `accepted_before_filing` tolerance (docs/SEC_RAG_COVERAGE_RUNBOOK.md:115)
- Changed from `accepted_ts < cast(filing_date AS timestamp)` to `accepted_ts < cast(filing_date AS timestamp) - INTERVAL 4 DAYS`.
- Documented that after-hours filings make non-zero counts expected.

### 7. XBRL client User-Agent (api/services/xbrl_client.py:30)
- Replaced `EDGAR_USER_AGENT` env var with pipeline resolver `_resolve_user_agent()` + `_validate_user_agent()`.
- Reuses `SEC_EDGAR_USER_AGENT` env or Databricks secret fallback.

### 8. Placeholder address rejection (notebooks/refresh_bronze_cot.py:75)
- Changed from `"example" in email.lower()` to regex matching placeholder domains (`@example.com/.org/.net`, `your-email@`, etc.).
- Valid addresses like `analyst@myexample.org` are now accepted.
- Same fix applied to `_validate_user_agent` in `sec_rag_ingest.py`.

## Checks run
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py tests/rag/test_sec_coverage_sql.py tests/rag/test_rag_eval_corpus.py tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_round3.py tests/rag/test_rag_eval_round4.py -q` → 227 passed, 6 skipped
- `python3 -m pytest tests/bronze -q` → 260 passed, 22 skipped
- No pyspark available in test environment (CI-compatible).

## Non-blocking notes
- The `_resolve_canonical_ticker` function queries the coverage table to resolve aliases. For offline evals, the monkey-patched `check_ticker_coverage` handles this without Spark.
- The `canonical_per_cik` CTE uses `min(ticker)` which is equivalent to first alphabetically — consistent with `resolve_canonical_tickers` in Python.