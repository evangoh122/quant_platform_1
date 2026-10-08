# Codex gpt-5.6-sol review — UI A5 r3 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

1. `frontend/src/components/SymbolPicker.tsx:168-170` — Clearing the picker calls `onChange('')`. In Market and Options, this updates the dependency used by `useApi` (`MarketDashboard.tsx:208-210`, `OptionsAnalytics.tsx:40-42`), immediately requesting the market endpoint with an empty symbol. This violates the requirement to avoid sending invalid values to endpoints. Add a test asserting that clearing the picker does not request an empty symbol.

Validation:
- 166 tests passed.
- `npx tsc --noEmit` passed.
- Production build passed.
- `/tmp` mutation proofs killed all eight named regression classes.
- No tracked files were edited; no package installation was run.

===VERDICT END===
