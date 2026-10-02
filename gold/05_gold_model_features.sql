-- gold_model_features: PIT-joined feature matrix
--
-- One snapshot row per (symbol, prediction_ts). prediction_ts is the
-- AVAILABILITY timestamp of the last minute bar of the market-feature spine
-- (gold_ohlcv_features): a bar labelled [t, t+1min) is known only at t+1min,
-- so prediction_ts = MAX(information_available_ts) = last bar's feature_ts + 1
-- minute. (Round 7 fix — previously prediction_ts was the last bar's START,
-- leaking the final bar 60s early.) The spine covers the full 39-symbol MVP
-- universe. Every other source (options, SEC, COT) is joined LEFT from that
-- spine, so a symbol is NOT dropped merely for lacking options or SEC coverage
-- — missing optional features are NULL, never imputed.
--
-- PIT rule (no-look-ahead): every feature is joined AS-OF with
--   feature.information_available_ts <= prediction_ts.
--   ohlcv  : information_available_ts = feature_ts + bar interval (the close
--            is known one minute after a minute bar's start); ohlcv is joined
--            directly on information_available_ts == prediction_ts (the last
--            bar's availability), never on the bar's start.
--   options: latest daily feature with info_ts <= prediction_ts
--   sec    : latest filing with accepted_ts <= prediction_ts
--   cot    : latest equity_index release with release_ts <= prediction_ts
-- The gold/pit_guard.py validator re-checks this invariant and the PIT leakage
-- test (tests/gold/test_pit_leakage.py) proves a leaking row fails the build.
--
-- Round 8 changes:
--   * RETAIN SOURCE AVAILABILITY: each source row's information_available_ts is
--     retained in a per-source availability column (ohlcv_available_ts,
--     options_available_ts, sec_available_ts, cot_available_ts). The
--     orchestrator's run_matrix_invariant now checks these columns directly
--     (GREATEST of non-null *_available_ts <= prediction_ts, and a source's
--     features non-NULL only if its *_available_ts is non-NULL) instead of
--     value-matching against a sampled source column.
--   * SELF-RECONCILING BUILD: before the MERGE, stale rows for each rebuilt
--     (symbol, trading session) whose prediction_ts differs from the session's
--     new prediction_ts are DELETEd, so a changed prediction_ts (late bar, or a
--     redeploy over old data) no longer leaves a duplicate (symbol,
--     prediction_ts) row. --truncate remains an optional full rebuild.
--   * TRADING SESSION is the America/New_York session date (DST-aware), NOT the
--     UTC date, so a session that ends after midnight UTC is not split across
--     two UTC dates.
--
-- Idempotent: DELETE of stale session rows + MERGE on (symbol, prediction_ts).

CREATE OR REPLACE TEMP VIEW _silver_gold_daily_base AS
SELECT
  symbol,
  DATE(convert_timezone('UTC', 'America/New_York', feature_ts)) AS session_date,
  MAX(information_available_ts) AS prediction_ts
FROM bootcamp_students.evangoh_capstone.gold_ohlcv_features
GROUP BY symbol, DATE(convert_timezone('UTC', 'America/New_York', feature_ts));

DELETE FROM bootcamp_students.evangoh_capstone.gold_model_features AS tgt
WHERE EXISTS (
  SELECT 1
  FROM _silver_gold_daily_base db
  WHERE db.symbol = tgt.symbol
    AND db.session_date = DATE(convert_timezone('UTC', 'America/New_York', tgt.prediction_ts))
    AND db.prediction_ts <> tgt.prediction_ts
);

MERGE INTO bootcamp_students.evangoh_capstone.gold_model_features AS tgt
USING (
  WITH ohlcv_day AS (
    SELECT db.symbol, db.prediction_ts,
           f.information_available_ts AS ohlcv_available_ts,
           f.return_1m, f.return_5m, f.return_15m, f.return_30m,
           f.rvol_5m, f.rvol_15m, f.rvol_30m,
           f.atr_14, f.rsi_14, f.vwap_deviation, f.relative_volume
    FROM _silver_gold_daily_base db
    JOIN bootcamp_students.evangoh_capstone.gold_ohlcv_features f
      ON f.symbol = db.symbol AND f.information_available_ts = db.prediction_ts
  ),
  opt_join AS (
    SELECT db.symbol, db.prediction_ts,
           opt.information_available_ts AS options_available_ts,
           opt.put_call_ratio, opt.iv_atm, opt.iv_skew, opt.iv_term_slope, opt.volume_anomaly_zscore,
           ROW_NUMBER() OVER (PARTITION BY db.symbol, db.prediction_ts
                              ORDER BY opt.information_available_ts DESC) AS rn
    FROM _silver_gold_daily_base db
    JOIN bootcamp_students.evangoh_capstone.gold_options_features opt
      ON opt.symbol = db.symbol AND opt.information_available_ts <= db.prediction_ts
  ),
  sec_join AS (
    SELECT db.symbol, db.prediction_ts,
           sec.information_available_ts AS sec_available_ts,
           sec.sentiment_score AS sec_sentiment_score,
           sec.risk_factor_change AS sec_risk_factor_change,
           sec.material_event_flag AS sec_material_event,
           ROW_NUMBER() OVER (PARTITION BY db.symbol, db.prediction_ts
                              ORDER BY sec.information_available_ts DESC) AS rn
    FROM _silver_gold_daily_base db
    JOIN bootcamp_students.evangoh_capstone.gold_sec_features sec
      ON sec.ticker = db.symbol AND sec.information_available_ts <= db.prediction_ts
  ),
  cot_join AS (
    SELECT db.symbol, db.prediction_ts,
           cot.information_available_ts AS cot_available_ts,
           cot.lev_money_zscore_52w AS cot_lev_money_zscore,
           cot.crowding_score        AS cot_crowding_score,
           cot.regime_label          AS cot_regime_label,
           ROW_NUMBER() OVER (PARTITION BY db.symbol, db.prediction_ts
                              ORDER BY cot.information_available_ts DESC) AS rn
    FROM _silver_gold_daily_base db
    JOIN bootcamp_students.evangoh_capstone.gold_cot_features cot
      ON cot.mapped_asset = 'equity_index' AND cot.information_available_ts <= db.prediction_ts
  )
  SELECT
    o.symbol,
    o.prediction_ts,
    sha2(concat_ws('|', o.symbol, cast(o.prediction_ts AS STRING)), 256) AS feature_snapshot_id,
    o.return_1m, o.return_5m, o.return_15m, o.return_30m,
    o.rvol_5m, o.rvol_15m, o.rvol_30m,
    o.atr_14, o.rsi_14, o.vwap_deviation, o.relative_volume,
    op.put_call_ratio, op.iv_atm, op.iv_skew, op.iv_term_slope, op.volume_anomaly_zscore,
    s.sec_sentiment_score, s.sec_risk_factor_change, s.sec_material_event,
    c.cot_lev_money_zscore, c.cot_crowding_score, c.cot_regime_label,
    'silver-gold-v1' AS model_version,
    current_timestamp() AS processed_ts,
    o.ohlcv_available_ts,
    op.options_available_ts,
    s.sec_available_ts,
    c.cot_available_ts
  FROM ohlcv_day o
  LEFT JOIN opt_join op ON op.symbol = o.symbol AND op.prediction_ts = o.prediction_ts AND op.rn = 1
  LEFT JOIN sec_join s  ON s.symbol  = o.symbol AND s.prediction_ts  = o.prediction_ts AND s.rn = 1
  LEFT JOIN cot_join c  ON c.symbol  = o.symbol AND c.prediction_ts  = o.prediction_ts AND c.rn = 1
) AS src
ON tgt.symbol = src.symbol AND tgt.prediction_ts = src.prediction_ts
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT (
  symbol, prediction_ts, feature_snapshot_id,
  return_1m, return_5m, return_15m, return_30m,
  rvol_5m, rvol_15m, rvol_30m,
  atr_14, rsi_14, vwap_deviation, relative_volume,
  put_call_ratio, iv_atm, iv_skew, iv_term_slope, volume_anomaly_zscore,
  sec_sentiment_score, sec_risk_factor_change, sec_material_event,
  cot_lev_money_zscore, cot_crowding_score, cot_regime_label,
  model_version, processed_ts,
  ohlcv_available_ts, options_available_ts, sec_available_ts, cot_available_ts
) VALUES (
  src.symbol, src.prediction_ts, src.feature_snapshot_id,
  src.return_1m, src.return_5m, src.return_15m, src.return_30m,
  src.rvol_5m, src.rvol_15m, src.rvol_30m,
  src.atr_14, src.rsi_14, src.vwap_deviation, src.relative_volume,
  src.put_call_ratio, src.iv_atm, src.iv_skew, src.iv_term_slope, src.volume_anomaly_zscore,
  src.sec_sentiment_score, src.sec_risk_factor_change, src.sec_material_event,
  src.cot_lev_money_zscore, src.cot_crowding_score, src.cot_regime_label,
  src.model_version, src.processed_ts,
  src.ohlcv_available_ts, src.options_available_ts, src.sec_available_ts, src.cot_available_ts
)
