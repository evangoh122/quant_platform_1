# BUILD: NL1 round 5 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

Claude's review of round 4: the DDL aliases UNADJUSTED close as `adj_close` (`close AS adj_close`,
`docs/NL1_PROPOSED_SERVING_VIEWS.md:48,240`), and `source_schemas_v1.yaml:56,99` lists `adj_close` as
an "alias". That labels unadjusted prices as adjusted, which is the exact confusion round 4 was meant
to remove.

A corporate-actions lane (`slice/corporate-actions`) will provide the governed adjusted source
`silver_ohlcv_day_adjusted`, with these columns:
- symbol, event_date, event_ts;
- open, high, low, close, volume, vwap, trade_count (raw);
- cumulative_split_ratio, price_adjustment_factor;
- adj_open, adj_high, adj_low, adj_close, adj_vwap, adj_volume;
- raw_overnight_return, adjusted_return_1d_unmasked;
- return_1d (NULL on data-quality breaks), is_data_quality_break;
- information_available_ts (16:30 America/New_York on the bar date, in UTC), processed_ts.

PIT rule from that spec: `adj_*` levels are current-scale back-adjusted. They are approved for
RETURNS. Price LEVELS shown historically are display values (disclose this). They are not model
features.

Fix:
1. Delete the `close AS adj_close` aliases and the alias entries.
2. Root the daily-price views on `silver_ohlcv_day_adjusted`:
   - returns, volatility, drawdown, momentum and relative performance use `return_1d` / `adj_close`;
   - volume uses `adj_volume`;
   - `information_available_ts` comes from the source, not re-derived.
   Add `silver_ohlcv_day_adjusted` to `source_schemas_v1.yaml` with exactly the columns above,
   marked `status: pending_corporate_actions_lane`.
3. The split-safety rejection (round 4) becomes a FALLBACK. If `silver_ohlcv_day_adjusted` is
   unavailable (a registry flag `adjusted_source_available: false`, the default until the lane
   merges), the metrics spanning a known or suspected split REJECT as now. With the flag true, they
   use adjusted returns. A `return_1d` that is NULL (data-quality break) inside the window → disclose
   it, and exclude the day from aggregates. Test both modes.
4. The schema-truth test: no column named `adj_*` may be read from `bronze_ohlcv_day`. Prove by
   mutation that reintroducing `close AS adj_close` fails it.

Run `python3 -m pytest -q tests/analytics_nl` and the full suite with `--ignore=tests/lakebase`.
LF line endings only. Don't touch `.agents/dispatch.sh`. Update `.agents/mimo/VERDICT-nl1-contracts.md`
(round 5).
