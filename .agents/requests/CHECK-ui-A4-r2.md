# CHECK: UI A4 round 2 (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD` (+ symlink frontend/node_modules — NEVER run `npm ci`/`npm install`: it broke node_modules last time).
Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r1 verdict: .agents/deepseek-fallback/VERDICT-ui-A4.md (5 findings). Fixes d7e0400..c50e3bf (spec .agents/requests/BUILD-ui-A4-r2.md). Claude: vitest 115 passed, tsc clean;
error rows rendered as sources (ProvenanceGrid) → 1 failed.
Re-run each of your r1 mutations and the five spec mutations (error rows as SourceCards; error rows counted; ok:false → success on the tool card; note saved without note_id;
agent-unavailable hidden with no tool calls) — each must fail. Confirm the required follow-up rendering matches docs/ui_enhancement/BUILD-ui-A4.md. Re-run the A4 r1 named
mutations and A1–A3 regressions; tsc + build.
