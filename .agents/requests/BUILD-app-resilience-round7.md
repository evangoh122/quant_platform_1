# BUILD app resilience round 7 — IMPLEMENT NOW (Claude LIVE findings on round 6)

You are MiMo. Commit per item, LF endings, do not touch `.agents/dispatch.sh`, never delete/weaken tests, capture the red phase,
mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.

Round 6 live (pyspark disabled, real warehouse): `:name` params now work (signals query runs in 0.9 s). New live failures — your SQL does
not match the real tables. Live schemas (DESCRIBE, 2026-10-04, bootcamp_students.evangoh_capstone):
- gold_trading_signals: signal_id, symbol, prediction_ts, horizon, direction, probability, model_version, feature_snapshot_id, status,
  processed_ts — currently 0 ROWS (no signals have ever been published).
- gold_ohlcv_features (intraday features, 23.4M rows, 39 symbols, 2022-01-03 → 2026-09-02): symbol, feature_ts, information_available_ts,
  return_1m/5m/15m/30m, rvol_5m/15m/30m, atr_14, momentum_5m/15m, rsi_14, vwap_deviation, relative_volume, dist_session_high/low, processed_ts.
  NO open/high/low/close/volume.
- gold_options_features (20,318 rows, 39 symbols, latest 2026-10-01): symbol, feature_ts, information_available_ts, put_volume, call_volume,
  put_call_ratio, iv_atm, iv_25d_put, iv_25d_call, iv_skew, iv_term_slope, avg_spread_pct, volume_anomaly_zscore, oi_concentration,
  net_delta_exposure, processed_ts. NO expiry column.
- gold_cot_features: mapped_asset IN ('rate','other','fx','equity_index','crypto','commodity'), report_date, information_available_ts,
  lev_money_net, lev_money_net_chg_1w, lev_money_pctile_52w, lev_money_zscore_52w, asset_mgr_net, asset_mgr_pctile_52w, crowding_score,
  regime_label, processed_ts.
- silver_ohlcv_day_adjusted (daily, split-adjusted): symbol, event_date, adj_open, adj_high, adj_low, adj_close, adj_vwap, adj_volume,
  return_1d, information_available_ts, ...

Failures: `get_market_features` → UNRESOLVED_COLUMN `open`; `get_options_features` → UNRESOLVED_COLUMN `expiry`; `get_cot_positioning("SPX")`
→ {} (it filters by ticker; mapped_asset holds asset classes); signals → [] (table empty).

1. Market: daily bars from `silver_ohlcv_day_adjusted` (adj_* aliased explicitly, labelled split-adjusted) + optional intraday features from
   `gold_ohlcv_features` with their real column names. Bounded window/LIMIT as before.
2. Options: remove the `expiry` filter/param (or make it explicitly unsupported → 422); select the real columns.
3. COT: accept an asset class (validated against the six values) and map tickers to asset classes via `config/tickers.yaml` taxonomy where
   possible (e.g. SPY/SPX → equity_index); unknown → explicit `no_mapping` response, never silent {}.
4. Signals: empty table must render an explicit `no_signals_published` state (route + frontend), not an empty list that looks like "no
   signal for this symbol". Health/coverage should report the signals table row count.
5. Schema contract tests: a single `db/schema_contract.py` listing the columns each query uses per table (from the DESCRIBE above), and a
   test that every warehouse query only references columns in the contract (parse the SELECT/WHERE identifiers, or build queries from the
   contract). Mutation: reference `open` from gold_ohlcv_features → FAIL. Plus `scripts/check_schema_contract.py` that Claude runs live
   (DESCRIBE each table, diff against the contract, non-zero exit on drift).
Claude reruns the live checks afterwards. Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (known ml
ablation timeout excepted); frontend build. Verdict: `.agents/mimo/VERDICT-app-resilience-round7.md`.
