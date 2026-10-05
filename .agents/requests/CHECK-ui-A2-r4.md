# CHECK: UI A2 round 4 — Codex findings (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules. Run WSL commands directly as
`wsl -d Ubuntu -- bash -lc '<cmd>'` — never wrap wsl.exe in PowerShell and never write scripts to C:\temp (Windows Defender blocks that).
Never run git inside a copy. Write .agents/deepseek/VERDICT-ui-A2-r4.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED"
or "Status: CHANGES_REQUESTED", file:line.
Findings fixed: .agents/codex/VERDICT-ui-A2.md (close side effect inside the setIndex updater; spotlight not clamped to the viewport).
Commit 77d3b63; spec .agents/requests/BUILD-ui-A2-r4.md. MiMo's verdict is a self-report. Claude (WSL): vitest 58 passed, no
"Cannot update a component" warning, tsc clean.
1. Mutations, each must fail a test: move handleClose back into the updater; remove the clamp; remove the StrictMode wrapper from the
   once-only test (it must still be meaningful — if it passes without StrictMode, check it would catch a double call).
2. Clamp: off-screen and wider-than-viewport targets at 360px; tooltip in viewport; scrollIntoView respects reduced motion.
3. Re-run the nine earlier A2 mutations; no A1 regression; build OK.
