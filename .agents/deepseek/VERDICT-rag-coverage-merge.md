===VERDICT START===
# VERDICT: rag-coverage merge (origin/main + post-merge fixes) — DeepSeek (checker)
**Status:** APPROVED
**Round:** 16d-merge (post-merge check)

## Scope

Checked the merge `5ba57e4` (`origin/main` incl. #16/#26/#27) plus post-merge commits
`8b792dc` (r16c tests) and `787e725` (fixture sys.modules restore + isolation guards), at HEAD
`5c562bf`. Read-only; the only mutation was performed in a `git archive HEAD | tar -x` copy at
`/tmp/qp1-mut` (no git in the copy).

## (1) Conflicted files — union preserved (both parents)

Per-file diff of `HEAD` against `5ba57e4^1` (branch) and `5ba57e4^2` (origin/main). Nothing from
either side is dropped.

| File | Branch-only content retained | Main-only content retained |
| :--- | :--- | :--- |
| `agent/tools_retrieval.py` | `NoCoverageError`/`TickerRequiredError` → `no_coverage`/`ticker_required` (`:121-128`) | `retrieve_and_rerank` (`:93`) + PIT substring fallback (`:151-195`) |
| `docs/DATA_SCHEMAS.md` | `sec_ingest_log`, `sec_cik_mapping_log`, `gold_sec_coverage` | `gold_sec_kg_*`, `gold_tradable_universe`, `gold_regime_features`, `bronze_corporate_actions`, `silver_ohlcv_day_adjusted`, `data_quality_breaks` |
| `pipelines/run_silver_gold.py` | `gold_sec_coverage` step/table (`:55,:67`) | `silver_ohlcv_day_adjusted`, `data_quality_breaks`, `_NO_TRUNCATE` (`:102`), corporate-action checks (`:314+`), `{catalog}/{schema}` substitution |
| `resources/jobs.yml` | `sec_rag_ingest` (with `--user-agent-secret-scope/--user-agent-secret-key`) | `corporate_action_refresh`, `sec_knowledge_graph_build` |
| `tests/rag/conftest.py` | `_clear_ticker_lru_cache`, `_mock_check_ticker_coverage`, `psycopg.rows`, `_ColExpr.__and__/__or__/__invert__` | `_reset_retriever_singletons`, `_block_network`, `_FakeCrossEncoder`, `_no_cross_encoder_load` |
| `tests/rag/test_hybrid_retriever.py` | 112 test defs (superset) | 112 test defs (superset) |

### jobs.yml union (verbatim)
6 jobs at HEAD: `silver_gold_refresh`, `corporate_action_refresh`, `ml_ablation`, `sec_embeddings`,
`sec_rag_ingest`, `sec_knowledge_graph_build` — every job from both parents. `sec_rag_ingest` keeps
the secret params `--user-agent-secret-scope evangoh_capstone` / `--user-agent-secret-key
sec_edgar_user_agent` (scope/key names only, no secret value in repo).

### search_sec_filings invariants
`agent/tools_retrieval.py:67` `except` ordering is: `(NoCoverageError, TickerRequiredError)` at
`:121` → `EmbeddingConfigError` at `:127` (correctly before its parent `CorpusUnavailableError`,
which is at `:143`) → generic `except Exception` (substring fallback) at `:151`. `NoCoverageError`
and `TickerRequiredError` are direct `Exception` subclasses (`api/services/hybrid_retriever.py:46,:50`),
not `CorpusUnavailableError` subclasses, so they are caught at `:121` and **never reach the
fallback**. The PIT substring fallback (`:161-168`) filters `unix_timestamp(accepted_ts) <=
as_of_epoch` and tags `retrieval_mode: "substring_fallback"` (`:192`). This matches the request:
branch's no_coverage/ticker_required **and** main's retrieve_and_rerank **and** main's PIT fallback
are all present.

## (2) No test deleted or weakened

`def test_` counts: P1=110, P2=87, HEAD=112 (superset of both). The 4 names present in a parent but
absent from HEAD are renames that reflect the intended merged semantics, not deletions:

- `test_spark_table_error_returns_retrieval_unavailable` (P1) → `test_spark_table_error_triggers_substring_fallback` (`tests/rag/test_hybrid_retriever.py:1257`) + `test_generic_exception_returns_retrieval_unavailable` (`:1329`). P1 asserted "no fallback"; the merged code has a fallback, so the test was correctly rewritten.
- `test_missing_accepted_ts_included_defensively` (P2) → `test_missing_accepted_ts_excluded` (`:308`). The branch deliberately changed `_pit_filter` to EXCLUDE missing/null `accepted_ts` (`api/services/hybrid_retriever.py:618-636`); the P1 semantics won and the test was flipped to match. Not a weakening.
- `test_fallback_as_of_filters_future_filings` (P2) → `test_generic_exception_fallback_succeeds_with_pit_filter` (`:1356`); `test_fallback_error_returns_structured_unavailable` (P2) → `test_generic_exception_returns_retrieval_unavailable` (`:1329`).

PIT coverage is intact: `TestPITFilter` + `TestPITIntegrationRetrieval` assert future-dated chunks
are excluded in `bm25_search`, `vector_search`, and `retrieve` (`:276-445`).

## (3) Fixture sys.modules restore — mutation proof

The fix at `tests/rag/test_sec_rag_ingest.py:75-116` snapshots every `pyspark*`/`databricks*`
`sys.modules` entry before the module-scoped `_mock_pyspark` patch, then after `yield` drops any
submodule imported during the mock window and restores the snapshot. `tests/rag/test_sec_retrieval_tool.py:17-32`
pre-imports `pyspark.sql.column` for the same reason.

Mutation (revert both in `/tmp/qp1-mut`):

```
$ python3 -m pytest tests/rag tests/bronze -q
FAILED tests/bronze/test_refresh_bronze_options.py::test_shape_day_emits_uppercase_right
AssertionError in pyspark/sql/connect/functions/builtin.py:138 _invoke_function
1 failed, 1127 passed, 36 skipped
```

With the fix in place, the same command → **1128 passed, 0 failed**. The fixture fix is
load-bearing: reverting it reproduces the exact order-dependent bronze failure that round 16d
described.

## (4) Branch invariants hold

- **rows=unknown semantics**: `TestTotalRowsAppendedAggregation` (`tests/rag/test_sec_rag_ingest.py:2279+`)
  asserts `total_rows_appended is None` when any filing's writer returns `None` (8 cases + 1 mutation
  test that fails if skip-None aggregation is restored).
