# VERDICT: app-resilience-round8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None.

## Changes implemented

### 1. scripts/check_schema_contract.py — sys.path + LIMIT fix
- `scripts/check_schema_contract.py:13-17` — added repo root to `sys.path` so `python3 scripts/check_schema_contract.py` resolves `db` module.
- `db/delta_adapter.py:163-165` — `_warehouse_query` now only appends `LIMIT` to `SELECT` statements. `DESCRIBE`/`SHOW`/`SET` pass through unmodified. This fixes the `PARSE_SYNTAX_ERROR` on warehouse.
- Test: `tests/test_check_schema_contract.py::test_script_importable_from_repo_root` — subprocess runs `--help`, exits 0.
- Test: `tests/api/test_health_diagnostics.py::test_warehouse_query_no_limit_on_describe` — DESCRIBE has no LIMIT in executed SQL.
- Test: `tests/api/test_health_diagnostics.py::test_warehouse_query_limit_on_bare_select` — bare SELECT gets LIMIT appended.
- Test: `tests/api/test_health_diagnostics.py::test_warehouse_query_preserves_existing_limit` — SELECT with existing LIMIT is not double-limited.

### 2. get_latest_signal empty state
- `agent/tools_retrieval.py:46` — returns `{"status": "no_signals_published"}` instead of `{}` when table is empty. Matches the signals route behavior.
- Test: `tests/api/test_health_diagnostics.py::test_get_latest_signal_empty_returns_no_signals_published` — asserts exact dict shape.

### 3. Market daily bars: event_date, vwap, price_basis, options bounding
- `db/delta_adapter.py:380-395` — `market_features` warehouse/pyspark paths return `event_date` (not aliased `feature_ts`).
- `api/schemas.py:62` — `OHLCVFeature.event_date` replaces `feature_ts`; added `price_basis: str = "split_adjusted"`.
- `api/routes/market.py:72-73` — route reads `event_date` (falls back to `feature_ts`), sets `price_basis="split_adjusted"`.
- `api/routes/market.py:60` — options limit uses `min(days, limit)` (default 252 rows).
- `frontend/src/api/types.ts:33` — `OHLCVFeature.event_date` + `price_basis`.
- `frontend/src/screens/MarketDashboard.tsx:15,85` — column header "Date", rowKey uses `event_date`.
- Test: `tests/api/test_market.py::test_options_bounded_by_days` — days=50 → options limit=50.
- Test: `tests/api/test_market.py::test_ohlcv_uses_event_date_and_price_basis` — asserts `event_date`, `price_basis`, no `feature_ts`.
- Test: `tests/api/test_market.py::test_default_days_param` — updated assertion: options limit=252 (was 5000).

## Checks run
- `python3 -m pytest -q tests/api/ tests/test_check_schema_contract.py -m "not spark and not lakebase and not databricks"` → **278 passed**
- `npm run build` (frontend) → **✓ built in 2.16s**
- `git diff --stat` → 10 files changed, 191 insertions, 14 deletions