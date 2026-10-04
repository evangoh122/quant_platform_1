# VERDICT options-right-case
Checker: Claude Sonnet subagent (DeepSeek out of credit)
Commit checked: 6b5e6c4 (diff bbe7147..6b5e6c4). No Databricks access used.

## Verdict: CHANGES_REQUESTED

## Findings
1. PASS gold/02: all 4 `right` comparisons are UPPER(right) vs uppercase literal: gold/02_gold_options_features.sql:73,74 (day CTE), :115 (p25 = 'PUT'), :123 (c25 = 'CALL'). p25/c25 still match any case in bronze_options_quotes. Line 96 only selects `right`.
2. PASS repo-wide grep (silver gold pipelines ml strategies api analytics_nl notebooks): no other case-sensitive option-side comparison. silver/03:30-33 and silver/04:20-23 use lower(right) IN ('call','c'). ml/features.py `right` is a pandas frame (unrelated). notebooks/01_ingest_market_data.py:243-286 writes 'C'/'P' to a separate path (not touched, not compared). api/ references are doc strings only.
3. CHANGE REQUESTED (scope creep, new mixed case): the commit also changed the bronze_options_quotes writer. notebooks/refresh_bronze_options.py:247-253 (_right_from_contract_type, used by shape_quote_row at :278/:305) now emits 'CALL'/'PUT' (was 'call'/'put' since 103fba1, "matching live table encoding"). The BUILD spec said not to change quotes semantics unless docs say uppercase. docs/DATA_SCHEMAS.md says nothing on case for quotes, and BRONZE_REFRESH_PLAN.md:223 only specifies CALL/PUT for the DAY table. Original p25/c25 compared lowercase against quotes, which implies existing quotes rows are lowercase. New uppercase quote rows will create a mixed-case bronze_options_quotes, with no backfill. Downstream stays correct (gold UPPER, silver lower()), so no data bug today. Fix: either revert the quotes path to lowercase (the day path stays uppercase through parse_opra_symbol/_shape_day), or add a quotes normalisation maintenance SQL after Claude verifies live quote case. Note _right_from_contract_type is only used by the quotes path, and parse_opra_symbol only by the day path, so they are separable. The MiMo verdict does not mention this.
4. MINOR sql/maintenance/2026-10-04_normalize_options_right_case.sql: correct table, idempotent (WHERE right IN ('put','call')), touches only those values, has pre/post SELECTs. `right` is unquoted (lines 18, 23, 24, 29); gold/silver also use it unquoted and those run live, so it very likely parses, but backticks (`right`) are safer in UPDATE SET. The pre/post SELECTs include 'PUT','CALL' so they show the delta. File lacks a trailing newline. Header should note it contradicts the BRONZE_REFRESH_PLAN.md:13 "no Bronze UPDATE" rule (one-off, owner-approved).
5. CHANGE REQUESTED tests/gold/test_options_right_case.py: the DuckDB semantic test (lines 49-62, `_DAY_CTE`) is a retyped copy, NOT extracted from gold/02, so reverting gold/02 does not fail it. test_mutation_proof_revert_upper_fails (:117) is tautological (it asserts mutated SQL yields the wrong number; always passes). Regex tests do scan the real file, but repo-wide test covers only *.sql in silver/gold/pipelines (not .py).
6. PASS tests/bronze/test_refresh_bronze_options.py: 5 assertion edits (lines 28, 38, 188, 204, 232-235), all lowercase to uppercase, none removed.

## Test run (/tmp/h8-venv, pyspark hidden PYTHONPATH)
pytest tests/gold tests/bronze tests/silver: 194 passed, 22 skipped, 7 failed. All 7 failures are `ModuleNotFoundError: pytz` (5 in test_refresh_bronze_cot.py, 2 in test_pit_leakage.py); the same fail on base bbe7147 (env issue, not this change).

## Mutation proofs (/tmp/optcase-mut-a, -b, -c)
- a) gold/02:73 UPPER reverted: FAILED test_gold_sql_right_comparisons_are_case_insensitive and test_repo_wide_no_case_sensitive_right_comparisons (2 failed). The DuckDB test still passed (finding 5).
- c) all UPPER(right) reverted: same 2 regex tests fail.
- b) ingestion reverted to base (lowercase): 8 failed (parse_opra_symbol call/put, shape_quote_row_full/put/normalisation, and 3 new tests in test_options_right_case.py).

## Required for APPROVED
- Resolve finding 3 (revert quotes writer to lowercase, or justify and add quotes normalisation).
- Make the DuckDB test read the `day` CTE from gold/02 (shim only convert_timezone/make_interval), and drop or replace the tautological mutation test.
