===VERDICT START===
# VERDICT: rag-coverage-coderabbit-r2 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 2

## Summary

Checked the 9 CodeRabbit PR #28 round-2 findings against MiMo's fixes
(`ca64736`) and regression tests (`5ef5687`), read-only, in a `git archive HEAD`
copy under `/tmp/ragcov-r2-check`. The 6 named mutation-proof tests were each
reverted and re-run. 5 of 6 fail on revert as claimed; **1 does not** — the
discovery-CIK test passes with the fix fully reverted, so the fix has no
regression protection. The MAJOR single-accession lookup is correct and
parameterized. The offline suite is green (2447 passed, 0 failed).

## Blocking findings

- [tests/rag/test_sec_rag_ingest.py:4777] `TestDiscoveryCikPerFiling::
  test_override_ticker_uses_discovery_cik` is NOT mutation-proof → reverting the
  discovery-CIK fix (`plan_cik = discovery_cik or next(iter(ticker_ciks))` →
  `plan_cik = next(iter(ticker_ciks))` in `pipelines/sec_rag_ingest.py:1601,1603`)
  leaves the test PASSING. Root cause: the test's only filing has accession
  `0001045810-25-000010`, whose filer prefix `0001045810` == `cik_a`, which IS a
  member of `ticker_ciks` {`cik_a`,`cik_b`}; so the first branch
  (`if is_override and filer_cik in ticker_ciks` → `plan_cik = filer_cik`,
  `sec_rag_ingest.py:1593-1594`) fires and `discovery_cik` is never consulted.
  The CodeRabbit scenario the fix targets is the opposite case — filer prefix
  *not* in the override group (e.g. filing-agent prefix `0001193125`). Concrete
  failure scenario: a future refactor that drops the `accession_discovery_cik`
  tracking would reintroduce the `next(iter(set))` non-determinism (wrong CIK →
  `fetch_failed` → run exits 1) and this test would still pass, so the regression
  goes undetected. MiMo's self-report lists this as "PASS (contract test)" and
  understates the gap; the test does not exercise the fallback branch at all.

## Non-blocking notes

- Fixes #7 (runbook `catalog`/`schema`/`PILOT_TICKERS` vars, `docs/SEC_RAG_COVERAGE_RUNBOOK.md:51-54`)
  and #8 (test monkeypatch hygiene, `tests/rag/test_hybrid_retriever.py:3352,3362`)
  have no named mutation-proof test. #7 is docs-only (no test possible); #8 is
  itself a test-isolation fix (its "failure" only manifests as cross-test order
  pollution, not a single named test). Both fixes are correct in place.
- `api/main.py:305` — see item 3 below; MiMo's "NOT VALID" is defensible, not a
  blocker.

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` →
  **2447 passed, 107 skipped, 24 deselected, 44 warnings** (217.5s), run in a
  clean `git archive HEAD` copy via `/tmp/run_offline.sh`. `tests/ml/test_hardening.py`
  (known flaky) passed this run; no failures.
- Revert #1 (single-accession) → `test_process_one_calls_singular_lookup`
  **FAILED** at `tests/rag/test_sec_rag_ingest.py:4762`
  (`assert 0 >= 1` — singular never called).
- Revert #2 (discovery CIK) → `test_override_ticker_uses_discovery_cik`
  **PASSED** (5/5 runs) — mutation gap (see blocking finding).
- Revert #3 (`global _alias_map_loaded`) → `test_full_reload_resets_alias_map_loaded`
  **FAILED** at `tests/rag/test_hybrid_retriever.py:3387` (`assert True is False`).
- Revert #4 (alias-before-invalidate) → `test_alias_invalidation_evicts_canonical`
  **FAILED** at `tests/rag/test_hybrid_retriever.py:3463`
  (`assert 'GOOG' not in OrderedDict({'GOOG': ...})`).
- Revert #5 (provider-aware embedding model) → `test_huggingface_provider_returns_hf_model`
  **FAILED** at `tests/rag/test_hybrid_retriever.py:3503`
  (`assert 'BAAI/bge-small-en-v1.5' == 'custom/hf-model'`).
- Revert #6 (offline alias map) → `TestOfflineAliasMap` **3 FAILED**, first at
  `tests/rag/test_rag_eval_corpus.py:236` (`assert False is True`).

## Item-by-item verification

### 1. Mutation-proof revert of each fix (acceptance item 1)
5 of 6 named tests fail on revert. Fix #2 (discovery CIK) does not — blocking
finding above. Fixes #7 (runbook) and #8 (monkeypatch) have no named test.

### 2. MAJOR fix: per-filing single-accession lookup is parameterized
`pipelines/sec_rag_ingest.py:1692` now calls
`accession_reader.read_existing_accession(catalog, schema, filing.accession_number)`.
`SparkAccessionReader.read_existing_accession` (`:1980-1998`) builds
`.where(F.col("accession_number") == accession_number)` — a bound column
predicate, **no f-string accession**. The only f-strings in the read path
interpolate table-name constants (`f"{catalog}.{schema}.bronze_sec_filings_v2"`,
config-controlled, not user input). The full-table `read_existing_accessions`
remains only at `:1474` (the one-time initial anti-join, before the loop), not
per filing. `FakeAccessionReader` (`tests/rag/test_sec_rag_ingest.py:203-207`)
and `TestAccessionConflict`'s race reader also implement the singular method.
**PASS.**

### 3. MiMo's "NOT VALID" on api/main.py:305 vs CodeRabbit text
CodeRabbit's finding (`.agents/coderabbit-pr28-round2.md:1-5`) has an **empty
body** — only `_Stability & Availability_ | _Minor_ | _Quick win_`, no defect
description. Line 305 is the `_log.warning(...)` inside
`_warm_sec_corpus_in_background` (`api/main.py:283-307`). The warm-up is guarded
by `SEC_CORPUS_WARMUP != "1" and not DATABRICKS_APP_NAME`, runs in a daemon
thread, and catches all exceptions. **MiMo's judgment is defensible** — there is
no concrete claim to refute. Two adjacent (pre-existing, Minor) nuances MiMo does
not mention: (a) `_load_alias_map`'s "load once" guard is not atomic — the
`_alias_map_loaded` check is inside `_alias_map_lock` but the load happens outside
it (`hybrid_retriever.py:467-527`), so the warm-up thread and a concurrent first
request can both trigger a load; (b) on load failure `_load_alias_map` sets
`_alias_map_loaded = True` with an empty map (`:524-526`), permanently disabling
alias resolution until restart. Neither is introduced by the warm-up and neither
rises above Minor.

### 4. Offline suite
Green (see Checks run). No branch-caused failures.
===VERDICT END===
