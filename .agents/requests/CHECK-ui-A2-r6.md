# CHECK: UI A2 round 6 — two-edge spotlight clamp + real 360px test (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Run WSL commands directly as
`wsl -d Ubuntu -- bash -lc '<cmd>'` — never wrap wsl.exe in PowerShell and never write scripts to C:\temp. Never run git inside a copy.
Write .agents/deepseek/VERDICT-ui-A2-r6.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Findings fixed: .agents/codex/VERDICT-ui-A2-r2.md. Commit 9f935fe (spec .agents/requests/BUILD-ui-A2-r6.md). Claude (WSL): vitest 62 passed, tsc clean.
1. Restore the old one-edge clamp (`width = Math.min(raw.width, vw - Math.max(0, raw.left))`) → a test must FAIL (vw=1024, left=1200).
2. Off-screen targets above/below/right/left → width/height never negative; spotlight inside the viewport or the centered fallback.
3. The 360px test really sets innerWidth=360. Re-run the updater, clamp and nine earlier A2 mutations; build OK; no A1 regression.
