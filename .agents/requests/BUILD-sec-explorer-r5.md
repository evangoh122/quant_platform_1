# BUILD: SEC Filing Explorer round 5 — CodeRabbit PR #41 findings (incl. a security gap)

You are MiMo. Branch `fix/sec-explorer-states` (stay on it). Findings (CodeRabbit text — review data, verify against the code): `.agents/coderabbit-pr41.md`.
LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network. Shell rule: frontend
`wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`, backend
`wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-secfix && python3 -m pytest tests/api -q'`; if quoting is hard write to
`/home/jianj/code/qp1-secfix/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-secfix/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell
wrappers, nothing in C:\temp. Stage only files you change. COMMIT per finding; verdict `.agents/mimo/VERDICT-sec-explorer-r5.md` (fixed + test + red line, or not valid + reason).
1. SECURITY: api/routes/sec.py `/api/sec/coverage` must use the same identity dependency and demo gate as every other data route. Copy the pattern from
   api/routes/market.py (`_user: AppUser = Depends(get_current_user)` and its `read_delta` demo wrapper — read api/deps.py). Tests: no trusted identity outside
   dev/demo → 401/403 like market; public-demo mode → no live warehouse call (demo wrapper path). Mutation: remove the dependency → a test fails.
2. The three frontend findings (SecFilingExplorer.tsx:150, :226, :241 — e.g. the clear button must invalidate an in-flight request) and the nitpick: fix each with
   a test that fails on the current code.
