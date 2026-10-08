# BUILD-ui-A4 round 3 (checker CHANGES_REQUESTED — three gaps)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek-fallback/VERDICT-ui-A4-r2.md`. LF endings, never touch `.agents/dispatch.sh`, NEVER run npm ci.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard, use
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`. No PowerShell, nothing in C:\temp. Stage only files you change. COMMIT; verdict
`.agents/mimo/VERDICT-ui-A4-r3.md` with FAILED output per mutation (/tmp `git archive` copy). Tests may only render production components.
1. ToolCallCard.tsx:63-69 — test asserts the displayed source count equals the number of NON-error rows (fixture: 2 good rows + 1 no_coverage row → "2 sources").
   Mutation: count all rows → fails.
2. ToolCallCard.tsx:35-38 — a successful save_research_note result WITHOUT note_id must not say "Note saved" (show e.g. "Save not confirmed"). Fix the code and test both
   cases. Mutation: drop the note_id check → fails.
3. Add a test that the rendered answer/evidence never shows a model confidence value: if the API response contains a `confidence`/`score` field, it is not displayed
   (assert no /confidence/i text and no % score). Mutation: render response.confidence → fails.
