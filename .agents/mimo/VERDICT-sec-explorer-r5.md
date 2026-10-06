# VERDICT: sec-explorer-r5 — MiMo
**Status:** APPROVED
**Round:** 5

## Fixed findings

### 1. SECURITY: /api/sec/coverage missing identity dependency and demo gate
- **File:** `api/routes/sec.py:50-55`
- **Defect:** Endpoint invoked `_read_coverage_rows()` directly without `Depends(get_current_user)` or `read_delta` wrapper. Unauthenticated requests could trigger warehouse reads; public-demo mode bypassed the no-live-data gate.
- **Fix:** Added `_user: AppUser = Depends(get_current_user)` parameter and wrapped read with `read_delta()` (returns `unavailable` in demo mode without calling live fn). Pattern copied from `api/routes/signals.py` and `api/routes/market.py`.
- **Mutation test:** `test_coverage_requires_auth` — removing the dependency causes 200 instead of 401.
- **Demo isolation test:** `test_coverage_demo_mode_no_live_warehouse` — asserts `_read_coverage_rows` is never called in demo mode.

### 2. Frontend: secTool error without rows shows empty results instead of error
- **File:** `frontend/src/screens/SecFilingExplorer.tsx:143-163`
- **Defect:** When `secTool.result` had `{error: "execution_failed"}` without `rows`, `rawRows` was `[]`, error classification skipped, and "No SEC filing sections found" displayed.
- **Fix:** Added `secToolError` extraction from `secTool.result.error` when present. `effectiveError` merges `firstRowError` and `secToolError` so error classification runs even without rows.
- **Test:** `shows error state when secTool result has error without rows` — asserts `ErrorState` with error message, not empty state.

### 3. Frontend: Input change doesn't invalidate in-flight request
- **File:** `frontend/src/screens/SecFilingExplorer.tsx:220-228`
- **Defect:** Editing the ticker input cleared `selected` but left `requestIdRef`, `result`, `error`, and `loading` unchanged. Stale responses could render for a deselected ticker.
- **Fix:** When input changes and clears `selected`, calls `resetRequest()` which increments `requestIdRef`, clears `result`/`error`/`loading`, then restores the typed query value.
- **Test:** `editing ticker input invalidates in-flight request` — old request result does not appear after edit.

### 4. Frontend: Clear button doesn't invalidate in-flight request
- **File:** `frontend/src/screens/SecFilingExplorer.tsx:236-241`
- **Defect:** Clear handler reset `selected`/`query`/`result` but didn't increment `requestIdRef` or reset `loading`/`error`. Old response could restore results for a cleared selection; spinner stayed visible.
- **Fix:** Clear button now calls `resetRequest()` which increments `requestIdRef` and resets all request state.
- **Test:** `clear button invalidates in-flight request` — stale result does not appear after clear.

### 5. Test nitpick: Assert exact n_chunks > 0 predicate
- **File:** `tests/api/test_sec_coverage.py:180-183`
- **Defect:** Assertion checked for `n_chunks` in SQL and `>` or `WHERE` separately, which also passed for incorrect predicates like `WHERE n_chunks < 0`.
- **Fix:** Replaced with `assert "WHERE n_chunks > 0" in sql`.

## Non-blocking notes
- Shared `resetRequest` callback used by both clear button and input change handler ensures consistent state invalidation.
- Frontend `secToolError` extraction handles error-only responses (no `rows` array) without changing the existing row-level error flow.

## Checks run
- `python3 -m pytest tests/api/test_sec_coverage.py -q` → 10 passed
- `python3 -m pytest tests/api -q` → 327 passed
- `npx vitest --run` → 24 passed
- `npx tsc --noEmit` → pass
- `npm run build` → built in 1.53s

## Commits
- `6ab07f9` fix(sec): add identity dependency and demo gate to /api/sec/coverage
- `3a77095` fix(frontend): handle secTool errors and invalidate stale requests