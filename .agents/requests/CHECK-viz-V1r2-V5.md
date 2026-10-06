# CHECK-viz V1 round 2 + V5 Positioning (Codex gpt-5.6-luna — you ARE the DeepSeek CHECK step; no DeepSeek verdict is required)
Independent checker on branch feat/ui-visuals. Don't commit or edit tracked files; NEVER npm ci/install.
A. V1 r2 (7029352): stacked put/call bars per `.agents/requests/BUILD-viz-V1-r2.md`. Check a null put does NOT place the call segment as if put were 0 at a fabricated height
   (decide: call drawn from baseline with a visible "put missing" marker, or the whole bar treated as incomplete — either is fine if honest and tested).
B. V5 (1ce6729, 9cb8cfc, 4f37c30) per `.agents/requests/BUILD-viz-V5.md`: `/api/positioning/cot` validation, parameterized SQL, auth dependency, PIT filter on information_available_ts /
   release_ts (no future releases), typed schemas, Envelope/freshness; Positioning screen series/gaps, both dates on tiles, contract sort, snapshot-only options stats; nav entry.
Run `cd frontend && npx vitest --run && npx tsc --noEmit && npm run build` and `python -m pytest -q tests/api/test_positioning.py tests/api -x --timeout 300`. Do your own mutation proofs in
a /tmp `git archive` copy for A and B. One block ===VERDICT START=== Status: APPROVED | CHANGES_REQUESTED, findings with file:line ===VERDICT END===.
