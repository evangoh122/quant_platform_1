# VERDICT: bronze-cot-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Summary

Extracted the incremental date filter into a pure, testable function
`filter_report_window(pdf, start_date, end_date)` and replaced the tautological
tests with ones that actually call the production code.

## Changes made

### notebooks/refresh_bronze_cot.py
- Added `filter_report_window()` at line 343 — pure function that strips,
  parses, and filters the report-date column using `>=` / `<=` (inclusive window).
- `refresh_dataset()` now calls `filter_report_window()` via `try/except KeyError`
  instead of inline logic. Behaviour is identical: column-missing → FAILED status.
- Edge cases handled: empty DataFrame (early return), `.astype(str)` for mixed
  dtypes, `pd.Timestamp` comparison to avoid NaT/date type mismatch.

### tests/bronze/test_refresh_bronze_cot.py
- Added `filter_report_window` to imports.
- `TestIncrementalWindow`: 8 tests, all calling `filter_report_window()` directly.
  Key test: `test_filter_on_max_plus_one` — a report dated exactly `max + 1 day`
  must be included. Reverting `>=` to `>` in production causes this test to fail.
- `TestReportDateParsing`: 3 tests exercising the parsing path inside
  `filter_report_window()` — ISO format, invalid date (NaT excluded), whitespace.
- Both classes no longer re-implement the comparison logic; they delegate to
  the production function.

## Mutation proof

Scratch copy at `/tmp/cot-mutation-test/refresh_bronze_cot_buggy.py` with
`(parsed > start_ts)` instead of `(parsed >= start_ts)`:

```
=== MUTATION TEST: >= changed to > ===
Testing filter_report_window with start_date=2026-10-04, end_date=2026-10-04
Result rows: 0
FAIL: max+1 row was dropped (off-by-one bug reintroduced)
```

Real test (production code with `>=`):

```
tests/bronze/test_refresh_bronze_cot.py::TestIncrementalWindow::test_filter_on_max_plus_one PASSED
```

Full suite: **41 passed in 20.96s**

## Checks run

- `python3 -m pytest tests/bronze/test_refresh_bronze_cot.py -v` → 41 passed
- `python3 -m pytest tests/bronze/test_refresh_bronze_cot.py::TestIncrementalWindow tests/bronze/test_refresh_bronze_cot.py::TestReportDateParsing -v` → 11 passed
- Mutation test (>= → >) → FAIL (0 rows instead of 1) → proves test guards the bug
- `grep "parsed >= start_ts" notebooks/refresh_bronze_cot.py` → line 368, correct `>=`
- `file notebooks/refresh_bronze_cot.py tests/bronze/test_refresh_bronze_cot.py` → LF line endings, no CRLF
- `git diff` reviewed — only the two target files changed, no secrets