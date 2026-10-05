# BUILD app health diagnostics + warehouse data path (round 4) — IMPLEMENT NOW

You are MiMo. Branch `slice/app-frontend-deploy`, on top of round 3. Owner request: "add print status on where things
get stuck in the app, i.e. health check". Commit per item, LF endings, do not touch `.agents/dispatch.sh`,
never delete/weaken tests, mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.
NEVER log or return secrets, tokens, connection strings with passwords, or user emails beyond the existing privacy-reduced form.

1. Stage timing logs ("where it gets stuck"). Add a small helper (e.g. `api/diagnostics.py`, context manager
   `stage(name, **safe_fields)`) that logs `STAGE start <name>` and `STAGE done <name> ms=<elapsed> ok=<bool>`
   (and `error=<ExceptionType>` on failure) at INFO to stdout, so they appear in Databricks Apps /logz.
   Wrap: app startup steps (config load, router mount, frontend dist detection), Lakebase pool build / connect /
   first query, role resolution (`_ensure_user`/role cache hit vs miss), circuit-breaker transitions (open/half-open/closed),
   each Delta/warehouse query in the market/signals/analytics routes (table name + row count, no SQL literals with user input),
   and a per-request middleware line: method, route template (not raw path with query), status, total ms, and the slowest stage.
   Also keep an in-memory ring buffer (last ~200 stage events, thread-safe) for item 2.
2. `/api/health` must never hang and must show where things are stuck:
   - Each dependency probe runs with its own hard timeout (Lakebase ~3 s, warehouse ~5 s) — a probe that times out reports
     `ok=false, detail="timeout after Xs"`; the endpoint as a whole returns within ~6 s even if everything hangs.
     (Today it calls `get_lakebase().fetchone("SELECT 1")` with no bound.)
   - Response adds per-dependency `latency_ms`, `last_error` (exception type + short safe message), `last_ok_at`,
     circuit breaker state, role-cache size, and app `startup` stage timings.
   - Add `GET /api/health/trace` returning the ring buffer (recent stage events + slow requests > 2 s). Read-only;
     same auth as other read routes; no secrets.
   - Frontend: the existing SystemHealth view shows each dependency's state, latency and last error, plus a
     "slowest recent stages" list from `/api/health/trace`. Keep it simple.
3. Warehouse data path (blocking for the deployed app). `db/delta_adapter.py` reads via pyspark, but pyspark is
   intentionally NOT in the app's requirements.txt, so on Databricks Apps every market/signals/analytics read fails.
   Add a SQL-warehouse backend (databricks-sql-connector or `databricks.sdk` statement execution, warehouse id from config/env
   `DATABRICKS_WAREHOUSE_ID`, default `b15d3d6f837ba428`, auth from the app's service principal via the SDK default chain),
   parameterised queries only, bounded LIMIT, statement timeout. Select it automatically when pyspark is absent; keep the
   pyspark path for notebooks. Health reports `delta` as the warehouse probe (`SELECT 1` with timeout) rather than "pyspark installed".
   Add the warehouse to `resources/app.yml` as an app resource (`sql_warehouse`, permission CAN_USE) and document it in DEPLOYMENT.md.
4. Tests (behavioural, red phase captured): health returns within bound when Lakebase and the warehouse probe both hang
   (fakes that sleep); a timed-out probe reports `timeout`; stage logs are emitted with elapsed ms and error type on failure
   (caplog); ring buffer is bounded and thread-safe; no secret/token string appears in logs or health output (seed a fake
   secret and assert absence); warehouse backend is selected when pyspark is missing and passes parameters (not string
   interpolation). Mutations that must FAIL: remove the probe timeout; drop the error type from stage logs; select pyspark
   backend when pyspark is absent.

Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (only the known pre-existing ml ablation
timeout may fail; report it); `cd frontend && npm ci && npm run build`. Claude will run the live warehouse probe from WSL.
Verdict: `.agents/mimo/VERDICT-app-health-diagnostics-round4.md`.
