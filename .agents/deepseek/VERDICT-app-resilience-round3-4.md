# VERDICT: app-resilience-round3-4 — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 3 + 4 (check)

===VERDICT START===

## Round 3 — prior blocking findings (fixed)

1. **Bounded pool establishment — FIXED.** `db/lakebase.py:151-167` now builds with `open=False` and calls `pool.wait(timeout=LAKEBASE_CONNECT_TIMEOUT)`, so a first request against a hanging endpoint raises `PoolTimeout` within ~3 s instead of retrying 30+ s. `tests/api/test_resilience.py::test_first_request_bounded_when_pool_hangs` exercises it. Verified: `python3 -m pytest tests/api/test_resilience.py -q` → pass (the 18-test run incl. test_market passed).
2. **test_market isolation — FIXED.** `tests/api/test_market.py:17` now declares `def client(fake_lakebase)`, so the 7 market tests run offline. Verified: 18 passed in the resilience+market run.
3. **requirements additions — FIXED.** `python-dotenv`, `pyyaml`, `langsmith`, `edgartools`, `finvizfinance` are all in `requirements.txt`. AST-scan test added (`tests/test_requirements_completeness.py`). **But see Blocking-1 below — the AST test itself now fails.**
4. **degraded role == viewer — FIXED.** `tests/api/test_resilience.py::test_degraded_user_role_is_viewer` asserts read 200 + write 503 with the degraded viewer, and the mechanics in `api/deps.py:314-334` (`ensure_role` 503s before the role check) hold.
5. **cleanups — FIXED.** `api/deps.py:94-96` adds a lock-guarded `_RoleCache.size()` used by `lakebase_status()`; `docs/DEPLOYMENT.md` nesting now matches `resources/app.yml`.

## Round 4 — blocking findings

- **[Blocking-1] The acceptance command no longer passes: the new AST-scan test flags the stdlib module `contextvars` as an undeclared third-party import.** `api/diagnostics.py:18` does `from contextvars import ContextVar` at module scope; `tests/test_requirements_completeness.py:56-88` `_STDLIB_MODULES` does not list `contextvars`. Result: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → `2 failed` — the pre-existing `tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms` (known/environmental, excepted) **plus a new failure** `tests/test_requirements_completeness.py::test_all_top_level_imports_declared_in_requirements`. → **Concrete failure:** the acceptance gate (0 failures except the named ml-ablation timeout) is broken by round-4 code.

- **[Blocking-2] The SQL-warehouse backend is not actually consumable by the routes that must use it — consumers still assume Spark DataFrames.** `db/delta_adapter.py` returns plain `List[Dict]` from `_warehouse_query` in the no-pyspark path, but every caller still calls `.collect()`/`.asDict()` on the result:
  - `api/routes/signals.py:36-37` — `df = latest_signals(...); return [r.asDict() for r in df.collect()]`. With pyspark absent, `latest_signals` returns a list of dicts, so `.collect()` raises `AttributeError` and the route degrades to `"unavailable"` instead of returning warehouse data.
  - `agent/tools_retrieval.py:44-46` (`get_latest_signal`), `:53-54` (`get_market_features`) — same `df.collect()` on a warehouse list.
  - `agent/tools_retrieval.py:57-70` (`get_options_features`) and `:351-359` (`get_cot_positioning`) — import `pyspark.sql.functions` / `_spark()` directly with **no** warehouse fallback, so the options read fails outright when pyspark is absent.
  → **Concrete failure:** round-4 item 3 requires "every route previously using pyspark (market, signals, analytics, options) works through the warehouse backend." It does not. The `tests/api/test_health_diagnostics.py` warehouse tests (`:276-344`) only exercise `db.delta_adapter` in isolation (they monkeypatch `_warehouse_query` / `_get_warehouse_connection`), never the route→tool→adapter chain, so this regression is invisible to the test suite.

- **[Blocking-3] `/api/health` leaks unbounded daemon threads under repeated calls when a probe hangs forever.** `api/routes/health.py:127-159` `_run_with_timeout` spawns one new `threading.Thread(daemon=True)` per probe per call, with **no** single in-flight guard and **no** bounded executor. If a probe blocks indefinitely (e.g. `db.fetchone("SELECT 1")` on an established-but-hung connection — psycopg has no statement timeout), that daemon thread is never reaped, and every subsequent health call adds two more. The CHECK explicitly calls this out as blocking ("require a single in-flight probe per dependency or a bounded executor"). The mutation "remove the probe timeout" is covered by a test, but this thread-leak scenario is not tested and the design does not bound it.

- **[Blocking-4] "Statement timeout" is declared but never applied.** `db/delta_adapter.py:96-123` `_warehouse_query` accepts `timeout: int` (default `WAREHOUSE_TIMEOUT_S`), and `:106` documents "has a statement timeout", but the parameter is never passed to `cursor.execute` or the connection — there is no statement timeout anywhere in the warehouse path. Only the health endpoint's daemon-thread wrap bounds its own probe; the market/signals warehouse queries themselves can hang indefinitely.

- **[Blocking-5] `/api/health/trace` is unauthenticated.** `api/routes/health.py:229-242` `health_trace` has no `Depends(get_current_user)`, while every other read route (signals, market, analytics) requires `get_current_user` (401 in prod mode). The CHECK requires "Read-only; same auth as other read routes". In non-demo mode the endpoint exposes internal stage events (table names, symbols, timings) with no auth.

## Non-blocking notes

- `stage("delta_read", ..., symbol=symbol)` in `api/routes/market.py:64,66` and `signals.py:41` logs the (normalized, allow-listed) symbol as a stage field. Not a secret/token/email and not SQL-with-user-values, so acceptable; the no-secret tests (`test_no_secret_in_health_output`, `test_no_secret_in_logs`) pass.
- `check_warehouse_health` (`db/delta_adapter.py:132-141`) returns `f"{type(exc).__name__}: {str(exc)[:80]}"`, which includes the first 80 chars of an exception message. Unlike the Lakebase probe (which logs only the type), this can embed host/credential fragments from a connector error into `last_error`/`detail`. The seeded-secret test only exercises the Lakebase path. Recommend type-only here too.
- `health()` runs the two probes sequentially (`:184-202`), so worst-case bound is ~3 s + ~5 s ≈ 8 s, above the "~6 s" figure in the CHECK. Not blocking on its own but worth aligning.

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2 failed, 1498 passed, 97 skipped, 24 deselected** (FAIL — Blocking-1).
  - `tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms` — pre-existing pytest-timeout, excepted per protocol.
  - `tests/test_requirements_completeness.py::test_all_top_level_imports_declared_in_requirements` — NEW failure (`contextvars`).
- `python3 -m pytest tests/test_requirements_completeness.py -q` → 1 failed (0.25s) — `contextvars → contextvars` false positive.
- `python3 -m pytest tests/api/test_health_diagnostics.py -q` → 11 passed (21s).
- `python3 -m pytest tests/api/test_resilience.py tests/api/test_market.py -q` → 18 passed (2.7s).
- `cd frontend && npm ci && npm run build` (via WSL, node v22) → pass (`vite v5.4.21 built in 1.94s`, `tsc` clean).

===VERDICT END===
