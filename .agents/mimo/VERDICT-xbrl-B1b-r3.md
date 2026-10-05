# VERDICT: xbrl-B1b-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
- (none)

## Non-blocking notes
- The fix changes `f.ticker`/`f.concept` to bare `ticker`/`concept` in the outer WHERE clause. Since the outer query wraps the base SQL as `_asof_filtered` and there is only one table source, bare column names resolve unambiguously.
- DuckDB mutation test confirms the original `f.` prefix causes `BinderException: Referenced table "f" not found`, proving the bug was real and the fix eliminates it.

## Checks run
- `python3 -m pytest tests/db/test_xbrl_queries.py -v` → 14 passed (9 FakeSpark string tests + 5 DuckDB execution tests)
- `python3 -m pytest tests/silver/test_sec_xbrl_facts.py -v` → 15 passed (silver transform + PIT query tests)
- `git diff --cached` → 2 files changed: `db/xbrl_queries.py` (alias fix), `tests/db/test_xbrl_queries.py` (test updates + new DuckDB tests)