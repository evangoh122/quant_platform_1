===VERDICT START===
# VERDICT: ui-A2-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Summary

All 7 blocking findings from DeepSeek's round-1 verdict are resolved. The dead `useTour` hook
is deleted (single auto-start path via `useTourHost` in TourHost.tsx). Focus restore timing bug
is fixed (deferred via setTimeout to avoid focus trap interference). All 9 mutations now fail at
least one test. Suite: 54/54 pass, tsc clean, build OK (185.18 kB JS, 21.21 kB CSS).

## Changes

| Commit | Scope |
|--------|-------|
| `b45b2a6` | Delete dead `useTour` hook; fix focus restore timing in `handleClose` |
| `1d39eac` | Fix all 7 blocking findings in CoachMarks tests |
| `98b0ff0` | Add TourHost production path tests |
| `e65d24d` | Add hardcoded key assertions to catch versioned-key mutations |
| `742bbbd` | Strengthen spotlight and versioned-key mutation coverage |

## Blocking findings addressed

1. **§1 Versioned keys** — Tests assert `qp_tour_application_v1`, `qp_tour_agent_v1`,
   `qp_tour_architecture_v1` written on close; hardcoded key check prevents auto-start.
2. **§2 Focus restore** — Tests verify `document.activeElement` returns to opener after Escape
   and Done (production path with `run=false` parent).
3. **§3 Spotlight reposition** — Tests verify spotlight `left`/`top` style updates after
   `resize` and `scroll` events.
4. **§4 Production path** — TourHost tests cover `markTourSeen` via `closeTour` and
   reduced-motion guard; dead `useTour` hook deleted.
5. **§5 Focus trap** — Test fires `focusin` on external element and verifies focus returns to
   card.
6. **§6 Header replay** — Test dispatches `qp-tour-request` event and verifies tour starts.
7. **§7 Missing-selector** — Test uses distinct titles ("Missing Step" / "Continue Step") and
   asserts second step title after clicking Next.

## Named mutations — run and results

| # | Mutation (location) | Result |
|---|---|---|
| 1 | versioned key → unversioned (`tourSteps.ts:3`) | **FAILS 2**: `writes qp_tour_application_v1 on close`, `stored _v1 key prevents auto-start` |
| 2 | remove completion write in `useTour.close()` | **N/A** — hook deleted |
| 3 | missing selector blocks Next (`CoachMarks.tsx:86`) | **FAILS 1**: `continues to next step when current selector is missing` |
| 4 | remove focus restore (`CoachMarks.tsx:82`) | **FAILS 2**: `closes on Escape and restores focus to the opener`, `closes on Done and restores focus to the opener` |
| 5 | ArrowLeft wraps to last step (`CoachMarks.tsx:96`) | **FAILS 1**: `ArrowLeft does not wrap to last step` |
| 6 | remove reduced-motion guard in `useTour` | **N/A** — hook deleted |
| 7 | drop resize/scroll listeners (`CoachMarks.tsx:64-73`) | **FAILS 2**: `repositions the spotlight after resize`, `repositions the spotlight after scroll` |
| 8 | remove `markTourSeen` in TourHost (`TourHost.tsx:35`) | **FAILS 3**: `writes qp_tour_application_v1 on close`, `writes qp_tour_agent_v1 on close`, `writes qp_tour_architecture_v1 on close` |
| 9 | remove reduced-motion guard in TourHost (`TourHost.tsx:51-54`) | **FAILS 1**: `does not auto-start under prefers-reduced-motion` |

All 7 applicable mutations fail at least one test. Mutations 2 and 6 are N/A (target code deleted).

## Representative FAILED output

Mutation 8 (remove `markTourSeen`):
```
 FAIL  src/components/tours/TourHost.test.tsx > useTourHost — versioned keys > writes qp_tour_application_v1 on close
AssertionError: expected undefined to be '1'
 ❯ src/components/tours/TourHost.test.tsx:59:44
```

Mutation 4 (remove focus restore):
```
 FAIL  src/components/tours/CoachMarks.test.tsx > CoachMarks > closes on Escape and restores focus to the opener
AssertionError: expected <div tabindex="-1" …> to be <button> // Object.is equality
 ❯ src/components/tours/CoachMarks.test.tsx:197:36
```

Mutation 7 (drop resize/scroll listeners):
```
 FAIL  src/components/tours/CoachMarks.test.tsx > CoachMarks > repositions the spotlight after resize
AssertionError: expected '92px' to be '400px' // left unchanged after resize
 ❯ src/components/tours/CoachMarks.test.tsx:274:39
```

## Checks run

- `npx vitest --run` → **54/54 pass** (6 files)
- `tsc --noEmit` → **pass** (0 errors)
- `vite build` → **pass** (185.18 kB JS, 21.21 kB CSS)
- 9 mutations applied and reverted; 7 fail, 2 N/A

## Commits on `feat/ui-enhancement`

```
742bbbd test: strengthen spotlight and versioned-key mutation coverage
e65d24d test: add hardcoded key assertions to catch versioned-key mutations
98b0ff0 test: add TourHost production path tests
1d39eac test: fix all 7 blocking findings in CoachMarks tests
b45b2a6 fix: remove dead useTour hook and fix focus restore timing
```
===VERDICT END===