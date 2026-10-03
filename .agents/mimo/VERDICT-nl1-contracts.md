# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
None (all 4 DeepSeek blocking issues resolved).

### Resolved issues

1. **[docs/NL1_PROPOSED_SERVING_VIEWS.md:~100-111] `SELECT *` in DDL → FIXED.**
   Replaced bare `SELECT *` in `with_vol` and `with_drawdown` CTEs with explicit
   column enumerations: `symbol, trade_date, adj_close, information_available_ts,
   return_1d` (with_vol) and `symbol, trade_date, adj_close, information_available_ts,
   return_1d, realized_vol_20d` (with_drawdown).

2. **[tests/analytics_nl/test_ddl.py:45-59] Vacuous `SELECT *` test → FIXED.**
   Replaced the OR-of-negations assertion with a whitespace-normalising regex
   approach: strip block/line comments, collapse all whitespace (including
   newlines), then match `\bSELECT\s+\*` and `\.\*`. Proved in /tmp that the
   old DDL (with `SELECT *`) FAILS the new test, and the fixed DDL PASSES.

3. **[tests/analytics_nl/test_policy.py:~274-287] Silver bounds never tested → FIXED.**
   Added `TestSilverBounds` class with 9 tests covering:
   - 2-year boundary: exactly 2 years (ACCEPT) vs 2 years + 1 day (REJECT)
   - 10-ticker boundary: exactly 10 (ACCEPT) vs 11 (REJECT)
   - 10,000-row boundary: exactly 10,000 (ACCEPT) vs 10,001 (contract-level rejection)
   - Missing entity scope: contract-level rejection (min_length=1)
   - REJECT exposes no SQL
   - volume.trend also Silver with same bounds

4. **[analytics_nl/data/semantic_registry_v1.yaml] No Silver entries → FIXED.**
   Registered `price.trend` and `volume.trend` as Silver entries with:
   - `layer: silver`, `serving_view: serve_bounded_daily_bars_v1`
   - `max_entities: 10`, `row_limit: 10000`
   - Served from new `serve_bounded_daily_bars_v1` view over `bronze_ohlcv_day`
   - DDL added to appendix with explicit columns and `information_available_ts` filter
   - Silver vs Gold routing table documented

## Non-blocking notes
- Fixed stale comment in `analytics_nl/registry.py:230` — "check all 8 metrics" → "check all 9 metrics".
- `serve_bounded_daily_bars_v1` view name avoids `silver_` physical table name pattern
  (would fail `TestRegistryNoPhysicalNames`).
- Pre-existing tests that used `price.trend` (now Silver) updated to use Gold pairs
  (`return.trend`, `volume.compare`) where they tested Gold-specific behavior.
- Silver row boundary (10,000) equals CanonicalIntent contract max (le=10000), so the
  contract is the first line of defense for row limits.

## Checks run
- `python3 -m pytest -q tests/analytics_nl` → **175 passed** (0 failures)
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match** (exit 0)
- `python3 -m pytest -q --ignore=tests/lakebase` → 175 passed, 22 collection errors
  (all pre-existing import failures from missing deps: loguru, pandas, numpy, duckdb, etc.)

## Files changed (round 3 delta)
```
docs/NL1_PROPOSED_SERVING_VIEWS.md             (SELECT * → explicit columns; Silver DDL + routing table)
analytics_nl/data/semantic_registry_v1.yaml    (+1 approved_view; price.trend + volume.trend → silver layer)
analytics_nl/registry.py                       (stale comment fix: 8 → 9)
tests/analytics_nl/test_ddl.py                 (SELECT * test: whitespace-normalising regex)
tests/analytics_nl/test_policy.py              (+9 Silver boundary tests; 3 existing tests updated for Gold pairs)
```

## Scope exclusions
- No API routes, HTTP/SSE code, or Databricks client changes
- No SQL compilation, LLM calls, or frontend code
- No changes to `.agents/dispatch.sh`
- No secrets or absolute paths in committed files
- LF line endings on all text files