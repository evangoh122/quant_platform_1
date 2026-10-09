# Build: Decision Dashboard Phase 0a round 3 (Codex CHANGES_REQUESTED on eb1c931)

Builder: MiMo. Base: HEAD eb1c931 on `feat/decision-dashboard-p0`. Commit on this branch only; frontend-only change; no backend/dependency change; no deploy.
(Codex final validation found the bug; DeepSeek approved eb1c931 before it. Note Codex's restricted runner stalled on FastAPI TestClient tests; the full Python suite passes 485/485 under the sanctioned bridge — do not touch Python.)

## Blocking finding
`frontend/src/screens/PaperPortfolio.tsx:34-37` computes `pricedPositions = positions.filter(p => realized_pnl != null && unrealized_pnl != null)` and sums BOTH fields only over those. A position with
`realized_pnl = 50` and `unrealized_pnl = null` drops its known realized $50 from the realized total. Codex's isolated test expected 350.00 and production rendered 300.00.

## Required behaviour
1. Sum `realized_pnl` over every position whose `realized_pnl` is non-null, and `unrealized_pnl` over every position whose `unrealized_pnl` is non-null — independently. Never coerce null to 0 for a position's own cell.
2. Track two counts: positions with null unrealized (unpriced for unrealized) and positions with null realized. Show an "unpriced" note when either count > 0 (e.g. `realized 350.00 · 2 unrealized unpriced`); wording must not claim the total is complete.
3. "Total P&L" tile: it equals realized_known + unrealized_known only when at least one component is known. If NO realized and NO unrealized values are known (all null / no positions with data), render an em dash "—" (never "0.00"). When the total is partial (some nulls), label it clearly as partial (e.g. hint `partial: N unpriced`). Do not show a bare number that looks complete.
4. Table cells for null P&L keep rendering "—" (already done; keep).

## Required tests (render the real PaperPortfolio; stub the API via the existing test pattern in `frontend/src/screens/PaperPortfolio.test.tsx`)
- positions [{realized 50, unrealized null}, {realized 100, unrealized 200}, {realized 150, unrealized 0}] → realized total 300... compute by hand and assert exact strings in the test comments; include Codex's case (realized 50 + unrealized null must count toward realized) and assert the unpriced note.
- all positions have both null → Total P&L shows "—", not "0.00"; no NaN anywhere.
- all fully priced → totals exact, no unpriced note.
- empty positions → unchanged existing behaviour.
Expected values must be hand-computed literals, not recomputed with the production reduce logic.

## Mutations that MUST fail a test (isolated `git archive` copies; code edits not comments)
M1 restore the combined-filter `pricedPositions` logic. M2 coerce null to 0 in the total when nothing is known (render "0.00"). M3 drop the unpriced note. M4 sum realized only over positions with non-null unrealized.
Re-run the Phase 0a mutations from `.agents/requests/BUILD-decision-p0a-data-correctness.md` (M1-M5) and `BUILD-decision-p0a-r2.md` (M6-M7) via `.agents/run-mutations.py` and show they still fail tests.

## Acceptance
`cd frontend && npx tsc --noEmit && npx vitest run && npm run build` pass (`export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"`). Python tests unchanged and still pass: `python3 -m pytest tests/api tests/gold tests/agent -q`.
Evidence `.agents/mimo/VERDICT-decision-p0a-r3.md`. Descriptive commit message (e.g. `fix(ui): sum portfolio P&L components independently; show em dash when unpriced`). End with exactly:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/decision-dashboard-p0 | evidence: .agents/mimo/VERDICT-decision-p0a-r3.md`
