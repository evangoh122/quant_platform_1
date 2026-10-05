===VERDICT START===

# VERDICT: rag-coverage round 8c — DeepSeek (checker)
**Status:** APPROVED
**Round:** 8c

## Summary

All four round-8b "non-load-bearing test" findings are now resolved. Each of my four named
mutations now kills its target test, and the DuckDB test provably executes the SQL read from
`gold/07_gold_sec_coverage.sql` (not a copy). No tests were deleted or weakened. Full suites green.

## Verified items (positive)

- **Finding #1 (`test_comma_separated_ticker_uses_isin`) — LOAD-BEARING.** The `_EvalCol` spy
  captures the actual Column expression passed to `.filter()` and evaluates it on rows. Mutation
  `isin` → scalar `F.col("ticker") == ticker.upper().strip()` makes
  `evaluate({"ticker": "AAPL"})` return `False` → test fails with `"AAPL must be kept"`.
- **Finding #2 (`test_inserted_count_from_metrics`) — LOAD-BEARING.** 3 candidates vs
  `numTargetRowsInserted = "1"`. Mutation `return len(out_rows)` → `rows_written == 3` → test fails
  `assert 3 == 1`.
- **Finding #3 (DuckDB exact-rows test) — LOAD-BEARING, real file.** `_load_coverage_sql()` reads
  `SQL_PATH = …/gold/07_gold_sec_coverage.sql` (the actual file) and only strips the
  `{catalog}.{schema}.` prefix. Mutating the actual SQL file flips the DuckDB result, proving the
  test runs the extracted SQL, not a copy:
  - flip `ORDER BY mapped_ts DESC` → `ASC` kills `test_exact_output_rows` + `test_row_number_picks_latest_mapped` (AAPL CIK `0000000000` ≠ `0000320193`).
  - drop universe restriction (`LEFT JOIN` → `FULL OUTER JOIN`) kills `test_exact_output_rows` (3 rows ≠ 2) + static `test_restricted_to_universe`.
- **Finding #4 (`test_concurrent_batches_use_distinct_view_names`) — new "both batches' rows"
  assertion is independently LOAD-BEARING.** Mutation that drops the 2nd batch's rows *while keeping
  distinct view names* kills the new assertion (`Expected all 6 chunk_ids … got {c0,c1,c2}`). The
  shared-view-name regression (`view_name = "_embed_src"`) is still caught by the pre-existing
  distinct-view-names assertion, so the test fails under both drop-rows variants.

## Mutation results (fresh copies via `git archive HEAD | tar -x -C /tmp/rc8c-mut`)

| Mutation | Reverted fix | Result |
|---|---|---|
| m1 | `build_sec_embeddings.py:105-110` isin → scalar `F.col("ticker") == ticker.upper().strip()` | **KILLED** — `test_comma_separated_ticker_uses_isin` fails (`AAPL must be kept`, evaluate→False) |
| m2 | `build_sec_embeddings.py:284` `return inserted if inserted>0 else len(out_rows)` → `return len(out_rows)` | **KILLED** — `test_inserted_count_from_metrics` fails (`3 == 1`) |
| m3a | `gold/07_gold_sec_coverage.sql` `ORDER BY mapped_ts DESC` → `ASC` | **KILLED** — `test_exact_output_rows` + `test_row_number_picks_latest_mapped` fail (`0000000000` vs `0000320193`) |
| m3b | `gold/07_gold_sec_coverage.sql` `LEFT JOIN` → `FULL OUTER JOIN` | **KILLED** — `test_exact_output_rows` (3 rows) + `test_restricted_to_universe` fail |
| m4 | `build_sec_embeddings.py:250` unique view → shared `_embed_src` | **KILLED** — `test_concurrent_batches_use_distinct_view_names` fails (`_embed_src != _embed_src`) |
| m4c | drop 2nd batch's rows while keeping distinct view names | **KILLED** — new assertion fails (`all_chunk_ids` missing c3/c4/c5) |

## Non-blocking notes

- The DuckDB shim `_load_coverage_sql` strips `{catalog}.{schema}.` as one prefix, whereas the
  runner (`pipelines/run_silver_gold.py:145-148`) substitutes `{catalog}` and `{schema}`
  separately. Functionally equivalent for the test; cosmetic.
- `test_out_of_universe_excluded` does not fire on the FULL OUTER JOIN mutation alone — under a
  FULL OUTER JOIN the out-of-universe row surfaces with `ticker = NULL`, so `"GOOG" not in tickers`
  still passes. The regression is nonetheless caught by `test_exact_output_rows` (row count 3≠2)
  and the static `test_restricted_to_universe`. The named mutation still fails the suite.
- The "both batches' rows" assertion captures rows at `createDataFrame`/`createOrReplaceTempView`
  (the MERGE source), not literally the post-MERGE target row count. Reasonable mock-level proxy;
  not blocking.
- Out of scope, carried from prior verdicts: `pipelines/sec_rag_ingest.py` `SparkIngestLogReader`
  still builds `WHERE run_id = '{run_id}'` / `ticker = '{ticker}'` / `accession_number =
  '{accession_number}'` via f-string interpolation (hard-rule violation). Must be fixed before the
  gate; not part of round 8c scope.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **629 passed, 36 skipped, 0 failed** (13.8s)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **469 passed, 19 skipped, 0 failed** (13.2s)
- `git diff --check d2f4131^..d2f4131` → pass (no whitespace errors)
- `git show d2f4131` secret scan (password/secret/api_key/token/AKIA) → none
- `git show d2f4131 --name-only` → in-scope test files only (`tests/rag/test_sec_coverage_sql.py`,
  `tests/rag/test_sec_embeddings_incremental.py`)
- No tests deleted/weakened: embeddings file retains all 15 test functions (rewritten/strengthened);
  coverage file +3 new DuckDB tests (14→17). Net suite count 626→629.

===VERDICT END===
