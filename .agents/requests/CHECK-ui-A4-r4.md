# CHECK: UI A4 round 4 — conversation follow-ups + per-stage trace (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies (+ symlink frontend/node_modules; NEVER npm ci/install). Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Codex sol findings: .agents/codex/VERDICT-ui-A4.md (invented follow_ups field; global anyFailed in ExecutionTrace). Fix 745ec05 (spec .agents/requests/BUILD-ui-A4-r4.md). Claude: vitest 121
passed, tsc clean, no `follow_ups` left in src.
1. Mutations, each must fail: keep only the latest turn (no conversation history); a failed follow-up drops earlier turns or the typed question; restore a global anyFailed for the Retrieval
   stage. Mocks must match api/schemas.py ChatResponse exactly (no invented fields) — check every mock in the A4 tests.
2. ExecutionTrace.tsx:41-45 — the Response stage is 'failed' when ANY tool call failed. With a successful search + failed note write the answer still exists; judge whether Response should be
   'complete' (answer delivered) with only the Write/Tool stage failed — blocking if it misrepresents the observed outcome per BUILD-ui-A4.md item 3.
