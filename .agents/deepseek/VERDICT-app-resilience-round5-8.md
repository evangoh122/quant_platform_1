# VERDICT: app-resilience-round5-8 — DeepSeek (checker)

**Status:** APPROVED
**Round:** 5–8 (check)

===VERDICT START===

## Scope

Read-only check of rounds 5–8 (`eabe67e..f189e9b` r5, `90b8a88`+`677e368` r6,
`403f8a5` r7, `1bf9d5d` r8). Verified against HEAD `721882b`. MiMo self-reports
were ignored; everything below is from reading the diff and running the named
mutations + acceptance command myself.

## r3-4 blocking findings — all fixed

1. **Blocking-1 (AST scan `contextvars`)** — FIXED. `tests/test_requirements_completeness.py:48` now
   builds `_STDLIB_MODULES` from `sys.stdlib_module_names` (Python ≥3.10). The full suite no longer
   has a `test_all_top_level_imports_declared_in_requirements` failure.
2. **Blocking-2 (warehouse backend not consumable)** — FIXED. `db/delta_adapter.py:233-245` `as_dicts()`
   normalises both `list[dict]` and Spark DataFrames; `api/routes/signals.py:37-40`,
   `api/routes/market.py:52-60`, `agent/tools_retrieval.py:41-96` all consume `list[dict]`; no
   `pyspark` import outside the adapter's `_has_pyspark` branch. E2E tests drive route→tool→adapter with
   pyspark absent (`test_signals_route_warehouse_e2e`, `test_market_route_warehouse_e2e`,
   `test_options_features_warehouse_e2e`, `test_cot_positioning_warehouse_e2e`).
3. **Blocking-3 (health probe thread leak)** — FIXED. `api/routes/health.py:56,134-178` `_inflight`
   single-in-flight guard + `_run_with_timeout` returns `"probe still running"` when a probe is already
   live; `health()` runs both probes concurrently via `ThreadPoolExecutor(max_workers=2)`
   (`health.py:203-207`). `test_probe_thread_leak_bounded` (20 calls, growth ≤4).
4. **Blocking-4 (statement timeout declared, never applied)** — FIXED. `db/delta_adapter.py:159-224`
   runs `cursor.execute` in a daemon thread, `t.join(timeout=timeout)`, and on timeout calls
   `cursor.cancel()` then `close()` and raises `TimeoutError`. `test_warehouse_query_timeout_enforced`,
   `test_warehouse_query_calls_cancel_on_timeout`.
5. **Blocking-5 (`/api/health/trace` unauth)** — FIXED. `api/routes/health.py:256-258` adds
   `_user: AppUser = Depends(get_current_user)`. `test_health_trace_requires_auth` asserts 401.

Non-blocking r3-4 notes also closed: `check_warehouse_health` returns exception **type only**
(`db/delta_adapter.py:263`, seeded-secret test `test_warehouse_health_returns_type_only`), and the
two probes now run concurrently (no longer ~8 s sequential).

## r6 — verified

- **`:name` params everywhere** — `db/delta_adapter.py` warehouse SQL uses only `:name` + dict
  (`latest_signals`, `market_features`, `market_features_intraday`, `get_options_features`,
  `get_cot_positioning`). Grep of `db/delta_adapter.py` for `%s`/`?` in SQL → none. The `%s` remaining
  in `agent/tools_retrieval.py:435,455,474` are **Lakebase/psycopg** (`get_portfolio_positions`,
  `get_open_orders`, `get_watchlist`), which is correct — psycopg uses `%s`. Pinned
  `databricks-sql-connector>=3.0.0,<5` at `requirements.txt:11`.
- **Background warming + "connecting" state** — `warm_warehouse_connection`/`get_warm_state`
  (`delta_adapter.py:73-106`), `check_warehouse_health` reports `"connecting"` while warming
  (`:256-258`); called from `api/main.py` at startup. Tests: `test_warm_warehouse_connection_*`,
  `test_check_warehouse_health_reports_warming`, `test_health_probe_reports_warming_state`.
- **Bounded semaphore** — `_query_semaphore` (10) with `acquire(timeout=timeout)`
  (`delta_adapter.py:63,170-174`). Tests: `test_warehouse_query_semaphore_bounded`,
  `test_warehouse_query_semaphore_timeout`.

## r7 — verified

- **Schema contract** — `db/schema_contract.py` (`TABLE_COLUMNS`, `QUERY_COLUMNS`,
  `validate_query_columns`) + `scripts/check_schema_contract.py`. `test_schema_contract_passes` and
  `test_schema_contract_rejects_bad_column` assert queries only reference contract columns.
