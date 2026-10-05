# CHECK: app round 11b (checker: DeepSeek) — Claude's fixes for your r11 findings

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-app-resilience-round11b.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Your r11 verdict: (1) semaphore double release in db/delta_adapter.py (production bug); (2) token-mint timeout test did not drive production.
Claude's tiny fix (3718ab6): `worker_started` flag — the outer handler releases the slot only if the worker never started; once started the worker's
finally owns the release (even after a timeout). The mint test now monkeypatches `db.lakebase.subprocess.run` and calls production
`mint_token_via_cli`. Claude (WSL): semaphore test 5/5 passes; mutation "drop timeout= in mint_token_via_cli" → FAILS; full gate 1550 passed.
Verify: exactly one release per acquire on every path (normal, worker error, timeout + late completion, exception before thread start — no
NameError on `t`); concurrency never exceeds the bound with hung workers (and they eventually free their slots when the cursor returns/cancels);
re-run your mutations (remove acquire → FAIL; drop mint timeout → FAIL); run the semaphore test ≥5 times for flakiness.
Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks".
