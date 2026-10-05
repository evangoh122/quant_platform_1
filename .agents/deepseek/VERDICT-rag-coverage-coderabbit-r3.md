===VERDICT START===
# VERDICT: rag-coverage — CodeRabbit PR #28 round 3 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 3

## Summary

Independent check of MiMo's r3 fixes (commits `55f9bc4..b232b9f`) for the 7
CodeRabbit findings + 1 nitpick. Read-only verification; all mutations done in
fresh `git archive HEAD | tar -x -C /tmp/r3check/*` copies (never git inside a
copy). MiMo's verdict is a self-report and was not trusted; every claim was
re-run.

Baseline (clean tree, HEAD `a5e58da`): 25 targeted tests pass; the three affected
files (`test_sec_rag_ingest.py`, `test_rag_eval_corpus.py`,
`test_hybrid_retriever.py`) pass as a set (344 passed). Each of the 4 production
code fixes was individually reverted (production file only, tests left in place)
and a specific test FAILs — confirming the fixes are mutation-proof.

## Blocking findings

None.

## Finding-by-finding verification

- **F1 (docs runbook, `55f9bc4`)** — docs-only. New example
  `analyst@yourcompany.com` passes `_validate_user_agent`
  (`pipelines/sec_rag_ingest.py:156-176`: only rejects `@example.(com|org|net)`,
  `^your[-_]email@`, `^user@`, `^test@`, `^example@example`). Note about `export`
  not reaching `databricks bundle run` is correct.
- **F2 (alias-map originals, `d51e354`)** — revert → `UnboundLocalError` at
  `evals/rag_eval/corpus.py:526` (`hr._alias_map.update(orig_alias_map)`). Test
  `TestOfflineAliasMap::test_alias_map_restored_on_early_setup_error` FAILED. PASS.
- **F3 (NoCoverageError, `9a4cb7c`)** — revert → `DID NOT RAISE NoCoverageError`
  at `tests/rag/test_rag_eval_corpus.py:225`. Test
  `TestOfflineCoverageCheck::test_offline_ticker_outside_corpus_raises_no_coverage`
  FAILED. PASS.
- **F4 (cik log dry-run gate, `db791b0`)** — revert → `AssertionError: CIK
  mapping log should not be written during dry run` at
  `tests/rag/test_sec_rag_ingest.py:1228` (`assert 1 == 0`). Test
  `TestCikMappingLog::test_cik_mapping_log_skipped_on_dry_run` FAILED (uses
  recording writer `FakeCikMappingLogWriter`, asserts 0 entries + 0 flush). PASS.
- **F5 (parameterize sec_ingest_log, `e6bbc91`)** — revert → `DID NOT RAISE
  RuntimeError` at `tests/rag/test_sec_rag_ingest.py:2599`. Test
  `TestSparkIngestLogReader::test_read_succeeded_reraises_non_table_errors`
  FAILED. Queries now use `?` + `args=[...]`
  (`pipelines/sec_rag_ingest.py:2294-2296, 2317-2319`); only `catalog`/`schema`
  identifiers are f-string interpolated, no run_id/ticker/accession values.
  `_is_table_not_found` (line 2263) gates cold-start on `TABLE_OR_VIEW_NOT_FOUND`
  only; other errors logged + re-raised (lines 2299-2302, 2322-2324). PASS.
- **F6 (restated fallback tests, `b53b557`)** — test-only; contracts now say
  "generic error plus unavailable fallback → retrieval_unavailable" and `_spark`
  is patched explicitly. Passes in baseline. PASS.
- **F7 (Tuple import / F821, `97f777c`)** — `Tuple` added to `from typing import
  ...` (`tests/rag/test_sec_rag_ingest.py:16`). `python3 -m ruff check --select
  F821 tests/rag/test_sec_rag_ingest.py` → **All checks passed!** (0 F821). PASS.
- **Nitpick (O(1) chunk lookup, `77dac0a`)** — behaviour-preserving:
  `doc_by_id`/`bm25_by_id` dicts replace the nested scan; the global-path
  fallback to `_corpus` is retained. `-k 'vector_search or bm25 or pit or PIT or
  per_ticker'` → 33 passed. PASS.

## Non-blocking notes

- Full `ruff check` (all rules) on `test_sec_rag_ingest.py` still reports 75
  pre-existing issues (UP006/UP035/F401/F811/F841/I001/S102/TRY002…), none F821.
  Out of scope for this finding.
- `_is_table_not_found` fallback `getattr(exc, "errorCode", "").upper()` would
  raise if `errorCode` were present-but-`None`; the message-string check is the
  primary path and Spark reports this via `errorClass`/message, so no practical
  defect.
- `test_cik_mapping_log_skipped_on_dry_run` covers the dry_run skip only; the
  `log_dry_run=True` positive branch is untested but the condition is symmetric
  and trivial.
- `b53b557`, `97f777c`, `b232b9f` are test-only changes (contract restatement,
  import, cold-start FakeSpark), so no production revert-and-fail applies.

## Checks run

- `python3 -m pytest -q <25 targeted r3 tests>` → **25 passed** (1.93s). PASS.
- Revert F2 → `test_alias_map_restored_on_early_setup_error` FAILED
  (`evals/rag_eval/corpus.py:526` UnboundLocalError). PASS.
- Revert F3 → `test_offline_ticker_outside_corpus_raises_no_coverage` FAILED
  (`tests/rag/test_rag_eval_corpus.py:225`). PASS.
- Revert F4 → `test_cik_mapping_log_skipped_on_dry_run` FAILED
  (`tests/rag/test_sec_rag_ingest.py:1228`). PASS.
- Revert F5 → `test_read_succeeded_reraises_non_table_errors` FAILED
  (`tests/rag/test_sec_rag_ingest.py:2599`). PASS.
- `python3 -m ruff check --select F821 tests/rag/test_sec_rag_ingest.py` →
  **All checks passed!** PASS.
- `python3 -m pytest -q tests/rag/test_sec_rag_ingest.py tests/rag/test_rag_eval_corpus.py tests/rag/test_hybrid_retriever.py` →
  **344 passed** (6.69s). PASS.
===VERDICT END===
