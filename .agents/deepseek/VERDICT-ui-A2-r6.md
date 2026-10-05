===VERDICT START===
# VERDICT: ui-A2-r6 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 6

## Summary

Round 6 resolves both Codex round-2 blocking findings (`VERDICT-ui-A2-r2.md`). Commit `9f935fe`
clamps **both** spotlight edges before deriving width/height (`CoachMarks.tsx:161-170`), and the
360px test now actually sets `innerWidth = 360` (`CoachMarks.test.tsx:412`). All three CHECK items
pass, build is clean, and A1 is not regressed.

Copy built read-only via `git archive HEAD | tar -x -C /tmp/qp1-ui-check` + symlinked
`frontend/node_modules`; run with WSL node at `/home/jianj/.nvm/versions/node/v22.23.3/bin`.
Worktree left clean (`git status --short` empty).

## Item 1 — old one-edge clamp restored must FAIL

Restoring `width = Math.min(raw.width, vw - Math.max(0, raw.left))` (and the matching height line)
in the copy makes the new off-screen-right guard fail:

```
FAIL  CoachMarks.test.tsx > CoachMarks > clamps spotlight when target is entirely off-screen to the right
AssertionError: expected NaN to be greater than or equal to 0
  ❯ CoachMarks.test.tsx:470:15
```

With `vw=1024`, `rect.left=1200`, `rect.width=100`: `raw.left=1192`, `raw.width=116` →
`width = min(116, 1024-1192) = -168`; the browser rejects the negative CSS width, so
`parseInt(spotlight.style.width)` is `NaN`. The fixed two-edge clamp yields `width=0`
(`clampedLeft=clampedRight=1024`), which is inside `[0, vw]`. Guard is meaningful.

## Item 2 — off-screen targets above/below/left/right, never negative

`CoachMarks.tsx:161-170` clamps left/right/top/bottom independently then derives
`width = max(0, right - left)`, `height = max(0, bottom - top)`. A temporary four-direction test
(added only in the `/tmp` copy, not the repo) confirms above/below/left/right all produce
`width >= 0`, `height >= 0`, `left >= 0`, `top >= 0`, and `left+width <= 1024`, `top+height <= 768`
→ **4/4 pass**. For a fully off-screen target the `measure()` branch (`CoachMarks.tsx:47-51`) also
calls `el.scrollIntoView({ block: 'center' })` before re-measuring, so production scrolls it into
view (the centered fallback); the degenerate zero-size spotlight only appears when the mocked
`getBoundingClientRect` cannot move (jsdom no-op), and is still non-negative.

## Item 3 — 360px test + updater/clamp/nine mutations + build + A1

- 360px test really sets `innerWidth = 360`: `CoachMarks.test.tsx:412` (`Object.defineProperty(window, 'innerWidth', { value: 360, ... })`). At `vw=360 < 640`, `isMobile` is true so the overlay path (`bg-black`) renders — the "renders overlay instead of spotlight at 360px mobile viewport" test (`:410-440`) passes and is non-vacuous.
- updater mutation (move `handleClose()` inside the `setIndex` updater) → **FAILS** `CoachMarks.test.tsx:532` (`expected "spy" to be called 1 times, but got 2 times`).
- clamp-removal mutation → **FAILS** `CoachMarks.test.tsx:472` (`expected 1308 to be <= 1024`) plus the two earlier clamp tests.
- nine earlier A2 mutations — all still FAIL ≥1 guard:
  - M1 delete focus-trap listener → 1 fail (`traps focus inside the dialog…`)
  - M2 remove AppShell dispatch → 2 fail (`opens the tour dialog when Take a tour is clicked` [+already-seen])
  - N1 unversion keys → fail (`writes qp_tour_*_v1 on close` / hardcoded-key)
  - N2 remove `markTourSeen` → fail (`writes qp_tour_*_v1 on close`)
  - N3 missing selector blocks Next → 1 fail (`continues to next step when current selector is missing`)
  - N4 remove focus restore → 2 fail (`closes on Escape/Done and restores focus to the opener`)
  - N5 ArrowLeft wraps → 1 fail (`ArrowLeft does not wrap to last step`)
  - N6 remove reduced-motion guard → 1 fail (`does not auto-start under prefers-reduced-motion`)
  - N7 drop resize/scroll listeners → 2 fail (`repositions the spotlight after resize/scroll`)
- build OK; no A1 regression: baseline **62/62 pass** (6 files) includes A1 suites `states.test.tsx` (5), `MarketDashboard.test.tsx` (1), `layout.test.tsx` (5), `App.test.tsx` (10), `TourHost.test.tsx` (13), `CoachMarks.test.tsx` (28); `tsc --noEmit` clean; `vite build` 185.80 kB JS / 21.30 kB CSS.

## Non-blocking notes

- The off-screen-right guard asserts `w >= 0` and `left+width <= 1024`; with the fixed clamp the
  result is `width = 0` (degenerate but valid). In a real browser the target is scrolled into view
  first (`CoachMarks.tsx:50`), so this zero-size path is a jsdom-mock-only artifact.
- MiMo's self-report (`VERDICT-ui-A2-r6.md`) matches independent re-run: 62/62, tsc clean, build
  185.80 kB, and the NaN mutation failure reproduced here.

## Checks run

- `git archive HEAD | tar -x -C /tmp/qp1-ui-check` + symlink `node_modules` → read-only copy; no git in copy.
- `npx vitest --run` (baseline, WSL node v22.23.3) → **62/62 pass** (6 files).
- `npx tsc --noEmit` → **pass** (0 errors).
- `npm run build` → **pass** (185.80 kB JS, 21.30 kB CSS).
- one-edge-clamp mutation → **1 fail** (`CoachMarks.test.tsx:470`, NaN).
- four-direction off-screen temp test → **4/4 pass**.
- updater + clamp-removal + nine earlier A2 mutations → **all FAIL** their guards (table above).
- `git status --short` (repo) → clean.
===VERDICT END===