- **Secret resolution**: `_resolve_user_agent` (`pipelines/sec_rag_ingest.py:86-154`) resolves
  env → `sdk_runtime` dbutils → `globals()` dbutils → `WorkspaceClient().secrets.get_secret`,
  never hardcoding a value.
- **Value-leak tests**: `test_value_never_appears_in_log`, `test_log_value_leak_mutation_fails`,
  `test_sdk_success_value_never_in_logs`, `test_dbutils_sdk_runtime_success_value_never_in_logs`,
  `test_dbutils_globals_success_value_never_in_logs` (`tests/rag/test_sec_rag_ingest.py:3007-3251`).
- **Coverage gating**: `TestNoCoverage` (`tests/rag/test_hybrid_retriever.py:2568+`) +
  `test_no_coverage_never_reaches_fallback` (`:1398`) — `NoCoverageError` → `[{"error": "no_coverage"}]`,
  never the fallback.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **1128 passed, 36 skipped, 0 failed** (42.7s). Matches Claude's report.
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **5 failed, 2125 passed, 107 skipped, 24 deselected** (233s). See notes below.
- Mutation (git-archive copy `/tmp/qp1-mut`, revert of `787e725` to both `_mock_pyspark` fixtures) → `pytest tests/rag tests/bronze -q` → **1 failed** (`test_shape_day_emits_uppercase_right`).
- `git diff 5ba57e4^1 HEAD` and `git diff 5ba57e4^2 HEAD` over the six conflicted files → union verified (above).
- Test-def counts: `grep -c 'def test_'` → P1=110, P2=87, HEAD=112.

## Non-blocking notes

- **Full-suite failures are dev-machine-specific, not a merge regression.** The five failures are:
  1. `tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms` — `pytest-timeout >30s` in `ml/features.py:598` `pd.to_numeric`. `ml/` is untouched by this merge; pre-existing slow test.
  2. `test_fallback_results_tagged_with_retrieval_mode` (`tests/rag/test_hybrid_retriever.py:1236`) — `pytest-timeout >30s`: `_spark()` is not mocked, so the merged substring fallback calls `DatabricksSession.builder.serverless(True).getOrCreate()`, which resolves the dev's real `~/.databrickscfg` host `dbc-7b106152-caf3.cloud.databricks.com` and retries `/.well-known/databricks-config` until timeout.
  3. `test_fallback_output_keys_match_hybrid_path` (`:1300`) — same unmocked-`_spark()` cause.
  4. `test_zz_isolation.py::test_databricks_connect_not_polluted` — `databricks.connect` left as MagicMock (downstream of 2/3).
  5. `test_zz_isolation.py::test_pyspark_connect_mode_not_leaked` — `SPARK_CONNECT_MODE_ENABLED` set (downstream of 2/3; set by the databricks-connect library during the connection attempt, not by any repo test).

  In CI (`ubuntu-latest`, `.github/workflows/ci.yml`) `databricks-connect` and `pyspark` are not
  installed and there is no `~/.databrickscfg`, so `_get_spark()` fails fast (`ImportError`/no-host)
  and tests 2–5 pass. Recommended follow-up (not a gate): mock `_spark()` in
  `test_fallback_results_tagged_with_retrieval_mode` and `test_fallback_output_keys_match_hybrid_path`
  exactly as the sibling tests already do (`test_generic_exception_returns_retrieval_unavailable`,
  `test_spark_table_error_triggers_substring_fallback`), and refresh their stale docstrings ("not
  substring fallback") to match the merged fallback semantics.
===VERDICT END===
