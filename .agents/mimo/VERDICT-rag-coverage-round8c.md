# VERDICT: rag-coverage round 8c — MiMo (builder)
**Status:** APPROVED
**Round:** 8c

## Blocking findings
None.

## Non-blocking notes
- DuckDB `test_exact_output_rows` relies on `CREATE OR REPLACE TABLE ... AS` which DuckDB supports natively; no shim needed.
- The `_EvalCol` spy in `test_comma_separated_ticker_uses_isin` replaces `F.col` for the duration of the test and restores it in a `finally` block; no leakage to other tests.

## Changes made

### 1. `test_comma_separated_ticker_uses_isin` (line 368) — now load-bearing
Replaced the weak `assert mock_anti_join_df.filter.called` with an `_EvalCol` spy that:
- Captures the Column expression passed to `.filter()`
- Evaluates it on test rows: {"AAPL": keep, "MSFT": keep, "GOOG": drop}
- Mutation proof: scalar `F.col("ticker") == "AAPL,MSFT"` sets `_op="eq"` and `evaluate({"ticker": "MSFT"})` returns False → test FAILS.

### 2. `test_inserted_count_from_metrics` (line 486) — now load-bearing
Changed from 1 candidate chunk to 3 candidates. MERGE mock reports `numTargetRowsInserted = "1"` (2 already existed). Asserts `rows_written == 1`.
- Mutation proof: `return len(out_rows)` returns 3, not 1 → `assert 3 == 1` FAILS.

### 3. `test_sec_coverage_sql.py` — DuckDB execution test added
New `TestGoldCoverageDuckDB` class with3 tests:
- `test_exact_output_rows`: Runs gold SQL on DuckDB fixtures (universe: AAPL+MSFT; mapping_log: AAPL has 2 mapped entries with different CIKs; filings/chunks for AAPL, MSFT, GOOG). Asserts exact output rows.
- `test_out_of_universe_excluded`: GOOG (not in universe) must not appear.
- `test_row_number_picks_latest_mapped`: Asserts AAPL CIK is from the newer mapped entry.
- Mutation proof (ORDER BY ASC): AAPL gets older CIK 0000000000 instead of 0000320193 → FAILS.
- Mutation proof (FULL OUTER JOIN): GOOG appears in output → FAILS.

### 4. `test_concurrent_batches_use_distinct_view_names` (line 315) — now load-bearing
Added assertion that both concurrent batches' rows reached the target table. Tracks `createDataFrame` calls and verifies all 6 chunk_ids (c0-c5) appear across the2 batch write calls.

## Mutation results (revert each fix in `/tmp/rc8c-mut` = `git archive HEAD | tar -x`)

| Mutation | Reverted fix | Result |
|---|---|---|
| mutation1 | `build_sec_embeddings.py` isin → scalar `==` | **KILLED** — `test_comma_separated_ticker_uses_isin` fails (`MSFT must be kept`) |
| mutation2 | `_embed_and_write_batch` `return len(out_rows)` | **KILLED** — `test_inserted_count_from_metrics` fails (`3 == 1`) |
| mutation3 | `07_gold_sec_coverage.sql` ORDER BY DESC → ASC | **KILLED** — `test_row_number_picks_latest_mapped` fails (`0000000000 != 0000320193`) |
| mutation4 | `07_gold_sec_coverage.sql` LEFT JOIN → FULL OUTER JOIN | **KILLED** — `test_out_of_universe_excluded` fails (`GOOG` in output) |

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q` → 629 passed, 36 skipped, 0 failed (15.1s)
- `PYTHONPATH=.../nps python3 -m pytest tests/rag -q` → 469 passed, 19 skipped, 0 failed (13.8s)
- `git diff --stat HEAD~1` → 2 files changed (test_sec_coverage_sql.py, test_sec_embeddings_incremental.py)
- No secrets in committed files (password/secret/api_key/token/AKIA scan clean)
- No tests deleted or weakened