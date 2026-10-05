# VERDICT: xbrl-B1b — MiMo
**Status:** APPROVED
**Round:** 4

## Changes made
- `tests/db/test_xbrl_queries.py`: Replaced `_build_asof_facts_sql()` (test-local query reconstruction) with `CapturingSpark` + `asof_facts()` + `_run_in_duckdb()`.
- Removed `_build_asof_facts_sql()` function entirely (was lines 170-186).
- All 5 `TestAsofFactsDuckDB` tests now call production `asof_facts()` to capture SQL, then execute it in DuckDB.
- `test_mutation_f_alias_breaks_filters` captures production SQL and mutates the WHERE clause to re-introduce `f.` alias, proving DuckDB rejects it.

## Blocking findings
None.

## Non-blocking notes
- No production code (`db/xbrl_queries.py`) was changed — only the test file.
- The `_ASOF_SQL_PATH` import was removed from the test file since `_build_asof_facts_sql` no longer exists.

## Checks run
- `python3 -m pytest tests/db/test_xbrl_queries.py -v` → 14 passed
- Mutation proof (f.ticker/f.concept in production code): 3 DuckDB filter tests fail with `BinderException: Referenced table "f" not found!` → confirms tests catch the regression

## Commit
`de9d04f` on `feat/xbrl-silver`