- Market daily bars from `silver_ohlcv_day_adjusted` (`adj_*` aliased, `delta_adapter.py:372-406`),
  options real columns (no `expiry`, 422-style dict if passed), COT asset-class mapping + `no_mapping`,
  signals `no_signals_published`.

## r8 — verified

- **LIMIT only on SELECT** — `delta_adapter.py:162-165` guards with `_upper.startswith("SELECT")`.
  Tests `test_warehouse_query_no_limit_on_describe`, `test_warehouse_query_limit_on_bare_select`,
  `test_warehouse_query_preserves_existing_limit`.
- **Agent signal empty state** — `agent/tools_retrieval.py:46` `get_latest_signal` returns
  `{"status": "no_signals_published"}` on empty. `test_get_latest_signal_empty_returns_no_signals_published`.
- **Market `event_date`/`vwap`/`price_basis`** — `api/routes/market.py:73,79-80`; `vwap` from
  `adj_vwap` (`delta_adapter.py:400`). `test_ohlcv_uses_event_date_and_price_basis`.
- **Options bound** — `api/routes/market.py:60` `get_options_features(symbol, limit=min(days, limit))`
  → default 252. `test_default_days_param` (`opt_limit == 252`), `test_options_bounded_by_days` (50).
  Claude's live "options AAPL → 521 rows" came from the tool/raw path (default `limit=5000`), **not**
  the route; the route is bounded, so this is **not** the "blocking if unbounded" case.

## Named mutations (each FAILed its test)

| mutation | test that failed |
|---|---|
| drop probe timeout (`t.join()` in `_run_with_timeout`) | `test_timed_out_probe_reports_timeout` (detail `'should not reach here'`) |
| drop `cursor.cancel()` | `test_warehouse_query_calls_cancel_on_timeout` (`cancel() was not called`) |
| put one `%s` back (`WHERE symbol = %s`) | `test_warehouse_latest_signals_uses_named_params` (`ValueError: legacy %s`) |
| reference `open` from `gold_ohlcv_features` | `test_schema_contract_passes` |
| select pyspark when absent (`if True:` in `latest_signals`) | `test_warehouse_backend_selected_when_pyspark_missing` (`ImportError`) |
| LIMIT appended to DESCRIBE (drop `startswith("SELECT")`) | `test_warehouse_query_no_limit_on_describe` |

## Non-blocking notes

- `scripts/check_schema_contract.py:30-31` — `_get_warehouse_columns` never stops at the first
  `#`-prefixed row, so Delta DESCRIBE's partition-section rows (`# Partition Information`, `# col_name`)
  are counted as columns and reported as spurious "extra columns" (warnings; exit still 0). Claude
  flagged this "minor, include" — still present.
- r8 asked "Exit codes: 0 on no drift, non-zero on drift or query failure (**test both**)". Only
  `--help` (exit 0) is automated (`tests/test_check_schema_contract.py:8`). I verified the logic
  manually (no-drift→0, drift→1, query-failure→1 via `main()` return codes), but the drift/failure
  exit paths have no automated test.
- `api/routes/market.py:64,86` — the OHLCV stage/source is labelled `gold_ohlcv_features`, but the
  daily bars actually come from `silver_ohlcv_day_adjusted` (`delta_adapter.py:397-406`). Cosmetic.
- Options "latest N=252" is a bare `LIMIT` with no `ORDER BY feature_ts DESC`
  (`agent/tools_retrieval.py:88-96`), so "latest" ordering is not guaranteed — still bounded.
- `db/schema_contract.py:112` — `"UUP": "FX"` is uppercase while every other value is lowercase;
  `get_cot_positioning("UUP")` queries `mapped_asset='FX'` and matches nothing (table stores `fx`).

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **1 failed, 1533 passed,
  97 skipped, 24 deselected** (218.9 s). The single failure is
  `tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms` (pytest-timeout
  >30 s) — the known ml-ablation timeout, excepted per protocol.
- 6 mutation copies via `git archive HEAD | tar -x -C /tmp/mut-*` — all 6 FAIL as listed above.
- `frontend && npm ci && npm run build` (WSL, node v22.23.3) → pass (`tsc` clean,
  `vite v5.4.21 built in 1.92s`).
- `python3 scripts/check_schema_contract.py --help` → exit 0; drift/query-failure exit codes verified
  manually (0/1/1).

===VERDICT END===
