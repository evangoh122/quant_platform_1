# BUILD: SEC Filing Explorer round 3 (DeepSeek CHANGES_REQUESTED — three named mutations survive)

You are MiMo. Branch `fix/sec-explorer-states` (stay on it). Read `.agents/deepseek/VERDICT-sec-explorer.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: frontend `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`;
backend `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix && python3 -m pytest tests/api -q'`. If quoting is hard, write to
`/home/jianj/code/qp1-secfix/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`. No .ps1/.bat, no
PowerShell wrappers, nothing in C:\temp. Stage only files you change (no `git add -A`). Tests only unless a test proves the code wrong. COMMIT;
verdict `.agents/mimo/VERDICT-sec-explorer-r3.md` with each mutation's FAILED output (mutate in a `git archive HEAD | tar -x -C /tmp/<dir>` copy).
1. Restore a frontend test: a search whose search_sec_filings result is `{error: 'no_coverage'}` (use the exact shape the agent tool returns —
   check agent/tools_retrieval.py) renders "No SEC filings have been processed for TICKER yet." and NOT the generic empty message.
   Mutation `isNoCoverage = false` (SecFilingExplorer.tsx:134) must fail.
2. A mocked response whose tool_calls are [some_other_tool, search_sec_filings(rows…)] renders the rows from the search_sec_filings call.
   Mutation `result.tool_calls[0]` (SecFilingExplorer.tsx:129) must fail.
3. Backend: test the real `_read_coverage_rows` with a fake warehouse cursor/Spark that records the SQL and returns rows including n_chunks = 0;
   assert those rows are excluded (by the SQL WHERE clause or by filtering) and the SQL has no user values. Mutation: remove `WHERE n_chunks > 0`
   (api/routes/sec.py:44) must fail.
