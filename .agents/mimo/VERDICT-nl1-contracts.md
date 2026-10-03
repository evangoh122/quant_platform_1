# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
(none)

## Non-blocking notes
- `silver_ohlcv_day_adjusted` is declared in `source_schemas_v1.yaml` with `status: pending_corporate_actions_lane` — no DDL exists yet. The serving views are documented as proposals only; the admin must choose the correct DDL variant when the lane merges.
- The `adjusted_source_available` flag defaults to `false` in `policy_bounds_v1.yaml`. The fallback path (bronze + split-safety rejection) is the active path until the corporate-actions lane merges.
- The adjusted DDL uses a LEFT JOIN to `silver_ohlcv_day_adjusted` in `serve_daily_equity_metrics_v1` to source `return_1d`. NULL `return_1d` rows (data-quality breaks) are filtered by `WHERE return_1d IS NOT NULL` before volatility/drawdown computation — documented but not testable against a live table until the lane merges.
- The `suspected_split` column in the adjusted `serve_bounded_daily_bars_v1` is hardcoded to `FALSE` because the adjusted source has already handled corporate actions. This is intentional.

## Checks run
- `python3 -m pytest -q tests/analytics_nl` → 223 passed
- `python3 -m pytest -q --ignore=tests/lakebase` → 761 passed, 67 skipped
- `wsl file ...` on all changed files → no CRLF (LF only)
- `wsl git diff --name-only` → only 7 expected files changed, no secrets, no `.agents/dispatch.sh`

## Summary of changes

### source_schemas_v1.yaml
- Added `silver_ohlcv_day_adjusted` table (25 columns, `status: pending_corporate_actions_lane`)
- Removed `adj_close` derived alias from `serve_daily_prices_v1` and `serve_bounded_daily_bars_v1`
- Updated `input_from` to `silver_ohlcv_day_adjusted` with `fallback_input_from: bronze_ohlcv_day`
- Updated `serve_daily_equity_metrics_v1` derived column comments for return_1d sourcing

### NL1_PROPOSED_SERVING_VIEWS.md
- Removed all `close AS adj_close` aliases (lines 48, 240 in round 4)
- Added primary (adjusted) and fallback (unadjusted) DDL for `serve_daily_prices_v1`, `serve_daily_equity_metrics_v1`, `serve_bounded_daily_bars_v1`
- Updated corporate-action safety policy with dual-mode documentation (adjusted vs fallback)
- Updated Silver vs Gold routing table

### policy_bounds_v1.yaml
- Added `adjusted_source_available: false` flag

### policy.py
- Added `adjusted_source_available: bool = False` to `PolicyBounds`
- Updated `load_policy_bounds()` to read the flag
- Updated corporate-action check: skips split-safety rejection when `adjusted_source_available=True`

### Tests
- `test_source_schema.py`: Updated registry column check to handle `fallback_input_from`, added tests for `silver_ohlcv_day_adjusted` columns/status, added mutation test proving `close AS adj_close` is absent from DDL
- `test_ddl.py`: Updated `test_close_used_not_adj_close_source` to assert alias is absent, added `TestDDLAdjustedSource` class (6 tests)
- `test_policy.py`: Added `TestAdjustedSourceFallback` class (9 tests) covering both modes and other-violation passthrough