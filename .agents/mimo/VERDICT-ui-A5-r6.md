# VERDICT: ui-A5-r6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
- None

## Non-blocking notes
- Added `Number.isFinite()` check alongside `!= null` to catch NaN close values
- Changed `recent` from `useMemo(() => getRecentSymbols(), [])` to `useState(() => getRecentSymbols())` with `setRecent(getRecentSymbols())` after `pushRecentSymbol` in `handleSelect`
- Added 2 mutation-proof tests: all-null close → EmptyState, select → recent button appears

## Checks run
- `npx vitest --run` → 175/175 passed
- `npx tsc --noEmit` → pass
- `npm run build` → pass (dist/index-EV3pOjqi.js 222.92 kB)
- Mutation 1 (drop close guard) → FAILED (test: "renders EmptyState when all close values are null")
- Mutation 2 (recent at mount only) → FAILED (test: "updates recent list after selection without remount")

## Files modified
- `frontend/src/screens/MarketDashboard.tsx:62-72` — guard for no finite close values
- `frontend/src/components/SymbolPicker.tsx:52,87` — reactive recent state
- `frontend/src/screens/MarketDashboard.test.tsx` — all-null close test
- `frontend/src/components/SymbolPicker.test.tsx` — recent-update-after-select test

## Commit
`e2a7f07` on `feat/ui-enhancement`