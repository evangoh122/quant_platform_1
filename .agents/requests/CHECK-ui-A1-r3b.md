# CHECK: UI A1 round 3b — contrast test reads real tokens (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Never run git inside a copy.
Shell rule: if a command needs quoting, write it to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Write .agents/deepseek/VERDICT-ui-A1-r3b.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r3 verdict: .agents/deepseek/VERDICT-ui-A1-r3.md (contrast test vacuous). Fix commit 9b97fa1. Claude (WSL): vitest 77 passed, tsc clean,
build OK; `--text-muted: #94a3b8` + `--warning: #d97706` in index.css → 2 failed.
1. Repeat that mutation, plus dark-mode token mutations (if dark blocks exist), each must fail.
2. Re-run every other A1 r3 mutation (initial focus, aria-modal/trap, collapsed accessible names, min-w-[400px], remove "Options Analytics")
   and all A2 mutations; none may survive. Note: tests dropped from 79 to 77 — confirm only the vacuous literal "mutation" cases were removed.
