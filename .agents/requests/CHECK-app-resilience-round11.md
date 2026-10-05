# CHECK: app round 11 (checker: DeepSeek) — test strength for Codex findings 1, 2, 4, 8

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-app-resilience-round11.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Your r9-10 verdict had 4 surviving mutations. Round 11 commits 99eab8b..94ec685 (tests + query-constant refactor only).
Claude's independent mutation runs (archive copies, WSL): no `pool.open(wait=False)` → 1 failed; no token-mint subprocess timeout → 1 failed;
no semaphore acquire → 2 failed; `databricks-sql-connector` removed from requirements → 1 failed; `"open"` added to `_INTRADAY_COLS` → 2 failed.
Re-run YOUR four mutations exactly as in your r9-10 verdict and confirm each FAILS a named test; confirm the query-constant refactor in
db/delta_adapter.py / agent/tools_retrieval.py did not change any production SQL text or params (diff the built queries before/after);
and that nothing from your r9-10 PASS list regressed. Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks".
