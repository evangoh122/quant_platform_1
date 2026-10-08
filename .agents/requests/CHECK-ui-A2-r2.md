# CHECK: UI A2 round 2 — coach marks and tours (checker: DeepSeek)

Read-only on the worktree. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules; run vitest from
WSL. Never run git inside a copy. Write .agents/deepseek/VERDICT-ui-A2-r2.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.

Your round-1 verdict: .agents/deepseek/VERDICT-ui-A2.md (7 blocking). Spec: .agents/requests/BUILD-ui-A2-r2.md. Commits b45b2a6..4deae4d.
MiMo's verdict is a self-report; it calls 2 mutations "N/A — deleted hook code". They are NOT N/A: apply "remove completion write" and
"remove reduced-motion guard" to TourHost.tsx (the path the app runs). Claude (WSL): vitest 54 passed, tsc clean.

Re-run all 7 named mutations from BUILD-ui-A2.md on the production path plus the two TourHost mutations; every one must FAIL a test.
Item 6: the spec requires a test that CLICKS "Take a tour" in the rendered app and sees the dialog (including after the tour was marked
seen) — a test that only dispatches `qp-tour-request` directly does not satisfy it. Item 5: the focus-trap test must exercise Tab/Shift+Tab
(or equivalent focus leaving the card) and assert focus stays inside. Confirm no A1 regression.
