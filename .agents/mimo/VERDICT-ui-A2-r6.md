# VERDICT: ui-A2 round 6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
(none)

## Non-blocking notes
- At vw=360, `isMobile=true` so the spotlight path is never taken — the overlay is rendered instead. The 360px test now correctly verifies the mobile overlay path rather than spotlight clamping.
- The off-screen right-edge case (vw=1024, rect.left=1200, width=100) now produces spotlight width=0 (within [0, vw]) instead of the old -168px (browser-rejected NaN).

## Mutation evidence — old one-edge clamp restored
```
FAIL  CoachMarks.test.tsx > CoachMarks > clamps spotlight when target is entirely off-screen to the right
AssertionError: expected NaN to be greater than or equal to 0
 ❯ CoachMarks.test.tsx:470:15
    468|     const w = parseInt(spotlight.style.width, 10);
    469|     const l = parseInt(spotlight.style.left, 10);
    470|     expect(w).toBeGreaterThanOrEqual(0);
```
Old code: `width = Math.min(raw.width, vw - Math.max(0, raw.left))` → min(116, 1024-1192) = -168 → browser rejects → NaN.

## Checks run
- `npx vitest --run` → 62/62 passed (28 CoachMarks tests including3 new)
- `npx tsc --noEmit` → passed
- `npm run build` → passed (185.80 KB JS)
- Old one-edge clamp mutation → correctly fails new off-screen-right test with NaN

## Files changed
- `frontend/src/components/tours/CoachMarks.tsx` — clamp both edges (left/right, top/bottom) before deriving width/height
- `frontend/src/components/tours/CoachMarks.test.tsx` — fix 360px test to use actual 360px viewport; add off-screen-right test at 1024px; add 360px mobile overlay test

## Commit
`9f935fe` on `feat/ui-enhancement`