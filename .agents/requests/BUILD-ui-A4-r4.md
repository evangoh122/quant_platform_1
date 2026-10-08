# BUILD-ui-A4 round 4 (Codex sol CHANGES_REQUESTED)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/codex/VERDICT-ui-A4.md`. LF endings, never touch `.agents/dispatch.sh`, NEVER run npm ci/install.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard, use
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`. No PowerShell, nothing in C:\temp. Stage only files you change. COMMIT; verdict
`.agents/mimo/VERDICT-ui-A4-r4.md` with FAILED output per mutation (/tmp `git archive` copy). Tests may only render production components with mocks that match the REAL backend
contract (api/schemas.py ChatResponse) — never add fields the backend does not return.
1. Remove the invented `follow_ups` field from frontend/src/api/types.ts and ResearchAgent.tsx. "Follow-ups" in BUILD-ui-A4.md item 2 means the conversation: after an answer the user can
   ask a follow-up question; the screen keeps the session's previous question/answer turns (client-side list, newest last, each with its own evidence), and each turn is still a plain
   `api.chat(message)` call — no API change. Tests: two consecutive questions → both turns visible in order with their own answers/evidence; a failed follow-up keeps earlier turns and
   preserves the new question text. Mutation: replace the history with only the latest turn → fails.
2. ExecutionTrace.tsx:18-37 — derive each stage's status from ITS OWN tool calls (retrieval stage from retrieval tools, write stage from write tools, …); a successful search_sec_filings
   followed by a failed save_research_note shows Retrieval = Complete and Write = Failed. Test exactly that. Mutation: restore the global anyFailed → fails.
