# VERDICT: app-resilience-round11 — MiMo

**Status:** APPROVED
**Round:** 11

## Scope

Fixed 4 blocking items from DeepSeek round 9-10 verdict. Test-only changes
plus a tiny refactor (item 3) to expose real SQL query strings as module-level
constants. Production behavior unchanged.

## Changes per item

### Item 1: Lakebase pool open/closed state + token-mint timeout
- `tests/api/test_resilience.py`: `BlockingPool` now raises `PoolClosed` when
  `wait()` is called before `open()`, `PoolTimeout` after `open()` — models
  real `psycopg_pool` behaviour.
- Added `test_pool_closed_without_open_raises`: calls `_build_pool()` directly
  and asserts the exception is NOT `PoolClosed`. Mutation: delete
  `pool.open(wait=False)` → `PoolClosed` raised → FAIL.
- Added `test_token_mint_subprocess_timeout`: fakes `subprocess.run` with a
  sleep command, asserts `RuntimeError("timed out")`. Mutation: drop
  `timeout=` → subprocess blocks forever → test hangs → FAIL.

### Item 2: Concurrency counter uses shared state
- `tests/api/test_health_diagnostics.py`: Replaced `threading.local()` with
  shared `state = {"cur": 0, "max": 0}` + `threading.Lock()`.
- `HangingCursor.execute()` increments on entry, sleeps, (implicitly)
  decrements via thread exit.
- Launches 6 concurrent queries with semaphore size 2. Asserts
  `state["max"] == 2` (exact equality, not ≤2 — proves the limit was reached).
- Mutation: remove semaphore acquire → all 6 start → max=6 → FAIL.

### Item 3: Schema contract from REAL SQL
- `db/delta_adapter.py`: Added `_INTRADAY_COLS`, `_build_latest_signals_query()`,
  `_build_market_features_daily_query()`, `_build_market_features_intraday_query()`.
  Production functions `latest_signals()`, `market_features()`,
  `market_features_intraday()` now use these builders.
- `agent/tools_retrieval.py`: Added `_OPTIONS_COLS`, `_COT_COLS`,
  `_build_options_query()`, `_build_cot_query()`. Production functions
  `get_options_features()`, `get_cot_positioning()` now use these.
- `db/schema_contract.py`: `validate_actual_queries()` now imports the real
  builders, builds actual SQL, parses selected/filtered identifiers.
  Deleted all duplicated hardcoded SQL.
- Mutation: add `open` to `_INTRADAY_COLS` → `test_actual_queries_match_contract`
  catches it → FAIL.

### Item 4: Requirements scan walks full AST
- `tests/test_requirements_completeness.py`: Renamed `_scan_top_level_imports`
  → `_scan_all_imports`. Uses `ast.walk(tree)` instead of
  `ast.iter_child_nodes(tree)` to catch deferred imports inside function bodies.
- For `ImportFrom` nodes, adds `module.alias_name` (e.g. `from databricks import
  sql` → `databricks.sql`) so dotted mappings in `_IMPORT_TO_DIST` are reachable.
- `_DEFERRED_ALLOWED` check now covers sub-packages (`pyspark.sql` etc.).
- Mutation: remove `databricks-sql-connector` from `requirements.txt` → FAIL.

## Blocking findings

None.

## Non-blocking notes

- `test_warehouse_available_detects_installed_connector` fails on this Windows
  env because `databricks-sql-connector` is not installed (pre-existing env
  issue, not caused by these changes — passes in WSL with connector 4.6.0).
- Full suite `python3 -m pytest -q -m "not spark and not lakebase and not
  databricks"` crashes on Windows due to torch DLL initialization failure
  (`tests/rag/test_langgraph_engine.py` collection). Pre-existing env issue.

## Checks run

- `python3 -m pytest tests/api/test_resilience.py -q -m "not spark and not lakebase and not databricks"` → **13 passed**
- `python3 -m pytest tests/api/test_health_diagnostics.py -q -m "not spark and not lakebase and not databricks"` → **46 passed, 1 failed** (pre-existing env)
- `python3 -m pytest tests/test_requirements_completeness.py -q` → **1 passed**
- `python3 -m pytest tests/api/test_resilience.py tests/api/test_health_diagnostics.py tests/test_requirements_completeness.py tests/test_smoke_app.py tests/test_app_yaml.py tests/api/test_frontend_serving.py -q -m "not spark and not lakebase and not databricks"` → **76 passed, 1 failed** (pre-existing env)

### Mutation re-runs (in mutation copies):
- Mutation 1: delete `pool.open(wait=False)` → `test_pool_closed_without_open_raises` **FAILED** ✓
- Mutation 2: remove semaphore acquire → `test_warehouse_query_semaphore_bounded` **FAILED** (max=6, expected 2) ✓
- Mutation 3: add `open` to `_INTRADAY_COLS` → `test_actual_queries_match_contract` **FAILED** ✓
- Mutation 4: remove `databricks-sql-connector` from requirements → `test_all_top_level_imports_declared_in_requirements` **FAILED** ✓

## Commits

- `99eab8b` fix(r11-item1): Lakebase pool fake models real state + token-mint timeout test
- `1e9b3e9` fix(r11-item2): concurrency counter uses shared lock-guarded state
- `ee90483` fix(r11-item3): schema contract derives from real SQL query constants
- `94ec685` fix(r11-item4): requirements scan walks full AST including function bodies