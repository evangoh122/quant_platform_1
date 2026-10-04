===VERDICT START===
# VERDICT: nl1-round13 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 13

Range verified: `eaccbed..HEAD` (implementation commits f9779a5 "fix(tests): parse CTEs with depth tracking…", 00dcf5b "feat: enforce CoverageStatus enum…", 689ca9d "fix(ddl): guard return_1d > -1…"). Source read-only; all mutations performed in `/tmp/nl1r13-mut-*` copies and discarded.

## Blocking findings

None.

## Mutation proofs (re-run of round-12 mutations + round-13 build items)

1. **PIT as-of before window** — serve_options_metrics_v1: removed `WHERE information_available_ts <= :as_of` from `as_of_filtered` and added `AND information_available_ts <= :as_of` to the final `WHERE rn = 1`.
   - `pytest …::TestDDLPITSafetyAsOfBeforeWindow::test_all_views_have_as_of_before_window -q` → **1 failed** (returncode 1, "SQL block 6 has window functions but no as-of filter … in a preceding CTE"). Expected FAIL. Proof holds.
   - Repeat (serve_daily_equity_metrics_v1 fallback): removed as_of from `daily_prices` CTE, added `WHERE information_available_ts <= :as_of` to final `FROM with_drawdown` → **1 failed** (returncode 1). Proof holds.

2. **Column extraction / registry mismatch** — renamed `close_price` → `close_price_bogus` in `price.trend` output_fields (semantic_registry_v1.yaml).
   - `pytest …::TestRegistryColumnsMatchViewOutput::test_registry_output_fields_match_view_columns -q` → **1 failed** (returncode 1, "output_field 'close_price_bogus' not found in view 'serve_bounded_daily_bars_v1'").
   - Extractor now returns non-empty correct sets for every view (empty extraction is `assert view_cols`, never `continue`):
     - serve_daily_prices_v1 → {symbol, event_date, open_price, high_price, low_price, close_price, volume, information_available_ts}
     - serve_daily_equity_metrics_v1 → {symbol, event_date, close, return_1d, realized_vol_20d, drawdown, momentum_20d, information_available_ts}
     - serve_relative_performance_v1 → {symbol, event_date, return_1d, rel_perf, benchmark, information_available_ts}
     - serve_options_metrics_v1 → {symbol, feature_ts, iv_atm, put_call_ratio, information_available_ts}
     - serve_bounded_daily_bars_v1 → {symbol, event_date, open_price, high_price, low_price, close_price, volume, suspected_split, information_available_ts}

3. **CoverageStatus enum / agg_value nullability** — mutated `CoverageResult.validate_agg_value_nullability` to `return self` (allow null agg_value with ok status).
   - `pytest …::TestCoverageResult -q` → **2 failed** (`test_ok_status_with_null_value_rejected`, `test_insufficient_data_with_value_rejected`), 4 passed. Expected FAIL. Proof holds.
   - Registry enforcement: reverted `implied_volatility.aggregate` status `type` to `string` → `load_registry()` raises `RegistryValidationError: status output_field type must be 'coverage_status', got 'string'`. Proof holds.

4. **LN guard** — `GREATEST(1 + return_1d, 1e-10)` present in both `entity_cumulative` and `benchmark_cumulative` CTEs (docs/NL1_PROPOSED_SERVING_VIEWS.md:340, :353), with the bounded-return assumption documented in comments. Present and correct.

## Non-blocking notes

- [tests/analytics_nl/test_ddl.py:380] The read-graph is built by exact-token match (`n in body.split()`). Adequate for the current DDL (CTE names never collide with column aliases), but a future column literally named like a CTE would create a false dependency edge. Not a defect today.
- [analytics_nl/registry.py:236] The registry-level `coverage_status` type enforcement is not covered by a dedicated test (only the `CoverageResult` model validator is tested). `load_registry` runs in every test fixture so a bad type would break the whole suite, and the mutation above confirms it fires — but an explicit unit test would make the enforcement self-documenting.
- Item 4 opinion (clamping a ≤−100% day): `GREATEST(1 + return_1d, 1e-10)` prevents `LN(0) = -inf` / `LN(negative) = NaN`, which is defensively correct, but it **silently** collapses a return of ≤−100% (a price-to-zero or bad-data event, impossible for positive-priced equities) into a tiny positive factor `1e-10`, yielding cumulative ≈ −100% rather than surfacing the anomaly. A stricter form (`CASE WHEN 1 + return_1d > 0 THEN LN(1 + return_1d) ELSE NULL END`) would flag such rows as data-quality breaks instead of masking them. Non-blocking: `return_1d IS NOT NULL` already excludes documented data-quality breaks and split-safety is enforced at the policy layer.

## Checks run

- `python3 -m pytest tests/analytics_nl -q` → 338 passed (13.4s) [was 329; +9 new tests].
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → 338 passed (pyspark hidden; no pyspark import).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- `git diff eaccbed..HEAD -- tests` → no test deleted/weakened; all removed lines are the two vacuous parsers and the `if not view_cols: continue` skip being replaced with stronger assertions, plus EOF-newline re-adds (`resolve_relative_date(…, clock=NaiveClock())`, `TestCoverageResult` append).
- `git diff eaccbed..HEAD -- analytics_nl` → `CoverageStatus` import removed from policy.py (was unused); `CoverageResult` + registry enforcement added; no secrets.
===VERDICT END===
