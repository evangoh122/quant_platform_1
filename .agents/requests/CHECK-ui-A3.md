# CHECK: UI slice A3 — Platform Overview + Architecture & Tests (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Never run git inside a copy.
Shell rule: run checks as `wsl -d Ubuntu -- bash -lc 'cd <dir>/frontend && npx vitest --run'`; if quoting is hard, write the command to
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run exactly `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`.
No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Write .agents/deepseek/VERDICT-ui-A3.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Binding spec: docs/ui_enhancement/BUILD-ui-A3.md (+ PLAN.md, OWNER_PLAN.md). Commit 49882dc. MiMo's verdict is a self-report.
Claude (WSL): vitest 91 passed, tsc clean, build OK.
1. Run every named mutation in BUILD-ui-A3.md yourself; any survivor is blocking. Confirm each "test that must fail on the current code" exists
   and asserts behaviour (not just render).
2. Honesty: every evidence card labelled exactly `Verified snapshot: 2026-10-05`; no live-looking counters, no confidence scores; test-group
   placeholders clearly not fabricated counts; hero copy exactly as OWNER_PLAN.md; no React Flow / old PipelineFlow import.
3. Actions navigate through the shell callback (no invented routes); 360px layout has no horizontal overflow; A1/A2 not regressed.
4. MiMo also edited SignalExplorer.tsx (baseline disclaimer) — in scope? Note: signals are now 1-day horizon (PR #40), not 30-minute; flag any
   copy that says otherwise.
