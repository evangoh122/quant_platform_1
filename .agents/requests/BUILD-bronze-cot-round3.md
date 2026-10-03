# BUILD-REQUEST: bronze-cot — ROUND 3 (make the date filter testable)

**Branch:** `slice/bronze-cot` · **Builder:** MiMo · **Checkers:** Claude, then DeepSeek
Read `.agents/deepseek/VERDICT-bronze-cot-check.md`. The production fix is correct; the test is not.

1. Extract the incremental date filter at `notebooks/refresh_bronze_cot.py:408`
   (`pdf["_parsed_date"] >= start_date`, plus the end bound and the report-date parsing used
   there) into a pure function, e.g. `filter_report_window(pdf, start_date, end_date)`, and call
   it from `refresh_dataset`. Behaviour must not change.
2. Replace `TestIncrementalWindow.test_filter_after_start_date` (test file :271) and
   `TestReportDateParsing` (:300-316) with tests that **call that function**, including a report
   dated exactly `max + 1 day`.
3. **Prove the test guards the bug:** in a scratch copy under `/tmp` (never in the worktree),
   change `>=` back to `>` and show the new test fails; paste that output, then the passing run.

Do not re-run `--write`. Edit only `notebooks/refresh_bronze_cot.py` and
`tests/bronze/test_refresh_bronze_cot.py`. LF line endings. **Commit your work.**
Write `.agents/mimo/VERDICT-bronze-cot-round3.md`.
