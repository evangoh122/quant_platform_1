# CHECK: UI A2 round 3 (checker: DeepSeek)

Read-only on the worktree. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules; run vitest from
WSL. Never run git inside a copy. Write .agents/deepseek/VERDICT-ui-A2-r3.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your round-2 verdict: .agents/deepseek/VERDICT-ui-A2-r2.md (2 blocking: vacuous focus-trap test; no click on "Take a tour" in the rendered
app). Round 3 commit f7984bb (spec .agents/requests/BUILD-ui-A2-r3.md). MiMo's verdict is a self-report. Claude (WSL): vitest 56 passed, tsc clean.
1. Delete the trap listener (CoachMarks.tsx focusin handler) → the focus-trap test must FAIL.
2. Remove the AppShell "Take a tour" click dispatch → the App-level click test must FAIL (both the fresh and the already-seen case).
3. Re-run all nine mutations from round 2 (7 named + 2 TourHost) — each must still fail a test. Confirm no A1 regression; build OK.
