# Build: fix cross-screen tour reset (r4)

Builder: MiMo. Base: r3 commit `6a33f723a399681d5f1294044a401a7f4a53af0b` on `feat/rag-workbench-theme`. Findings: `.agents/deepseek/VERDICT-coachmarks-rag-theme-r3.md` (read it fully).
Commit on this branch only; no backend/API/dependency change; no deploy.

## Blocking bug (B1)
`frontend/src/components/tours/CoachMarks.tsx:68-75`: the effect `[run, currentScreen]` calls `setIndex(0)` and overwrites `initialScreenRef` every time the tour navigates
(the navigation changes `currentScreen`). Result: steps after a `navigateTo` step are unreachable (tour loops to step 1) and closing restores the destination screen, not the start.
Fix: reset index / capture opener / capture `initialScreenRef` ONLY on the false→true transition of `run` (e.g. `prevRunRef` or an effect keyed on `[run]` that reads the latest
`currentScreen` via a ref). Do not reintroduce a dependency on `currentScreen` for the reset.

## Required tests (render real components; no vacuous harness)
1. A stateful test (real `App`, or a harness whose `onNavigate` really updates `currentScreen` via `useState`) that proves: (a) the Application tour advances past EVERY `navigateTo`
   step to the last step with each target visible/non-zero; (b) the step counter increases monotonically (never returns to "Step 1" after navigating); (c) closing/finishing/skipping
   calls `onNavigate(<screen the user started on>)` and the user ends on that screen. Cover starting from a non-default screen (e.g. started on `signals`).
2. Replace the static-prop `Test 16` in `frontend/src/components/tours/coachmarks-r2.test.tsx` (~792-825) with the stateful version (delete the vacuous one).
3. Convert the source-scan tests (`Test 11`, `Test 13`, `Test 14`, first `Test 12` case) into rendered DOM/ARIA assertions (render the component; assert `aria-expanded`/`aria-controls`
   ids exist in the DOM, skip link is the first focusable and targets `#main-content`, etc.) — keep any extra source scan only as an addition.
4. Add a rendered test that the mobile drawer root has the `inert` attribute on the background while open and not when closed.
5. Fix evidence accuracy: the replay-ignores-seen-keys proof is `App.test.tsx` "opens the tour dialog … even if already seen", not `Test 8`; make `Test 8` either assert something real
   about replay (render full `App`/`TourHost`) or drop the misleading claim. Remove the sentinel text `r2 check script finished` from `.agents/run-coachmarks-rag-theme-r3-check.sh` (rename to r4 script
   `.agents/run-coachmarks-rag-theme-r4-check.sh` with the new SHA placeholder pattern as r3, with `export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"` and /mnt/ boundary assertion).
6. Use a descriptive commit message (e.g. `fix(tours): reset only on run start; restore starting screen`), not `fix:`.

## Mutations that MUST make a test fail (isolated `git archive` copies; never git in a cp -r copy)
- M1 put `currentScreen` back into the reset effect deps → stateful test fails.
- M2 overwrite `initialScreenRef` on every render → restore-screen test fails.
- M3 remove `inert` from the drawer → new test fails.
- M4 remove `aria-controls` from one evidence disclosure → rendered test fails.
- Re-run all r3 mutations M1-M9 from `.agents/deepseek/VERDICT-coachmarks-rag-theme-r3.md` (hardcode `tour:'application'`, seen-key replay, 44px rule, stale keys, blue badge, aria-expanded, skip link, Escape, restore) and show each still fails a test.

## Acceptance
`cd frontend && npx tsc --noEmit && npx vitest run && npm run build` pass; legacy-class grep returns none. Evidence file `.agents/mimo/EVIDENCE-coachmarks-rag-theme-r4.md`. Commit. End with exactly:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/rag-workbench-theme | evidence: .agents/mimo/EVIDENCE-coachmarks-rag-theme-r4.md`
