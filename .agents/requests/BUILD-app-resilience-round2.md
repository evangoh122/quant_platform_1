# BUILD app frontend/deploy round 2 — resilience + deploy fixes (builder: MiMo; checker: DeepSeek; reviewer: Codex; final: Claude)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/app-frontend-deploy. Commit after each item, descriptive messages. LF.
NEVER delete or weaken tests. Every fix needs a test that FAILS on the old code (prove with a `git archive HEAD | tar -x -C /tmp/<dir>` copy).

LIVE FACTS (Claude, 2026-10-04): the app is deployed and RUNNING at quant-platform-dev, but the Lakebase instance is STOPPED, so every authenticated
request blocks ~30 s on Lakebase role resolution. Two deploy fixes were needed by hand in the preview deploy and must be made in the repo:
(a) app.yaml `--port "${DATABRICKS_APP_PORT:-8000}"` is NOT shell-expanded by Databricks Apps → crash; use "8000" (Apps routes to 8000).
(b) requirements.txt has `ibapi>=10.19.0` (not on PyPI) → install fails; and the app imports packages listed nowhere (python-dotenv, pandas, numpy,
    pyyaml, tenacity, polars, openai, langchain-openai, langchain-core, huggingface-hub) plus requirements-app.txt (psycopg, sentence-transformers,
    rank-bm25). Create a dedicated app requirements file used by the app (Databricks Apps installs ./requirements.txt — so either move non-app deps
    out of the root requirements.txt into requirements-dev/pipelines files that CI installs, or otherwise ensure the app's root requirements.txt is the
    app set WITHOUT ibapi/pyspark). Keep CI green. Test: every top-level third-party import reachable from api/ and agent/ is declared in the app
    requirements (AST scan), and ibapi/pyspark are not.

Items (from the deployment analysis):
1. Lakebase auth resilience (api/deps.py get_current_user + api/db):
   - connection timeout 2–3 s (configurable);
   - in-process cache of resolved roles for ~5 min (TTL, keyed by user);
   - circuit breaker: after N consecutive authorization/connection failures, skip Lakebase for a cool-down window;
   - read-only market/strategy/analytics/SEC routes must NOT wait on Lakebase: if identity storage is unavailable, treat the user as an
     authenticated viewer (identity from x-forwarded-email) with read-only access; write routes (portfolio/watchlist/orders) return a fast 503
     "Account services unavailable".
   - frontend: show a fast "Account services unavailable" banner when /api/health (or a status endpoint) reports Lakebase down; analytics pages still work.
   Tests with a fake DB that hangs/raises: read routes return < 1 s; writes return 503 fast; breaker opens after N failures and recovers after cool-down;
   cache hit avoids DB.
2. /api/market/{symbol} (api/routers/market.py): bounded recent date window by default (e.g. last 252 trading days, configurable via query param with a
   max), explicit row LIMIT, select only needed columns, ONE options query (no second query), no unbounded .collect(). Tests assert the generated SQL /
   query plan has the window, LIMIT, column list, and a single options query.
3. Declare the Lakebase database resource in resources/app.yml (Databricks Apps `resources: - database:` with the instance evangoh-capstone-lakebase and
   CAN_CONNECT_AND_CREATE) instead of relying only on env vars; document the required Postgres grants (schema USAGE; SELECT/INSERT on users; the
   operational tables used by portfolio/watchlist/orders) in docs/DEPLOYMENT.md as SQL the owner runs. Do not run anything live.
Acceptance: CI-equivalent `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` passes; `cd frontend && npm ci && npm run build`;
`databricks bundle validate` is Claude's job. .agents/mimo/VERDICT-app-resilience-round2.md. Commit everything.
