# Build: measured-height coach-mark placement (r5)

Builder: MiMo. Base: r4 commit `bd73396a07fa97b60584efe8ef2d8f48086d0a19` on `feat/rag-workbench-theme`. Finding: Codex final validation CHANGES_REQUESTED (DeepSeek missed it in r2-r4).
Commit on this branch only; frontend only; no backend/dependency change; no deploy.

## Blocking finding
`frontend/src/components/tours/CoachMarks.tsx:332` auto placement uses a hardcoded `below + 180 > vh && rect.top > 200` and never measures the rendered card (`cardRef`, line 40/264/379).
Explicit `placement: 'top' | 'bottom'` (lines ~327-331) ignores viewport collision entirely. The r2 requirement (`BUILD-coachmarks-rag-theme-r2.md` item 4) says placement "must account for measured card height and viewport collision".

## Required change
1. Measure the real card height (`cardRef.current.getBoundingClientRect().height` or `offsetHeight`) in a layout effect after render and whenever step content/viewport changes; store in state with a sane first-render fallback (CARD_H_FALLBACK constant, not an inline magic number).
2. Placement algorithm (desktop path), using the measured height `h`, GAP=12 and a viewport margin of 12:
   - `bottom`: place below if `rect.bottom + GAP + h <= vh - margin`; otherwise flip above if it fits (`rect.top - GAP - h >= margin`); otherwise pick the side with more room and clamp the card inside the viewport.
   - `top`: mirror image.
   - `auto`: prefer below; flip above when below doesn't fit and above has more room; same final clamp.
   - Always clamp so the whole card stays inside the viewport (top >= margin, bottom <= vh - margin) and horizontally (existing clamp stays).
   Mobile (bottom-sheet) path unchanged.
3. Remove the magic `180` / `200`.

## Required tests (render the real component; stub measured height — jsdom has no layout)
Stub `HTMLElement.prototype.getBoundingClientRect`/`offsetHeight` (or the specific card element) to return controllable heights and the target rect via the real selector element. Cover, for card heights {120, 320} and targets near top, middle and bottom of a 800px-high viewport:
- `auto` flips above when the tall card does not fit below, stays below for the short card.
- `bottom` and `top` honor the request when they fit and flip when they don't.
- In every case the card's computed top/bottom keep it fully inside the viewport.
- Assert the decision changes with the measured height (same target, different card height → different side).
Keep all existing tests passing; do not delete existing placement tests unless replaced by stronger ones.

## Mutations that MUST fail a test (isolated `git archive` copies; code edits, not comments)
M1 restore a hardcoded height (ignore measurement). M2 make `bottom` ignore collision (never flip). M3 remove the final viewport clamp. M4 swap top/bottom branches.
Re-run the r4 mutations (`currentScreen` back into reset deps; overwrite `initialScreenRef`; remove `inert`; remove `aria-controls`; hardcode `tour:'application'`; remove `aria-expanded`) and show each still fails a test.

## Acceptance
`cd frontend && npx tsc --noEmit && npx vitest run && npm run build` pass (export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"); legacy-class grep none. Create `.agents/run-coachmarks-rag-theme-r5-check.sh` like the r4 script (pin new SHA via placeholder pattern, PATH + /mnt/ boundary assertion).
Evidence `.agents/mimo/EVIDENCE-coachmarks-rag-theme-r5.md`. Descriptive commit message (e.g. `fix(tours): place coach marks using measured card height`). End with exactly:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/rag-workbench-theme | evidence: .agents/mimo/EVIDENCE-coachmarks-rag-theme-r5.md`
