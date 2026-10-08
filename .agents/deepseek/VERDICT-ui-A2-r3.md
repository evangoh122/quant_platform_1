===VERDICT START===
# VERDICT: ui-A2-r3 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 3

## Summary

Round 3 resolves both round-2 blocking findings. The focus-trap test now moves **real** focus
(`outside.focus()` at `CoachMarks.test.tsx:335`, replacing the vacuous `fireEvent.focusIn`) and is
killed by deleting the trap listener; two click-through tests in `App.test.tsx` render `<App />`,
click the header "Take a tour" button, and assert `role="dialog"` / `aria-label="Guided tour"` —
and are killed by deleting the AppShell dispatch. All seven round-2 named mutations (including the
two in `TourHost.tsx`) still fail. Baseline is green (56/56, tsc clean, build 185.18 kB / 21.21 kB)
and A1 is not regressed.

Copy built read-only via `git archive HEAD | tar -x -C /tmp/qp1-ui-a2-r3-pristine` + symlinked
`frontend/node_modules`; run with the WSL node at `/home/jianj/.nvm/versions/node/v22.23.3/bin`.
Worktree left clean (only pre-existing untracked `docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md`).

## Round-2 blocking findings — resolution confirmed

1. **[`CoachMarks.test.tsx:324-340`] focus-trap test is no longer vacuous.** The test now calls
   `outside.focus()` (line 335), which moves `document.activeElement` to the outside `<button>` and
   fires a real `focusin` that the trap listener (`CoachMarks.tsx:108-120`) refocuses back onto the
   card. Deleting the trap listener makes `expect(document.activeElement).toBe(card)` (line 337) fail
   — see mutation M1 below. Round-2 §1 resolved.

2. **[`App.test.tsx:150-192`] click-through replay tests exist and exercise the rendered app.** Two
   tests render `<App />`, click `getByRole('button', { name: 'Take a tour' })`, and assert
   `getByRole('dialog', { name: 'Guided tour' })` appears. Deleting the AppShell dispatch
   (`AppShell.tsx:42-44`) fails both — see mutation M2 below. Round-2 §2 resolved.

## Mutations — run and results (production path, WSL, read-only copy)

| # | Mutation (production location) | Result |
|---|---|---|
| M1 | delete focus-trap listener (`CoachMarks.tsx:108-120`) | **FAILS 1**: `traps focus inside the dialog when focus moves outside` |
| M2 | remove AppShell tour dispatch (`AppShell.tsx:42-44`) | **FAILS 2**: `opens the tour dialog when Take a tour is clicked`, `opens the tour dialog when Take a tour is clicked even if already seen` |
| N1 | versioned key → unversioned (`tourSteps.ts:3-5`) | **FAILS 4**: `writes qp_tour_application_v1 on close`, `writes qp_tour_agent_v1 on close`, `writes qp_tour_architecture_v1 on close`, `stored _v1 key prevents auto-start (hardcoded key check)` |
| N2 | remove `markTourSeen(tour.key)` (`TourHost.tsx:35`) | **FAILS 3**: the three `writes … on close` tests |
| N3 | missing selector blocks Next (`CoachMarks.tsx:85-93`) | **FAILS 1**: `continues to next step when current selector is missing` |
| N4 | remove focus restore (`CoachMarks.tsx:82`) | **FAILS 2**: `closes on Escape and restores focus to the opener`, `closes on Done and restores focus to the opener` |
| N5 | ArrowLeft wraps to last step (`CoachMarks.tsx:95`) | **FAILS 1**: `ArrowLeft does not wrap to last step` |
| N6 | remove reduced-motion guard (`TourHost.tsx:51-54`) | **FAILS 1**: `does not auto-start under prefers-reduced-motion` |
| N7 | measure once, drop resize/scroll listeners (`CoachMarks.tsx:64-73`) | **FAILS 2**: `repositions the spotlight after resize`, `repositions the spotlight after scroll` |

Representative FAILED output (M1 — trap listener deleted):

```
 FAIL  src/components/tours/CoachMarks.test.tsx > CoachMarks > traps focus inside the dialog when focus moves outside
AssertionError: expected <button></button> to be <div tabindex="-1" …(2)>…(5)</div> // Object.is equality
 Test Files  1 failed | 5 passed (6)
      Tests  1 failed | 55 passed (56)
```

Representative FAILED output (M2 — AppShell dispatch removed):

```
 FAIL  src/App.test.tsx > App shell and navigation > opens the tour dialog when Take a tour is clicked
 FAIL  src/App.test.tsx > App shell and navigation > opens the tour dialog when Take a tour is clicked even if already seen
TestingLibraryElementError: Unable to find role="dialog" and name "Guided tour"
 Test Files  1 failed | 5 passed (6)
      Tests  2 failed | 54 passed (56)
```

Note: N1 is slightly broader than round-2's single-key version (it unversions all three keys), hence
4 failures instead of 2 — the mutation is still caught, which is the requirement.

## Non-blocking notes

- **[`App.test.tsx:173-192`] the "even if already seen" test is order-dependent.** It marks only
  `qp_tour_application_v1` seen. It passes in the suite because the preceding test (line 150) marks
  all three keys seen and jsdom `localStorage` persists across tests in the same file, so the
  auto-start effect (`TourHost.tsx:49-69`) does not fire the `agent`/`architecture` fallback timer.
  Run in isolation (or after a `localStorage.clear()`), `agent` would auto-start after the 600 ms
  timer and could satisfy the dialog assertion without the click. Recommend marking all three keys
  seen in the already-seen case (or clearing `localStorage` in `beforeEach`) so the test proves the
  click path independently of auto-start and of test ordering. Not blocking: the requirement that
  "removing the dispatch fails both tests" holds (M2 above).
- **[`CoachMarks.tsx:85-93`]** `next()` invokes `handleClose()` (which calls `onClose()` → parent
  `setState`) inside the `setIndex` updater — an impure side effect in a state updater, pre-existing
  from round 1/2, unchanged here.

## A1 regression

No regression. Baseline run of the full suite passes the A1 files: `states.test.tsx` (5),
`MarketDashboard.test.tsx` (1), `layout.test.tsx` (5), plus `App.test.tsx` (10),
`CoachMarks.test.tsx` (22), `TourHost.test.tsx` (13) = **56/56**.

## Checks run

- `git log --oneline` → `f7984bb` ("fix: round-3 focus-trap and click-through test gaps") present on
  `feat/ui-enhancement`; HEAD `2b06608`; worktree clean (tracked).
- `git archive HEAD | tar -x -C /tmp/qp1-ui-a2-r3-pristine` + symlink `node_modules` → read-only copy.
- `node node_modules/.bin/vitest --run` (baseline, WSL) → **56/56 pass** (6 files).
- `node node_modules/.bin/tsc --noEmit` → **pass** (0 errors).
- `node node_modules/.bin/vite build` → **pass** (185.18 kB JS, 21.21 kB CSS).
- 9 mutations applied in the copy; results in table above (all FAIL at least one test).
===VERDICT END===
