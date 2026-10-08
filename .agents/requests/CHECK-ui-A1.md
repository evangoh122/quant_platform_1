# CHECK: UI slice A1 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (symlink frontend/node_modules from the worktree). Write
.agents/deepseek/VERDICT-ui-A1.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Spec: .agents/requests/BUILD-ui-A1.md (+ docs/ui_enhancement/PLAN.md, OWNER_PLAN.md). Commit b5b71bc. MiMo's self-report is NOT evidence.
Claude (WSL): vitest 14 passed; `npm run build` OK.
Verify every numbered item and the spec's named mutations (each must FAIL a test); internal screen ids / API calls unchanged (diff
frontend/src/api); navigation groups and labels match the owner plan; mobile drawer + keyboard navigation + visible focus; Lakebase degradation
banner still driven by /api/health; design tokens used (no hard-coded colours in new components); empty/error/stale state components accessible
(roles / aria-live). No new heavy dependencies (React Flow, LangGraph, DuckDB). Run (WSL if UNC blocks):
`cd frontend && npm ci && npx vitest --run && npx tsc --noEmit && npm run build`.
