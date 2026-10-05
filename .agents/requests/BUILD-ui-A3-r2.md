# BUILD-ui-A3 round 2 (DeepSeek CHANGES_REQUESTED)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek/VERDICT-ui-A3.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: run checks as `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`;
if quoting is hard, write to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`.
No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp. COMMIT; verdict `.agents/mimo/VERDICT-ui-A3-r2.md`.
1. SignalExplorer.tsx:38-41 — do not hardcode a model version or AUC (the baseline was redesigned to a 1-day horizon in PR #40 and will be
   republished as baseline-logreg-v1-1d). Show the model_version(s) and horizon from the loaded signal rows when present, and the fixed text
   "Baseline demonstration — no validated trading edge claimed." Never show an AUC that is not in the data.
2. Test that mounts SignalExplorer (mock the API like the existing screen tests) and asserts the "no validated trading edge claimed" caveat is
   visible in the loaded, empty and error states, and that the model_version from the mocked rows is shown. Paste FAILED output with the caveat
   replaced by "This is a validated trading signal with a proven statistical edge." (in a `git archive HEAD | tar -x -C /tmp/<dir>` copy).
