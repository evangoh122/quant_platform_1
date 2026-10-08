# CHECK: UI A3 round 4 — Codex findings (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Never run git inside a copy.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd <dir>/frontend && npx vitest --run'`; if quoting is hard, write to
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell
wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-ui-A3-r4.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Findings: .agents/codex/VERDICT-ui-A3.md (stale v0/AUC copy in ArchitectureEvidence; diagram hidden behind role="img"). Fix c9be7b4 (spec
.agents/requests/BUILD-ui-A3-r4.md). Claude: vitest 97 passed, tsc clean; no "AUC"/"baseline-logreg-v0"/role="img" left in ArchitectureEvidence.tsx.
Mutations, each must fail: put the v0/AUC copy back; swap two diagram nodes; re-add role="img" on the diagram container. Re-run all A3/A1/A2 mutations.
