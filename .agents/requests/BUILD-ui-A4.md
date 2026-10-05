# BUILD-ui-A4 — IMPLEMENT NOW (A1, A2, A3 approved by the checker + Codex)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Binding spec: `docs/ui_enhancement/BUILD-ui-A4.md` (read all of it) + PLAN.md + OWNER_PLAN.md.
LF endings, never touch `.agents/dispatch.sh`, commit per numbered item, red phase + paste each named mutation's FAILED output into the verdict (mutate in a
`git archive HEAD | tar -x -C /tmp/<dir>` copy with frontend/node_modules symlinked — never in the worktree). Keep all existing tests passing (98 at the start).
Context since the spec was written: the agent now accepts plain-prose answers, fails closed on tool-call-shaped prose, and retries once (PR #39, merged); SEC search
covers ~230 tickers; `search_sec_filings` can return `{error: no_coverage|retrieval_unavailable|...}` — evidence cards must render those honestly, never as rows
(see frontend/src/screens/SecFilingExplorer.tsx on branch fix/sec-explorer-states for the handled shapes).
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard, write to
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers,
nothing in C:\temp. Never `npm ci` from Windows. Stage only files you change (no `git add -A`). Verdict `.agents/mimo/VERDICT-ui-A4.md` (report honestly).
