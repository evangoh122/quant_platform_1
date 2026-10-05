# CHECK: app resilience round 3 + health diagnostics round 4 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-app-resilience-round3-4.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Requests: .agents/requests/BUILD-app-resilience-round3.md (commits 2c3a376..3eac145) and
.agents/requests/BUILD-app-health-diagnostics-round4.md (commit b0a095a). Your previous verdict: .agents/deepseek/VERDICT-app-resilience-round2.md.
MiMo's self-reports are NOT evidence.

Round 3: verify each of your round-2 blocking findings is fixed — total pool establishment bounded (first request against a
hanging DB returns a read route fast; mutation "remove the bound" FAILS); test_market isolated from live Lakebase; requirements
complete with an AST-scan test that FAILS when pyyaml is dropped; degraded role == viewer test.
Round 4: verify every numbered item:
1. stage logs (start/done, elapsed ms, error type) + per-request middleware line + bounded thread-safe ring buffer; NO secrets/tokens/
   emails/SQL-with-user-values in logs (a seeded fake secret must not appear).
2. /api/health can never hang: per-probe hard timeouts, whole endpoint bounded (~6 s) when Lakebase and warehouse both hang. Check the
   daemon-thread timeout design does not leak unbounded threads under repeated health calls (e.g. probe stuck forever → one new
   thread per call?) — if it can, that's blocking; require a single in-flight probe per dependency or a bounded executor.
   /api/health/trace auth = read-route auth, no secrets. Frontend SystemHealth renders dependency state/latency/last error + slow stages.
3. SQL-warehouse backend in db/delta_adapter.py: auto-selected when pyspark absent; parameterised only (no f-string user values);
   bounded LIMIT; statement timeout; auth via SDK default chain (app service principal); `databricks-sql-connector` (or whatever it
   imports) is in requirements.txt and the AST-scan test covers it; resources/app.yml sql_warehouse resource + env var correct.
   Every route previously using pyspark (market, signals, analytics, options) works through the warehouse backend — list them.
4. Tests behavioural; run the named mutations (remove probe timeout; drop error type from stage logs; select pyspark when absent) and
   report survivors as blocking.
Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks" (known pre-existing ml ablation timeouts excepted —
name them); cd frontend && npm ci && npm run build (if npm is blocked by the UNC path, run it from WSL: `wsl -d Ubuntu -- bash -lc
'cd /home/jianj/code/qp1-appfe/frontend && npm ci && npm run build'`).
