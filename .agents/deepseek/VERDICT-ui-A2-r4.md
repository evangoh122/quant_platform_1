===VERDICT START===
# VERDICT: ui-A2-r4 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 4

## Summary

The two Codex findings are *functionally* fixed: the `setIndex` updater in `next` is now pure
(`CoachMarks.tsx:99`) with `handleClose()` called once outside the updater, and the spotlight
rectangle is clamped after padding (`CoachMarks.tsx:161-166`). Mutation B (remove the clamp) fails
2 tests and all nine earlier A2 mutations still fail their guards, so the guard tests that do exist
are meaningful. However, the round-4 BUILD spec required specific tests that were **not written**,
and the checker's own item 1 mandates that "move handleClose back into the updater" **must fail a
test** — it does not (58/58 pass; only an unasserted stderr warning). Details below.

Baseline (read-only copy `git archive HEAD | tar -x -C /tmp/qp1-ui-a2-r4-pristine` + symlinked
`frontend/node_modules`, WSL node v22.23.3): vitest 58/58 pass (6 files), tsc clean, vite build
185.73 kB JS / 21.21 kB CSS. Worktree left clean.

## Blocking findings

1. **[`CoachMarks.test.tsx` (whole file) / `BUILD-ui-A2-r4.md` item 1] The required StrictMode
   once-only test was never written, so the primary round-4 mutation does not fail a test.**
   The spec required: "under `<React.StrictMode>`, clicking Done/Next-on-last-step calls onClose
   exactly once and markTourSeen writes once; the test run emits no 'Cannot update a component while
   rendering a different component' warning (spy on console.error and assert it was not called with
   that text)". `grep StrictMode frontend/src` matches only `main.tsx:7`; there is no
   `console.error` spy and no `toHaveBeenCalledTimes` assertion anywhere in the suite. Consequence:
   re-applying the bug (mutation: move `handleClose()` back inside the `setIndex` updater, as in the
   pre-fix `CoachMarks.tsx`) leaves **58/58 tests passing**, emitting only an unasserted
   `Warning: Cannot update a component (FocusTest) while rendering a different component (CoachMarks)`
   on stderr. This violates CHECK-ui-A2-r4.md item 1 ("Mutations, each must fail a test") and item 1's
   third mutation ("remove the StrictMode wrapper from the once-only test") is un-performable because
   the test does not exist. The pure-updater fix is therefore unguarded.

2. **[`CoachMarks.test.tsx:344` and `:378`] Clamp tests use `innerWidth = 1024`, not 360px, and the
   clamp path is unreachable at 360px.** Both new tests — "clamps spotlight left to 0 when target is
   at x=-20" and "clamps spotlight to viewport when target is wider than a 360px viewport" — set
   `window.innerWidth = 1024` (lines 344 and 378). At a real 360px viewport, `isMobile = vw < 640`
   (`CoachMarks.tsx:133`) is true, so the spotlight branch `rect && !isMobile` (`CoachMarks.tsx:154`)
   is never rendered and the component falls back to the full `bg-black/58` overlay
   (`CoachMarks.tsx:180`). The "off-screen and wider-than-viewport targets at 360px" requirement
   (CHECK item 2, BUILD item 2) is therefore not exercised at the specified viewport width.

3. **[`CoachMarks.tsx:48-51`, `:67-68`, `:147-148`] No test for tooltip-in-viewport or for
   `scrollIntoView` respecting reduced motion.** CHECK item 2 requires "tooltip in viewport;
   scrollIntoView respects reduced motion". The fully-off-screen `measure` branch
   (`CoachMarks.tsx:48-51`) and the layout-effect `scrollIntoView` (`CoachMarks.tsx:67-68`) correctly
   gate `behavior` on `prefers-reduced-motion`, but no test covers either; the desktop card clamp
   (`CoachMarks.tsx:147-148`) that keeps the tooltip inside the viewport is likewise untested.
   Deleting either scrollIntoView call or the reduced-motion ternary would survive the suite.

## What IS correct (verified)

- `next()` (`CoachMarks.tsx:94-100`) is now a pure updater: `if (index >= steps.length - 1) { handleClose(); return; } setIndex((i) => i + 1);`. No side effect in an updater.
- Clamp (`CoachMarks.tsx:161-166`): `left/top = max(0, raw)`, `width = min(raw.width, vw - max(0, raw.left))`, `height = min(raw.height, vh - max(0, raw.top))` — satisfies left/top ≥ 0 and right/bottom ≤ innerWidth/innerHeight.
- Mutation B (clamp removed) → **2 tests fail**: `expected -28 to be >= 0` and `expected -8 to be >= 0` (CoachMarks.test.tsx:369 and :402).
- All nine earlier A2 mutations re-run and each still fails ≥1 test (see Checks run).

## Non-blocking notes

- [`CoachMarks.tsx:164`] When `raw.left < 0`, `width = Math.min(raw.width, vw - 0)` does not shrink
  by the negative overflow, so a target partially off the left edge keeps its full padded width (e.g.
  x=-20 → spotlight covers 0..216 while the visible target ends at 180). Cosmetic over-extension;
  it stays within `[0, innerWidth]`, so not blocking.
- [`App.test.tsx:173-192`] the "even if already seen" test remains order-dependent as noted in r3
  (only `qp_tour_application_v1` is marked seen; it relies on the preceding test marking all three).
  Pre-existing, non-blocking.

## A1 regression

None. Baseline run passes A1 suites: `states.test.tsx` (5), `MarketDashboard.test.tsx` (1),
`layout.test.tsx` (5), plus `App.test.tsx` (10), `CoachMarks.test.tsx` (24), `TourHost.test.tsx` (13)
= 58/58.

## Checks run

- `git log --oneline -1` → `136208f` on `feat/ui-enhancement`; worktree clean (tracked).
- `node node_modules/.bin/vitest --run` (baseline) → **58/58 pass** (6 files), no "Cannot update a
  component" warning on stderr.
- `node node_modules/.bin/tsc --noEmit` → **pass** (0 errors).
- `node node_modules/.bin/vite build` → **pass** (185.73 kB JS, 21.21 kB CSS).
- Mutation A (handleClose inside updater) → **58/58 pass** with only an unasserted stderr
  `Warning: Cannot update a component (FocusTest) while rendering a different component (CoachMarks)`.
- Mutation B (clamp removed) → **2 fail**: `clamps spotlight left to 0 when target is at x=-20`
  (`expected -28 to be >= 0`), `clamps spotlight to viewport when target is wider than a 360px
  viewport` (`expected -8 to be >= 0`).
- Nine earlier A2 mutations re-run (each still fails ≥1 test): m1 focus-trap listener removed → 1
  fail (`traps focus inside the dialog…`); m2 AppShell dispatch removed → 2 fail (`opens the tour
  dialog when Take a tour is clicked` [+already-seen]); n1 unversioned keys → 4 fail; n2 remove
  `markTourSeen` → 3 fail; n3 missing selector blocks Next → 1 fail; n4 remove focus restore → 2
  fail; n5 ArrowLeft wraps → 1 fail; n6 remove reduced-motion guard → 1 fail; n7 drop resize/scroll
  listeners → 2 fail.
===VERDICT END===
