# BUILD EVIDENCE: coachmarks-rag-theme-r5 — MiMo

## Commit
- **SHA:** `970c4b49fb92606d6becda502847c1035f71ebca`
- **Branch:** `feat/rag-workbench-theme`
- **Message:** `fix(tours): place coach marks using measured card height`
- **Base:** r4 commit `bd73396a07fa97b60584efe8ef2d8f48086d0a19`
- **Scope:** `frontend/src/components/tours/CoachMarks.tsx` + `frontend/src/components/tours/coachmarks-r2.test.tsx` only. No backend/API/dependency change. No deploy.

## Acceptance checks (via `.agents/run-coachmarks-rag-theme-r5-check.sh`, wsl Ubuntu, node v26.5.0)

| Command | Result |
|---------|--------|
| `npx tsc --noEmit` | pass (0 errors) |
| `npx vitest run` | pass (334/334 tests, 16 files) |
| `npm run build` | pass (tsc && vite build, 68 modules) |
| legacy light-style grep (non-test tsx) | `none` |
| node/npm/npx boundary (`/mnt/*` rejects) | pass (all under `~/.nvm/versions/node/`) |
| `git rev-parse HEAD` == committed SHA | pass |
| `git status --porcelain --untracked-files=no` | clean |
| `git merge-base --is-ancestor origin/main HEAD` | pass |
| `git diff --check origin/main...HEAD` | clean |
| sentinel | `r5 check script finished` |

## Blocking finding (from `.agents/deepseek/VERDICT-coachmarks-rag-theme-r4.md`)

`frontend/src/components/tours/CoachMarks.tsx:332`: placement algorithm used hardcoded `180`/`200` magic numbers and never measured the rendered card height (`cardRef`). The explicit `placement: 'top' | 'bottom'` and `auto` modes ignored viewport collision entirely, never clamping the card inside the viewport.

## Fix

`frontend/src/components/tours/CoachMarks.tsx`:

### 1. Card height measurement
- Added `CARD_H_FALLBACK = 180` constant (named fallback, not inline magic).
- Added `cardHeight` state initialized to `CARD_H_FALLBACK`.
- Added `useLayoutEffect` that measures `cardRef.current.getBoundingClientRect().height` (or `offsetHeight`) after render and whenever `run`, `index`, `step`, `rect`, `waitingForTarget`, or `targetTimedOut` change. Accepts measurement only when `> 0` (jsdom returns 0; fallback retained).

### 2. Placement algorithm
- Constants: `GAP = 12`, `VIEWPORT_MARGIN = 12`.
- Uses measured `h = cardHeight` for all fit/room calculations.
- `fitsBelow = rect.bottom + GAP + h <= vh - VIEWPORT_MARGIN`
- `fitsAbove = rect.top - GAP - h >= VIEWPORT_MARGIN`
- `belowRoom = vh - VIEWPORT_MARGIN - (rect.bottom + GAP)`
- `aboveRoom = rect.top - GAP - VIEWPORT_MARGIN`
- **`bottom`**: place below if fitsBelow; else above if fitsAbove; else side with more room.
- **`top`** (mirror): place above if fitsAbove; else below if fitsBelow; else side with more room.
- **`auto`**: prefer below; flip above when below doesn't fit and above has more room.
- **Clamp**: `cardTop = clamp(desiredTop, VIEWPORT_MARGIN, max(vh - VIEWPORT_MARGIN - h, VIEWPORT_MARGIN))`. Horizontal clamp updated to use `VIEWPORT_MARGIN` constant.
- Above placement uses `bottom: vh - cardTop - h`; below uses `top: cardTop`.
- Mobile (bottom-sheet) path unchanged.
- Removed all magic `180`/`200` from placement logic.

## Required tests (all render real component; stub measured height via prototype spy)

All in `frontend/src/components/tours/coachmarks-r2.test.tsx`, Test 18.

### Test 18: Measured-height viewport collision placement

Setup: `vi.useFakeTimers()`, viewport 1024×800. Helper `stubCardHeight(h)` spies `HTMLElement.prototype.getBoundingClientRect` to return height `h` for elements with `tabindex="-1"` inside `[role="dialog"]`; own-property overrides on target elements (via `installTarget`) take precedence. Helper `getCardEdges(card, h)` reads `style.top`/`style.bottom` to compute card's viewport-coordinate top/bottom edges. `assertInsideViewport(edges)` asserts `top >= 12` and `bottom <= 788`.

#### Auto placement (6 cases + decision-change test)
Targets: near-top (20/60), middle (450/500), near-bottom (740/780). Heights: 120, 320.

