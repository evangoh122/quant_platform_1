# BUILD-ui-A4 round 2 (checker CHANGES_REQUESTED + Claude spot check)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek-fallback/VERDICT-ui-A4.md` and the spec docs/ui_enhancement/BUILD-ui-A4.md. LF endings,
never touch `.agents/dispatch.sh`. Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`;
if quoting is hard, write to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no
PowerShell wrappers, nothing in C:\temp, NEVER run `npm ci` (node_modules is installed). Stage only files you change. COMMIT per item; verdict
`.agents/mimo/VERDICT-ui-A4-r2.md` with FAILED output per mutation (mutate in a /tmp `git archive` copy).
Tests may only call production components; never copy their logic into a test (see memory of past failures).
1. ProvenanceGrid.tsx:43-45 — render row-level errors honestly (no_coverage "No SEC filings processed for TICKER yet", retrieval_unavailable "SEC search temporarily
   unavailable", ticker_required, unknown → generic) instead of silently dropping them; never as source cards. ToolCallCard.tsx:13-18 — count only non-error rows as
   sources. Mutation: render error rows as SourceCards → test fails; count error rows → test fails.
2. ToolCallCard.tsx:10-12 — `ok:false` must show a failed badge on the tool card itself; test asserts the card (not ExecutionTrace). Mutation: ok:false → success → fails.
3. ToolCallCard.tsx:27-31 and ResearchAgent.tsx:92-95 — claim "note saved" only when the write result has a note_id; otherwise show the honest state. Mutation: drop the
   note_id requirement → fails.
4. EvidencePanel.tsx:12-21 — show the agent-unavailable state even when there are no tool calls. Mutation: hide it → fails.
5. Add the required follow-up rendering from BUILD-ui-A4.md (read which follow-up the spec requires and implement exactly that) with a test.
