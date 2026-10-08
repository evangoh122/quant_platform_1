# CHECK: UI slice A4 — Research Agent redesign + evidence cards (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD` (+ symlink frontend/node_modules). Print the verdict to stdout between ===VERDICT START=== /
===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Binding spec: docs/ui_enhancement/BUILD-ui-A4.md (+ .agents/requests/BUILD-ui-A4.md context) + PLAN.md + OWNER_PLAN.md. Commit 5e47381. MiMo's verdict is a self-report.
Claude: vitest 110 passed, tsc clean, build OK. Claude spot check — SURVIVING MUTATION: in src/components/evidence/ProvenanceGrid.tsx change
`if (isSecRow(row) && !hasError(row))` to `if (isSecRow(row))` (error rows like {error:'no_coverage'} rendered as SEC source cards) → ResearchAgent tests still 12/12 pass.
1. Run every named mutation in docs/ui_enhancement/BUILD-ui-A4.md plus the one above; list every survivor (blocking).
2. Contract: still calls api.chat(message) and the existing /api/agent/chat shape; no raw JSON in the default view; suggested questions, empty-input blocking, disabled send
   while submitting, question preserved on failure; tool-level and row-level error shapes (no_coverage, retrieval_unavailable, ticker_required, unknown) rendered honestly,
   never as sources; developer details hidden by default; no fabricated confidence scores. A1–A3 not regressed; 360px; accessibility.
