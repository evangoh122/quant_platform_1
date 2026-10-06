# VERDICT: ui-A5-r4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None.

## Non-blocking notes
- `ResearchAgent` does not use `api.market()` with the symbol in the URL — the symbol only affects UI text (suggested questions). No guard needed.
- `SecFilingExplorer.handleSelect` already handles empty ticker correctly (clears state, no API call). No change needed.

## Changes made
- `frontend/src/hooks/useApi.ts` — added `options?: { enabled?: boolean }` parameter. When `enabled` is false, the hook skips the fetch, sets `loading=false`, and clears error.
- `frontend/src/screens/MarketDashboard.tsx` — added `hasSymbol` guard; passes `{ enabled: hasSymbol }` to `useApi`. Shows `EmptyState("Select a symbol")` when symbol is empty.
- `frontend/src/screens/OptionsAnalytics.tsx` — same pattern as MarketDashboard.
- `frontend/src/screens/MarketDashboard.test.tsx` — added 2 tests: clear picker → no fetch + prompt shown; pick symbol after clear → fetch fires.
- `frontend/src/screens/OptionsAnalytics.test.tsx` — new file, 3 tests: renders data on load; clear picker → no fetch + prompt shown; pick symbol after clear → fetch fires.

## Checks run
- `npx vitest --run` → 171 passed (14 files)
- `npx tsc --noEmit` → pass
- `npm run build` → pass (1.76s)
- Mutation test (remove `if (!enabled)` guard in /tmp copy) → 2 tests FAIL:
  - `MarketDashboard > skips fetch and shows prompt when symbol is cleared` — `expected '/api/market/' not to match /\/api\/market\/$/`
  - `OptionsAnalytics > skips fetch and shows prompt when symbol is cleared` — same failure