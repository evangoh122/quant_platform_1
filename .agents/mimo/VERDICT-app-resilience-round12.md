# VERDICT: app-resilience-round12 — MiMo
**Status:** APPROVED
**Round:** 12

## Blocking findings
- None

## Non-blocking notes
- Full Python test suite (`-m "not spark and not lakebase and not databricks"`) cannot collect on Windows due to PyTorch DLL crash in `tests/rag/test_langgraph_engine.py` (unrelated to this change). Relevant subset (15 tests) passes cleanly.
- Frontend tests require running from a Windows-accessible path (UNC/WSL paths break vitest's module resolution). Tests verified by copying to temp dir.

## Checks run
- `python3 -m pytest tests/api/test_market.py tests/test_smoke_app.py -v` → 15 passed
- `cd frontend && npx vitest run` → 3 passed (1 MarketDashboard + 2 App)
- `cd frontend && npm ci --ignore-scripts && npx tsc --noEmit && npx vite build` → passed, 48 modules
- `git diff --check` → clean

## Commits
1. `7c5128a` fix: correct source labels to silver_ohlcv_day_adjusted for daily OHLCV
   - `api/routes/market.py:64,86,87` → `silver_ohlcv_day_adjusted`
   - `MarketDashboard.tsx:85` → `silver_ohlcv_day_adjusted`
   - Added `test_ohlcv_source_label_is_silver` backend test
   - Mutation: revert label → test FAIL ✓
2. `dd10994` fix: smoke tests mock all endpoints so frontend check is the sole failing condition
   - `test_smoke_fails_on_json_hint` and `test_smoke_fails_on_non_html` now mock all 7 endpoints
   - Asserts `result is False` and captures `"FAIL  GET /"` in stdout
   - Mutation: `_check_frontend_build()` always returns True → both tests FAIL ✓
3. `bd150e5` feat: add Vitest frontend tests for max-date selection and Lakebase health banner
   - Added vitest, @testing-library/react, @testing-library/jest-dom, jsdom as devDependencies
   - Added `npm test` script, vitest config with jsdom environment
   - `MarketDashboard.test.tsx`: verifies MAX event_date from unsorted rows (mutation: `data[0]` → FAIL ✓)
   - `App.test.tsx`: verifies banner shows on Lakebase degraded/breaker open, hides when healthy (mutation: hard-code false → FAIL ✓)