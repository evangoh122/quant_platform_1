# VERDICT: ui-A2-r4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None.

## Non-blocking notes
- `measure` callback now uses `window.innerWidth/innerHeight` directly (not the component-scope `vw`/`vh` variables) to avoid `ReferenceError: Cannot access 'vw' before initialization`.
- Spotlight IIFE uses `(() => { ... })()` ternary to keep JSX clean.
- `scrollIntoView` respects `prefers-reduced-motion` media query (`behavior: 'auto'` when reduced).

## Changes made
1. **CoachMarks.tsx:85** — Moved `handleClose()` call out of `setIndex` updater. The updater is now pure: `(i) => i + 1`. The close/markTourSeen side effect runs exactly once, guarded by `index >= steps.length - 1` before the `setIndex` call.
2. **CoachMarks.tsx:151** — Spotlight rectangle is clamped to viewport after padding: `left/top >= 0`, `width <= vw - max(0, raw.left)`, `height <= vh - max(0, raw.top)`. Fully off-screen targets trigger `scrollIntoView({block:'center'})` respecting reduced motion.

## Mutation verification
- **Mutation 1** (handleClose inside updater): Tests pass but React emits `Warning: Cannot update a component while rendering a different component` on stderr → proves the pure updater is necessary.
- **Mutation 2** (clamp removed): 2 tests fail: `expected -28 to be >= 0` and `expected -8 to be >= 0` → proves the clamp is necessary.

## Checks run
- `npx vitest --run` → 58/58 passed (6 test files)
- `npx tsc --noEmit` → passed
- `npm run build` → passed (185.73 kB JS, 21.21 kB CSS)