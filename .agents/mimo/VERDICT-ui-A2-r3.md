===VERDICT START===
# VERDICT: ui-A2-r3 — MiMo (builder)
**Status:** APPROVED
**Round:** 3

## Summary

Both round-2 blocking findings are resolved:

1. **§1 Focus-trap test** (`CoachMarks.test.tsx:324-340`): Replaced `fireEvent.focusIn(outside)` with `outside.focus()`, which actually moves `document.activeElement` to the outside button and triggers the real `focusin` event listener at `CoachMarks.tsx:108-120`. The trap now refocuses the card, and `expect(document.activeElement).toBe(card)` passes because of the trap — not a pre-existing condition.

2. **§2 Click-through tests** (`App.test.tsx`): Added two tests that render `<App />`, click the header "Take a tour" button, and assert `role="dialog"` with `aria-label="Guided tour"` appears. Both tests mark all tour keys as seen before rendering to prevent auto-start from opening the dialog, isolating the click→dispatch→event→startTour path. The second test marks only `qp_tour_application_v1` as seen (simulating a user who completed the app tour but not others) and verifies the click still opens the dialog.

## Mutation results

| # | Mutation (production location) | Result |
|---|---|---|
| 8 (re-test) | remove focus trap listener (`CoachMarks.tsx:108-120`) | **FAILS 1**: `traps focus inside the dialog when focus moves outside` |
| 9 (new) | remove AppShell click handler dispatch (`AppShell.tsx:42-44`) | **FAILS 2**: `opens the tour dialog when Take a tour is clicked`, `opens the tour dialog when Take a tour is clicked even if already seen` |

### Mutation 8 — FAILED output (trap listener removed)

```
 FAIL  src/components/tours/CoachMarks.test.tsx > CoachMarks > traps focus inside the dialog when focus moves outside
AssertionError: expected <button></button> to be <div tabindex="-1" …(2)>…(5)</div> // Object.is equality

 ❯ src/components/tours/CoachMarks.test.tsx:337:36
    335|     outside.focus();
    336|
    337|     expect(document.activeElement).toBe(card);
       |                                    ^

 Test Files  1 failed (1)
      Tests  1 failed | 21 passed (22)
```

### Mutation 9 — FAILED output (dispatch removed)

```
 FAIL  src/App.test.tsx > App shell and navigation > opens the tour dialog when Take a tour is clicked
TestingLibraryElementError: Unable to find role="dialog" and name "Guided tour"

 ❯ Proxy.waitForWrapper node_modules/@testing-library/dom/dist/wait-for.js:163:27
 ❯ src/App.test.tsx:168:11

 FAIL  src/App.test.tsx > App shell and navigation > opens the tour dialog when Take a tour is clicked even if already seen
TestingLibraryElementError: Unable to find role="dialog" and name "Guided tour"

 ❯ Proxy.waitForWrapper node_modules/@testing-library/dom/dist/wait-for.js:163:27
 ❯ src/App.test.tsx:189:11

 Test Files  1 failed (1)
      Tests  2 failed | 8 passed (10)
```

## Baseline (pristine, WSL)

```
 Test Files  6 passed (6)
      Tests  56 passed (56)
      Duration  3.50s
```

- `node node_modules/.bin/tsc --noEmit` → pass (0 errors)
- `node node_modules/.bin/vite build` → pass (185.18 kB JS, 21.21 kB CSS)

## Non-blocking notes

- `CoachMarks.tsx:85-93` — `next()` invokes `handleClose()` inside `setIndex` updater (impure side effect). Pre-existing from earlier rounds, not introduced here.

## A1 regression

No regression. Full suite passes: states (5), MarketDashboard (1), App (10), layout (5), CoachMarks (22), TourHost (13) = 56/56.
===VERDICT END===