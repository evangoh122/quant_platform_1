# CHECK: app round 12 (checker: DeepSeek) — Codex re-review survivors

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (symlink frontend/node_modules from the worktree for frontend
mutations). Write .agents/deepseek/VERDICT-app-resilience-round12.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Codex survivors: .agents/codex/VERDICT-app-frontend-deploy-2.md. Round 12 commits 7c5128a, dd10994, bd150e5 (branch slice/app-frontend-deploy).
Claude's mutations (archive copies): max-date reducer → data[0] → vitest 1 failed; banner hard-coded false → 1 failed; `_check_frontend_build`
always True → 2 failed; label reverted to gold_ohlcv_features → 1 failed. `npx vitest --run` → 3 passed.
Verify the four fixes and re-run the mutations yourself; confirm package.json/package-lock.json add only Vitest/testing-library/jsdom dev deps,
`npm ci && npm run build` still works, and nothing from your r11b PASS list regressed.
Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks"; cd frontend && npm ci && npx vitest --run && npm run build.
