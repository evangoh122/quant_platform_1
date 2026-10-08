# CHECK: UI A3 round 5 — snapshot labels on every figure (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD` (+ symlink frontend/node_modules). Print the verdict to stdout between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Finding: .agents/codex/VERDICT-ui-A3-r2.md (PlatformOverview.tsx:82,:98 repeated 10,720 / 287M+ without the `Verified snapshot: 2026-10-05` label). Fix 81ab1a7
(spec .agents/requests/BUILD-ui-A3-r5.md). Claude: vitest 98 passed.
Mutation: add an unlabelled "287M+ records" (or "10,720 chunks") to the hero → the new test fails. Every numeric claim on Platform Overview and Architecture &
Tests sits inside a container with the snapshot label. Re-run the A3/A1/A2 mutations; tsc + build.
