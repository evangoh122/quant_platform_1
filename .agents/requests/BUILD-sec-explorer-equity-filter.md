# BUILD: SEC Filing Explorer round 2 — equity filter over ALL covered tickers (owner request 2026-10-06)

You are MiMo. Branch `fix/sec-explorer-states` (stay on it). LF endings, never touch `.agents/dispatch.sh`.
Shell rule: frontend checks `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`;
backend `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix && python3 -m pytest tests/api -q'`. If quoting is hard, write the command to
`/home/jianj/code/qp1-secfix/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. COMMIT per item; verdict `.agents/mimo/VERDICT-sec-explorer-equity-filter.md`.
Owner: "showcase all of the tickers … filter to select equity". Live data now: gold_sec_coverage has 558 tickers, 228 with chunks (n_chunks > 0).
1. Backend: `GET /api/sec/coverage` (new router module, registered in api/main.py like the others) → list of {ticker, cik, n_filings, n_chunks,
   first_filed, last_filed} for rows with n_chunks > 0, sorted by ticker. Read through db/delta_adapter.py's existing warehouse/Spark read path
   (follow how other routes read Delta; constant table name `gold_sec_coverage`; no user input in SQL). Pydantic response model. Honest
   states: table missing → 200 with empty list + status "unavailable" (not a 500). Tests with a fake adapter: rows mapped; n_chunks=0 rows excluded;
   missing table → unavailable.
2. Frontend: replace the free-text box in SecFilingExplorer with a searchable equity selector populated from /api/sec/coverage (type-ahead
   filter by ticker; show filing count and last filed date per option; keyboard accessible; works at 360px). Show "N equities with SEC filings"
   above it. Selecting an equity runs the search. Keep the round-1 states (initial / loading / no coverage / empty / error); if the coverage call
   fails, fall back to the free-text input with a notice.
3. Tests: the selector lists all tickers from a mocked coverage response (e.g. 228 items) and filters on typing; choosing one calls api.chat with
   that ticker; coverage failure → free-text fallback. Named mutations for the checker: endpoint includes n_chunks=0 tickers; selector caps the
   list (e.g. slice(0,16)); fallback removed.
