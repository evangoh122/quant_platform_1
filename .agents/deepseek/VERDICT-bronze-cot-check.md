# VERDICT: bronze-cot — DeepSeek (checker)

**Status:** APPROVED
**Round:** 3 (check)

===VERDICT START===

## Round-2 blocking finding resolved

The round-2 CHANGES_REQUESTED (off-by-one regression test was tautological) is fixed.
`filter_report_window()` was extracted as a production function
(`notebooks/refresh_bronze_cot.py:343`) and `refresh_dataset` now calls it
(`:427`), so the window-filter tests exercise production code rather than a
re-implemented comparison.

## Independent checks

1. **Append-only write path, incl. table creation — PASS.**
   Single write site: `notebooks/refresh_bronze_cot.py:488-489`
   `.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table)`.
   Missing-table creation is `CREATE TABLE IF NOT EXISTS ... USING DELTA`
   (`:484-486`) with no `.mode("overwrite")` anywhere in the file (grep confirms
   the only `overwrite` token is the comment "never overwrite" at `:479`).

2. **Verify before OK + nonzero exit — PASS.**
   After the append, `post_count - pre_count != new_count` triggers FAILED
   (`:496-502`), then a duplicate-key scan (`:504-517`) runs, and only then is
   `status = "OK"` set (`:519`). `main()` propagates any FAILED to `sys.exit(1)`
   (`:625-628`). "All keys present" is enforced indirectly: a dropped key lowers
   the post delta (caught by the count check); a dropped key plus a duplicated
   row trips the dup scan — sound, though count-based (non-blocking note).

3. **Off-by-one fixed + max+1 test — PASS.**
   Filter uses inclusive `>=` (`notebooks/refresh_bronze_cot.py:368`), and
   `main()` derives `start_date = pre_max + timedelta(days=1)` (`:582`), so a
   report dated exactly max+1 is included. Test
   `tests/bronze/test_refresh_bronze_cot.py:298` (`test_filter_on_max_plus_one`)
   builds a report dated `max + 1 day` and asserts it survives the window.

4. **Tests genuinely cover production — PASS (mutation-verified).**
   - Mutating `filter_report_window` `>=` → `>` in an isolated `/tmp` copy made
     `test_filter_on_max_plus_one` FAIL (`assert 0 == 1`).
   - Mutating `validate_contract_code_column` to return `"WRONG_COL"` made
     `TestValidateContractCodeColumn::test_exact_match` FAIL
     (`assert 'WRONG_COL' == 'CFTC_Contract_Market_Code'`).
   Both tests call the real functions; reverting the round-1/round-2 bugs breaks them.

5. **No re-run duplication — PASS.**
   Existing-table path dedups + left-anti-joins against target keys
   (`anti_join_new_rows`, `:303-320`); no-table path dedups
   (`bronze_df.dropDuplicates(full_key)`, `:466`). A re-run over an already-loaded
   window yields `new_count == 0` and skips the write (`:478`). A crash between
   append and verification is idempotent on the next run because the anti-join
   filters the already-written keys.

## Checks run

- `python3 -m pytest tests/bronze/test_refresh_bronze_cot.py -q` → `41 passed in 20.16s`
- grep `overwrite` in `notebooks/refresh_bronze_cot.py` → only comment token; no write uses overwrite → pass
- grep `\.write|saveAsTable|mode\(` in `refresh_bronze_cot.py` → single append site `:488-489` → pass
- `file` / CRLF scan on both edited files → LF only, no CRLF → pass
- mutation 1 (`>=` → `>`, /tmp copy) → `test_filter_on_max_plus_one` FAIL → pass
- mutation 2 (`return cols_lower[key]` → `"WRONG_COL"`, /tmp copy) → `test_exact_match` FAIL → pass

===VERDICT END===