| Target | h | Decision | Reason |
|--------|---|----------|--------|
| near top | 120 | below | fitsBelow (60+12+120=192 ≤ 788) |
| near top | 320 | below | fitsBelow (60+12+320=392 ≤ 788) |
| middle | 120 | below | fitsBelow (500+12+120=632 ≤ 788) |
| middle | 320 | above | !fitsBelow (500+12+320=832 > 788), fitsAbove (450-12-320=118 ≥ 12) |
| near bottom | 120 | above | !fitsBelow (780+12+120=912 > 788), fitsAbove (740-12-120=608 ≥ 12) |
| near bottom | 320 | above | !fitsBelow, fitsAbove (740-12-320=408 ≥ 12) |

**Decision-change test**: same middle target, h=120 → below, h=320 → above (different sides prove measured height affects decision).

All cases assert `assertInsideViewport(edges)`.

#### Bottom and top placement (4 cases)
- **bottom + middle h=120** (both sides fit): honors → below (top set).
- **bottom + near-bottom h=320** (below doesn't fit): flips → above (bottom set).
- **top + middle h=120** (both sides fit): honors → above (bottom set).
- **top + near-top h=120** (above doesn't fit): flips → below (top set).

All cases assert `assertInsideViewport(edges)`.

#### Viewport clamping (3 cases)
- **bottom, neither fits, above has more room** (target 340/470, h=320): aboveRoom=316 > belowRoom=306 → placeAbove=true, desiredTop=8 → clamped to 12 → inside viewport.
- **bottom, neither fits, below has more room** (target 300/470, h=320): belowRoom=306 > aboveRoom=276 → placeAbove=false, desiredTop=482 → clamped to 468 → inside viewport.
- **auto, extreme card height** (near-bottom 740/780, h=720): neither fits, desiredTop=8 → clamped to 12 → inside viewport.

## Mutation testing (isolated `git archive` copies under `/tmp/r5mut`, node_modules symlinked)

Each row: mutation applied to a fresh archive of `970c4b49fb92606d6becda502847c1035f71ebca`, target test re-run, expected FAIL observed.

| # | Mutation | Target test | Result |
|---|----------|-------------|--------|
| M1 | hardcode `const h = CARD_H_FALLBACK` (ignore measurement) | `Test 18` (14 cases) | FAIL — 5 tests fail: decision-change test (both sides same), middle-h=320 expects above gets below, viewport-clamp cases break (bottom=802 > 788, top=8 < 12) |
| M2 | make `bottom` ignore collision (`placeAbove = false`) | `Test 18` | FAIL — 2 tests fail: bottom-flip (near-bottom h=320 expects above), clamp-above-more-room (expects above) |
| M3 | remove final viewport clamp (`cardTop = desiredTop`) | `Test 18` | FAIL — 3 tests fail: clamp-above-more-room (top=8 < 12), clamp-below-more-room (bottom=802 > 788), clamp-extreme (top=8 < 12) |
| M4 | swap top/bottom branch expressions | `Test 18` | FAIL — 2 tests fail: bottom-honor (middle h=120 expects below, gets above), top-honor (middle h=120 expects above, gets below) |
| r4-M1 | put `currentScreen` back into reset deps | `Test 16` (4 cases) | FAIL — 4/4 cases fail (loop to step 1) |
| r4-M2 | overwrite `initialScreenRef` on every render | `Test 16` | FAIL — 4/4 cases fail (wrong screen restored) |
| r4-M3 | remove `inert` from drawer | `Test 17` | FAIL — `expected null not to be null` |
| r4-M4 | remove `aria-controls` from disclosure | `Test 14` | FAIL — `aria-controls` attribute null |
| r3-M1 | hardcode `tour:'application'` | `Test 1` | FAIL — 2 cases expect `['agent']/['architecture']`, receive `['application']` |
| r3-M6 | remove `aria-expanded` | `Test 14` | FAIL — both rendered cases see attribute null |

## Files modified (2)
1. `frontend/src/components/tours/CoachMarks.tsx` — card-height measurement + measured-height placement algorithm
2. `frontend/src/components/tours/coachmarks-r2.test.tsx` — Test 18 (14 new test cases)

## Non-blocking notes
- `CARD_H_FALLBACK = 180` serves as the initial state value and fallback in jsdom (where `getBoundingClientRect().height` returns 0). In a real browser, the layout effect updates to the measured height on the first paint.
- The placement algorithm now uses named constants (`GAP`, `VIEWPORT_MARGIN`, `CARD_H_FALLBACK`) instead of inline magic numbers, making the logic self-documenting and easy to tune.
- All 10 mutations (4 new + 6 r4/r3 re-runs) are detected by the test suite.

BUILD DONE | status: SUCCESS | sha: 970c4b49fb92606d6becda502847c1035f71ebca | branch: feat/rag-workbench-theme | evidence: .agents/mimo/EVIDENCE-coachmarks-rag-theme-r5.md