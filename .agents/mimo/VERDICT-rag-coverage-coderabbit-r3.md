# VERDICT: rag-coverage — CodeRabbit PR #28 round 3 — MiMo
**Status:** APPROVED
**Round:** 3

## Finding 1 — docs/SEC_RAG_COVERAGE_RUNBOOK.md:24 (User-Agent env setup)
**Fixed.** Docs-only, no test needed.
- Changed example email from `your-email@example.com` to `analyst@yourcompany.com` (passes `_validate_user_agent`)
- Clarified that `export` has no effect on `databricks bundle runs` (job reads from secrets)
- Fixed claim about "example" rejection — only `@example.(com|org|net)` domains are rejected

Commit: `55f9bc4`

## Finding 2 — evals/rag_eval/corpus.py:482 (alias-map originals before try)
**Fixed.** Test: `test_alias_map_restored_on_early_setup_error`
- Moved `orig_alias_map` and `orig_alias_loaded` assignments before the `try` block
- Test uses a `BrokenAdapter` whose `records()` raises — verifies no `UnboundLocalError` in `finally`
- Red line (old code): `UnboundLocalError: cannot access local variable 'orig_alias_map' where it is not associated with a value`

Commit: `d51e354`

## Finding 3 — evals/rag_eval/corpus.py:497 (NoCoverageError for out-of-corpus tickers)
**Fixed.** Test: `test_offline_ticker_outside_corpus_raises_no_coverage`
- Changed `return _orig(ticker)` to `raise NoCoverageError(ticker)` for tickers not in `offline_tickers`
- Test verifies `NoCoverageError` is raised for a ticker outside the offline corpus
- Red line (old code): `_orig(ticker)` would call the live checker, leaking a Databricks connection

Commit: `9a4cb7c`

## Finding 4 — pipelines/sec_rag_ingest.py:1469 (sec_cik_mapping_log dry_run gate)
**Fixed.** Test: `test_cik_mapping_log_skipped_on_dry_run`
- Changed condition from `if cik_mapping_log_writer is not None` to `if cik_mapping_log_writer is not None and (not dry_run or log_dry_run)`
- Test verifies no entries are written and no flush occurs during `dry_run=True`
- Red line (old code): `cik_log.entries` would have 1 entry, `cik_log.flush_count` would be 1

Commit: `db791b0`

## Finding 5 — pipelines/sec_rag_ingest.py:2294 (parameterize sec_ingest_log queries)
**Fixed.** Tests: `test_read_succeeded_reraises_non_table_errors`, `test_read_max_attempt_reraises_non_table_errors`, `test_read_succeeded_returns_empty_on_table_not_found`, `test_read_max_attempt_returns_zero_on_table_not_found`
- Replaced f-string interpolation with `?` placeholders + `args=` (matching `repair_cik_ownership` pattern)
- Added `_is_table_not_found()` helper that checks for `TABLE_OR_VIEW_NOT_FOUND` in error message
- Only table-not-found errors are treated as cold start; other exceptions propagate with logging
- Red line (old code): `except Exception: return set()` swallowed all errors including parse/permission/transient failures

Commit: `e6bbc91`

## Finding 6 — tests/rag/test_hybrid_retriever.py:1265 (stated contract in two tests)
**Fixed.**
- Renamed `test_fallback_results_tagged_with_retrieval_mode` → `test_generic_error_with_unavailable_fallback_returns_retrieval_unavailable`
- Explicitly patches `_spark` to raise `RuntimeError("databricks connect unavailable")` so test doesn't depend on environment
- Updated docstring to accurately state: "Generic error plus unavailable fallback returns retrieval_unavailable"
- Updated `test_generic_exception_returns_retrieval_unavailable` docstring similarly

Commit: `b53b557`

## Finding 7 — tests/rag/test_sec_rag_ingest.py:16 (Import Tuple — Ruff F821)
**Fixed.** Docs-only (Ruff lint).
- Added `Tuple` to `from typing import Any, Dict, List, Optional, Set, Tuple`
- Syntax check passes

Commit: `97f777c`

## Nitpick — api/services/hybrid_retriever.py:1082 (nested chunk lookup)
**Fixed.** Existing tests (`test_vector_search_returns_docs`, PIT tests) verify correctness.
- Per-ticker path: built `doc_by_id = {d.metadata.get("chunk_id"): d for d in corpus.docs}` once, then `doc = doc_by_id.get(cid)` — O(1) per embedding
- Global path: built `bm25_by_id = {d.metadata.get("chunk_id"): d for d in _bm25_docs}` once, same pattern
- Red line (old code): inner `for d in corpus.docs` loop — O(n) per embedding, O(n²) total

Commit: `77dac0a`

## Checks run
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → 2525 passed, 107 skipped, 0 failed (3m42s)