# BUILD: NL1 round 4 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each step. NEVER delete or weaken
> existing tests.

DeepSeek check2 (`.agents/deepseek/VERDICT-nl1-contracts-check2.md`, read it fully): the proposed DDL
and registry reference columns that DON'T EXIST. Claude verified the live schemas (2026-10-04); USE
THESE EXACTLY:

    bronze_ohlcv_day: symbol string, event_ts timestamp, event_date date, event_year int, open, high,
      low, close double, volume bigint, vwap double, trade_count bigint, timespan string, source,
      source_file string, ingest_ts timestamp
      (NO trade_date, NO adj_close, NO information_available_ts)
    gold_options_features: symbol, feature_ts timestamp, information_available_ts timestamp,
      put_volume, call_volume bigint, put_call_ratio, iv_atm, iv_25d_put, iv_25d_call, iv_skew,
      iv_term_slope, avg_spread_pct, volume_anomaly_zscore, oi_concentration, net_delta_exposure
      double, processed_ts

(Claude's earlier fact sheet wrongly said bronze_ohlcv_day had `information_available_ts`. It doesn't.)

## Fixes
1. **Real columns only.** Use `event_date` (daily) and `feature_ts` (options). There is no
   `adj_close`: price metrics use `close` and the registry marks `price_adjustment: unadjusted`.
2. **Daily point-in-time availability.** It must be DERIVED in the serving view, per the project
   convention: a daily bar is available at 16:00 America/New_York + 30 minutes on `event_date`. Use
   `to_utc_timestamp(concat(event_date,' 16:30:00'),'America/New_York')`, with DST handled by the
   timezone function. The view exposes it as `information_available_ts`. Document it.
3. **Corporate-action safety.** The prices are UNADJUSTED, so stock splits create fake returns (e.g.
   NVDA 10:1 in June 2024 → about −90%). Until a governed split source exists:
   - In the DDL appendix, propose a `known_splits` table (symbol, ex_date, ratio, source), marked "to
     be populated by owner/admin".
   - In NL1 policy, any intent using return / realized_volatility / drawdown / momentum /
     relative_performance over a window that contains a known split → REJECT, with reason code
     `unadjusted_corporate_action` and no SQL. With an empty `known_splits`, also add a detector rule
     to the proposed view (overnight |close/prev_close − 1| ≥ 0.4 AND the ratio within 3% of 1/k or k
     for k ∈ {2,3,4,5,10,20}) that flags `suspected_split`, and route flagged windows to the same
     rejection.
   - Price `trend` may show raw close, with a disclosed assumption "unadjusted prices".
   - Tests for each case.
4. **A schema-truth test.** Add `analytics_nl/data/source_schemas_v1.yaml` holding the column lists
   above, plus a test that EVERY column referenced by the DDL appendix and every registry
   `input_column` exists in the source schema or is defined by an earlier view stage. Prove that
   reintroducing `adj_close` fails it.

Regenerate the schemas if the models change. Run `python3 -m pytest -q tests/analytics_nl` and the
full suite with `--ignore=tests/lakebase`. LF line endings only. Don't touch `.agents/dispatch.sh`.
Update `.agents/mimo/VERDICT-nl1-contracts.md` (round 4).
