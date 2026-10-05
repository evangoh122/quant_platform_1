# VERDICT: app-resilience-round5 — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings

All 5 blocking findings from DeepSeek round 3-4 verdict fixed:

- **Blocking-1 FIXED** — `tests/test_requirements_completeness.py` now uses `sys.stdlib_module_names` (Python ≥3.10) instead of a hand-curated set. `contextvars` and all other stdlib modules are correctly recognized. Commit: `eabe67e`.

- **Blocking-2 FIXED** — `db/delta_adapter.py` exports `as_dicts()` helper that normalizes pyspark DataFrames and plain `list[dict]` to a uniform `list[dict]` return. All consumers updated:
  - `api/routes/signals.py:34` — uses `as_dicts(latest_signals(...))` instead of raw `.collect()`
  - `agent/tools_retrieval.py:41` (`get_latest_signal`) — uses `as_dicts()`
  - `agent/tools_retrieval.py:49` (`get_market_features`) — uses `as_dicts()`
  - `agent/tools_retrieval.py:57` (`get_options_features`) — added warehouse fallback with parameterized query
  - `agent/tools_retrieval.py:87` (`get_cot_positioning`) — added warehouse fallback with parameterized query
  - No direct pyspark imports outside the adapter's pyspark branch (tools_retrieval uses `_has_pyspark` guard)
  - E2e tests: signals, market, options, COT routes drive through warehouse with pyspark absent and assert real rows. Commit: `d78ea32`.

- **Blocking-3 FIXED** — `api/routes/health.py` `_run_with_timeout` now has a single in-flight guard per dependency via `_inflight` dict. If a previous probe is still running, returns `(False, 0, "probe still running")` without spawning another thread. Both probes run concurrently via `ThreadPoolExecutor(max_workers=2)`, bounding the whole endpoint by ~max(timeouts)+margin (~6s). Test: 20 calls with hanging probes → thread growth ≤ 4. Commit: `a501619`.

- **Blocking-4 FIXED** — `db/delta_adapter.py` `_warehouse_query` enforces the `timeout` parameter for real: runs `cursor.execute` + `fetchall` in a daemon thread, raises `TimeoutError` if the thread doesn't finish within the bound. Test: hanging warehouse → `TimeoutError` within 3s. Mutation: remove timeout → test hangs. Commit: `fa33c99`.

- **Blocking-5 FIXED** — `api/routes/health.py` `health_trace` now requires `Depends(get_current_user)` like other read routes. Returns 401 without auth in non-demo mode. Test: `GET /api/health/trace` without auth → 401. Commit: `f189e9b`.

## Non-blocking notes

- `check_warehouse_health` now returns exception TYPE only (`type(exc).__name__`), no `str(exc)`. Seeded-secret test added for the warehouse path. Commit: `d78ea32`.
- Probes now run concurrently (non-blocking note from round 3-4 about sequential 8s worst-case). Commit: `a501619`.

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **1 failed (known ml ablation timeout, excepted), 1507 passed, 97 skipped, 24 deselected** — PASS
- `python3 -m pytest tests/api/test_resilience.py tests/api/test_market.py tests/test_requirements_completeness.py tests/api/test_health_diagnostics.py -q` → **38 passed** — PASS
- `python3 -m pytest tests/test_requirements_completeness.py -q` → **1 passed** — PASS (contextvars no longer flagged)
- `python3 -m pytest tests/api/test_health_diagnostics.py -q` → **19 passed** — PASS (includes all new tests)
- `npm ci && npm run build` (WSL) → **vite v5.4.21 built in 2.08s, tsc clean** — PASS

## Commits

| Hash    | Description |
|---------|-------------|
| `eabe67e` | fix: use sys.stdlib_module_names in AST-scan test (Blocking-1) |
| `d78ea32` | fix: warehouse backend end-to-end consumable (Blocking-2) |
| `a501619` | fix: health probe thread leak + concurrent probes (Blocking-3) |
| `fa33c99` | fix: enforce warehouse statement timeout via thread (Blocking-4) |
| `f189e9b` | fix: add auth to /api/health/trace (Blocking-5) |