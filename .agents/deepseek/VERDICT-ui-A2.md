===VERDICT START===
# VERDICT: ui-A2 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 1

## Summary

The three tours, CoachMarks component, and TourHost wiring are implemented and the suite is green
(41/41, tsc clean, build OK). However, **three of the seven named mutations survive the test suite**
(they are uncaught), and the hook that is actually wired into the app (`useTourHost`) is entirely
untested while the hook that *is* tested (`useTour`) is dead code. Several of the "tests that must
fail on the current code" from `BUILD-ui-A2.md` are missing or vacuous. Details below with file:line.

## Blocking findings

1. **Versioned-key contract is untested.** The exact keys `qp_tour_application_v1` /
   `qp_tour_agent_v1` / `qp_tour_architecture_v1` are declared only in
   `frontend/src/components/tours/tourSteps.ts:3-5` and referenced nowhere in any test
   (`grep -rn qp_tour frontend/src/` returns only those three lines). Mutation — changing
   `qp_tour_application_v1` → `qp_tour_application` — **survives**: all 41 tests still pass.
   A returning user whose key loses its `_v1` suffix would be re-shown the tour and nothing
   would catch it.

2. **Focus restore to the opener is untested.** `frontend/src/components/tours/CoachMarks.tsx:82`
   (`openerRef.current?.focus()`) is the only place focus is restored. The required test
   "closes on Escape and restores focus to the opener" exists only in its Escape half —
   `CoachMarks.test.tsx:101-113` asserts `onClose` was called and never inspects
   `document.activeElement`. Mutation — deleting line 82 — **survives**: 41/41 pass.

3. **Spotlight reposition after scroll/resize is untested.** The resize/scroll re-measure lives in
   `frontend/src/components/tours/CoachMarks.tsx:64-73`. The required test "repositions the spotlight
   after scroll and resize" does not exist anywhere. Mutation — replacing that effect with a one-shot
   `measure()` (stale spotlight) — **survives**: 41/41 pass.

4. **The wired auto-start path (`useTourHost`) has zero tests; the tested `useTour` hook is dead
   code.** `App.tsx:75` calls `useTourHost()` from `TourHost.tsx:21`, but every auto-start /
   reduced-motion / mark-seen test (`CoachMarks.test.tsx:213-357`) exercises the `useTour` hook at
   `CoachMarks.tsx:247`, which nothing in the app imports (`grep -rn useTour frontend/src/` → only
   its own test file). Concretely, mutating the *production* path is uncaught:
   - Removing the completion write `markTourSeen(tour.key)` in `TourHost.tsx:35` **survives** (41/41
     pass) — the "marks tour seen on close" test only covers the dead `useTour.close()`.
   - Removing the reduced-motion guard in `TourHost.tsx:51-54` **survives** (41/41 pass) — the
     "does not auto-start under prefers-reduced-motion" test only covers the dead `useTour`.

5. **"traps Tab focus inside the dialog" test is missing.** The focus trap is implemented at
   `CoachMarks.tsx:108-120` (a `focusin` listener that refocuses the card) but has no test. The
   `render`-only tests in `CoachMarks.test.tsx` never send Tab through the dialog.

6. **"replays from the header" is asserted as button presence, not behaviour.** The only coverage is
   `App.test.tsx:132` (`getByRole('button', { name: 'Take a tour' })` exists). No test clicks it and
   asserts the tour opens via the `qp-tour-request` event dispatched in `AppShell.tsx:42-44`.

7. **The "continues to next step when current selector is missing" test is vacuous.**
   `CoachMarks.test.tsx:154-168` asserts `screen.getByText('Next')`, which matches both the Next
   *button* (shown when the missing-selector step is stuck) and the second step's *title* `'Next'`
   (shown after a successful advance). Under mutation 3 (a `next()` guard that blocks when the
   current step has a selector with no target) this test **still passes**, proving it cannot
   distinguish blocked from unblocked navigation.

## Named mutations — run and results

Copy built read-only via `git archive HEAD | tar -x -C /tmp/qp1-a2-check` + symlinked
`frontend/node_modules`; run from WSL with
`PATH=/home/jianj/.nvm/versions/node/v22.23.3/bin npx vitest --run`.

