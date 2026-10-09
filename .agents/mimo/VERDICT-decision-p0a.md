# VERDICT: decision-p0a — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
(none)

## Non-blocking notes
- Fix 2 uses weekday approximation only; NYSE holidays are not excluded. The helper is named `start_for_trading_days` with a docstring noting "weekday approximation" and the freshness detail includes "calendar_limited" for the UI.
- Fix 3 `market_price` was already `Optional[float]`; only `realized_pnl` and `unrealized_pnl` needed changing.

## Checks run
- `pytest tests/api/test_market.py tests/api/test_portfolio_null_pnl.py tests/api/test_trading_days.py tests/agent/test_tools_retrieval_ordering.py tests/gold/test_zscore_window_guard.py tests/gold/test_options_right_case.py tests/gold/test_pit_leakage.py tests/agent/test_contracts.py -v --timeout=60` → 76 passed
- `cd frontend && npx tsc --noEmit` → pass (0 errors)
- `cd frontend && npx vitest run` → 16 test files, 246 tests passed
- `cd frontend && npm run build` → built in 2.66s
- Mutation M1 (remove orderBy) → test_orderBy_called_before_limit FAILS (expected)
- Mutation M2 (replace helper with timedelta) → test_start_time_matches_helper_output FAILS (expected)
- Mutation M3 (coerce null to 0) → test_null_pnl_serializes_as_json_null FAILS (expected)
- Mutation M4 (remove count guard) → test_gold_sql_count_guard_produces_null_for_small_windows FAILS (expected)
- Mutation M5 (ignore weekends) → test_wednesday_back_5_trading_days FAILS (expected)
