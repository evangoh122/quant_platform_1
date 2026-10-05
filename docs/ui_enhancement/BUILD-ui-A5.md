# BUILD-ui-A5: SymbolPicker and modest market chart

Implement only A5 from `docs/ui_enhancement/PLAN.md`, after A4 has been
committed and checked.

## Numbered changes

1. Add `frontend/src/components/SymbolPicker.tsx` and replace the existing
   `SymbolSelect` usage in Market, Options, SEC Research, and the agent scope
   handoff. Reuse `frontend/src/data/symbols.json` and its market/options/sec
   lists; do not duplicate the universe in a component.
2. `SymbolPicker` must provide a validated text input, recent symbols in
   localStorage, quick choices `NVDA`, `AAPL`, `MSFT`, `AMD`, `SPY`, the
   existing data-backed lists, a `?symbol=` URL parameter, a coverage
   indicator, and a no-coverage message. Normalize valid symbols consistently
   with the existing uppercase UI behavior and avoid sending invalid values to
   the endpoint. Preserve a caller's current symbol if it is not in a list so
   the UI can display no coverage rather than silently changing it.
3. Update `frontend/src/screens/MarketDashboard.tsx` to retain the existing
   table and add one modest adjusted-close-plus-volume chart with a range
   selector, empty state, source/freshness label, and accessible fallback
   table. Use only `MarketSnapshot.ohlcv.data`, sort by `event_date`, and do
   not add a chart dependency. A CSS/SVG chart is acceptable if it remains
   responsive and readable.
4. Update Options, SEC Research, and agent symbol scope to consume the shared
   picker without changing their API endpoint contracts. Keep the existing
   options envelope and SEC chat behavior. Add no-coverage handling for empty
   `ohlcv`/`options` envelopes and do not render empty data as zero.
5. Add picker, URL/local-storage, chart sorting/range, coverage, and empty
   state tests. Keep current `MarketDashboard.test.tsx` latest-date behavior.

## Tests that must fail on the current code

- `initializes from ?symbol=NVDA and persists a valid recent symbol` — current
  screens hardcode NVDA and have no URL/local-storage integration.
- `offers quick choices and the existing data-backed universe without
  duplication` — current component is a select with no quick/recent/search
  picker behavior.
- `shows no coverage for a valid-looking symbol outside the selected dataset`
  — current select silently limits choices and has no coverage message.
- `renders an adjusted-close/volume chart from rows sorted by event_date while
  retaining the table` — current MarketDashboard has no chart.
- `changes the chart range without changing the API response contract` —
  current dashboard has no range selector.
- `renders the market empty state and freshness/source instead of 0` — current
  screen has no chart empty-state contract to test.

## Named mutations for DeepSeek

Run mutations for: ignoring the URL query; not persisting recent symbols;
removing `MSFT` or `SPY` from quick choices; accepting an invalid symbol;
showing coverage for an empty envelope; plotting unsorted rows; hiding the
existing table; and rendering an empty series as numeric zero. DeepSeek must
provide file:line evidence.

## Acceptance

Run:

```sh
cd frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build
```

Use LF line endings, do not touch `.agents/dispatch.sh`, commit the A5
changes, and write a MiMo verdict naming the commit and test results.

