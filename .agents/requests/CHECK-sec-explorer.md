# CHECK: SEC Filing Explorer — honest states + equity filter over all covered tickers (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (+ symlink frontend/node_modules for frontend). Never run git inside a copy.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd <dir>/frontend && npx vitest --run'` / `wsl -d Ubuntu -- bash -lc 'cd <dir> && python3 -m pytest tests/api -q'`;
if quoting is hard, write to `/home/jianj/code/qp1-secfix/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-sec-explorer.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Branch fix/sec-explorer-states (off main). Specs: .agents/requests/BUILD-sec-explorer-states.md, BUILD-sec-explorer-equity-filter.md. Commits
e5526a3, f4cac23, 65d29ee, 2ec39ab. MiMo verdicts are self-reports. Claude: frontend 14 passed, tsc clean; tests/api 324 passed; LIVE
`GET /api/sec/coverage` → 200, 228 equities with real counts/dates.
1. Run every named mutation in both specs (initial state shows the empty message; no-coverage treated as empty; tool_calls[0] used when the first call
   is not search_sec_filings; endpoint includes n_chunks=0 tickers; selector caps the list; fallback removed) — each must fail a test.
2. SQL safety in api/routes/sec.py (constant table, no user input); missing table → 200 + "unavailable" (not 500).
3. Selector: accessible (label, keyboard), works with 228+ items, 360px; the old "silver_sec_sections is empty" copy is gone everywhere.
