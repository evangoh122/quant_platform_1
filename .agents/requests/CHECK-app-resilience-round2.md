# CHECK: app resilience round 2 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-app-resilience-round2.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-app-resilience-round2.md. MiMo's self-report (.agents/mimo/VERDICT-app-resilience-round2.md) is NOT evidence.
Commits: e75c0ac a2984a3 800e794 00557d1 357ad2a.

Verify every BUILD item, specifically:
1. app.yaml uses literal port 8000; requirements for the app exclude ibapi/pyspark and include every import the API needs at runtime.
2. api/deps.py: Lakebase connect/statement timeout is 2-3 s (not the default); 5-min role cache; circuit breaker opens after N failures,
   half-opens after cooldown, recovers; read-only routes are NOT blocked when Lakebase is down (degrade to viewer); write routes fail fast with 503.
   Check thread-safety of cache/breaker and that a cached role never outlives TTL. Check that degraded mode cannot grant write/admin.
3. /api/market/{symbol}: bounded window and LIMIT, parameterised (no SQL injection via symbol/days), selected columns only.
4. resources/app.yml declares the Lakebase database resource correctly for Databricks Asset Bundles; DEPLOYMENT.md grants SQL is correct and grants least privilege.
Mutations that must FAIL a test: remove timeout; breaker never opens; read-only route blocked when breaker open; degraded mode returns admin;
drop LIMIT / days bound. Report any that survive as blocking.
Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks"; cd frontend && npm ci && npm run build.
