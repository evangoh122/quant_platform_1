# VERDICT: app-resilience-round9-10 — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 9–10 (check)

===VERDICT START===

## Scope

Read-only check of rounds 9–10 (`3b9c840..4a34f8a` r9, `a30557d` r10) against HEAD
`28ae9d4`. MiMo self-reports were ignored. Every claim below is from reading the
diff and re-running Codex's own mutations against the current code. Four of the
eight Codex findings are **not actually fixed** — the new tests do not guard the
defect, and the named mutation still survives.

## Blocking findings (mutations that still survive)

1. **[1] Lakebase pool open/closed state is not modelled by the fake.** The fix
   `pool.open(wait=False)` before `pool.wait(...)` at `db/lakebase.py:173-174` is
   correct, but `BlockingPool` in `tests/api/test_resilience.py:340-358` makes
   `wait()` raise `PoolTimeout` unconditionally (`:349-350`), regardless of
   whether `open()` was called. Removing `pool.open(wait=False)` still passes
   `test_first_request_bounded_when_pool_hangs` — the "don't open → FAIL"
   mutation **survives**. The fake must make a *closed* pool's `wait()` raise
   `PoolClosed` (the real `psycopg_pool` behaviour Codex demonstrated), so
   dropping the `open()` call is caught. Also there is **no test** for the
   token-mint subprocess timeout added at `db/lakebase.py:65-71`.

