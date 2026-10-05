===VERDICT START===
# VERDICT: rag-coverage round 18 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 18

## Summary

Full suite green (1144 passed, 36 skipped, 35.4 s), and items 1–4 and 8 are fixed with
load-bearing mutation proofs (each reverts to the old code and the targeted test fails). Two
problems remain:

- **Item 5 (runbook) is only half fixed.** The `sec_rag_ingest` commands now repeat
  `--catalog`/`--schema`/secret args, but all four `sec_embeddings` commands still pass only
  `--batch-size`/`--partitions`/`--ticker` after `--`, so they still run against the wrong
  schema. This is exactly the defect CodeRabbit #5 named ("Each `sec_rag_ingest` **and**
  `sec_embeddings` command").
- **Item 7 (XBRL client resolver) has no mutation-proof test.** Reverting
  `api/services/xbrl_client.py` `_get_user_agent` to the old `os.getenv("EDGAR_USER_AGENT")`
  path changes no test result (suite stays 1144 passed). The "never logs it" property is only
  asserted transitively at the `_resolve_user_agent` level.

## Blocking findings

- [docs/SEC_RAG_COVERAGE_RUNBOOK.md:90] `databricks bundle run -t dev sec_embeddings -- --ticker "$PILOT_TICKERS" --batch-size 256 --partitions 4` does not repeat `--catalog`/`--schema`. The `sec_embeddings` task parameters in `resources/jobs.yml:54` are `["--catalog", "${var.catalog}", "--schema", "${var.schema}"]`; args after `--` **replace** those, so `build_sec_embeddings.py` falls back to `CATALOG=bootcamp_students`, `SCHEMA=evangoh_capstone` (`pipelines/build_sec_embeddings.py:319-320`) and writes `gold_sec_chunk_embeddings` to the wrong schema for any non-default target. Same defect at lines 167, 182, 203.
  → Concrete failure: operator runs Phase 1/2 against `${var.schema}=evangoh_capstone_prod`; `sec_rag_ingest` writes bronze/silver to prod, but `sec_embeddings` writes chunks to the *default* `bootcamp_students.evangoh_capstone`, leaving prod with zero embeddings and the retrieval smoke test silently returning `no_coverage` for every ticker.

- [api/services/xbrl_client.py:25] `_get_user_agent` now delegates to `_resolve_user_agent`/`_validate_user_agent`, but no test asserts this delegation. Mutation (restore `raw = os.getenv("EDGAR_USER_AGENT", "")` + `"example" in raw.lower()`) produced **no test failure** (`1144 passed`), so a future revert to the unset-`EDGAR_USER_AGENT` bug would ship silently. The item-7 acceptance ("reuse the pipeline resolver … never log the value") is therefore not guarded by a test, only by code inspection.
  → Concrete failure: the original bug (client reads `EDGAR_USER_AGENT`, which the pipeline never sets, while the pipeline sets `SEC_EDGAR_USER_AGENT`) can regress without any test turning red.

## Non-blocking notes

- Items 5/6 are docs-only (runbook) so no unit test is expected for the *text*; the blocking
  issue above is the *incompleteness*, not the absence of a test.
- Item 2's alias map is invalidated per-process only (`reload_corpus` clears `_alias_map` at
  `api/services/hybrid_retriever.py:684-686`), with no TTL. `reload_corpus` is not wired to any
  production trigger (no caller outside tests). A coverage refresh followed by a new share-class
  CIK mapping would leave the cached map stale until process restart. Acceptable under the
  "per process" criterion in the request, but worth an explicit invalidation call after ingest.
- `test_mutation_drop_alias_resolution_fails` (tests/rag/test_hybrid_retriever.py:3346) is a
  *self-mutating* proof (it monkeypatches `_resolve_canonical_ticker` to identity inside the
  test); it does not prove the production wiring. The wiring is proven separately by my
  independent mutation of `get_ticker_corpus` (below), which does fail.

