# VERDICT: coachmarks-rag-theme-r5 — DeepSeek
**Status:** APPROVED
**Round:** 5

Validated commit `970c4b49fb92606d6becda502847c1035f71ebca` read-only. This is a
read-only check request; I wrote no feature code. Reproduced MiMo's r5 evidence
independently (evidence is self-report; all claims re-verified below).

## Blocking findings

None.

## Non-blocking notes

- `CoachMarks.tsx:43` `CARD_H_FALLBACK = 180` is the initial state value and the
  jsdom fallback. On the first desktop paint, before the layout effect measures
  the card, placement may briefly use 180px; the next layout effect corrects it.
  No render loop (see below) and no stale-height bug — not a defect.
- `CoachMarks.tsx:349` `maxTop = Math.max(minTop, vh - VIEWPORT_MARGIN - h)`
  degenerates for a card taller than `vh - 2*VIEWPORT_MARGIN` (would overflow),
  but this is pathological and is bounded + covered at h=720 in an 800px
  viewport (`Test 18` "extreme card height"). Not blocking.

## Review findings (per CHECK-coachmarks-rag-theme-r5.md)

1. **HEAD / tree / ancestry / scope** — `HEAD` = `970c4b49fb92606d6becda502847c1035f71ebca`;
   `git status --porcelain --untracked-files=no` empty (tracked tree clean);
   `git merge-base --is-ancestor origin/main HEAD` passed. HEAD commit touches
   only `frontend/src/components/tours/CoachMarks.tsx` and
   `frontend/src/components/tours/coachmarks-r2.test.tsx` (frontend + artifacts only).

2. **Check script** — ran exactly
   `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r5-check.sh`:
   tsc --noEmit pass, `vitest run` **334/334 passed (16 files)**, `npm run build`
   pass, legacy light-style grep `none`, boundary/node-platform/diff checks pass,
   sentinel `r5 check script finished`. No boundary failure.

3. **Placement (production, `CoachMarks.tsx` 326-357)** — verified:
   - Height **measured**: `useLayoutEffect` (213-218) reads
     `cardRef.current.getBoundingClientRect().height || offsetHeight`, re-runs on
     `run/index/step/rect/waitingForTarget/targetTimedOut`; `rect` updates on
     window resize/scroll (156-165), so height re-measures on step/content/viewport
     change. Not a one-time guess.
   - Fallback is the named constant `CARD_H_FALLBACK = 180` (not an inline magic).
   - `fitsBelow`/`fitsAbove`/`belowRoom`/`aboveRoom` use measured `h` + `GAP=12` +
     `VIEWPORT_MARGIN=12`. `auto`/`top`/`bottom` flip logic (341-347) is correct:
     `bottom` places below unless it doesn't fit, then above if it fits, else the
     side with more room; `top` mirrors; `auto` prefers below and flips above only
     when below doesn't fit and above has more room.
   - Clamp (348-351): `cardTop = clamp(desiredTop, 12, max(vh-12-h, 12))` guarantees
     `top >= margin` and `bottom <= vh - margin` for `h <= vh - 2*margin`; horizontal
     clamp (352-353) holds (`left` in `[margin, vw - CARD_W - margin]`).
   - `above` branch (354-355) positions with `bottom: vh - cardTop - h`, which yields
     top edge `= cardTop` — correct.
   - No render loop: `setCardHeight` is not a dependency of the measuring effect;
     same-height measurement bails out of re-render. First render before measurement
     and window resize both correct (traced).

4. **Tests stub measured height via the real card element** — `stubCardHeight(h)`
   (`coachmarks-r2.test.tsx:1022-1031`) spies `HTMLElement.prototype.getBoundingClientRect`
   and returns the stubbed height only for the element that is `[tabindex="-1"]`
   inside `[role="dialog"]` (the real card node); target rects come from the real
   selector element via its own `getBoundingClientRect`. `getCardEdges` reads
   `style.top`/`style.bottom` and derives edges — it does not copy production logic.
   Coverage: heights {120, 320} × targets near-top/middle/near-bottom for
   `auto` (7 cases incl. a decision-change test) and `top`/`bottom` (4 cases) plus
   3 viewport-clamp cases. The decision-change test proves the same target picks a
   different side when the height changes (120 → below, 320 → above).
   **Would fail on r4** — verified independently: overlaying the r5 test file onto
   `bd73396` code yields **7 Test 18 failures** (auto middle/h=320, decision-change,
   bottom flip, top flip, and all 3 clamp cases).

5. **Mutations in isolated `git archive` copies** (fresh archive of
   `970c4b49…`, `node_modules` symlinked; edits are code, not comments). Each
   mutation fails its intended rendered test for the intended reason:

   | Mutation | Result | Intended failures |
   |---|---|---|
   | M1 hardcode `const h = CARD_H_FALLBACK` | FAIL | 5 × Test 18 (middle h=320, decision-change, 3 clamp: 802>788 / 8<12) |
   | M2 bottom never flips (`placeAbove=false`) | FAIL | 2 × Test 18 (bottom flip, clamp above-more-room) |
   | M3 remove clamp (`cardTop=desiredTop`) | FAIL | 3 × Test 18 (clamp-above 8<12, clamp-below 802>788, clamp-extreme 8<12) |
   | M4 swap top/bottom branches | FAIL | 3 (Test 6 top placement, Test 18 bottom-honor→above, top-honor→below) |
   | r4-M1 `currentScreen` back into reset deps | FAIL | 4 × Test 16 (reset to step 1) |
   | r4-M2 overwrite `initialScreenRef` every render | FAIL | 4 × Test 16 (restores destination, not start) |
   | r4-M3 remove `inert` from drawer background | FAIL | 1 × Test 17 |
   | r4-M4 remove `aria-controls` | FAIL | 1 × Test 14 |
   | r3-M1 hardcode `tour:'application'` | FAIL | 3 (Test 1 ×2, Test 8) |
   | r3-M6 remove `aria-expanded` | FAIL | 2 × Test 14 |

6. No missing, vacuous, or surviving proof; no production defect found.

## Checks run

- `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r5-check.sh` → pass (334/334, tsc, build, grep none)
- `git rev-parse HEAD` → `970c4b49fb92606d6becda502847c1035f71ebca`
- `git status --porcelain --untracked-files=no` → clean
- `git merge-base --is-ancestor origin/main HEAD` → pass
- `git show --stat 970c4b49…` → 2 files, frontend only
- r5 test file vs r4 `bd73396` source → 7 Test 18 failures (expected)
- 10 isolated-archive mutations → all fail intended tests (expected)

VALIDATION DONE | verdict: APPROVED | sha: 970c4b49fb92606d6becda502847c1035f71ebca | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r5.md
