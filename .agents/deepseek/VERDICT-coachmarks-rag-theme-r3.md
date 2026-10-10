# VERDICT: coachmarks-rag-theme-r3 — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 3

## Scope / git audit (request item 1)

- HEAD `6a33f723a399681d5f1294044a401a7f4a53af0b` matches the required SHA. ✓
- `git merge-base --is-ancestor origin/main HEAD` → pass. ✓
- `git status --porcelain --untracked-files=no` → empty (tracked tree clean). ✓
- `git diff --check origin/main...HEAD` → clean. ✓
- r3 delta (`a3c1236…HEAD`) limited to `frontend/**` (12 files) + `.agents/**` artifacts
  (4 files). No backend/API/dependency change. ✓
- The commit message is only `fix:`. Noted (non-blocking, per request).

## Blocking findings

### B1. Cross-screen tours reset to step 1 on navigation, and "restore screen" restores the wrong screen
`frontend/src/components/tours/CoachMarks.tsx:68-75`:

```tsx
useEffect(() => {
  if (run) {
    openerRef.current = document.activeElement as HTMLElement;
    initialScreenRef.current = currentScreen;
    setIndex(0);
    setTargetTimedOut(false);
  }
}, [run, currentScreen]);
```

The dependency array was changed from `[run]` (r2) to `[run, currentScreen]` in r3. When a
step with `navigateTo` is reached, the `useLayoutEffect` at `CoachMarks.tsx:83-85` calls
`onNavigate(step.navigateTo)`; in the real `App` (`App.tsx:139` passes `currentScreen={screen}`
and `onNavigate={handleTourNavigate}` → `setScreen`) this changes `screen`, which changes the
`currentScreen` prop, which re-runs the effect above. Two consequences:

1. `setIndex(0)` resets the tour to the first step every time the tour navigates. The
   `APPLICATION_TOUR` steps 2-4 (`market-research`→market, `agent`→agent,
   `analytics-evidence`→health) and the `AGENT_TOUR`/`ARCHITECTURE_TOUR` navigation steps are
   therefore unreachable — the tour loops back to the intro step forever.
2. `initialScreenRef.current = currentScreen` is overwritten with the *destination* screen, so
   `handleClose` (`CoachMarks.tsx:207-213`) restores to the screen the user is already on
   (a no-op), never the screen they started from. Part B item 7 is not satisfied.

Reproduced independently (isolated `git archive` copy, real stateful harness that wires
`onNavigate` to a real `useState` setter, i.e. what `App` does):

- After clicking "Next" on step 1 (which has `navigateTo: 'agent'`), the rendered dialog shows
  `Step 1 of 2` / "Intro" while the screen already reads "agent" — the index reset. The
  assertion `getByText('GoToAgent')` fails. (See `repro-crossscreen.test.tsx`, run in
  `/tmp/r3check`; 1 failed / 1 passed.)

The shipped `Test 16` (`coachmarks-r2.test.tsx:792-825`) is vacuous against this defect: it
renders `CoachMarks` with a *static* `currentScreen="platform-overview"` and a mock
`onNavigate` that never mutates the prop, so `currentScreen` never changes, the effect never
re-runs, and `initialScreenRef` is never overwritten. It cannot catch either the index reset or
the wrong-screen restore.

Required fix: capture the starting screen and reset the index only on the tour's `run` transition
(false→true), e.g. key the reset effect on `[run]` and capture `initialScreenRef` in a
`run`-edge effect (or a `prevRun` ref), independent of `currentScreen`. Then add a test that
renders the real `App` (or a stateful harness that actually navigates) and asserts (a) the tour
advances past a `navigateTo` step, and (b) `onNavigate(initialScreen)` on close.

## Non-blocking notes

