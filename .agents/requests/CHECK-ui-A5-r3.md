# CHECK-ui-A5 round 3 (Codex gpt-5.6-luna, DeepSeek fallback)
You are the independent checker. Branch feat/ui-enhancement; commits 36aae81, 763590b, 24fa727 fix the 3 findings in `.agents/codex/VERDICT-ui-A5.md`
(request: `.agents/requests/BUILD-ui-A5-r3.md`). NEVER run npm ci/install; do not commit; do not edit tracked files. Run `cd frontend && npx vitest --run && npx tsc --noEmit && npm run build`.
For each finding: confirm it is fixed in production code, confirm the test renders the production component with real-contract mocks (ChatRequest has only `message`/`write_authorization`),
and do a mutation proof in a /tmp `git archive` copy (revert the fix → named test FAILS). Also check for regressions in A1–A4 behaviour.
Output exactly one block:
===VERDICT START===
Status: APPROVED | CHANGES_REQUESTED
findings with file:line evidence; mutation results
===VERDICT END===
