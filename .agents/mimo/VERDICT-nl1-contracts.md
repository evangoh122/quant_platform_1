# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings

None. All 4 fixes from BUILD-nl1-round4.md implemented and verified.

### Fixes applied

1. **[docs/NL1_PROPOSED_SERVING_VIEWS.md + analytics_nl/data/semantic_registry_v1.yaml] Real columns only → FIXED.**
   - Replaced `trade_date` with `event_date` in all daily views (serve_daily_prices_v1, serve_daily_equity_metrics_v1, serve_relative_performance_v1, serve_bounded_daily_bars_v1).
   - Replaced `trade_date` with `feature_ts` in serve_options_metrics_v1.
   - Replaced `adj_close` with `close` as source column; `adj_close` retained as alias of `close` for backward compatibility.
   - All 36 registry entries updated: `input_columns`, `allowed_ordering`, `output_fields` now use real column names.
   - Added `price_adjustment: unadjusted` field to price.* entries.

2. **[docs/NL1_PROPOSED_SERVING_VIEWS.md] Daily point-in-time availability → FIXED.**
   - `information_available_ts` derived in serving views as `to_utc_timestamp(concat(event_date, ' 16:30:00'), 'America/New_York')`.
   - DST handled by Spark's `to_utc_timestamp` timezone function.
   - Documented in Assumptions section and per-view column notes.
   - For options, `information_available_ts` sourced directly from `gold_options_features`.

3. **[analytics_nl/contracts.py + analytics_nl/policy.py + analytics_nl/data/policy_bounds_v1.yaml + docs/NL1_PROPOSED_SERVING_VIEWS.md] Corporate-action safety → FIXED.**
   - Added `UNADJUSTED_CORPORATE_ACTION` to `PolicyReasonCode` enum in contracts.py.
   - Added `known_splits` field to `PolicyBounds` (loaded from policy_bounds_v1.yaml, empty by default).
   - Policy rejects metrics using unadjusted prices (return, realized_volatility, drawdown, momentum, relative_performance) over date ranges containing known splits for requested symbols.
   - `known_splits` table DDL proposed in serving views doc (to be populated by owner/admin).
   - `suspected_split` detector added to `serve_bounded_daily_bars_v1` view — flags rows where overnight |close/prev_close − 1| ≥ 0.4 and ratio within 3% of 1/k or k for k ∈ {2,3,4,5,10,20}.
   - 11 corporate-action tests added to test_policy.py (5 rejection, 4 non-rejection, 1 empty-splits, 1 outside-window).

4. **[analytics_nl/data/source_schemas_v1.yaml + tests/analytics_nl/test_source_schema.py] Schema-truth test → FIXED.**
   - Created `source_schemas_v1.yaml` with authoritative column lists for `bronze_ohlcv_day` and `gold_options_features`.
   - Includes `derived_columns` section documenting all columns produced by each serving view stage.
   - Test `test_registry_columns_exist_in_source` verifies every registry `input_column` exists in source schema or is defined by an earlier view stage.
   - Tests prove `adj_close`, `trade_date`, and `information_available_ts` are NOT in `bronze_ohlcv_day` source schema.
   - Test `test_adj_close_is_derived_alias` proves reintroducing `adj_close` as a source column would fail.

## Non-blocking notes

- `adj_close` is retained as an alias of `close` in serving views for backward compatibility with downstream consumers. The registry marks `price_adjustment: unadjusted`.
- `serve_relative_performance_v1` still hardcodes `WHERE symbol = 'SPY'`; the registry declares benchmark enum [SPY, QQQ, RSP]. Documented as "defaults to SPY; parameterized queries should substitute".
- `DateExpression.relative` remains a free-form string (DeepSeek blocking finding 2 from check2 — not in MiMo scope for this round).
- The `known_splits` table is proposed but not populated; the policy check is defensive (empty table → no rejections from this rule).
- The `suspected_split` detector uses heuristics; false positives are possible for extreme but legitimate price moves.

## Checks run

- `python3 -m pytest -q tests/analytics_nl` → **205 passed** (0 failures)
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match** (exit 0)
- `python3 -m pytest -q --ignore=tests/lakebase` → **743 passed, 67 skipped** (0 failures)

## Files changed (round 4 delta)
```
docs/NL1_PROPOSED_SERVING_VIEWS.md             (trade_date→event_date, adj_close→close, PIT derivation, known_splits DDL, suspected_split detector)
analytics_nl/data/semantic_registry_v1.yaml    (trade_date→event_date, adj_close→close, feature_ts for options, price_adjustment field)
analytics_nl/contracts.py                      (+UNADJUSTED_CORPORATE_ACTION reason code)
analytics_nl/policy.py                         (corporate-action rejection logic, known_splits loading)
analytics_nl/data/policy_bounds_v1.yaml        (+known_splits section, empty by default)
analytics_nl/data/source_schemas_v1.yaml       (NEW: authoritative source column lists)
analytics_nl/schemas/*.json                    (regenerated — includes new reason code)
tests/analytics_nl/test_ddl.py                 (+event_date/feature_ts/close tests, PIT derivation test, unadjusted/suspected_split tests, known_splits tests)
tests/analytics_nl/test_policy.py              (+11 corporate-action rejection tests)
tests/analytics_nl/test_source_schema.py       (NEW: schema-truth tests)
tests/analytics_nl/test_contracts.py           (chart tests updated: event_date/close; +UNADJUSTED_CORPORATE_ACTION test)
```

## Scope exclusions
- No API routes, HTTP/SSE code, or Databricks client changes
- No SQL compilation, LLM calls, or frontend code
- No changes to `.agents/dispatch.sh`
- No secrets or absolute paths in committed files
- LF line endings on all text files