| # | Mutation (location) | Result |
|---|---|---|
| 1 | versioned key → unversioned (`tourSteps.ts:3`) | **SURVIVES** — 41/41 pass (blocking, §1) |
| 2 | remove completion write in `useTour.close()` (`CoachMarks.tsx:266`) | fails 1: `useTour > marks tour seen on close` (`CoachMarks.test.tsx:356`) |
| 3 | missing selector blocks Next (`CoachMarks.tsx:85`) | fails 2: `shows Done on the last step`, `calls onClose when Done is clicked` |
| 4 | remove focus restore (`CoachMarks.tsx:82`) | **SURVIVES** — 41/41 pass (blocking, §2) |
| 5 | ArrowLeft wraps to last step (`CoachMarks.tsx:95`) | fails 1: `ArrowLeft does not wrap to last step` |
| 6 | remove reduced-motion guard in `useTour` (`CoachMarks.tsx:258`) | fails 1: `useTour > does not auto-start under prefers-reduced-motion` |
| 7 | measure once, drop resize/scroll listeners (`CoachMarks.tsx:64-73`) | **SURVIVES** — 41/41 pass (blocking, §3) |

Additional uncaught mutations on the production path (blocking, §4): removing
`markTourSeen(tour.key)` at `TourHost.tsx:35` → 41/41 pass; removing the reduced-motion guard at
`TourHost.tsx:51-54` → 41/41 pass.

Representative FAILED output (mutation 2):

```
 FAIL  src/components/tours/CoachMarks.test.tsx > useTour > marks tour seen on close
AssertionError: expected false to be true // Object.is equality
 ❯ src/components/tours/CoachMarks.test.tsx:356:39
```

## Constraint checks (BUILD-ui-A2 item 3)

- No disclaimer dependency: `grep -rn 'disclaimer\|Disclaimer' frontend/src/` → none. PASS.
- No RAG copy: `tourSteps.ts` text is rewritten for QP1 (quant platform); compared against
  `/home/jianj/code/Rag_workbench/frontend/src/components/tourSteps.ts` (which uses `rw_tour_*_v1`
  keys and SEC/XBRL/hallucination copy) — no verbatim overlap. PASS.
- No `glass-*` classes: `grep -rn 'glass-' frontend/src/` → none. PASS.
- No old workbench service imports: `grep -rn 'Rag_workbench\|workbench' frontend/src/` → none. PASS.
- `data-tour` attributes, not classes: confirmed on `MarketDashboard.tsx:38`, `ResearchAgent.tsx:37`,
  `PaperPortfolio.tsx:37`, `SystemHealth.tsx:75,83,97`, `Sidebar.tsx:14`, `StatusBanner.tsx:10`,
  `PageHeader.tsx:30`, `App.tsx:65`. PASS.
- Exact keys `qp_tour_application_v1` / `qp_tour_agent_v1` / `qp_tour_architecture_v1`:
  `tourSteps.ts:3-5`. PASS (but untested — see §1).
- Dialog semantics: `CoachMarks.tsx:146` has `role="dialog"`, `aria-modal="true"`,
  `aria-label="Guided tour"`. PASS.
- Overlay blocks page interaction: `CoachMarks.tsx:146` renders a `fixed inset-0 z-[200]` container
  with a full-viewport transparent catch layer at line 163 (`onClick={stopPropagation}`); the
  spotlight uses `pointer-events-none` (line 149). Interaction with the page beneath is blocked.
  PASS (no test exercises this).
- Tooltip inside 360px viewport: `CoachMarks.tsx:129-143` clamps the card
  `left = max(12, …)` / `width = min(320, vw-24)`, so at 360px the card occupies x∈[20,340]. PASS
  (no dedicated test — the 360px test in `layout.test.tsx:167` covers the shell only).

## A1 regression

A1 suites remain green in the pristine copy: `states.test.tsx` (5), `MarketDashboard.test.tsx` (1),
`App.test.tsx` (8), `layout.test.tsx` (5) all pass, so A1 navigation/active-state/breaker/360px
behaviour is not regressed.

## Checks run

- `git show --stat 8dad99b` → 10 files, +830/−25.
- `git archive HEAD | tar -x -C /tmp/qp1-a2-check` + symlink node_modules → clean copy.
- `npx vitest --run` (baseline, WSL) → **41/41 pass** (5 files).
- `npx tsc --noEmit` → **pass** (0 errors).
- `npm run build` → **pass** (185.14 kB JS, 21.21 kB CSS).
- Seven named mutations applied and reverted; results in table above (3 survive).

## Commit

`8dad99b` on `feat/ui-enhancement`; worktree at HEAD `0bad226` clean.
===VERDICT END===
