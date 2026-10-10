# VERDICT: coachmarks-rag-theme-r4 — DeepSeek
**Status:** APPROVED
**Round:** 4

## Scope / git audit (request item 1)

- HEAD `bd73396a07fa97b60584efe8ef2d8f48086d0a19` matches the required SHA. ✓
- `git status --porcelain --untracked-files=no` → empty (tracked tree clean). ✓
- `git merge-base --is-ancestor origin/main HEAD` → pass. ✓
- `git diff --check origin/main...HEAD` → clean. ✓
- r4 commit scope: `frontend/src/components/tours/CoachMarks.tsx` +
  `frontend/src/components/tours/coachmarks-r2.test.tsx` only (2 files,
  `git show --stat`). Full branch delta (origin/main...HEAD) is frontend + `.agents/*`
  artifacts. No backend/API/dependency change. ✓
- Commit message `fix(tours): reset only on run start; restore starting screen` (descriptive). ✓

## B1 fix verified (request item 3)

`frontend/src/components/tours/CoachMarks.tsx`:

- `:44-45` `currentScreenRef` mirrors latest `currentScreen` on every render
  (`currentScreenRef.current = currentScreen;`), so the reset effect reads a ref, not a stale
  closure.
- `:70-77` reset effect is keyed on `[run]` only; on the false→true edge it captures
  `initialScreenRef.current = currentScreenRef.current`, resets `setIndex(0)`, clears timeout.
  `currentScreen` is NOT a reset dependency. ✓
- `:80-150` navigation `useLayoutEffect` keyed `[run, step, measure, onNavigate]` — unchanged,
  no reintroduction of `currentScreen` into a reset. ✓
- `:209-215` `handleClose` restores `onNavigate(initialScreenRef.current)`. All four close paths
  route through `handleClose`: X (`:389`), Skip (`:417`), Done via `next`→`handleClose`
  (`:217-223`, `:432`), Escape (`:230`). ✓

Independent reproduction (isolated `git archive` copies, real stateful `onNavigate`→`useState`):
- M1 (put `currentScreen` back into reset deps) → stateful harness shows
  `Step 1 of 2` (loop-to-step-1 defect, exact B1 failure). ✓
- M2 (overwrite `initialScreenRef` every render) → harness restore call is
  `['market','market']` instead of `['market','signals']` (wrong screen restored). ✓
- Clean tree: `npx vitest run` 320/320 incl. Test 16 which starts on `signals` (non-default)
  and asserts monotonic `Step 1..5 of 5` counters and restore-to-`signals`. ✓

## Tests (request item 4)

- Vacuous static-prop Test 16 is gone; replacement is stateful: real `App` + a `useState`
  harness, 4 cases (advance-to-last-step + monotonic counter, Done/Escape/Skip restore,
  stateful harness restore). ✓
- Source-scan tests converted to rendered DOM/ARIA: Test 11 (`role=status` + heading),
  Test 12 (skip link first focusable → `#main-content`), Test 13 (labelled textbox),
  Test 14 (`aria-expanded`/`aria-controls` wired to real id). ✓
- Test 17 renders `AppShell`→`MobileNavigation` and asserts `[inert]` on open, absent on close. ✓
- Test 8 rewritten as real `App`+`TourHost` replay (route-correct tour with all seen keys = 1);
  misleading attribution removed. ✓
- Check script `.agents/run-coachmarks-rag-theme-r4-check.sh`: no stale `r2 check script
  finished` sentinel (prints `r4 check script finished`), has `export PATH=...node/v26.5.0/bin`
  and the `/mnt/*` boundary assertion. r3 script removed. ✓

## Mutation testing (request item 5; isolated `git archive` copies, node_modules symlinked; no
`git` inside a `cp -r` copy)

| # | Mutation | Target | Result |
|---|----------|--------|--------|
| M1 | `currentScreen` back in reset deps | Test 16 | FAIL 4/4 (harness `Step 1 of 2`) |
| M2 | overwrite `initialScreenRef` every render | Test 16 | FAIL 4/4 (`['market','market']`) |
| M3 | remove `inert` from drawer | Test 17 | FAIL 1/1 |
| M4 | remove `aria-controls` from disclosure | Test 14 | FAIL (case 1) |
| r3-M1 | hardcode `tour:'application'` | Test 1 | FAIL 2/2 (agent + architecture) |
| r3-M2 | `qp-tour-request` respects seen keys | App "even if already seen" + Test 8 | FAIL 1/1 + 2/2 |
| r3-M3 | remove 44px `@media` rule | Test 5 | FAIL 1/1 |
| r3-M4 | stale `_v1` seen key | App auto-start guard | FAIL 1/1 |
| r3-M5 | `bg-blue-100 text-blue-700` badge | Test 10 (ToolCallCard) | FAIL 1/1 |
| r3-M6 | remove `aria-expanded` | Test 14 | FAIL 2/2 |
| r3-M7 | remove skip link | Test 12 | FAIL 2/2 |
| r3-M8 | drop Escape handling | layout "restores focus" | FAIL 1/1 |
| r3-M9 | remove `onNavigate(initialScreenRef)` | Test 16 | FAIL 4/4 |

New tests fail on r3 base `6a33f723a399681d5f1294044a401a7f4a53af0b` (archive + r4 test file
overlaid): Test 16 fails 4/4. ✓

## Checks run

- `git rev-parse HEAD` → `bd73396a07fa97b60584efe8ef2d8f48086d0a19` (pass)
- `git merge-base --is-ancestor origin/main HEAD` → pass
- `git status --porcelain --untracked-files=no` → clean
- `git diff --check origin/main...HEAD` → clean
- `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r4-check.sh`
  → pass (node v26.5.0; `tsc --noEmit` 0 errors; `vitest run` 320/320 across 16 files;
  `npm run build` ok, 68 modules; legacy light-style grep → none; sentinel `r4 check script
  finished`). Boundary: node/npm/npx resolve under `~/.nvm/versions/node/`, not `/mnt/`.
- Mutation matrix + r3-base overlay: reproduced independently as above (all intended failures).

## Non-blocking notes

- `CoachMarks`' step `useLayoutEffect` (`:80-150`) re-fires `onNavigate(step.navigateTo)` if a
  caller passes an unstable `onNavigate`/`steps` identity. The real `App` is safe
  (`handleTourNavigate` is `useCallback([])`; `steps` set once per tour). Matches MiMo's note;
  worth a defensive guard in a future round.
- r3-M1 verification ran `-t "Test 1"`, which also matched Test 10–17 as substring; the extra
  45 passes are unrelated tests, not a product concern. Test 1's agent + architecture cases
  failed as intended.

VALIDATION DONE | verdict: APPROVED | sha: bd73396a07fa97b60584efe8ef2d8f48086d0a19 | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r4.md
