# CHECK: XBRL B1a round 2 (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`),
never via PowerShell wrappers or C:\temp scripts. Write .agents/deepseek/VERDICT-xbrl-B1a-r2.md between ===VERDICT START=== /
===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r1 verdict: .agents/deepseek/VERDICT-xbrl-B1a.md. Round 2 commit 80c5c38 (spec .agents/requests/BUILD-xbrl-B1a-r2.md).
Claude: 42 passed; append→overwrite mutation now fails tests.
1. Re-run all four named mutations (placeholder UA; remove rate limiter; overwrite instead of append; drop malformed facts) — each must fail.
2. The same-payload skip test is real (remove the skip logic → a test fails) and asserts rows written once + manifest status.
3. Bounded concurrency: ThreadPoolExecutor ≤ 4 workers sharing the process-wide limiter; ≤10 req/s holds under concurrency (test with a fake
   clock or call timestamps); manifest attempt_count is the real count. Thread safety of the shared writer/state.
4. Offline suite `python3 -m pytest -q -m "not spark and not lakebase and not databricks"`.
