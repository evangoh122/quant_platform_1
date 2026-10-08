# CHECK: UI A3 round 3 — absence assertions (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Never run git inside a copy.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd <dir>/frontend && npx vitest --run'`; if quoting is hard, write to
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell
wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-ui-A3-r3.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Your r2 verdict: .agents/deepseek/VERDICT-ui-A3-r2.md. Fix fa88f22. Claude: 95 passed; "hold-out AUC 0.47" appended to the disclaimer → 3 failed.
Run both of your surviving r2 mutations (hardcoded AUC; hardcoded `model baseline-logreg-v0-2026-10-05`) — each must fail now; re-run all A3 r1, A1 and
A2 mutations; tsc + build.
