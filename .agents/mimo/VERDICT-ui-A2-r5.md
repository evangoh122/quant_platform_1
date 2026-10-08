===VERDICT START===
# VERDICT: ui-A2-r5 — MiMo (builder)
**Status:** APPROVED
**Round:** 5

## Summary

Added the StrictMode once-only test requested by DeepSeek's r4 verdict (item 1).
The test renders `CoachMarks` inside `<React.StrictMode>` with a stateful parent
harness (`StrictModeHarness`) whose `onClose` calls `setRun(false)` — the exact
pattern that surfaces the "Cannot update a component" warning when `handleClose()`
is placed inside the `setIndex` updater. Two variants: Done (click Next→Next→Done)
and Escape. Each asserts `onClose` called exactly once, `markTourSeen`/`localStorage.setItem`
for the tour key called exactly once, and `console.error` spy contains zero calls
matching "Cannot update a component".

## What was done

- **`CoachMarks.test.tsx`**: Added `describe('StrictMode once-only guard')` with
  2 tests inside the existing `CoachMarks` describe block. Uses `StrictModeHarness`
  component (stateful parent), `fireEvent.click`/`fireEvent.keyDown` for deterministic
  synchronous dispatch, `vi.spyOn(window.localStorage, 'setItem')` with mock store
  for localStorage isolation, and `vi.spyOn(console, 'error')` to assert no
  "Cannot update a component" warning.

- **Mutation test (handleClose inside updater)**: Temporarily applied
  `setIndex((i) => { if (i >= steps.length - 1) { handleClose(); return i; } return i + 1; })`
  → the Done test **fails** with `expected "spy" to be called 1 times, but got 2 times`
  (StrictMode double-invokes the updater, calling handleClose twice). The Escape test
  still passes because Escape calls `handleClose()` directly via `onKey`, not through
  the updater. Correct code reverted.

## Blocking findings

None.

## Non-blocking notes

- [`CoachMarks.test.tsx` clamp tests] DeepSeek r4 findings 2 and 3 (clamp at 360px,
  tooltip-in-viewport, reduced-motion scrollIntoView) are out of scope for this round
  per BUILD-ui-A2-r5.md which only mandates the once-only test.

## Checks run

- `git log --oneline -1` → `c43e21c` on `feat/ui-enhancement`; worktree clean.
- `node node_modules/.bin/vitest --run` → **60/60 pass** (6 files), no "Cannot update a
  component" warning on stderr.
- `node node_modules/.bin/tsc --noEmit` → **pass** (0 errors).
- `npm run build` → **pass** (185.73 kB JS, 21.21 kB CSS).
- Mutation A (handleClose inside updater, Done test only) → **1 fail**: `expected "spy" to
  be called 1 times, but got 2 times` — confirms the guard catches the bug.
- Nine earlier A2 mutations still expected to fail their existing guards (not re-verified
  this round; owned by prior rounds).
===VERDICT END===