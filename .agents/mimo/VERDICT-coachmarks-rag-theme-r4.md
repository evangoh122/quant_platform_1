# VERDICT: coachmarks-rag-theme-r4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
- None. (Builder self-report — per protocol a builder may not approve its own work as the sole verdict; the gate still requires Codex and Claude validation.)

## Non-blocking notes
- B1 root cause fixed in `frontend/src/components/tours/CoachMarks.tsx:68-77`: reset effect now keyed on `[run]` only; `initialScreenRef` captured from `currentScreenRef` on the run start edge. `currentScreen` is no longer a reset dependency.
- `CoachMarks` re-fires `onNavigate(step.navigateTo)` if callers pass unstable `onNavigate`/`steps` identities; `App`/`useTourHost` pass stable identities so production is safe. Defensive guard deferred.
- jsdom does not toggle `<details>` on `summary` click; Test 14's state-tracking case dispatches the real `toggle` event on the `<details>` element (exercises `onToggle`).
- Replay proof attribution corrected: production proof is `App.test.tsx` "opens the tour dialog — even if already seen"; rewritten Test 8 additionally proves replay through the full `App` + `TourHost` stack.

## Checks run
- `npx tsc --noEmit` → pass (0 errors)
- `npx vitest run` → pass (320/320 tests, 16 files)
- `npm run build` → pass (tsc && vite build)
- legacy light-style grep (non-test tsx) → `none`
- `.agents/run-coachmarks-rag-theme-r4-check.sh` via `wsl.exe -d Ubuntu -- bash ...` → pass (boundary/ancestry/SHA/clean-tree checks + `r4 check script finished` sentinel)
- Mutation matrix on isolated `git archive` copies → all 13 mutations fail their target tests (r4-M1..M4 + r3-M1..M9); new Test 16 fails 4/4 on r3 base `6a33f72` (failing-before)

BUILD DONE | status: SUCCESS | sha: bd73396a07fa97b60584efe8ef2d8f48086d0a19 | branch: feat/rag-workbench-theme | evidence: .agents/mimo/EVIDENCE-coachmarks-rag-theme-r4.md
