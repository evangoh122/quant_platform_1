# Build: Decision Dashboard Phase 0a round 4 (coordinator finding on aa31ab5)

Builder: MiMo. Base: HEAD aa31ab5 on `feat/decision-dashboard-p0`. Frontend only; commit on this branch only; no backend/dependency change; no deploy.

## Finding (coordinator review of r3, before DeepSeek)
`frontend/src/screens/PaperPortfolio.tsx` (Total P&L StatTile) computes `unpricedUnrealized` and `unpricedRealized` but the `hint` ONLY considers `unpricedUnrealized` for text. Consequences:
1. positions with a null `realized_pnl` but all `unrealized_pnl` present → hint is `undefined`, so a partial total is shown as a bare number with no unpriced note and no "partial" label. This violates r3 requirements 2 and 3 (note when EITHER count > 0; label a partial total clearly).
2. Even when the hint appears, it says `realized X (N unpriced)` without saying the TOTAL is partial and without distinguishing which component is missing.

## Required behaviour
- If `unpricedRealized > 0 || unpricedUnrealized > 0`, the tile must show a hint that (a) says the total is partial and (b) names each missing component with its count, e.g. `partial · realized 350.00 · 2 unrealized unpriced · 1 realized unpriced` (omit a clause whose count is 0). Exact wording is yours but it must contain the word "partial" and both counts when both are non-zero.
- Fully priced → no hint (unchanged). Nothing known → value "—" and no number-like hint (unchanged).
- Keep the independent summation logic as is.

## Required tests (render real PaperPortfolio; hand-computed literals in comments)
- All unrealized present, one realized null → total is shown AND hint contains "partial" and "1 realized unpriced".
- All realized present, two unrealized null → hint contains "partial" and "2 unrealized unpriced".
- Both kinds of null present → hint contains both counts.
- Existing r3 tests still pass.

## Mutations that MUST fail a test (isolated `git archive` copies; code edits not comments)
M1 drop the `unpricedRealized` clause from the hint. M2 drop the word "partial". M3 only show hint when `unpricedUnrealized > 0` (the current defect). Re-run r3 mutations M1-M4 and the Phase 0a harness (`.agents/run-mutations.py`) and show they still fail tests.

## Acceptance
`cd frontend && npx tsc --noEmit && npx vitest run && npm run build` pass (`export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"`); `python3 -m pytest tests/api tests/gold tests/agent -q` still passes.
Evidence `.agents/mimo/VERDICT-decision-p0a-r4.md`. Descriptive commit message. End with exactly:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/decision-dashboard-p0 | evidence: .agents/mimo/VERDICT-decision-p0a-r4.md`
