# CHECK-viz-V1 (Codex gpt-5.6-luna, DeepSeek fallback)
Independent checker. Check commit d8bdac1 (V1 of docs/ui_enhancement/PLAN-V-visuals.md; request `.agents/requests/BUILD-viz-V1.md`). NEVER run npm ci/install; don't commit or
edit tracked files. Run `cd frontend && npx vitest --run && npx tsc --noEmit && npm run build`. Verify: tests render the production screens with fetch mocks that match api/schemas.py
exactly; null → gap (never zero); IV not charted as a series; "Baseline model probability" wording; coverage top-25 after sorting; empty/error states; accessible table fallback and
keyboard tooltip; dark mode; no new dependency. Do your own mutation proofs in a /tmp `git archive` copy. Output one block ===VERDICT START=== Status: APPROVED | CHANGES_REQUESTED,
findings with file:line ===VERDICT END===.
