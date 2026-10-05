# BUILD app resilience round 11 — IMPLEMENT NOW (DeepSeek: 4 Codex mutations still survive; TESTS ONLY)

You are MiMo. Fix `.agents/deepseek/VERDICT-app-resilience-round9-10.md` blocking items 1–4. Production code is correct — change tests only
(plus a tiny refactor in item 3 if needed to expose the real SQL). Commit per item, LF endings, do not touch `.agents/dispatch.sh`.
For EACH item you must run the named mutation in a `git archive HEAD | tar -x -C /tmp/<dir>` copy and paste the FAILED output in your verdict.
1. Lakebase pool fake (tests/api/test_resilience.py:~340-358): model real psycopg_pool state — `wait()` on a pool that was never `open()`ed raises
   `psycopg_pool.PoolClosed`; after `open()`, `wait()` hangs/raises PoolTimeout as the scenario needs. Mutation: delete `pool.open(wait=False)`
   (db/lakebase.py:~173) → the first-request test FAILS. Add a test for the token-mint subprocess timeout (db/lakebase.py:~65-71): a fake
   subprocess that sleeps past the timeout → bounded failure. Mutation: drop `timeout=` → FAIL.
2. Concurrency counter (tests/api/test_health_diagnostics.py:~1004-1055): use a SHARED lock-guarded counter (e.g. `state = {"cur":0,"max":0}`
   + `threading.Lock`), have the fake cursor increment on entry, sleep, decrement; launch ≥6 concurrent queries with semaphore size 2; assert
   max == 2 (not ≤2 — prove it was reached) and never > 2. Mutation: remove the semaphore acquire (db/delta_adapter.py:~172) → FAIL.
3. Schema contract from REAL SQL: move the query strings in db/delta_adapter.py and agent/tools_retrieval.py into module-level constants (or
   builder functions) that production uses, and have the contract test import THOSE and parse their selected/filtered identifiers per table.
   Delete the duplicated hardcoded SQL in db/schema_contract.py:~223-258. Mutation: change the real intraday query constant to select `open`
   → FAIL.
4. Requirements scan: include imports inside function bodies (walk the whole AST, not only module scope) for packages the app needs at runtime,
   so `from databricks import sql` (deferred) maps to databricks-sql-connector. Keep pyspark/ibapi excluded (they are optional). Mutation: remove
   databricks-sql-connector from requirements.txt → FAIL.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → 0 failed. Verdict: .agents/mimo/VERDICT-app-resilience-round11.md.
