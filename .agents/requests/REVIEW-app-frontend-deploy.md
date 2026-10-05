# REVIEW: app frontend deploy + resilience + warehouse path (reviewer: Codex gpt-5.6-sol) — final review before Claude's deploy validation

Do NOT edit repo files; mutation proofs in copies made with `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Diff under review: `git diff origin/main...HEAD` on slice/app-frontend-deploy. Requests: BUILD-app-frontend-deploy*.md, BUILD-app-resilience-round2..8,
BUILD-app-health-diagnostics-round4. DeepSeek: latest VERDICT-app-resilience-round5-8.md APPROVED.
Context: Databricks App `quant-platform-dev` (no pyspark in the app; SQL warehouse b15d3d6f837ba428 via databricks-sql-connector `:name` params);
Lakebase `evangoh-capstone-lakebase` (currently STOPPED — the app must degrade to read-only fast, never hang). Claude's live checks from WSL with
pyspark disabled: market 19 daily bars 0.8 s; options OK; COT SPY→equity_index; signals → no_signals_published (table empty); schema contract
script exit 0.
Review: deploy config (app.yaml literal port, requirements completeness, resources/app.yml Lakebase + sql_warehouse resources, sync.include dist,
no personal schema names hardcoded where config should be used); Lakebase resilience (bounded total connect, circuit breaker, role cache TTL,
degraded viewer can never write); health/trace (no hang, no thread leak, auth, no secrets); warehouse backend (param style, LIMIT only on SELECT,
statement timeout + cancel, bounded concurrency, schema contract); frontend SystemHealth. Known non-blocking from DeepSeek to judge: options
LIMIT without ORDER BY feature_ts DESC (returns arbitrary rows, not "latest"); schema checker treating DESCRIBE partition rows as columns.
Run your own mutations on the core safety properties and report survivors.
Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line.
Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks" (known ml ablation timeout excepted); cd frontend && npm ci && npm run build
