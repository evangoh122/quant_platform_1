# VERDICT: corporate-actions-round6
Checker: Claude Sonnet subagent (DeepSeek out of credit)
**Status: CHANGES_REQUESTED**
Reviewed commits a91a2df..2c2ba4a (HEAD). MiMo's self-verdict not used as evidence.

## Counts
- `pytest -q tests/bronze tests/silver tests/test_security.py` (uv env with duckdb/pytest/pandas/polars/loguru/polygon-api-client): 328 passed, 24 skipped, 5 failed. The 5 failures are all `tests/bronze/test_refresh_bronze_cot.py::TestComputeReleaseTs`, which this round does not touch (environment/pre-existing). Identical with the pyspark-hidden PYTHONPATH.
- tests/silver/test_silver_sql_semantics.py: 8 passed. LF endings: 0 CRLF files among changed files.
- No tests deleted or weakened: the only removed test lines are a no-newline-at-EOF line rewritten identically (tests/bronze/test_corporate_actions.py ~1111) and a header renumber.

## Verified OK
1. Suppression SQL silver/08_silver_ohlcv_day_adjusted.sql:161-171 (`WHERE NOT (ca.source='yfinance' AND EXISTS(... m.source='massive' AND ABS(DATEDIFF(m.ex_date, ca.ex_date)) <= 3))`) is valid Databricks SQL (alias `ca` added in 2c2ba4a; correlated EXISTS in WHERE of a window-bearing subquery is permitted; DATEDIFF(end,start) 2-arg form). My own repro (.agents/requests/ca5-sem-repro.py, DuckDB 1.5.6, shim DATEDIFF('day', start, end)): same-day -> 20; massive 06-06 + yfinance 06-03 -> 20 for all bars before 06-06 (not 400). Test DATEDIFF shim (tests/silver/test_silver_sql_semantics.py:55-60) maps `\1`=end,`\2`=start correctly; sign preserved. SQL is extracted at test time from silver/08 (not retyped).
2. Key leak: etl/corporate_actions.py:361 redacted_url, :380-383 own RuntimeError message, :386-396 `raise ... from None`; notebook :449-455 redacts `failures`, print and checkpoint error. Mutation (remove both redactions in /tmp/ca6-mut-c): 3 tests FAIL (test_http_error_no_key_in_exception, test_connection_error_no_key_in_exception, test_mutation_remove_redaction_leaks). Remaining prints (notebook :418 validation err, :545 spark exc) carry no URL.
3. Docs (docs/DATA_SCHEMAS.md ~501, 570-574; notebook docstring) describe the ±3-day rule, both reason codes and back-adjustment caveat.

## Findings (blocking)
1. **SPLIT_SINGLE_SOURCE is never emitted.** grep shows it only in docs/notebook docstring/test docstring, not in silver/08. Case 3 of `_split_source_mismatches` (sql:233-252) emits reason `split_source_mismatch`, and classification is always `SPLIT_SOURCE_MISMATCH` (sql:432). Request item 1 requires yfinance-only splits to be applied AND reported SPLIT_SINGLE_SOURCE; docs now claim behaviour that does not exist. MiMo's own verdict admits this. No test asserts reporting of yfinance-only splits.
2. **Near-match pairs with date difference > 0 are not reported.** Case 1 (sql:~196-212) joins on equal ex_date only; Cases 2/3 are only for rows with NO counterpart within ±3d. AMZN massive 06-06 / yfinance 06-03 (or ratio disagreement at 1-3 days offset) therefore produces no data_quality_breaks row, contrary to request item 1. Not tested.
3. **Mutation `WHERE rn = 1` -> `WHERE 1=1` SURVIVES.** I mutated only the `_resolved_splits` view in /tmp/ca6-mut-a: 8/8 semantics tests still pass. `TestMutationProofs.test_mutation_dedupe_removal_fails` (test file :290+) tests a hand-retyped round-5 SQL string, not a mutation of the real SQL, which the request prohibited. Need a fixture exercising rn (e.g. two massive rows same symbol/ex_date with different fetched_ts/ratio) and a mutation test that edits the extracted real SQL.
4. Mutation removing the ±3-day suppression (`AND 1=0`, /tmp/ca6-mut-b): correctly FAILS (test_near_date_suppression_factor_20, got 400). OK, but that mutation test also uses its own copy; confirm it edits extracted SQL.
5. No test covers `_split_source_mismatches` / data_quality_breaks output at all (request item 2 required "in data_quality_breaks as SPLIT_SINGLE_SOURCE" and "mismatch reported").

## Findings (non-blocking)
6. Notebook-boundary leak tests (test_corporate_actions.py:1227-1275) re-implement the notebook catch block in the test instead of exercising notebook code; report["failures"]/checkpoint error_text paths are not driven through `main()`. Mutating the notebook redaction alone is not caught (adapter redaction masks it).
7. Resume tests (test_corporate_actions.py:~817-850) are source-text greps plus a retyped boolean expression; the per-adapter loop (notebook :408) still refetches an already-completed source in both mode, and failures are checkpointed under adapters[0][0] only (:455).
8. duckdb is installed in CI (.github/workflows/ci.yml:42) but not listed in a requirements file.

## Required for APPROVED
Implement SPLIT_SINGLE_SOURCE (distinct reason) and near-match (|date diff|>0 within 3d, or ratio disagreement) reporting in the SQL; add real-SQL tests for both plus a duplicate-row fixture; make mutation tests mutate the extracted real SQL and show `WHERE rn = 1` -> `1=1` fails.
