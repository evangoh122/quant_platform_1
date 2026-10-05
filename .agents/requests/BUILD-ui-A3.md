# BUILD-ui-A3 — IMPLEMENT NOW (A1 and A2 approved by DeepSeek + Codex)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Binding spec: `docs/ui_enhancement/BUILD-ui-A3.md` (read all of it) +
docs/ui_enhancement/PLAN.md + OWNER_PLAN.md. LF endings, never touch `.agents/dispatch.sh`, commit per numbered item, red phase + paste each
named mutation's FAILED output into the verdict (mutations in a `git archive HEAD | tar -x -C /tmp/<dir>` copy with frontend/node_modules
symlinked — never in the worktree). Keep all existing A1/A2 tests passing (77 at the start).
Shell rule: run frontend checks with `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`.
If a command needs quoting, write it to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Never `npm ci` from Windows. Verdict `.agents/mimo/VERDICT-ui-A3.md` (report honestly what is and is not done).
