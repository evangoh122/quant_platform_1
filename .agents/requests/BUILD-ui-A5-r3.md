# BUILD-ui-A5 round 3 (Codex sol CHANGES_REQUESTED)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/codex/VERDICT-ui-A5.md` and docs/ui_enhancement/BUILD-ui-A5.md. LF endings, never touch `.agents/dispatch.sh`, NEVER run npm
ci/install. Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard, use
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`. No PowerShell, nothing in C:\temp. Stage only files you change. COMMIT per item; verdict
`.agents/mimo/VERDICT-ui-A5-r3.md` with FAILED output per mutation (/tmp `git archive` copy). Tests may only render production components with mocks matching the real backend contracts
(api/schemas.py ChatRequest has only `message` and `write_authorization` — the agent symbol scope must NOT add a request field; scope the question text or the UI only).
1. ResearchAgent.tsx:24 — add the shared SymbolPicker as the agent's symbol scope (spec item 4): the selected symbol is shown as context and used to prefill/scope the suggested questions
   (e.g. "What risks does {SYMBOL} describe in its latest 10-K?"); the API call stays `api.chat(message)`. Tests: picking AMD changes the suggested questions/prefill to AMD; the chat request body
   contains only `message`. Mutation: ignore the picked symbol → fails.
2. SymbolPicker.tsx:60 — a valid-format ticker from `?symbol=` that is not in the options list is preserved (not replaced by NVDA) and shows the no-coverage message. Test `?symbol=ZZZZ`.
   Mutation: fall back to the default → fails.
3. MarketDashboard.tsx:46 — anchor 1M/3M/6M/1Y ranges to the latest returned event_date, not Date.now(). Test with data ending 2026-09-02 and a mocked "now" of 2026-10-06 → 1M shows August–
   September points. Mutation: use Date.now() → fails.
