# BUILD: SEC Filing Explorer round 4 (Codex CHANGES_REQUESTED)

You are MiMo. Branch `fix/sec-explorer-states` (stay on it). Read `.agents/codex/VERDICT-sec-explorer.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is
hard, write to `/home/jianj/code/qp1-secfix/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`. No
.ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT; verdict `.agents/mimo/VERDICT-sec-explorer-r4.md` with
FAILED output per mutation (mutate in a /tmp `git archive` copy).
1. Handle every error shape the tool returns — read agent/tools_retrieval.py (e.g. lines ~140-210: `no_coverage`, `retrieval_unavailable` with
   message/ticker, ticker_required, any others). `retrieval_unavailable` → an honest "SEC search is temporarily unavailable" error state (retry
   button), not rows. Any unknown `{error: …}` → generic error state, never rendered as a result row. Tests with the real shapes. Mutation: drop the
   retrieval_unavailable branch → fails.
2. Stale responses: track a request id (or AbortController) so only the latest selection's response is applied; test A then B where A resolves last →
   B's results stay shown. Mutation: remove the guard → fails.
