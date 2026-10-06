# REVIEW: UI slice A5 — SymbolPicker + market chart (reviewer: Codex sol)

Branch feat/ui-enhancement. A5 commits 6b30a27 (r1, incl. the post-merge navigation-test fix for PR #41's SEC Explorer), eb69f8e, 2ae8ec9, 1b3dc77 (r2). Spec docs/ui_enhancement/BUILD-ui-A5.md
(+ .agents/requests/BUILD-ui-A5*.md). Checker luna: r1 CHANGES_REQUESTED (URL param overwritten; null→0 chart data; SEC fallback typed tickers; 3 surviving mutations) → r2 APPROVED
(.agents/deepseek-fallback/VERDICT-ui-A5-r2.md). Claude: vitest 162 passed, tsc clean; spot checks (`inList = true`, null closes zero-filled) each fail a test.
Run `cd frontend && npx vitest --run && npx tsc --noEmit && npm run build` (NEVER npm ci/install). Mutation proofs only in /tmp via `git archive HEAD` (+ symlink frontend/node_modules).
Focus: no fabricated or live-looking data in the chart; symbol state (URL, recent symbols, localStorage failures); SEC Research keeps #41's coverage selector and honest states; mocks match the real
backend contracts; 360px; accessibility; A1–A4 not regressed. Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line.
Do not edit files.
