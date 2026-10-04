# VERDICT: app-resilience-round2 — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 2 (check)

===VERDICT START===

## Blocking findings

1. **`tests/api/test_market.py` — the 7 market tests are not isolated from the live Lakebase and time out, so the CI-equivalent command fails.**
   The local `client` fixture (`tests/api/test_market.py:16-22`) overrides the shared one but installs **no** fake/patched Lakebase (no `fake_lakebase`, no `monkeypatch` of `db.lakebase.get_lakebase`). Every request therefore runs `get_current_user` → `_resolve_role` → `_ensure_user`, which builds the *real* `db.lakebase.Lakebase` pool against `ep-steep-truth-d1ex36nr…` (currently "endpoint has been disabled"). Result:
   ```
   FAILED tests/api/test_market.py::test_default_days_param - Failed: Timeout (>30.0s)
   ... (all 7 market tests)
   8 failed, 1478 passed, 97 skipped, 24 deselected
   ```
   → **Concrete failure:** `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (the acceptance command) does **not** pass — 7 failures. The previous round's verdict reported `1470 passed` clean; this round regressed the gate.
   Root cause below (finding 4): the `connect_timeout=3` is per-TCP-attempt, not a bound on total pool establishment, so `psycopg_pool.ConnectionPool` retries until the pytest-timeout (30s) fires.

2. **`requirements.txt` is missing `python-dotenv`, which `api/config.py:4` imports at module top level.**
   `from dotenv import load_dotenv` is unconditional. `python-dotenv` is one of the packages BUILD item (b) explicitly listed as "imports the app needs but listed nowhere", yet commit `a2984a3` did not add it (it added tenacity/numpy/pandas/polars/openai/langchain-core/langchain-openai/huggingface-hub/psycopg/psycopg-pool/sentence-transformers/rank-bm25, but omitted python-dotenv and pyyaml).
   → **Concrete failure:** any import of `api.config` (reached from `api/services/embeddings.py:20`, `api/services/runtime_snapshot.py:42`, `api/services/sec_analyzer.py:21`, `api/services/langgraph_engine.py:16`, etc.) raises `ModuleNotFoundError: No module named 'dotenv'` on a Databricks App that installs only `requirements.txt`.

3. **`requirements.txt` is missing `pyyaml`, which is imported via `config/tickers.py:9` (`import yaml`) reachable from `agent/guardrails.py:120` (`from config.tickers import get_all_ticker_symbols`).**
   `pyyaml` is also explicitly listed in BUILD item (b). `config/tickers.py`, `config/universe.py`, `config/update_tickers.py` all `import yaml`.
   → **Concrete failure:** the symbol allow-list (`normalize_symbol`/`load_allow_list`) cannot load, so `/api/market/{symbol}` and the SEC/agent tools fail with `ModuleNotFoundError: yaml` at runtime.

4. **The "read route returns < 1 s when Lakebase is down" guarantee is not actually met on the first request — the 3 s timeout is per-connection, not a bound on total connection establishment.**
   `db/lakebase.py:136` sets `connect_timeout=LAKEBASE_CONNECT_TIMEOUT` (3) in `_conninfo`, and `_build_pool` (`db/lakebase.py:150-159`) constructs `psycopg_pool.ConnectionPool(..., open=True)` with **no** `timeout`/`reconnect_timeout`/`reconnect_failed` bound. `psycopg_pool` then retries the (disabled) endpoint with backoff, so the first `_ensure_user` blocks ~30 s before the circuit breaker ever opens. This is exactly the "blocks ~30 s" symptom from the LIVE FACTS, now only mitigated *after* N failures.
   → **Concrete failure:** the resilience tests (`tests/api/test_resilience.py`) only prove fast degradation by *pre-tripping* the breaker (`test_read_route_returns_fast_when_db_hangs`) or by using a fake that raises immediately; none exercises a first request against a slow/hanging DB. The market tests (finding 1) are the accidental proof that the first request still hangs ~30 s.

## Mutation coverage (per CHECK item 2 list)

- **remove timeout** → **survives.** No test references `LAKEBASE_CONNECT_TIMEOUT`, `connect_timeout`, or `_LAKEBASE_TIMEOUT` (grep over `tests/` returns nothing). Reverting to the default connect timeout changes no test outcome. Blocking (acceptance relies on an untested property).
- **breaker never opens** → covered. `test_breaker_opens_after_threshold_failures` and `test_read_route_returns_fast_when_db_hangs` both depend on the breaker opening.
- **read-only route blocked when breaker open** → covered. `test_read_route_returns_fast_when_db_hangs` / `_when_db_raises` assert 200 under an open breaker.
- **degraded mode returns admin** → partially survives. No test asserts the degraded user's `role == "viewer"`; the property is enforced by the `degraded` flag in `ensure_role` (`api/deps.py:315`) which 503s before the role check, and `test_write_route_returns_503_when_breaker_open` covers that. Functional safety holds; the specific role value is untested (defense-in-depth gap).
- **drop LIMIT / days bound** → covered in intent. `test_days_param_max_capped` (days=2000→422), `test_limit_param_max_capped` (limit=10000→422) would fail if the `le=` bounds are removed — but these tests are themselves currently red (finding 1), so the coverage does not presently run green.

## Verified (non-blocking)

1. **`app.yaml` literal port — PASS.** `app.yaml:6-7` uses `"8000"`; `resources/app.yml:8` also uses literal `8000`. No `${DATABRICKS_APP_PORT}` shell-expansion string remains.
2. **ibapi / pyspark excluded from app requirements — PASS.** `requirements.txt` contains neither `ibapi` nor `pyspark`; both were moved out (ibapi removed, mlflow/yfinance/etc. moved to `requirements-dev.txt`). All `pyspark` imports in `api/`/`agent/` are deferred (inside function bodies, e.g. `agent/tools_retrieval.py:59,153,353`, `api/services/hybrid_retriever.py:230,265`), so `import api.main` does not require pyspark.
3. **`api/deps.py` resilience core — PASS on mechanics.**
   - Role cache `_RoleCache` (`:63-95`) TTL 300 s default, `threading.Lock`, and `get` evicts on `monotonic() >= expires_at` — a cached role never outlives its TTL.
   - `_CircuitBreaker` (`:99-152`) threshold 3, cooldown 30 s, lock-guarded; `is_open` half-opens after cooldown and `record_success` resets.
   - Degraded path (`:284-301`) returns `role="viewer", degraded=True`; `ensure_role` (`:304-324`) raises 503 on `degraded` **before** the role membership check, so degraded mode cannot grant write/admin.
   - Read routes (`signals`, `market`, `analytics`) depend only on `get_current_user`; write routes (`watchlists` POST, `orders`) depend on `require_role("trader")` → 503 fast when degraded. Verified in `api/routes/{signals,market,analytics,watchlists,orders}.py`.
   - Tests `tests/api/test_resilience.py` (9) and `tests/api/test_auth.py` (4) pass.
4. **`/api/market/{symbol}` bounded query — PASS on code.** `api/routes/market.py:27-36`: `days` default 252, `ge=1, le=1000`; `limit` default/max 5000; symbol normalized via `normalize_symbol` (injection-shaped symbol → 422). `db/delta_adapter.py:90-100` selects explicit column lists and applies `.limit(limit)`. Parameterized, no f-string SQL. Note: the route still reads `gold_options_features` twice (once via the `market_features` ohlcv⊗opts join, once via `get_options_features`), so "single options query" is only partially met — flagged as non-blocking below.
5. **`resources/app.yml` Lakebase resource + `docs/DEPLOYMENT.md` grants — PASS on content.** `resources/app.yml:14-18` declares `database: {instance: evangoh-capstone-lakebase, permission: CAN_CONNECT_AND_CREATE}`. `docs/DEPLOYMENT.md:118-133` documents `USAGE` on schema, `SELECT,INSERT` on `users`, and `SELECT/INSERT/UPDATE` (no DELETE) on watchlists/orders/positions plus `SELECT/INSERT` on the remaining operational tables; no `CREATE`/`ALL`/admin. Least privilege.
6. **Frontend build — PASS.** `cd frontend && npm ci && npm run build` → `vite v5.4.21` built `dist/index.html` + `assets/*` cleanly.

## Non-blocking notes

- **No AST-scan test was added** even though BUILD item 1 calls for one ("Test: … AST scan"). The scan I ran manually flags the gaps in findings 2–3, plus two further undeclared top-level third-party imports reachable from `api/`: `langsmith` (`api/services/chat_engine.py:5`) and `edgar` (`api/services/sec_client.py:7`) — neither in Claude's explicit list but both would be caught by the required AST scan and are likely needed by the agent/SEC paths.
- **Single options query** (BUILD item 2): the market route issues a second read of `gold_options_features` via `get_options_features` in addition to the join inside `market_features`. Functionally correct, mildly redundant; not a correctness bug.
- **`tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms`** fails with `pytest-timeout (>30.0s)` in isolation. `ml/` is untouched by these 5 commits; appears to be a slow/pre-existing test (environmental), not this round's defect. Included in the failing set only insofar as the acceptance command reports 8 failures total.
- **`api/deps.py:161` `lakebase_status()`** reads `len(_role_cache._store)` without the lock — benign racy length in a status endpoint.
- **`docs/DEPLOYMENT.md:105-111`** shows the Lakebase resource as a top-level `resources:` list, while `resources/app.yml` actually nests it under `resources.apps.quant_platform.resources`. Minor doc/impl mismatch; `databricks bundle validate` is Claude's job.
- **Frontend banner** (BUILD item 1, not in the CHECK list): no global "Account services unavailable" banner exists; only `SystemHealth` shows a degraded dependency count.

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **8 failed** (7 × `tests/api/test_market.py` timeout; 1 × `tests/ml/test_ablation.py` timeout), `1478 passed, 97 skipped, 24 deselected` — FAIL (blocking, finding 1).
- `python3 -m pytest tests/api/test_market.py -x -q` → `1 failed in 32.71s` (`test_default_days_param` timeout; root cause is real-Lakebase pool retry, not the assertions).
- `python3 -m pytest tests/api/test_resilience.py tests/api/test_auth.py -q` → pass (13 tests; they isolate `db.lakebase.get_lakebase`).
- manual AST scan of `api/` + `agent/` third-party imports vs `requirements.txt` → flagged `dotenv` (python-dotenv), `yaml` (pyyaml), plus `langsmith`, `edgar` as undeclared; `pyspark` correctly deferred.
- `cd frontend && npm ci && npm run build` → pass (built in 1.73s).

===VERDICT END===
