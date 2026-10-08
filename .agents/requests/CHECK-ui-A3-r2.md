# CHECK: UI A3 round 2 — SignalExplorer caveat (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Never run git inside a copy.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd <dir>/frontend && npx vitest --run'`; if quoting is hard, write to
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell
wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-ui-A3-r2.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Your r1 verdict: .agents/deepseek/VERDICT-ui-A3.md. Fix b9c3c59 (spec .agents/requests/BUILD-ui-A3-r2.md). Note b9c3c59 also (accidentally) committed
docs/data/PLAN-massive-incremental.md — a Codex plan doc, not code; ignore it. Claude (WSL): vitest 95 passed; caveat replaced by "validated" wording → 3 failed.
1. Repeat that mutation; also hardcode a model version/AUC back → must a test fail? (the spec forbids showing an AUC not in the data).
2. Re-run every A3 named mutation from round 1 and all A1/A2 mutations; tsc + build.
