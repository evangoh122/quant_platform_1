# VERDICT: bronze-cot — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 2 (check)

## Blocking findings

- [tests/bronze/test_refresh_bronze_cot.py:271] The off-by-one regression test is
  tautological and does not exercise production code. `TestIncrementalWindow.test_filter_after_start_date`
  re-implements the comparison `d >= start_date and d <= end_date` inside the test body
  (line 277) and never imports or calls any production function. The production filter it
  is meant to guard lives inline in `notebooks/refresh_bronze_cot.py:408`
  (`pdf["_parsed_date"] >= start_date`), which is not reachable from the test module
  (the test file imports only `cftc_url`, `sanitize_columns`, `compute_release_ts`,
  `validate_contract_code_column`, `anti_join_new_rows`, `detect_revision_conflicts`,
  `to_bronze` — no `refresh_dataset`). Concrete failure scenario: revert line 408 to the
  round-1 buggy `> start_date` and the suite still reports `36 passed` — the off-by-one
  regression is silently unguarded. Round-2 item 3 required "a test with a report dated
  max+1"; item 4's principle "each must fail if that function were broken" is not met for
  this fix. `TestReportDateParsing` (lines 300-316) has the same defect: it re-implements
  `pd.to_datetime(...)` rather than calling the parsing path in `refresh_dataset`.

## Non-blocking notes

- Production off-by-one fix is itself correct: `notebooks/refresh_bronze_cot.py:408` now
  uses `>= start_date`, and `main()` derives `start_date = pre_max + timedelta(days=1)`
  (`:560`), so a report dated exactly max+1 is included.
- "All expected keys present" is enforced indirectly rather than by a literal per-key
  semi-join: `post_count - pre_count == new_count` (`:474`) combined with the zero-duplicate
  key scan (`:482-495`) together imply every new key landed (a dropped key lowers the delta;
  a dropped key plus a duplicated row trips the dup scan). Sound, but only a count-based check.
- The write is not transactional: if verification fails after the append, rows remain
  appended and status is FAILED (nonzero exit). Append-only + anti-join make the next run
  idempotent, so no corruption; flagging for awareness only.
- `CREATE TABLE IF NOT EXISTS` DDL (`:462-464`) uses backtick-quoted names and
  `simpleString()` types (all String/Date/Integer/Timestamp here). `sanitize_columns`
  removes ` ,;{}()\n\t=` but not backtick/backslash, so a hostile column name containing a
  backtick could break the DDL quote — theoretical only (CFTC TFF headers are underscore-safe,
  per `:126-127`), and `table` is a hardcoded constant, not user input.
- `get_target_stats` uses an f-string for `table` (`:297`) — it is a fixed catalog constant,
  not user input, so no injection risk.

## Checks run

- `python3 -m pytest tests/bronze/test_refresh_bronze_cot.py -q` → `36 passed in 21.27s`
- grep `overwrite` in `notebooks/refresh_bronze_cot.py` → no `.mode("overwrite")`; only
  `CREATE TABLE IF NOT EXISTS` + `.mode("append")` (`:462-466`) → pass (append-only)
- verification-before-OK review (`:469-497`) → count-delta + zero-dup checks precede
  `status = "OK"`, FAILED propagates to `sys.exit(1)` (`:603-606`) → pass
- mutation demo (copy of `validate_contract_code_column` forced to return `"WRONG_COL"` in
  `/tmp`) → `test_exact_match` assertion FAILs → test genuinely covers the function → pass
- mutation analysis of `TestIncrementalWindow` → self-contained; independent of
  `refresh_bronze_cot.py:408` → fail (finding above)
