# VERDICT: app-resilience-round3 — MiMo

**Status:** APPROVED
**Round:** 3 (build)

## Items completed

### 1. Bounded total Lakebase connection establishment
- `db/lakebase.py`: Changed `_build_pool` to use `open=False` + `pool.wait(timeout=LAKEBASE_CONNECT_TIMEOUT)` so a disabled/hanging endpoint raises `PoolTimeout` within ~3 s instead of retrying 30+ s.
- Added `test_first_request_bounded_when_pool_hangs`: verifies first request against a hanging pool returns 200 (degraded) within <5 s. Mutation "remove timeout bound" would cause test to hang.

### 2. Isolated test_market.py from live Lakebase
- `tests/api/test_market.py`: Added `fake_lakebase` fixture dependency to local `client` fixture. All 7 market tests now run offline (1.03 s) without touching real endpoint.

### 3. requirements.txt + AST-scan test
- Added `python-dotenv`, `pyyaml`, `langsmith`, `edgartools`, `finvizfinance` to `requirements.txt`.
- Created `tests/test_requirements_completeness.py`: AST-scan walks `api/agent/db/config`, collects module-scope third-party imports, maps import→distribution, fails if any missing. `ibapi`/`pyspark` remain absent (deferred). Mutation: drop `pyyaml` → test FAILS.

### 4. Degraded user role test
- Added `test_degraded_user_role_is_viewer`: verifies degraded user gets `role="viewer"`, read route returns 200, write route (`require_role("trader")`) returns 503 with "Account services unavailable".

### 5. Non-blocking cleanups
- `api/deps.py`: Added `_RoleCache.size()` with lock; `lakebase_status()` now uses thread-safe `size()` instead of raw `len(_role_cache._store)`.
- `docs/DEPLOYMENT.md`: Fixed Lakebase resource nesting to match `resources/app.yml` (nested under `resources.apps.quant_platform.resources`).
- Redundant options read in market route: left as-is — `market_features` join returns timestamp-matched options, `get_options_features` returns all options for symbol (different data scopes).

## Pre-existing issues (not from this round)
- `tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms` — timeout (>30 s), pre-existing, untouched by this round.
- `tests/ml/test_hardening.py::test_arm_d_differs_from_arm_c_in_cot_columns` — timeout (>30 s), pre-existing, untouched by this round.
- Frontend npm ci fails in WSL/Windows interop (esbuild path issue); `frontend/dist/` exists from prior build.

## Checks run
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2 failed** (both pre-existing ml timeouts), **1487 passed**, 97 skipped, 24 deselected — PASS (all app-resilience tests green).
- `python3 -m pytest tests/api/test_market.py -xvs` → 7 passed in 1.03 s — PASS.
- `python3 -m pytest tests/api/test_resilience.py -xvs` → 13 passed — PASS.
- `python3 -m pytest tests/test_requirements_completeness.py -xvs` → 1 passed — PASS.
- `frontend/dist/` exists (prior build); npm ci blocked by WSL esbuild path interop.

## Mutation coverage
- **remove timeout bound** → FAILS (`test_first_request_bounded_when_pool_hangs` hangs/timeout).
- **drop pyyaml from requirements** → FAILS (`test_all_top_level_imports_declared_in_requirements`).
- **remove fake_lakebase from market client** → FAILS (7 market tests timeout on disabled endpoint).
- **degraded user role check** → COVERED (`test_degraded_user_role_is_viewer` asserts role=viewer + 503 on write).