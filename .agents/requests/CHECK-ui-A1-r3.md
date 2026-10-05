# CHECK: UI A1 round 3 — Codex A1 findings (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Never run git inside a copy.
Shell rule: if a command needs quoting, write it to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Write .agents/deepseek/VERDICT-ui-A1-r3.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Findings to fix: .agents/codex/VERDICT-ui-A1.md; spec .agents/requests/BUILD-ui-A1-r3.md (6 items). Commits 1f07c83..0ee1694. MiMo verdict is a
self-report. Claude (WSL): vitest 79 passed, tsc clean, build OK.
Claude's concern: b73dfce "use hardcoded token values" in the contrast test — if the test no longer reads the real CSS tokens, changing
`--text-muted`/`--warning` in the stylesheet to a low-contrast colour will NOT fail it (vacuous). Mutate the CSS token value in the copy and report.
Each named mutation in BUILD-ui-A1-r3.md must fail a test: no focus move on initial render; aria-modal + focus trap; collapsed sidebar keeps
full accessible names; `min-w-[400px]` on the shell root → overflow test fails; remove "Options Analytics" from NAV_GROUPS → nav test fails;
low-contrast token → contrast test fails; Strategy Lab placeholder + environment badge present. All A2 tests still pass.
