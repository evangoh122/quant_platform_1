# Codex gpt-5.6-sol review — UI A5 r5 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

Findings:

1. `frontend/src/screens/MarketDashboard.tsx:53-70` — OHLCV rows with all-null `close`/`volume` values still render a chart with fabricated `0.0–1.0` price-axis labels. This violates the requirement not to render empty data as zero. A `/tmp` probe expecting the chart empty state failed.

2. `frontend/src/components/SymbolPicker.tsx:52,79-87` — Recent symbols are read only once at mount. A newly selected symbol is persisted to localStorage but does not appear under “Recent” until the picker remounts. A `/tmp` probe selecting `TSLA` confirmed the missing recent button.

Validation:

- Vitest: 173/173 passed
- `npx tsc --noEmit`: passed
- `npm run build`: passed
- Mutation proof: reverting share-class ticker validation caused the `BRK.B` URL test to fail as expected
- No tracked files edited

===VERDICT END===

