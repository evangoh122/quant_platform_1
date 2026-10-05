# VERDICT: app-resilience-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
- None.

## Non-blocking notes
- The known ml ablation timeout (`test_ablation_runner_varies_feature_set_between_arms`) fails as anticipated in the BUILD request — unrelated to this round's changes.
- `databricks-sql-connector>=3.0.0,<5` pin guards against future breaking changes in param style.

## Checks run
- `python3 -m pytest tests/api/test_health_diagnostics.py -q` → 31 passed
- `python3 -m pytest tests/api/test_resilience.py -q` → 11 passed
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → 1519 passed, 1 failed (known ml ablation timeout), 97 skipped
- `git diff --cached --stat` on commit 1 → 4 files, 170 insertions, 22 deletions
- `git diff --cached --stat` on commit 2 → 3 files, 363 insertions, 26 deletions
- `file` check on all modified files → all UTF-8 text (LF endings)
- Branch: `slice/app-frontend-deploy` (not main)

## Items implemented

### Item 1: Named parameter conversion (`:name` + dict)
- `db/delta_adapter.py`: `_warehouse_query` params changed from `Tuple` to `Dict[str, Any]`; `latest_signals` and `market_features` use `:symbol`/`:start_ts`/`:end_ts` markers.
- `agent/tools_retrieval.py`: `get_options_features` uses `:symbol`/`:expiry`; `get_cot_positioning` uses `:mapped_asset`.
- `requirements.txt`: pinned `databricks-sql-connector>=3.0.0,<5`.
- Tests: `_NamedParamValidatingCursor` rejects `%s`/`?` and validates `:name` keys match dict keys. 4 new tests cover `latest_signals`, `market_features`, `get_options_features`, `get_cot_positioning`. Mutation: put back one `%s` → FAIL.

### Item 2: Background connection warming
- `db/delta_adapter.py`: `warm_warehouse_connection()` starts a background thread; state tracked as idle/warming/ready/error via `get_warm_state()`.
- `check_warehouse_health()` returns `(False, "connecting")` while warming.
- `api/main.py`: `warm_warehouse_connection()` called in `create_app()` for non-demo mode.
- Tests: warming state transitions, error on failure, idempotent, health probe reports warming. Fake slow connect test.

### Item 3: cursor.cancel() + bounded semaphore
- `db/delta_adapter.py`: On timeout, `cursor.cancel()` is called before `cursor.close()`. `_query_semaphore` (bounded to `_MAX_CONCURRENT_QUERIES=10`) caps in-flight queries. `Semaphore.acquire(timeout=...)` prevents infinite blocking.
- Tests: hanging cursor → cancel() called AND timeout error within bound; 20 hanging calls → bounded live threads; semaphore timeout when all slots busy. Mutation: drop cancel() → FAIL.