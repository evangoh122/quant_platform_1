===VERDICT START===

# VERDICT: rag-coverage round 8b — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 8b

## Summary

All four production fixes (Codex findings 7–10) are implemented and correct, and the
Claude tiny fix (my 8a-2 findings 1–2) is confirmed load-bearing. But item 7 has two
regression tests that do **not** fail on the old code, and item 9 is missing its required
DuckDB "exact rows" test. Per the build request — "Every fix needs a test that FAILS on the
old code" — those items are not fully satisfied, so the round cannot be APPROVED yet.

## Blocking findings

1. **[tests/rag/test_sec_embeddings_incremental.py:368] `test_comma_separated_ticker_uses_isin`
   is not load-bearing.** It asserts only `mock_anti_join_df.filter.called` and never inspects
   the predicate (the test even comments "we can't easily inspect the isin"). Mutation proof:
   revert `pipelines/build_sec_embeddings.py:105-110` to scalar `F.col("ticker") == ticker.upper().strip()`
   → the test still **passes**. Concrete failure: a regression back to scalar equality — the exact
   defect item 7 fixes (a comma list embeds nothing) — ships green.

2. **[tests/rag/test_sec_embeddings_incremental.py:435] `test_inserted_count_from_metrics` is not
   load-bearing.** It embeds a single chunk, so candidate count (`len(out_rows)` == 1) equals the
   MERGE metric (`numTargetRowsInserted` == 1) and the assertion `rows_written == 1` cannot
   distinguish the two sources. Mutation proof: revert `_embed_and_write_batch` to
   `return len(out_rows)` → test still **passes**. Concrete failure: the "actual inserted rows"
   vs "candidates" fix could be reverted and CI stays green.

3. **[tests/rag/test_sec_coverage_sql.py] Item 9's DuckDB "exact rows" test is missing.** The build
   request requires "SQL extracted from the file run in DuckDB on fixtures (universe, mapping log,
   filings, chunks) asserting exact rows". Only static substring assertions exist; nothing executes
   the SQL. Concrete failure: a semantically wrong query (wrong `ROW_NUMBER() ... ORDER BY mapped_ts`
   direction, join on the wrong column, `status` filter on the wrong CTE, `coalesce` of the wrong
   column) passes every current static check. The repo already has DuckDB fixture tests
   (`tests/gold/test_pit_leakage.py`, `tests/rag/test_chat_engine.py`) to copy the pattern from.

4. **[tests/rag/test_sec_embeddings_incremental.py:315] Item 7 "both batches' rows written" is not
   asserted.** `test_concurrent_batches_use_distinct_view_names` verifies only that two distinct
   view names were created; it never checks that both batches' rows reached the table (the second
   half of the build-request test spec). Non-ideal but lower severity than #1–#2.

## Verified items (positive)

- **Item 8 (retrieval) — PASS.** `reload_corpus(None)` no-eager-load spy
  (`test_hybrid_retriever.py:2906`) and NULL/unparseable-`accepted_ts` exclusion
  (`test_hybrid_retriever.py:3024`+ `TestNullTimestampExcludedFromVectorSearch`) are both killed on
  old code (4 tests fail when `api/services/hybrid_retriever.py` reverts to `return _load_corpus()`
  and `if accepted_dt is not None and accepted_dt > as_of`).
- **Item 10 (tools_retrieval + bronze MERGE) — PASS.** `test_table_error_does_not_invoke_substring_path`
  (`test_sec_retrieval_tool.py:146`) asserts `_spark().table` is never called; killed when
  `agent/tools_retrieval.py` reverts to the substring fallback. Bronze MERGE now uses an explicit
  column list (`pipelines/sec_rag_ingest.py:1573-1586`).
