# VERDICT: ui-A5 — MiMo
**Status:** APPROVED
**Round:** 1

## Summary
Implemented SymbolPicker component, modest market chart, and fixed post-merge regression per BUILD-ui-A5 spec.

## Changes committed
- **Commit:** `6b30a27` on branch `feat/ui-enhancement`
- **10 files changed**, 895 insertions, 334 deletions

## Item 0 — Regression fix
- `frontend/src/layout/layout.test.tsx`: Added `/api/sec/coverage` mock to `mockFetch` with real `SecCoverageResponse` shape `{data, count, status}`. The SEC screen (PR #41) was crashing on `coverage.length` because the mock returned `{}` for unmocked URLs.

## Item 1 — SymbolPicker
- `frontend/src/components/SymbolPicker.tsx`: New component with combobox input, quick choices (NVDA/AAPL/MSFT/AMD/SPY), recent symbols from localStorage, data-backed lists from `symbols.json`, `?symbol=` URL param reading, coverage indicator (Has data/No coverage), no-coverage warning message, uppercase normalization.
- `frontend/src/utils/symbolStorage.ts`: URL param helpers and localStorage recent-symbol management with try/catch for jsdom safety.

## Item 2 — Screen integration
- `frontend/src/screens/MarketDashboard.tsx`: Replaced `SymbolSelect` with `SymbolPicker`, added `hasCoverage` prop.
- `frontend/src/screens/OptionsAnalytics.tsx`: Replaced `SymbolSelect` with `SymbolPicker`, added `hasCoverage` prop.
- `frontend/src/screens/SecFilingExplorer.tsx`: Replaced custom combobox with `SymbolPicker` in `secMode` (coverage-backed) and fallback (`list="sec"`). Added empty-ticker guard in `handleSelect`.

## Item 3 — Market chart
- `frontend/src/screens/MarketDashboard.tsx`: Added `AdjCloseChart` SVG component with adjusted-close line, volume bars, area fill, range selector (1M/3M/6M/All), accessible fallback `<table>`, source/freshness label, row count. No chart library dependency. Data sorted by `event_date`.

## Item 4 — Empty/coverage states
- MarketDashboard and OptionsScreens show `hasCoverage` indicator via SymbolPicker.
- Empty ohlcv/options envelopes show honest empty states (not numeric zero).

## Item 5 — Tests
- `frontend/src/components/SymbolPicker.test.tsx`: 11 tests covering quick choices, data-backed universe, no-coverage message, coverage indicator, recent symbols persistence, uppercase normalization, URL updates, filtering, secMode.
- `frontend/src/screens/MarketDashboard.test.tsx`: 5 tests covering latest-date pick, chart rendering, range selector (no API change), empty state with freshness, SymbolPicker usage.
- `frontend/src/screens/SecFilingExplorer.test.tsx`: 18 tests updated for SymbolPicker integration.
- `frontend/src/test/setup.ts`: Added localStorage polyfill for jsdom.

## Checks run
- `npx vitest --run` → **156 passed (13 files)**
- `npx tsc --noEmit` → **pass**
- `npm run build` → **pass** (221 KB gzip 67 KB)

## Non-blocking notes
- The SymbolPicker is controlled (parent owns value); URL param reading is display-only on mount. The parent screen should read `?symbol=` and pass it as `value` for full URL→API integration.
- The SVG chart uses inline `<text>` elements for axis labels; a future round could add ARIA descriptions for individual data points.

## Blocking findings
- None.