# CHECK: SEC Filing Explorer round 3 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (+ symlink frontend/node_modules). Never run git inside a copy.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd <dir>/frontend && npx vitest --run'` / `... && python3 -m pytest tests/api -q'`; if quoting is hard, write to
`/home/jianj/code/qp1-secfix/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`. No .ps1/.bat, no
PowerShell wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-sec-explorer-r3.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r2 verdict: .agents/deepseek/VERDICT-sec-explorer.md (3 surviving mutations). Fix b2d1438. Claude: frontend 16 passed, tests/api 325 passed;
removing `WHERE n_chunks > 0` → 1 failed.
Re-run your three surviving mutations (isNoCoverage=false; tool_calls[0]; no n_chunks filter) — each must fail — and all the other named mutations
from both specs.
