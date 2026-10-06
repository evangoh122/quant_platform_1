# BUILD: SEC Filing Explorer — honest empty / no-coverage / initial states (owner-reported bug)

You are MiMo. Branch `fix/sec-explorer-states` (worktree qp1-secfix, off main; stay on it). LF endings, never touch `.agents/dispatch.sh`.
Shell rule: run checks as `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix/frontend && npm ci && npx vitest --run && npx tsc --noEmit && npm run build'`
(npm ci only from WSL, only if node_modules is missing). If quoting is hard, write the command to `/home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`
and run exactly `wsl -d Ubuntu -- bash /home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp.
COMMIT; verdict `.agents/mimo/VERDICT-sec-explorer-states.md`.

Bug (owner saw it on the deployed app): frontend/src/screens/SecFilingExplorer.tsx:74-79 shows "No SEC filing sections yet — silver_sec_sections is
empty …" whenever `rows` is empty. That is false: (a) before any search `result` is null; (b) for a ticker with no processed filings the agent's
`search_sec_filings` tool returns an error/no-coverage result (see agent/tools_retrieval.py ~140-185 for the exact result shape: inspect it);
(c) only a successful search with zero rows is really empty. Also it reads only `tool_calls[0]` — use the first `search_sec_filings` call.
Fix: four distinct states — initial ("Search a ticker to see its SEC filing sections"), loading, no coverage for TICKER ("No SEC filings have been
processed for TICKER yet." — do not name tables), empty result, error. Never claim the whole table is empty.
Tests (frontend, mock api.chat like existing screen tests): initial state text before any search; no-coverage response → no-coverage message naming
the ticker; rows → rows rendered; zero rows → empty message; the old string "silver_sec_sections is empty" never appears. Show each test failing on
main (red phase). Named mutations for the checker: initial state shows the empty message; no-coverage treated as empty; tool_calls[0] used when the
first call is not search_sec_filings.
