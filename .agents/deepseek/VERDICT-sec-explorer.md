===VERDICT START===
# VERDICT: sec-explorer — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 1

## Blocking findings

- [frontend/src/screens/SecFilingExplorer.test.tsx] Named mutation "no-coverage treated as
  empty" fails no test. Commit 65d29ee removed the round-1 test
  `shows no-coverage message for ticker without processed filings`. Mutating
  `frontend/src/screens/SecFilingExplorer.tsx:134` (`const isNoCoverage = rawRows.length > 0
  && rawRows[0]?.error === 'no_coverage'` → `const isNoCoverage = false`) leaves the suite at
  11/11 passing, so a regression that shows "No SEC filing sections found for this search"
  instead of "No SEC filings have been processed for TICKER yet."
  (`SecFilingExplorer.tsx:268`) is undetectable. No test asserts the no-coverage message or
  renders a `{error: 'no_coverage'}` result.

- [frontend/src/screens/SecFilingExplorer.test.tsx] Named mutation "tool_calls[0] used when
  the first call is not search_sec_filings" fails no test. Mutating
  `frontend/src/screens/SecFilingExplorer.tsx:129`
  (`result?.tool_calls.find((tc) => tc.name === 'search_sec_filings')` → `result.tool_calls[0]`)
  leaves the suite at 11/11 passing. Every mock in the suite has `search_sec_filings` as the
  only/first tool call, so the round-1 acceptance "use the first `search_sec_filings` call" is
  not exercised.

- [tests/api/test_sec_coverage.py:55-70] Named mutation "endpoint includes n_chunks=0 tickers"
  fails no test. `test_excludes_nchunks_zero` patches
  `api.routes.sec._read_coverage_rows` with an already-filtered list (line 64), so removing the
  `WHERE n_chunks > 0` clause (`api/routes/sec.py:44`) still yields 7/7 passing backend tests
  (verified by applying the mutation). The suite never inspects the generated SQL or runs the
  real `_read_coverage_rows`; `test_sec_coverage.py:133-157` itself documents this gap.

## Non-blocking notes

- The implementation under test is otherwise correct: four honest states + error are present
  (`SecFilingExplorer.tsx:263-309`); `.find()` is used (not `tool_calls[0]`);
  no-coverage detection matches the real `search_sec_filings` result shape
  (`agent/tools_retrieval.py:177-182` returns `[{"error": "no_coverage", "ticker": symbol}]`).
- SQL safety (`api/routes/sec.py:37-47`): constant `_TABLE = "gold_sec_coverage"`, no user
  input, `_fqn`-qualified. Missing table / ImportError → 200 + `status: "unavailable"`
  (`api/routes/sec.py:50-59`), never a 500. Covered by `test_missing_table_returns_unavailable`
  and `test_import_error_returns_unavailable`.
- Selector accessibility OK: `role="combobox"`, `aria-expanded/controls/autocomplete/label`,
  ArrowUp/Down/Enter/Escape (`SecFilingExplorer.tsx:91-113`), 228+ items render and scroll
  (`max-h-60 overflow-auto`), `max-w-xs` (320px) fits 360px.
- "silver_sec_sections is empty" copy is gone from the entire frontend (grep: no matches in
  `frontend/src`).
- Named mutations 1 (initial state shows empty message), 5 (selector caps list) and 6 (fallback
  removed) ARE caught: mutating each fails 1/1/3 tests respectively.
- Cosmetic: initial-state copy reads "Select a ticker…" (`SecFilingExplorer.tsx:264`) vs the
  spec's "Search a ticker…"; wording differs but the honest-initial-state intent is met.
- Minor: "works at 360px" has no explicit test (only implied by `max-w-xs`).

## Checks run

- `wsl -d Ubuntu -- bash -lc 'cd frontend && npx vitest --run'` → pass (14 tests, 3 files)
- `wsl -d Ubuntu -- bash -lc 'cd frontend && npx tsc --noEmit'` → pass (exit 0)
- `wsl -d Ubuntu -- bash -lc 'python3 -m pytest tests/api -q'` → pass (324 tests)
- Mutation "no-coverage treated as empty" → 11/11 pass (should fail) — NOT caught
- Mutation "tool_calls[0] used" → 11/11 pass (should fail) — NOT caught
- Mutation "n_chunks=0 filter removed" → 7/7 pass (should fail) — NOT caught
- Mutation "selector caps list (slice(0,16))" → 1 fail — caught
- Mutation "fallback removed" → 3 fail — caught
- Mutation "initial state shows empty message" → 1 fail — caught
===VERDICT END===
