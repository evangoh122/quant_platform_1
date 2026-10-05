# CHECK: app rounds 9–10 (checker: DeepSeek) — fixes for Codex's final review

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-app-resilience-round9-10.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Codex's findings: .agents/codex/VERDICT-app-frontend-deploy.md (7 + 2 non-blocking + requirements-test survivor). Requests: BUILD-app-resilience-round9.md,
-round10.md. Commits 3b9c840..4a34f8a (r9), a30557d (r10). MiMo's self-reports are NOT evidence.
Claude (WSL, shell with credential-looking env vars set): `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → 1548 passed, 0 failed.
Verify EACH Codex finding is fixed with a test that fails on the old code, re-running Codex's mutations:
1. Lakebase pool opened before wait; token-mint subprocess timeout; fake models open/closed (mutation: don't open → FAIL).
2. Warehouse concurrency truly bounded: slot released only when the worker finishes; connect+liveness inside the timeout; test counts concurrent
   executions (mutation: drop semaphore acquire → FAIL).
3. smoke_app.py requires real built HTML + hashed asset 200 (mutation: accept JSON hint → FAIL).
4. Schema contract derived from the real SQL (mutation: real intraday query selects `open` → FAIL).
5. ORDER BY ... DESC before LIMIT on daily + options; frontend picks the max date explicitly (test "latest" = max date).
6. Global "Account services unavailable" banner (frontend test).
7. app.yaml has no personal schema literal; bundle/app.yaml agree.
8. requirements test maps dotted imports (mutation: drop databricks-sql-connector → FAIL).
Plus r10: warming state detection with a real installed connector; frontend-serving tests isolated from the caller's env while the
PUBLIC_DEMO safety check still raises for the app's own env; ablation test timeout marker.
Run the selection above; frontend tests + `npm run build` (WSL if UNC blocks).
