# CHECK: UI A3 round 6 — snapshot labels on every figure (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD` (+ symlink frontend/node_modules). Print the verdict to stdout between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Finding: .agents/codex/VERDICT-ui-A3-r2.md (PlatformOverview.tsx:82,:98 repeated 10,720 / 287M+ without the `Verified snapshot: 2026-10-05` label). Fix 81ab1a7
(spec .agents/requests/BUILD-ui-A3-r5.md). Claude: vitest 98 passed.
Mutation: add an unlabelled "287M+ records" (or "10,720 chunks") to the hero → the new test fails. Every numeric claim on Platform Overview and Architecture &
Tests sits inside a container with the snapshot label. Re-run the A3/A1/A2 mutations; tsc + build.

## Round 6 delta
Your r5 verdict: .agents/deepseek-fallback/VERDICT-ui-A3-r5.md (test climbed to the root). Fix 0b892c4 scopes the check to the nearest evidence card. Claude:
98 passed; appending "287M+ records." to the hero paragraph → 1 failed. Repeat that mutation and one inside a non-evidence card; both must fail.
