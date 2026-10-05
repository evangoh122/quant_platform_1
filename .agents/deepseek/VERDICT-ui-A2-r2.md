===VERDICT START===
# VERDICT: ui-A2-r2 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 2

## Summary

Round 2 fixed six of the seven round-1 blocking findings and moved the suite onto the
production path: the dead `useTour` hook is deleted, `useTourHost` (TourHost.tsx) is the single
auto-start path, and 6 of the 7 named mutations now fail on the production code. However, two of
the checker's explicit round-2 requirements are still not met: the **focus-trap test is vacuous**
(§1) and there is **no test that clicks "Take a tour" in the rendered app** (§2). Baseline is
green (54/54, tsc clean, build 185.18 kB / 21.21 kB) and A1 is not regressed.

## Blocking findings

1. **[`CoachMarks.test.tsx:324-340`] The focus-trap test is vacuous — it does not exercise focus
   leaving the card.** The test fires `fireEvent.focusIn(outside)` on a detached `<button>`. Per
   `@testing-library/dom/dist/events.js:110-111`, `fireEvent.focusIn` only `dispatchEvent`s a
   `focusin` event; it never calls `element.focus()`, so `document.activeElement` is unchanged.
   The card is *already* focused by the initial-focus effect at `CoachMarks.tsx:75-78`
   (`cardRef.current.focus()`), so `expect(document.activeElement).toBe(card)` at line 337 passes
   regardless of whether the trap exists. Proof: deleting the trap listener
   (`CoachMarks.tsx:108-120`) yields **54/54 still passing** — the mutation survives. This does not
   satisfy item 5 ("exercise Tab/Shift+Tab or equivalent focus leaving the card and assert focus
   stays inside"). A probe confirms the trap *implementation* works when real focus moves
   (`outside.focus()` → `document.activeElement` flips to `outside`, the `focusin` handler refocuses
   the card), so the fix is to call `outside.focus()` (or send Tab/Shift+Tab) instead of
   `fireEvent.focusIn`.

2. **[`App.test.tsx:123-135`] No test clicks "Take a tour" in the rendered app.** The only coverage
   is button existence (`getByRole('button', { name: 'Take a tour' })` at line 132). The replay
   path test at `TourHost.test.tsx:227-236` dispatches `new CustomEvent('qp-tour-request', …)`
   directly against `renderHook`, which the checker's request explicitly disqualifies. Item 6
   requires a test that renders `<App />`, clicks the header button (which dispatches the event at
   `AppShell.tsx:42-44`), and asserts the tour dialog (`role="dialog"`, `aria-label="Guided tour"`)
   appears — including a second render where the tour was already marked seen
   (`markTourSeen('qp_tour_application_v1')`) and the click still opens the dialog. No such test
   exists.

## Named mutations — run and results (production path, WSL)

Copy built read-only via `git archive HEAD | tar -x -C /tmp/qp1-a2-r2-check` + symlinked
`frontend/node_modules`; run with `PATH=…/node/v22.23.3/bin node node_modules/.bin/vitest --run`.

| # | Mutation (production location) | Result |
|---|---|---|
| 1 | versioned key → unversioned (`tourSteps.ts:3`) | **FAILS 2**: `writes qp_tour_application_v1 on close`, `stored _v1 key prevents auto-start` |
| 2 | remove `markTourSeen(tour.key)` (`TourHost.tsx:35`) | **FAILS 4**: `writes qp_tour_application_v1 on close`, `writes qp_tour_agent_v1 on close`, `writes qp_tour_architecture_v1 on close`, `stored _v1 key prevents auto-start` |
| 3 | missing selector blocks Next (`CoachMarks.tsx:85-93`) | **FAILS 1**: `continues to next step when current selector is missing` |
| 4 | remove focus restore (`CoachMarks.tsx:82`) | **FAILS 2**: `closes on Escape and restores focus…`, `closes on Done and restores focus…` |
| 5 | ArrowLeft wraps to last step (`CoachMarks.tsx:95`) | **FAILS 1**: `ArrowLeft does not wrap to last step` |
| 6 | remove reduced-motion guard (`TourHost.tsx:51-54`) | **FAILS 1**: `does not auto-start under prefers-reduced-motion` |
| 7 | measure once, drop resize/scroll listeners (`CoachMarks.tsx:64-73`) | **FAILS 2**: `repositions the spotlight after resize`, `repositions the spotlight after scroll` |
| 8 | remove focus trap listener (`CoachMarks.tsx:108-120`) | **SURVIVES** — 54/54 pass (blocking, §1) |

Every one of the 7 named mutations (1-7) fails at least one test. MiMo's "N/A — deleted hook code"
for mutations 2 and 6 is refuted: both applied to TourHost.tsx (the path the app runs) and both
fail. The remaining gap is §1 (focus trap has no effective test) and §2 (no click-through replay
test).

Representative FAILED output (mutation 8 — the trap removal, which should have failed but did not):

```
Test Files  6 passed (6)
     Tests  54 passed (54)
```

Representative FAILED output (mutation 4 — focus restore removed):

```
 FAIL  src/components/tours/CoachMarks.test.tsx > CoachMarks > closes on Escape and restores focus to the opener
AssertionError: expected <body><button></button>…</body> to be <button></button> // Object.is equality
 ❯ src/components/tours/CoachMarks.test.tsx:197:36
```

## Non-blocking notes

- `CoachMarks.tsx:85-93` — `next()` invokes `handleClose()` (which calls `onClose()` → parent
  `setState`) inside the `setIndex` updater, an impure side effect in a state updater. It emits a
  React warning in the "closes on Done" test ("Cannot update a component while rendering a different
  component") and would double-fire under StrictMode. Harmless today because `markTourSeen` is
  idempotent, but worth moving `handleClose()` out of the updater.
- Mutation 2 also trips `stored _v1 key prevents auto-start` (a 4th failure) in addition to the
  three direct `writes … on close` catches; the 3 direct failures are sufficient on their own.

## A1 regression

No regression. In the pristine copy the A1 suites pass: `states.test.tsx` (5),
`MarketDashboard.test.tsx` (1), `App.test.tsx` (8), `layout.test.tsx` (5).

## Checks run

- `git log --oneline b45b2a6..4deae4d` → 5 commits (plus `b45b2a6` itself) present on
  `feat/ui-enhancement`; worktree clean at `a30ce79`.
- `git archive HEAD | tar -x -C /tmp/qp1-a2-r2-check` + symlink `node_modules` → clean copy.
- `node node_modules/.bin/vitest --run` (baseline, WSL) → **54/54 pass** (6 files).
- `node node_modules/.bin/tsc --noEmit` → **pass** (0 errors).
- `node node_modules/.bin/vite build` → **pass** (185.18 kB JS, 21.21 kB CSS).
- 8 mutations applied and reverted in the copy; results in table above (1 survives: the focus-trap
  removal).
- Probe (temporary test in the copy, since removed): real `outside.focus()` flips
  `document.activeElement` to the outside element and the trap refocuses the card
  (`afterRealFocusCard: true`); `fireEvent.focusIn(outside)` leaves `document.activeElement` on the
  card (`activeIsCard: true, activeIsOutside: false`) — confirming the existing trap test asserts a
  pre-existing condition.
===VERDICT END===
