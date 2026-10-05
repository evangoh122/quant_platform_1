# CHECK: UI A4 round 3 (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD` (+ symlink frontend/node_modules; NEVER npm ci/install). Print the verdict to stdout between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r2 verdict: .agents/deepseek-fallback/VERDICT-ui-A4-r2.md. Fix 4d5cfd8. Claude: vitest 116 passed. Claude spot check — SURVIVOR: ToolCallCard.tsx:37 `if (noteId) {` → `if (true) {`
(badge shows "Note undefined" for a save without note_id) → 116/116 still pass. Check whether a test renders the ToolCallCard badge for a save_research_note result without
note_id at all.
Re-run your three r2 mutations (error rows counted as sources; "Note saved" without note_id — both the badge at :37 and the body at :84; rendered model confidence) and list any
survivor. Re-run the earlier A4 mutations and A1–A3 regressions; tsc + build.