- F2 evidence misattributes the replay proof to `Test 8`. `coachmarks-r2.test.tsx:481-524`
  (`Test 8`) renders only `AppShell` (via `renderRealAppShell`), not the full `App`/`TourHost`,
  and `AppShell.handleTour` (`AppShell.tsx:42-45`) never reads seen keys — so the
  `markTourSeen(...)` seeding in `Test 8` still has no effect on the dispatch it asserts. The
  "manual replay ignores seen keys" regression is actually caught by
  `App.test.tsx:174-193` ("opens the tour dialog … even if already seen"), which renders the
  real `App`. Verified: making `TourHost`'s `qp-tour-request` handler respect seen keys fails
  that App test (dialog never opens). Net effect is acceptable, but the evidence/`Test 8`
  attribution is inaccurate.
- Part B tests `Test 11`, `Test 13`, `Test 14`, and the first `Test 12` case are *source-scan*
  tests (`readFileSync` + string match), not "render real components, assert DOM/ARIA and focus"
  as the BUILD request's test section specifies. They are not vacuous (the mutations fail them),
  but they are weaker than rendered-component assertions and do not prove the ARIA attributes
  are actually emitted to the DOM.
- No test asserts the mobile drawer's background `inert`. I verified independently that
  `inert=""` IS emitted (`MobileNavigation.tsx:81` `{...{ inert: '' }}`; rendered DOM shows
  `inert=""` on the overlay). The evidence's claim that this is "verified via existing
  layout.test.tsx escape/focus tests" is incorrect — those tests never touch `inert`.
- The r3 check script still prints the sentinel `r2 check script finished`
  (`run-coachmarks-rag-theme-r3-check.sh:17`) — cosmetic copy-paste, non-blocking.
- `App.test.tsx` uses current versioned keys (F4 satisfied) but does not itself assert the
  dispatched `tour` value; that assertion lives in `Test 1` (`coachmarks-r2.test.tsx:158-205`),
  which is appropriate.

## Checks run

- `git rev-parse HEAD` → `6a33f723a399681d5f1294044a401a7f4a53af0b` (pass)
- `git merge-base --is-ancestor origin/main HEAD` → pass
- `git status --porcelain --untracked-files=no` → clean
- `git diff --check origin/main...HEAD` → clean
- Sanctioned bridge
  `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r3-check.sh`
  → pass (Linux node v26.5.0; `tsc --noEmit` 0 errors; `vitest run` 315/315; `npm run build`
  ok; legacy light-style residual grep → `none`; sentinel printed). Boundary: node/npm/npx all
  resolve under nvm, not `/mnt/`.
- Mutation testing (isolated `git archive` copies under `/tmp/r3mut`, each re-extracted from
  HEAD, node_modules symlinked; target test re-run):
  - M1 hardcode `tour:'application'` in `AppShell.tsx` → `Test 1` agent/architecture fail. ✓
  - M2 `TourHost` handler respects seen keys → `App.test.tsx` "even if already seen" fails. ✓
  - M3 remove 44px `@media` rule → `Test 5` fails. ✓
  - M4 stale `_v1` keys in `App.test.tsx` → auto-start guard fails. ✓
  - M5 restore `bg-blue-*` badge → `Test 10` fails. ✓
  - M6 remove `aria-expanded` → `Test 14` fails. ✓
  - M7 remove skip link → `Test 12` fails (both cases). ✓
  - M8 drop Escape in `MobileNavigation` → `layout.test.tsx` "restores focus after closing" fails. ✓
  - M9 remove `onNavigate(initialScreenRef)` in `handleClose` → `Test 16` fails. ✓
- "New tests fail on r2" (`a3c1236` archive + r3 test files overlaid): `Test 7`(3rd case),
  `Test 11`, `Test 12`(×2), `Test 13`, `Test 14`, `Test 15`, `Test 16` → 8 failed. ✓
- Reproduction of B1 (real stateful `onNavigate`): cross-screen "Next" resets to `Step 1 of 2`
  while screen already shows destination → confirmed. ✗ (blocking)

VALIDATION DONE | verdict: CHANGES_REQUESTED | sha: 6a33f723a399681d5f1294044a401a7f4a53af0b | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r3.md
