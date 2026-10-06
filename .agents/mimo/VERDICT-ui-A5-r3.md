# VERDICT: ui-A5-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
(none)

## Non-blocking notes
- All three Codex CHANGES_REQUESTED findings resolved.
- SymbolPicker now accepts any valid-format ticker from `?symbol=` (not just those in lists), showing no-coverage message for unknowns.
- ResearchAgent now has a SymbolPicker scoped to the `sec` list; suggested questions dynamically include the selected symbol.
- MarketDashboard chart ranges anchor to the latest `event_date` in the data, not `Date.now()`.

## Commits
- `36aae81` — fix(ui-A5-r3): add SymbolPicker as agent symbol scope in ResearchAgent
- `763590b` — fix(ui-A5-r3): preserve valid-format ticker from URL not in options
- `24fa727` — fix(ui-A5-r3): anchor chart ranges to latest event_date not Date.now()

## Checks run
- `npx vitest --run` → 166 passed (13 test files)
- `npx tsc --noEmit` → passed (no errors)
- `npm run build` → built in 1.90s

## Mutation tests (all correctly FAIL)

### Mutation 1: ignore picked symbol → FAIL
```
× ResearchAgent > picking AMD changes the suggested questions to AMD
  → Unable to find an element with the text: /AMD.*latest reported export-control risks/
× ResearchAgent > chat request body contains only message, no symbol field
  → Unable to find an element with the text: /AMD.*latest reported export-control risks/
```
Location: `ResearchAgent.tsx:40` — forcing `makeSuggestedQuestions("NVDA")` instead of `makeSuggestedQuestions(symbol)` breaks both symbol-scope tests.

### Mutation 2: fall back to default → FAIL
```
× SymbolPicker > preserves a valid-format ticker from ?symbol= not in options and shows no-coverage
  → expected "spy" to be called with arguments: [ 'ZZZZ' ]
```
Location: `SymbolPicker.tsx:60` — reverting to `options.includes(upper) || LISTS.market.includes(upper)` rejects ZZZZ, so `onChange` is never called with the URL symbol.

### Mutation 3: use Date.now() → FAIL
```
× MarketDashboard > anchors 1M range to latest event_date, not Date.now()
  → expected null to be truthy
```
Location: `MarketDashboard.tsx:46` — using `new Date().toISOString().slice(0, 10)` instead of `sorted[sorted.length - 1].event_date` makes the 1M cutoff land in September 2026 (relative to mocked "now" 2026-10-06), filtering out all historical rows, so the fallback table is empty (null).