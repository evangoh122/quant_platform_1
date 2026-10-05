# CHECK: UI A2 round 5 — the once-only StrictMode test (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Run WSL commands directly as
`wsl -d Ubuntu -- bash -lc '<cmd>'` — never wrap wsl.exe in PowerShell and never write scripts to C:\temp. Never run git inside a copy.
Write .agents/deepseek/VERDICT-ui-A2-r5.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r4 verdict: .agents/deepseek/VERDICT-ui-A2-r4.md (missing once-only test). Round 5 commit c43e21c. Claude (WSL): vitest 60 passed, tsc clean.
1. Move handleClose back inside the setIndex updater (the exact mutation in BUILD-ui-A2-r5.md) → the new test must FAIL.
2. Re-run the clamp mutation and the nine earlier A2 mutations; build OK; no A1 regression.
