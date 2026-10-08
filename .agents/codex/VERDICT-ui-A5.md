# Codex gpt-5.6-sol review — UI A5 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

1. `frontend/src/screens/ResearchAgent.tsx:24` — The required agent symbol scope was not implemented. `ResearchAgent` has no `SymbolPicker`, selected-symbol state, or symbol handoff, despite A5 explicitly requiring the shared picker in the Agent.

2. `frontend/src/components/SymbolPicker.tsx:60` — A valid ticker supplied through `?symbol=` is accepted only if it appears in the selected options or market list. For example, `?symbol=ZZZZ` is silently ignored and the screen requests the default NVDA, instead of preserving the valid-looking symbol and displaying no coverage as required.

3. `frontend/src/screens/MarketDashboard.tsx:46` — Chart ranges are calculated relative to the current wall-clock date. Valid delayed or historical API data therefore becomes “No chart data” when selecting 1M/3M/6M. Ranges should be anchored to the latest returned `event_date`.

Validation:

- `npx vitest --run`: 162 passed.
- `npx tsc --noEmit`: passed.
- `npm run build`: passed.
- `/tmp` mutations confirmed tests fail when URL initialization, null handling, sorting, empty-envelope coverage, or retained table rows are broken.
- No repository files were edited.
- Neither `npm ci` nor `npm install` was run.

===VERDICT END===