2. **[2] Warehouse concurrency test counts nothing.** `test_warehouse_query_semaphore_bounded`
   at `tests/api/test_health_diagnostics.py:1004-1005` uses
   `concurrent_count = _threading.local()` — a per-thread object — so each worker
   thread sees its own isolated `value`, and `max_concurrent[0]` is pinned at 1.
   The assertion `max_concurrent[0] <= 2` (`:1055`) passes trivially. Removing the
   semaphore acquire at `db/delta_adapter.py:172` (the "drop semaphore acquire →
   FAIL" mutation) **survives** — I confirmed it passes. The counter must be a
   shared object (e.g. a lock-guarded `list[0]`), not `threading.local()`.

3. **[4] Schema contract is still a second manual list, not derived from the real
   SQL.** `validate_actual_queries()` at `db/schema_contract.py:186-263` builds
   hardcoded SQL from duplicated column lists (`:223-230`, `:238-244`,
   `:253-258`); `:221` reads `market_features_intraday.__doc__` and never uses it.
   It never imports the real query strings from `db/delta_adapter.py` or
   `agent/tools_retrieval.py`. Mutating the real intraday query
   (`db/delta_adapter.py:432-439`) to select `open` **survives**
   `test_actual_queries_match_contract` — I confirmed it passes.

4. **[8] Requirements dotted-import mapping is still unreachable.** The only
   `from databricks import sql` imports are **deferred** (inside function bodies:
   `db/delta_adapter.py:37,125`), and `_scan_top_level_imports`
   (`tests/test_requirements_completeness.py:93-104`) only walks module-scope
   nodes. So `databricks.sql` never appears in the scanned set, and the
   `"databricks.sql": "databricks-sql-connector"` mapping (`:37`) is dead.
   Removing `databricks-sql-connector` from `requirements.txt` **survives**
   `test_all_top_level_imports_declared_in_requirements` — I confirmed it passes.

## Findings that ARE fixed

- **[3] smoke_app.py** — FIXED. `scripts/smoke_app.py:53-120` requires HTML +
  `<div id="root">` (`:96`) + a hashed `/assets/*.js` asset that GETs 200
  (`:101-117`), and rejects the missing-build JSON hint (`:86-93`) and non-HTML
  (`:80-82`). `tests/test_smoke_app.py` covers pass + JSON-hint + non-HTML +
  missing-root + asset-404 (5 tests, all pass).
- **[5] ORDER BY DESC before LIMIT** — backend FIXED. `db/delta_adapter.py:420`
  `ORDER BY event_date DESC`; `agent/tools_retrieval.py:94` `ORDER BY feature_ts
  DESC`. Tests `test_warehouse_daily_query_has_order_by_desc` and
  `test_warehouse_options_query_has_order_by_desc` assert DESC present.
  Frontend source also fixed: `MarketDashboard.tsx:32-35` `reduce`s to the max
  `event_date` instead of trusting row 0. (No frontend unit test exists — see
  note below.)
- **[7] app.yaml** — FIXED. `app.yaml` has no `evangoh_capstone` literal and no
  `env` block; `resources/app.yml:9-13` injects `CATALOG`/`SCHEMA` via
  `${var.schema}`. `tests/test_app_yaml.py` (2 tests) pass.

## r10 items — all fixed

- **Warming state wins** — FIXED. `check_warehouse_health`
  (`db/delta_adapter.py:262-279`) checks `get_warm_state()` before
  `_warehouse_available()`, so `"connecting"` is reported while the first connect
  is in flight. `test_health_probe_reports_warming_state`,
  `test_check_warehouse_health_reports_warming`,
  `test_warehouse_available_detects_installed_connector` (connector 4.6.0
  detected) all pass.
- **Env isolation** — FIXED. `tests/api/test_frontend_serving.py:20-36` `_demo_env`
  strips every `api.demo._is_unsafe_key`-matching ambient var. I ran the file
  with `CLAUDE_CODE_MESSAGING_TOKEN`, `DATABRICKS_WORKSPACE_ID`, `HF_TOKEN`,
  `OPENAI_API_KEY`, `DATABRICKS_TOKEN` set → **9 passed**; and
  `test_safety_check_raises_when_own_env_has_secret` confirms the guard still
  fires for the app's own env.
- **Ablation timeout marker** — FIXED. `tests/ml/test_ablation.py:22`
  `@pytest.mark.timeout(120)`; `pytest.ini` registers `slow` marker and
  `timeout = 30`.

## Non-blocking notes

- **[6] Banner** is implemented in `frontend/src/App.tsx:52-54,81-85` (polls
  `/api/health`, shows "Account services unavailable" when the lakebase dependency
  is down or breaker open). But there is **no automated test**: the frontend has
  no test runner (`package.json` scripts are only `dev`/`build`/`preview`), and no
  Python test asserts the banner. The CHECK item "banner (frontend test)" is not
  satisfied by any test.
- Same gap for the [5] "latest = max date" frontend logic — source is correct but
  untested (no frontend test framework).
- `db/delta_adapter.py:20` still defaults `SCHEMA = os.getenv("SCHEMA",
  "evangoh_capstone")` (and `config/settings.py` defaults likewise, per
  `tests/test_schema_env_override.py:9`). The request only scoped `app.yaml`, so
  this is out of scope, but a direct/UI deployment with no `SCHEMA` env still
  falls back to the personal dev schema in code.

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` →
  **1548 passed, 97 skipped, 24 deselected, 44 warnings** in 230.7 s (exit 0).
  No ml-ablation timeout this run (timeout marker now 120 s).
- Focused: `tests/test_smoke_app.py`, `tests/test_app_yaml.py`,
  `tests/test_requirements_completeness.py`, `tests/api/test_frontend_serving.py`,
  `tests/api/test_resilience.py` → **29 passed**; `tests/api/test_health_diagnostics.py`
  → **47 passed** (36.8 s).
- Mutation re-runs (in-place, reverted via `git checkout`):
  - drop `pool.open(wait=False)` → `test_first_request_bounded_when_pool_hangs`
    **PASSED (survived)** ✗
  - drop `_query_semaphore.acquire` → `test_warehouse_query_semaphore_bounded`
    **PASSED (survived)** ✗
  - add `open` to real `intraday_cols` → `test_actual_queries_match_contract`
    **PASSED (survived)** ✗
  - drop `databricks-sql-connector` from requirements → `test_all_top_level_imports_declared_in_requirements`
    **PASSED (survived)** ✗
- Frontend: `tsc --noEmit` → pass; `npm run build` (WSL, node v22.23.3) → pass
  (`tsc && vite build`, 48 modules, built in 1.76 s). Note: `node_modules` had
  Windows-native `@rollup/rollup-win32-*` + non-executable `.bin` scripts; build
  passed only after `chmod +x node_modules/.bin/*` and installing
  `@rollup/rollup-linux-x64-gnu` (environment artifact, not a code defect).
- `git status` at end of check: clean working tree (no tracked files modified).

===VERDICT END===
