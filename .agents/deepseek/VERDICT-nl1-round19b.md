===VERDICT START===
# VERDICT: nl1-round19b — DeepSeek (checker)
**Status:** APPROVED
**Round:** 19b

Re-check of my round-19 blocker (item 5): the adjusted-return availability test was vacuous (skipped under Codex's DOC mutation). Claude added `tests/analytics_nl/test_ddl.py::test_adjusted_returns_availability_includes_adjusted_source`, which now reads the production DDL at test time via `extract_view_sql("serve_daily_equity_metrics_v1", variant="adjusted")`.

## Verification performed

All mutation checks run in `/tmp/nl1-mut` and `/tmp/nl1-clean` copies created via `git archive HEAD | tar -x -C /tmp/<dir>`. Working tree untouched.

- **Codex's exact mutation now FAILS (not skip).** In the archive copy I applied `GREATEST(dp.information_available_ts, adj.information_available_ts) AS information_available_ts` → `dp.information_available_ts AS information_available_ts` at docs/NL1_PROPOSED_SERVING_VIEWS.md:173:
  ```
  python3 -m pytest tests/analytics_nl/test_ddl.py::test_adjusted_returns_availability_includes_adjusted_source -q
  → 1 failed in 0.38s
  → AssertionError: returns_from_source must output GREATEST(dp.information_available_ts, adj.information_available_ts)
  ```
  Previously this mutation produced a SKIP; it now produces a hard FAIL.
- **Clean copy: the test PASSES (not skipped).**
  ```
  python3 -m pytest tests/analytics_nl/test_ddl.py::test_adjusted_returns_availability_includes_adjusted_source -v
  → 1 passed in 0.10s
  ```
- **Full suite on the unmutated archive:**
  ```
  python3 -m pytest tests/analytics_nl -q
  → 420 passed in 20.12s
  ```

## Blocking findings

None.

## Non-blocking notes

- `test_adjusted_returns_availability_includes_adjusted_source` (test_ddl.py:1988) is a standalone function, not a method of `TestDDLAvailabilityContract`, but it imports `extract_view_sql` locally and reads the production DDL at test time, so it is not vacuous. The `returns_from_source` CTE regex (`returns_from_source AS \((.*?)\n\)`) depends on the CTE closing paren being on its own line; if the DDL were reflowed such that `)` lands mid-line the regex could miss it, but the leading `assert m` guards against silent skipping (would raise, not skip).
- The assertion checks the exact GREATEST expression including both `dp.information_available_ts` and `adj.information_available_ts`, so it also protects against partial regressions (e.g. GREATEST of a single arg).

## Checks run

- `python3 -m pytest tests/analytics_nl/test_ddl.py::test_adjusted_returns_availability_includes_adjusted_source -q` → 1 failed (mutated copy) / 1 passed (clean copy)
- `python3 -m pytest tests/analytics_nl -q` → 420 passed (clean copy)
===VERDICT END===
