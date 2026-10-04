===VERDICT START===
Reviewer: Claude Sonnet subagent (stopgap for Codex, usage-limited)
Status: CHANGES_REQUESTED

Tests: `python3 -m pytest tests/analytics_nl -q` = 343 passed. `python3 -m analytics_nl.export_schemas --check` = "All schemas match."

Findings:

1. High (surviving mutation, Codex review2 item 1 not closed). Removing benchmark availability from the final select (`GREATEST(e.entity_info_ts, b.bench_max_info_ts)` -> `e.entity_info_ts`, docs/NL1_PROPOSED_SERVING_VIEWS.md:429) still gives 343 passed. Cause: `tests/analytics_nl/test_ddl.py:415-428` only asserts the strings "GREATEST" and "benchmark" occur anywhere in the section (the prose at doc line 438 satisfies both). `test_output_availability_is_window_max` (test_ddl.py:776+) loops over GREATEST args, so a block with no GREATEST makes zero assertions. Fix: assert the final SELECT of the relative-performance block contains GREATEST over both the entity and benchmark info_ts; make the generic test fail when the final select exposes information_available_ts without a GREATEST of window-MAX tokens.

2. High (surviving mutations, -100% requirement only keyword-tested). (a) Replacing the invalid-series `THEN NULL` with a computed value (doc :382 and :407) passes 343. (b) Setting the status CASE to `WHEN FALSE THEN 'invalid_return'` (doc :431) passes 343. `test_anomaly_propagation_for_invalid_returns` (test_ddl.py:540-562) checks for substrings "BOOL_OR", "return_1d <= -1", "invalid_return" and "CASE" only. Needs structural assertions: the `WHEN BOOL_OR(...) THEN NULL` arm, and that status keys on has_invalid_return/has_invalid_bench. (A GREATEST(1+r,1e-10) clamp mutation was caught, but by the availability-parse test failing, not by a semantic check.)

3. Medium (PIT, momentum). `momentum_20d` uses `LAG(close, 20)` (doc :233, :318). That row lies outside the 19-PRECEDING availability window, and the unbounded drawdown window is the only one that could cover it. `momentum_20d` has no info_ts term in the final GREATEST (:235-239, :320-324). A late revision of the t-20 bar will not advance availability. In adjusted mode LAG also runs after the `return_1d IS NOT NULL` filter (:199), so it counts rows rather than trading days.

4. Medium (PIT, fallback). In the bronze fallback (doc :97-114 and the bounded-bars equivalent) availability is derived solely from event_date 16:30 ET. The `ingest_ts` column is selected but not filtered by `<= :as_of`. A late backfill or restatement is visible to as-of queries before it was ingested. The row should be filtered on `ingest_ts <= :as_of`, and availability should be GREATEST(derived, ingest_ts).

5. Medium (bounded-bars fallback). The suspected_split LAG(close) windows are computed in `deduped` before `rn = 1` is applied. Duplicate (symbol, event_date) rows corrupt LAG: the ratio is about 1, so a split is missed. The dedup must happen before the LAG.

6. Medium (contracts, security). `TickerEntity`, `IndexEntity`, `SectorEntity` validators use `re.match` with `$` (contracts.py:~222, ~240, ~257). Verified: `TickerEntity(canonical_id="AAPL\n")`, `IndexEntity("SPY\n")` and `SectorEntity("tech\n")` are all accepted. A trailing newline reaches bind values and cache keys. Use `fullmatch` or `\Z`. `LLMEntityMention` is safe: the Rust-side pydantic pattern rejects the same payloads.

7. Medium (policy). The coverage check is fail-open: contracts/policy.py:~253 skips it when `coverage_stats` is None or the pair key is missing. An IV query with no stats returns NORMAL or CHEAP. The 12/19,390 case is correctly INSUFFICIENT_DATA for trend/compare/rank/aggregate when stats are supplied (the test_policy.py:997-1032 tests pass; the aggregate-only mutation fails 3 tests). Recommend failing closed for registry entries with `coverage` when stats are absent. Also min_coverage_ratio 0.001 is very loose (about 20 rows pass).

Low: CoverageResult.agg_value (float, strict) is the right place to also set `allow_inf_nan=False`. NaN is currently rejected, but only incidentally. Registry `feature_ts` is typed date while the view column is a timestamp.

Mutation results (copies via git archive in /tmp/rv_m*):
- Benchmark availability removed from final GREATEST: SURVIVED (343 passed) -> finding 1.
- Rolling window MAX replaced by the current row: killed (test_output_availability_is_window_max).
- Frame mismatch 19 -> 5 on the info-ts window: killed (same test).
- :start_date bound dropped: killed (test_start_date_bound_in_inputs).
- close_price renamed in the bounded-bars DDL only: killed (test_registry_output_fields_match_view_columns).
- Coverage restricted to aggregate: killed (3 failed: IV trend/compare/rank).
- -100% NULL arm replaced: SURVIVED. Status CASE disabled: SURVIVED -> finding 2.

Verified OK: LLM schema additionalProperties=false; hostile sql/limit/grouping/over-long list payloads rejected; mention allowlist, SQL keyword, comment and prompt-injection filters work; schemas in sync with models; all proposed views filter `information_available_ts <= :as_of` before windows; relative performance bounded by :start_date and benchmark parameterized; sample_count/coverage_ratio/status present on all four IV operations.
===VERDICT END===