## Verification of requested mutations (independent archive copies)

All mutations applied to `git archive HEAD` copies under `/tmp/ragcov-mut`, not the worktree.

- **Item 1** — removed the `else` branch that parses top-level history arrays
  (`pipelines/sec_rag_ingest.py:922-931`):
  ```
  FAILED tests/rag/test_sec_rag_ingest.py::TestFilingDiscovery::test_history_top_level_shape_discovered
  > assert 0 == 1   (len(filings)==0 — 10-K only in history file not discovered)
  ```
- **Item 2** — removed the `_resolve_canonical_ticker` call in `get_ticker_corpus`
  (`api/services/hybrid_retriever.py:331-335`):
  ```
  FAILED tests/rag/test_hybrid_retriever.py::TestAliasResolutionMutationProof::test_googl_resolves_to_goog_corpus
  > CorpusUnavailableError: Failed to load corpus for GOOGL: _get_spark called in test
  ```
- **Item 3** — removed the silver `UNION` block in `gold/07_gold_sec_coverage.sql`:
  ```
  FAILED tests/rag/test_sec_coverage_sql.py::TestGoldCoverageDuckDB::test_exact_output_rows
  FAILED tests/rag/test_sec_coverage_sql.py::TestGoldCoverageDuckDB::test_silver_only_ticker_included
  FAILED tests/rag/test_sec_coverage_sql.py::TestGoldCoverageAliases::test_silver_only_ticker_included
  > AssertionError: 'NVDA' in {'AAPL': 1}
  ```
- **Item 4** — removed the offline `check_ticker_coverage` monkey-patch
  (`evals/rag_eval/corpus.py`):
  ```
  FAILED tests/rag/test_rag_eval_corpus.py::TestOfflineCoverageCheck::test_offline_coverage_resolves_from_corpus
  > assert None == ''   (real check_ticker_coverage / mock returns None, offline path bypassed)
  ```
- **Item 7** — reverted `_get_user_agent` to `os.getenv("EDGAR_USER_AGENT")`:
  ```
  1144 passed, 36 skipped   (NO test catches the revert — coverage gap, see blocking #2)
  ```
- **Item 8** — reverted `_validate_user_agent` to bare `"example" in user_agent.lower()`:
  ```
  FAILED tests/rag/test_sec_rag_ingest.py::TestResolveUserAgent::test_valid_address_with_example_accepted
  FAILED tests/rag/test_sec_rag_ingest.py::TestValidateUserAgent::test_valid_user_agent_with_example_accepted
  > ValueError raised for 'analyst@myexample.org' (valid address wrongly rejected)
  ```

## Network guard check

`tests/rag/conftest.py` installs an autouse socket/DNS guard (`_block_network`, lines 111-197)
plus `_stub_xbrl_client` (255-282) and `_guard_spark` (322-342). `tests/rag/test_network_guard.py`
→ **17 passed**. The suite never blocks on real I/O (finishes in ~35 s with `--timeout 30`).

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q --timeout 30` → **1144 passed, 36 skipped, 10 warnings** (35.44 s)
- Mutation 1 (history) → **1 failed** (test_history_top_level_shape_discovered)
- Mutation 2 (alias wiring) → **1 failed** (test_googl_resolves_to_goog_corpus)
- Mutation 3 (silver UNION) → **3 failed** (test_silver_only_ticker_included ×2, test_exact_output_rows)
- Mutation 4 (offline monkeypatch) → **1 failed** (test_offline_coverage_resolves_from_corpus)
- Mutation 7 (XBRL resolver) → **0 failed** (coverage gap)
- Mutation 8 (placeholder) → **2 failed** (test_valid_address_with_example_accepted, test_valid_user_agent_with_example_accepted)
- `python3 -m pytest tests/rag/test_network_guard.py -q` → **17 passed**
===VERDICT END===
