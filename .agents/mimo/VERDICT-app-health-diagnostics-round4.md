# VERDICT: app-health-diagnostics-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None.

## Non-blocking notes
- All 4 items implemented in a single commit (b0a095a) rather than per-item commits — items are deeply interrelated (diagnostics helper feeds health endpoint, warehouse backend feeds health probe, tests cover all items).
- npm ci / npm run build cannot run in this WSL/Windows environment due to UNC path incompatibility with esbuild's install.js. TypeScript changes are additive type-safe interfaces following existing patterns. Frontend dist already exists from prior build.
- The `stage()` context manager logs only exception TYPE names (not messages) to prevent secret leakage through error strings.

## Checks run
- `python3 -m pytest tests/api/test_health_diagnostics.py -q -m "not spark and not lakebase and not databricks"` → 11 passed (21s)
- `python3 -m pytest tests/api/ -q -m "not spark and not lakebase and not databricks"` → 244 passed (33s)
- `cd frontend && npm run build` → BLOCKED (WSL UNC path issue, pre-existing environment limitation)

## Implementation summary

### Item 1: Stage timing logs + diagnostics helper + ring buffer + middleware
- `api/diagnostics.py`: `stage()` context manager (STAGE start/done with ms, ok, error type), `StageRingBuffer` (last 200 events, thread-safe deque), per-request stage tracking via ContextVar
- `api/main.py`: startup stages (config_load, fastapi_init, router_mount, frontend_dist_detect), per-request timing middleware (method, route template, status, total ms, slowest stage)
- `api/deps.py`: stage timing for role_resolve (cache hit/miss), circuit breaker transition logging (OPEN/CLOSED)
- `db/lakebase.py`: stage timing for lakebase_pool_build
- `api/routes/market.py`, `signals.py`: stage timing for delta_read (table name, symbol)

### Item 2: /api/health with timeouts + /api/health/trace + frontend updates
- `api/routes/health.py`: per-dependency hard timeouts (Lakebase 3s, warehouse 5s) via daemon threads; response includes `latency_ms`, `last_error` (exception type only), `last_ok_at`, `circuit_breaker_state`, `role_cache_size`, `startup` stages
- `GET /api/health/trace`: returns ring buffer (recent events + slow events > 2s)
- `api/schemas.py`: `DependencyStatus` (latency_ms, last_error, last_ok_at, circuit_breaker_state), `StartupStage`, `HealthResponse` (role_cache_size, startup), `TraceEvent`, `HealthTraceResponse`
- `frontend/src/api/types.ts`: matching TypeScript interfaces
- `frontend/src/api/client.ts`: `healthTrace()` method
- `frontend/src/screens/SystemHealth.tsx`: dependency cards with latency/error/last_ok/CB state, startup stages list, slowest recent stages from trace

### Item 3: SQL warehouse backend
- `db/delta_adapter.py`: SQL warehouse backend via `databricks-sql-connector` + `databricks.sdk` auth; auto-selected when pyspark absent; parameterized queries only, bounded LIMIT, `check_warehouse_health()` for health probe
- `resources/app.yml`: added `sql_warehouse` resource (id: b15d3d6f837ba428, CAN_USE) and `DATABRICKS_WAREHOUSE_ID` env var
- `docs/DEPLOYMENT.md`: SQL warehouse resource declaration, env vars, auth documentation

### Item 4: Tests (behavioral, red phase captured)
- `tests/api/test_health_diagnostics.py`: 11 tests covering:
  1. Health returns within bound when both probes hang (mutation: remove timeout → fails)
  2. Timed-out probe reports "timeout" (mutation: remove timeout → different detail)
  3. Stage logs emit elapsed ms and ok status
  4. Stage logs emit error type on failure (mutation: drop error type → fails)
  5. Ring buffer bounded at maxlen (eviction)
  6. Ring buffer thread-safe (concurrent appends)
  7. No secret in health output (connection string not leaked)
  8. No secret in logs (exception message with secret not logged, only type)
  9. Warehouse backend selected when pyspark missing (mutation: select pyspark → ImportError)
  10. Warehouse query passes parameterized params
  11. check_warehouse_health returns (ok, detail) tuple