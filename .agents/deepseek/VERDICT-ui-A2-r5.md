===VERDICT START===
# VERDICT: ui-A2-r5 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 5

## Summary

The round-4 blocking finding (missing once-only StrictMode test) is resolved. Commit
`c43e21c` adds `describe('StrictMode once-only guard')` (`CoachMarks.test.tsx:409-502`) with a
`StrictModeHarness` that renders `<CoachMarks>` inside `<React.StrictMode>` and a stateful parent
whose `onClose` calls `setRun(false)` + `markTourSeen`. Re-applying the round-5 mutation (move
`handleClose()` back inside the `setIndex` updater, exactly as in `BUILD-ui-A2-r5.md`) makes the Done
variant fail at `CoachMarks.test.tsx:464`. The clamp mutation and all nine earlier A2 mutations still
fail their guards; build is clean and A1 is not regressed.

## Item 1 — once-only StrictMode guard (r4 finding 1)

The new test exists and is non-vacuous:
- Renders under `<React.StrictMode>` (`CoachMarks.test.tsx:434`).
- Spies `console.error` (`:454`) and asserts zero "Cannot update a component" calls (`:468-473`).
- Asserts `onClose` exactly once (`:464`), `localStorage.setItem` exactly once with the tour key
  (`:465-466`); `markTourSeen` is invoked from `onClose` (`:442`).

Mutation (handleClose inside updater, exact code from `BUILD-ui-A2-r5.md`) → **FAILS**:
`CoachMarks.test.tsx:464` `AssertionError: expected "spy" to be called 1 times, but got 2 times`
(StrictMode double-invokes the updater, calling `handleClose()` twice). The Escape variant (`:479`)
still passes under this mutation because Escape calls `handleClose()` directly via the keydown handler
(`CoachMarks.tsx:107`), not through `next` — expected.

## Item 2 — clamp mutation + nine earlier A2 mutations

Baseline (read-only copy `git archive HEAD | tar -x -C /tmp/qp1-ui-a2-r5-pristine` + symlinked
`frontend/node_modules`, WSL node v22.23.3): **60/60 pass** (6 files), tsc clean, vite build
185.73 kB JS / 21.21 kB CSS. Worktree left clean.

Clamp mutation (clamp removed, `CoachMarks.tsx:161-166`) → **2 fail**: `clamps spotlight left to 0…`
(`expected -28 to be >= 0`, `:370`), `clamps spotlight to viewport…` (`expected -8 to be >= 0`, `:403`).

Nine earlier A2 mutations (production path) — all still fail ≥1 test, matching r3/r4:

| Mutation | Fails | Guard test |
|---|---|---|
| M1 delete focus-trap listener (`CoachMarks.tsx:115-127`) | 1 | `traps focus inside the dialog…` |
| M2 remove AppShell dispatch (`layout/AppShell.tsx:42-44`) | 2 | `opens the tour dialog when Take a tour is clicked` (+ already-seen) |
| N1 unversion keys (`tourSteps.ts:3-5`) | 4 | `writes qp_tour_*_v1 on close` ×3 + hardcoded-key check |
| N2 remove `markTourSeen` (`TourHost.tsx:35`) | 3 | `writes qp_tour_*_v1 on close` ×3 |
| N3 missing selector blocks Next (`CoachMarks.tsx:94-100`) | 1 | `continues to next step when current selector is missing` |
| N4 remove focus restore (`CoachMarks.tsx:91`) | 2 | `closes on Escape/Done and restores focus to the opener` |
| N5 ArrowLeft wraps (`CoachMarks.tsx:102`) | 1 | `ArrowLeft does not wrap to last step` |
| N6 remove reduced-motion guard (`TourHost.tsx:51-54`) | 1 | `does not auto-start under prefers-reduced-motion` |
| N7 drop resize/scroll listeners (`CoachMarks.tsx:73-82`) | 2 | `repositions the spotlight after resize/scroll` |

## A1 regression

None. Baseline 60/60 includes the A1 suites: `states.test.tsx` (5), `MarketDashboard.test.tsx` (1),
`layout.test.tsx` (5), plus `App.test.tsx` (10), `CoachMarks.test.tsx` (26), `TourHost.test.tsx` (13).

## Non-blocking notes

- r4 findings 2 and 3 (clamp tests use `innerWidth = 1024` not 360px; no test for
  tooltip-in-viewport / `scrollIntoView` reduced-motion) are still present but out of scope for this
  round per `BUILD-ui-A2-r5.md`, which mandated only the once-only test.

## Checks run

- `git log --oneline -1` → `592d924` on `feat/ui-enhancement`; `c43e21c` present; worktree clean.
- `node node_modules/.bin/vitest --run` (baseline, WSL) → **60/60 pass**.
- `node node_modules/.bin/tsc --noEmit` → **pass** (0 errors).
- `npm run build` → **pass** (185.73 kB JS, 21.21 kB CSS).
- Mutation (handleClose inside updater) → **1 fail** (`CoachMarks.test.tsx:464`).
- Clamp mutation → **2 fail** (`CoachMarks.test.tsx:370`, `:403`).
- Nine earlier A2 mutations → all fail ≥1 test (table above).
===VERDICT END===
