# VERDICT: ui-A5-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none)

## Non-blocking notes
- SymbolPicker URL init now calls `onChange` to lift the URL symbol to the parent, so the screen/API uses it on mount.
- Null close/volume points are filtered out before chart rendering; "n missing points" label shown when any are dropped.
- Typed tickers matching `^[A-Z]{1,5}$` that are not in the options list show a "Submit X — server will check coverage" button.
- `committedValue` tracks the last confirmed selection so `showNoCoverage` only fires after a selection, not during typing.
- SecFilingExplorer tests now clean up `?symbol=` URL state in `beforeEach` to prevent cross-test leakage.

## Mutation kill evidence
1. **Unsorted chart rows** — `sorts chart rows by event_date ascending` test (MarketDashboard.test.tsx) asserts sr-only table rows are in sorted order: 2025-01-10, 2025-01-12, 2025-01-15. Mutation: removing the `.sort()` in `sortedOhlcv` → fails.
2. **Coverage shown for empty envelope** — `shows no coverage indicator for empty envelope` test asserts `queryByText('Has data')` is null when `ohlcv.empty` is true. Mutation: `hasCoverage = true` for empty → fails.
3. **Table data removed while table renders** — `renders an adjusted-close/volume chart` test asserts `dataRows.length === 3` and checks each row's `textContent` contains the expected date and close value. Mutation: clearing tbody → fails.

## Checks run
- `npx vitest --run` → 162 passed (0 failed)
- `npx tsc --noEmit` → pass
- `npm run build` → pass (68 modules, 222 kB JS)

## Commits
- `eb69f8e` fix(ui-A5): lift URL symbol param to parent state on mount
- `2ae8ec9` fix(ui-A5): drop null close/volume points instead of rendering zero
- `1b3dc77` fix(ui-A5): allow typed ticker submission and clean URL state in tests