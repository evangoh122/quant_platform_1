# VERDICT: viz-V1 — MiMo
**Status:** APPROVED
**Round:** 1

## Summary
Built shared chart primitives and three data-driven charts (Options put/call timeline, Signal conviction ranking, SEC coverage) on existing APIs. All charts render honest empty/error states, use native SVG with no chart library dependencies, and include accessible `<details>` data-table fallbacks.

## Files created/modified
- `frontend/src/components/charts/scales.ts` — linearScale, bandScale, niceExtent, tickValues
- `frontend/src/components/charts/Axis.tsx` — XAxis, YAxis components
- `frontend/src/components/charts/LineSeries.tsx` — breaks at null (gap, not zero)
- `frontend/src/components/charts/BarSeries.tsx` — rect-based bars with title tooltips
- `frontend/src/components/charts/Tooltip.tsx` — hover + keyboard focus
- `frontend/src/components/charts/ChartFrame.tsx` — title, caption, legend, `<details>` data-table fallback
- `frontend/src/components/charts/index.ts` — barrel export
- `frontend/src/screens/OptionsAnalytics.tsx` — put/call stacked bars + ratio line + anomaly z-score line + IV stat (not charted)
- `frontend/src/screens/SignalExplorer.tsx` — horizontal bars sorted by probability desc, colored by direction, "Baseline model probability" label
- `frontend/src/screens/SecFilingExplorer.tsx` — top-N (default 25) bars of n_chunks per ticker with toggle, headline counts
- `frontend/src/components/charts/LineSeries.test.tsx` — 5 tests for null-gap behavior
- `frontend/src/screens/OptionsAnalytics.test.tsx` — 5 tests for IV stat, ratio line, table fallback, empty/error
- `frontend/src/screens/SignalExplorer.chart.test.tsx` — 5 tests for sorted bars, label text, empty/error
- `frontend/src/screens/SecFilingExplorer.chart.test.tsx` — 7 tests for default 25, toggle, ordering, empty/error

## Non-blocking notes
- ChartFrame `<details>` data-table uses `overflow-x-auto` for wide tables; no horizontal scroll on the SVG itself (controlled by parent Card)
- Tooltip auto-positions to avoid clipping but doesn't handle all edge cases for very small chart areas

## Checks run
- `npx vitest --run` → 188 passed (17 test files), 0 failed
- `npx tsc --noEmit` → pass (exit 0)
- `npm run build` → pass (235.36 kB JS, 28.04 kB CSS)

## Mutation tests
All 4 mutations detected and FAILED as required:

1. **LineSeries null→0 coalesce** → 4 tests failed (renders 1 path instead of 2 for [1, null, 3])
   ```
   ❌ renders 2 path segments for [1, null, 3] → expected 1 to be 2
   ❌ renders 0 paths when all null → expected 1 to be +0
   ❌ creates a gap at null → Cannot read properties of undefined
   ❌ renders 3 segments for [1, null, 2, null, 3] → expected 1 to be 3
   ```

2. **Options chart iv_atm series** → 1 test failed (IV ATM legend entry found when it shouldn't exist)
   ```
   ❌ shows IV stat with date, no IV line charted → expect(IV ATM).not.toBeInTheDocument()
   ```

3. **Signals unsorted** → 1 test failed (bars not in descending probability order)
   ```
   ❌ renders bars sorted by probability descending → expected 307 to be greater than 380
   ```

4. **Coverage slice before sort** → 1 test failed (T26 with 4740 chunks excluded from top 25)
   ```
   ❌ orders bars by n_chunks descending → expected [...T01-T25] to include 'T26'
   ```