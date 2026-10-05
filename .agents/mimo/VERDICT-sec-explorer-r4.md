# VERDICT: sec-explorer-r4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
- None.

## Non-blocking notes
- Mutation 1 (drop `retrieval_unavailable` branch) → parse error (JSX syntax break), confirming the branch is structurally necessary for the component to compile.
- Mutation 2 (remove stale response guard) → 1 fail (`stale response from A is discarded when B is selected after A`): "iPhone revenue" from stale A overwrites B's "GPU revenue" — CAUGHT.
- The `hasUnknownError` catch-all uses `rawRows[0].message ?? rawRows[0].error` as fallback, so any future `{error: "foo"}` without a message field will still display the error code to the user.

## Changes made
- `frontend/src/screens/SecFilingExplorer.tsx`:
  - Added `requestIdRef` counter incremented on each `handleSelect`; all `.then`/`.catch`/`.finally` callbacks guard on `reqId === requestIdRef.current`.
  - Added `isRetrievalUnavailable` detection for `{error: "retrieval_unavailable", message, ticker}` → renders `<ErrorState>` with retry button.
  - Added `hasUnknownError` catch-all for any other `{error: "..."}` shape → renders `<ErrorState>` with the error message/code.
  - Error rows (`no_coverage`, `retrieval_unavailable`, unknown) are excluded from result rendering via `isError` flag.
- `frontend/src/screens/SecFilingExplorer.test.tsx`:
  - `shows retrieval_unavailable error state with retry button` — real shape from `tools_retrieval.py:199-206`.
  - `retrieval_unavailable retry triggers re-fetch` — verifies retry button re-invokes `api.chat`.
  - `shows generic error state for unknown error shapes` — e.g. `{error: "rate_limited"}`.
  - `unknown error without message falls back to error code` — `{error: "something_broken"}` displays the code.
  - `stale response from A is discarded when B is selected after A` — selects AAPL then NVDA, resolves NVDA first, then AAPL; asserts AAPL's data never appears.

## Checks run
- `npx vitest --run` → pass (21 tests, 3 files)
- `npx tsc --noEmit` → pass (exit 0)
- `npm run build` → pass (vite v5.4.21, built in 2.20s)
- Mutation "drop retrieval_unavailable branch" → parse error (JSX break) — CAUGHT
- Mutation "remove stale response guard" → 1 fail (`stale response from A is discarded`) — CAUGHT