# BUILD-ui-A3 round 3 (DeepSeek CHANGES_REQUESTED on r2 — absence not asserted)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek/VERDICT-ui-A3-r2.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard,
write to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no
PowerShell wrappers, nothing in C:\temp. Stage ONLY the files you changed (`git add <paths>`, never `git add -A` / `git add .` — last round swept a
Codex plan doc into your commit). COMMIT; verdict `.agents/mimo/VERDICT-ui-A3-r3.md`.
In SignalExplorer.test.tsx add assertions that the rendered disclaimer contains NO AUC text (/\bAUC\b/i) and no model version other than the ones
in the mocked rows (e.g. mock rows with `baseline-logreg-v1-1d` → the page must not contain `baseline-logreg-v0`), in loaded, empty and error states
(empty/error: no model version at all). Paste FAILED output for: hardcoding "hold-out AUC 0.47" in the disclaimer; hardcoding
"model baseline-logreg-v0-2026-10-05".
