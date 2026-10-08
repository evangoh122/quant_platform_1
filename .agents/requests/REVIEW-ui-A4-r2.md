# REVIEW round 2: UI slice A4 — Research Agent redesign + evidence cards (reviewer: Codex sol)

Branch feat/ui-enhancement. A4 commits 5e47381 (r1), d7e0400..c50e3bf (r2), 4d5cfd8 (r3), 583e993 (Claude tiny fix: tool-card badge assertion). Spec docs/ui_enhancement/BUILD-ui-A4.md
(+ .agents/requests/BUILD-ui-A4*.md). Checker (Codex luna, DeepSeek out of balance): r1, r2, r3 CHANGES_REQUESTED → r3b APPROVED (.agents/deepseek-fallback/VERDICT-ui-A4-r3b.md).
Claude: vitest 116 passed, tsc clean, build OK; spot checks — error rows as sources and the note_id badge mutations both fail now.
Run `cd frontend && npx vitest --run && npx tsc --noEmit && npm run build` (NEVER npm ci/install — node_modules is present; npm ci broke it once). Mutation proofs only in /tmp via
`git archive HEAD` (+ symlink frontend/node_modules). Focus: /api/agent/chat contract unchanged; honest states for every tool/row error shape (no_coverage, retrieval_unavailable,
ticker_required, unknown) and unavailable agent; "note saved" only with note_id; no fabricated confidence; developer details hidden by default; A1–A3 not regressed; 360px; accessibility.
Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line. Do not edit files.

## Round 2 delta
Your r1 verdict: .agents/codex/VERDICT-ui-A4.md (invented follow_ups field; global anyFailed in ExecutionTrace). Fixes 745ec05 (follow-ups = the session's conversation turns, each a plain
api.chat call; per-stage retrieval/tool status) and c0b8651 (Claude tiny fix: Response stage = complete when the agent answered, failed when unavailable). Checker luna: r4 CHANGES_REQUESTED
(Response stage) → r4b APPROVED (.agents/deepseek-fallback/VERDICT-ui-A4-r4b.md). Claude: 122 passed. Confirm both findings are fixed and mocks match api/schemas.py ChatResponse.