- **Claude tiny fix (8a-2 #1 FakeDataWriter) — PASS.** `test_merge_rerun_inserts_zero` now asserts
  `first == 50` / `second == 0`; killed when `FakeDataWriter.append_bronze_rows` reverts to
  accession-dedup (assert `1 == 50` fails).
- **Claude tiny fix (8a-2 #2 history overlap) — PASS.** Fixture `filingFrom="2024-10-01"` (≥
  `start_date="2024-09-01"`) is now load-bearing: reverting the skip condition to old
  `filingFrom < start_date` semantics makes `test_history_overlap_uses_filing_to` fail
  (`assert '002' in {'001'}`).

## Non-blocking notes

- **[pipelines/run_silver_gold.py / gold/07_gold_sec_coverage.sql] "out-of-universe counted/logged"
  not implemented.** The SQL restricts to universe via `LEFT JOIN` (correct), but there is no
  separate log count of out-of-universe tickers as the build request's parenthetical suggests. Soft
  requirement; acceptable.
- **[pipelines/sec_rag_ingest.py:1663,1680-1682] 8a-2 blocking #3 (SQL injection) still open.**
  `SparkIngestLogReader` still builds `WHERE run_id = '{run_id}'` / `ticker = '{ticker}'` /
  `accession_number = '{accession_number}'` via f-string value interpolation. Out of scope for round
  8b (which covers findings 7–10 only), but it is a hard-rule violation from my prior verdict and
  must be fixed before the gate. Flagging so it is not lost.
- **[tests/rag/test_sec_retrieval_tool.py:128] `test_spark_table_error_returns_retrieval_unavailable`
  is not independently load-bearing** (it also passes on old code because the substring fallback's
  own failure yields `retrieval_unavailable`). Item 10 remains covered by the
  `assert_not_called()` test at :146; no action required, just noting the overlap.

## Mutation results (revert each fix in `/tmp/rc8b-mut` = `git archive HEAD | tar -x`)

| Mutation | Reverted fix | Result |
|---|---|---|
| item10 | `agent/tools_retrieval.py` → substring fallback | **KILLED** — `test_table_error_does_not_invoke_substring_path` fails (`table` called) |
| item8 | `hybrid_retriever.py` → `return _load_corpus()` + `accepted_dt is not None` | **KILLED** — 4 tests fail |
| item7 | `build_sec_embeddings.py` → scalar `==` / shared `_embed_src` / `len(out_rows)` | **PARTIAL** — `test_concurrent_batches_use_distinct_view_names` fails; `test_comma_separated_ticker_uses_isin` and `test_inserted_count_from_metrics` PASS (weak) |
| item9 | `gold/07_gold_sec_coverage.sql` → hardcoded catalog/schema + FULL OUTER JOIN + CIK-from-bronze | **KILLED** — 4 static tests fail (but no DuckDB exact-rows test exists) |
| claude-8a2-1 | `FakeDataWriter` → accession-dedup | **KILLED** — `test_merge_rerun_inserts_zero` fails (`1 == 50`) |
| claude-8a2-2 | history overlap skip → `filingFrom >= start_date` | **KILLED** — `test_history_overlap_uses_filing_to` fails (`002` missing) |

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **626 passed, 36 skipped, 0 failed** (15.7s)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **466 passed, 19 skipped, 0 failed** (12.3s)
- `git diff --check 2100743..HEAD` → pass (no whitespace errors)
- `git show 2100743..HEAD` secret scan (password/secret/api_key/token/AKIA) → none
- `git show 2100743..HEAD --name-only` → in-scope files only (`build_sec_embeddings.py`, `resources/jobs.yml`,
  `hybrid_retriever.py`, `gold/07_gold_sec_coverage.sql`, `run_silver_gold.py`, `tools_retrieval.py`,
  `sec_rag_ingest.py`, and their tests) plus the Claude test-only commit `956184f`.
- No tests deleted/weakened: the ~194 removed lines in commit `70a966c` are the substring-fallback
  tests, deleted because the fallback path itself (the item-10 defect) was removed, and replaced by
  structured-error tests. Net test count rose (608 → 626).

===VERDICT END===
