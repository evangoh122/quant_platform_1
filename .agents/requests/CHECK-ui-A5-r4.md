# CHECK-ui-A5 round 4 (Codex gpt-5.6-luna, DeepSeek fallback)
Independent checker. Commit bdcd093 fixes the Codex sol finding in `.agents/codex/VERDICT-ui-A5-r3.md` (clearing SymbolPicker must not request an empty symbol). Request:
`.agents/requests/BUILD-ui-A5-r4.md`. NEVER run npm ci/install; don't commit or edit tracked files. Run `cd frontend && npx vitest --run && npx tsc --noEmit && npm run build`.
Verify the useApi guard can't suppress legitimate requests on other screens (it changed frontend/src/hooks/useApi.ts — check every caller), that every screen feeding the picker to an
API is covered, and that tests render production screens. Mutation proof in a /tmp `git archive` copy. One block ===VERDICT START=== Status: APPROVED | CHANGES_REQUESTED, findings with file:line ===VERDICT END===.
