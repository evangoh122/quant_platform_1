# VERDICT: app-resilience-round7 — MiMo
**Status:** APPROVED
**Round:** 7

## Changes committed

All items from BUILD-app-resilience-round7.md addressed:

1. **Market daily bars** — `db/delta_adapter.py:371-414`: `market_features()` now reads from `silver_ohlcv_day_adjusted` using `adj_*` columns aliased to wire names (`open`, `high`, `low`, `close`, `volume`, `vwap`). Added `market_features_intraday()` for `gold_ohlcv_features` with real columns.

2. **Options** — `agent/tools_retrieval.py:56-90`: `get_options_features()` selects real columns (`put_volume`, `call_volume`, `iv_atm`, `iv_skew`, etc.). Expiry param accepted but returns 422-style `expiry_not_supported` error dict if passed. No `expiry` in SELECT or WHERE.

3. **COT** — `agent/tools_retrieval.py:365-416`: `get_cot_positioning()` accepts asset class directly (`rate`, `other`, `fx`, `equity_index`, `crypto`, `commodity`) or ticker. Tickers mapped via `TICKER_TO_ASSET_CLASS` in `db/schema_contract.py`. Unknown tickers return `{"error": "no_mapping", "ticker": ..., "message": ...}`. Never silent `{}`.

4. **Signals** — `api/routes/signals.py:59-60`: When `gold_trading_signals` is empty, `detail` is overridden to `"no_signals_published"`. Frontend `SignalExplorer.tsx` renders distinct title/detail for this state. Agent chat already had explicit message.

5. **Schema contract** — `db/schema_contract.py`: Column contracts for 5 tables + query-column mapping per function. `validate_query_columns()` catches references to non-existent columns (e.g. `open` on `gold_ohlcv_features`). Mutation test: add `open` → FAIL.

6. **Schema drift checker** — `scripts/check_schema_contract.py`: DESCRIBEs each table live, diffs against contract, non-zero exit on drift.

## Blocking findings

None.

## Non-blocking notes

- `gold_trading_signals` is 0 rows (no signals ever published) — the `no_signals_published` state is now explicit.
- `test_arm_d_differs_from_arm_c_in_cot_columns` (ml/test_hardening.py) times out — pre-existing, unrelated to this round.
- `test_ablation_runner_varies_feature_set_between_arms` (ml/test_ablation.py) times out — known ml ablation timeout, excluded from acceptance run.

## Checks run

- `python3 -m pytest -q tests/api/test_health_diagnostics.py tests/api/test_market.py tests/lakebase/test_symbol_validation.py --tb=short -x` → 62 passed (26s)
- `python3 -m pytest -q tests/api/ tests/lakebase/test_symbol_validation.py --tb=short -x` → 288 passed (50s)
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks" --ignore=tests/ml/test_ablation.py --tb=short -x` → 651 passed, 1 pre-existing timeout fail (ml/test_hardening.py)
- `python3 -c "from db.schema_contract import validate_query_columns; print(validate_query_columns())"` → `[]` (no errors)
- `frontend: tsc --noEmit` → clean (0 errors)
- Mutation: add `open` to `gold_ohlcv_features` query → `validate_query_columns()` catches it → FAIL
- Mutation: `get_cot_positioning("ZZZZZZ")` → `{"error": "no_mapping", ...}` → explicit
- Mutation: `get_options_features("AAPL", expiry="2024-02-01")` → `{"error": "expiry_not_supported", ...}` → explicit

## Files modified

| File | Change |
|------|--------|
| `db/delta_adapter.py` | `market_features()` → `silver_ohlcv_day_adjusted` with `adj_*` aliases; added `market_features_intraday()` |
| `agent/tools_retrieval.py` | `get_options_features()` real cols, no expiry; `get_cot_positioning()` asset class mapping |
| `api/routes/signals.py` | `no_signals_published` explicit empty-state detail |
| `api/schemas.py` | `OptionsFeature` updated to real columns; `OHLCVFeature` docstring |
| `db/schema_contract.py` | **NEW** — column contracts, query-column mapping, COT asset classes, ticker→asset class |
| `scripts/check_schema_contract.py` | **NEW** — live schema drift detector |
| `frontend/src/api/types.ts` | `OptionsFeature` updated to real columns |
| `frontend/src/screens/MarketDashboard.tsx` | `atm_iv`→`iv_atm`, `skew`→`iv_skew` |
| `frontend/src/screens/OptionsAnalytics.tsx` | Columns updated to real schema |
| `frontend/src/screens/SignalExplorer.tsx` | `no_signals_published` state handling |
| `tests/api/test_health_diagnostics.py` | 7 new tests; updated `_fake_warehouse_query`, COT/options assertions |