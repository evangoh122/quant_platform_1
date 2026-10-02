-- gold_model_features: PIT-joined feature matrix
--
-- One snapshot row per (symbol, prediction_ts). prediction_ts is the end-of-day
-- close (last minute bar) of the market-feature spine (gold_ohlcv_features),
-- which covers the full 39-symbol MVP universe. Every other source (options,
-- SEC, COT) is joined LEFT from that spine, so a symbol is NOT dropped merely
-- for lacking options or SEC coverage — missing optional features are NULL,
-- never imputed.
--
-- PIT rule (no-look-ahead): every feature is joined AS-OF with
--   feature.information_available_ts <= prediction_ts.
--   ohlcv  : information_available_ts = bar close (== prediction_ts)
--   options: latest daily feature with info_ts <= prediction_ts
--   sec    : latest filing with accepted_ts <= prediction_ts
--   cot    : latest equity_index release with release_ts <= prediction_ts
-- The gold/pit_guard.py validator re-checks this invariant and the PIT leakage
-- test (tests/gold/test_pit_leakage.py) proves a leaking row fails the build.
--
-- Idempotent: MERGE on (symbol, prediction_ts).

MERGE INTO bootcamp_students.evangoh_capstone.gold_model_features AS tgt
USING (
  WITH daily_base AS (
    SELECT symbol, MAX(feature_ts) AS prediction_ts
    FROM bootcamp_students.evangoh_capstone.gold_ohlcv_features
    GROUP BY symbol, DATE(feature_ts)
  ),
  ohlcv_day AS (
    SELECT db.symbol, db.prediction_ts,
           f.return_1m, f.return_5m, f.return_15m, f.return_30m,
           f.rvol_5m, f.rvol_15m, f.rvol_30m,
           f.atr_14, f.rsi_14, f.vwap_deviation, f.relative_volume
    FROM daily_base db
    JOIN bootcamp_students.evangoh_capstone.gold_ohlcv_features f
      ON f.symbol = db.symbol AND f.feature_ts = db.prediction_ts
  ),
  opt_join AS (
    SELECT db.symbol, db.prediction_ts,
           opt.put_call_ratio, opt.iv_atm, opt.iv_skew, opt.iv_term_slope, opt.volume_anomaly_zscore,
           ROW_NUMBER() OVER (PARTITION BY db.symbol, db.prediction_ts
                              ORDER BY opt.information_available_ts DESC) AS rn
    FROM daily_base db
    JOIN bootcamp_students.evangoh_capstone.gold_options_features opt
      ON opt.symbol = db.symbol AND opt.information_available_ts <= db.prediction_ts
  ),
  sec_join AS (
    SELECT db.symbol, db.prediction_ts,
           sec.sentiment_score AS sec_sentiment_score,
           sec.risk_factor_change AS sec_risk_factor_change,
           sec.material_event_flag AS sec_material_event,
           ROW_NUMBER() OVER (PARTITION BY db.symbol, db.prediction_ts
                              ORDER BY sec.information_available_ts DESC) AS rn
    FROM daily_base db
    JOIN bootcamp_students.evangoh_capstone.gold_sec_features sec
      ON sec.ticker = db.symbol AND sec.information_available_ts <= db.prediction_ts
  ),
  cot_join AS (
    SELECT db.symbol, db.prediction_ts,
           cot.lev_money_zscore_52w AS cot_lev_money_zscore,
           cot.crowding_score        AS cot_crowding_score,
           cot.regime_label          AS cot_regime_label,
           ROW_NUMBER() OVER (PARTITION BY db.symbol, db.prediction_ts
                              ORDER BY cot.information_available_ts DESC) AS rn
    FROM daily_base db
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
    current_timestamp() AS processed_ts
  FROM ohlcv_day o
  LEFT JOIN opt_join op ON op.symbol = o.symbol AND op.prediction_ts = o.prediction_ts AND op.rn = 1
  LEFT JOIN sec_join s  ON s.symbol  = o.symbol AND s.prediction_ts  = o.prediction_ts AND s.rn = 1
  LEFT JOIN cot_join c  ON c.symbol  = o.symbol AND c.prediction_ts  = o.prediction_ts AND c.rn = 1
) AS src
ON tgt.symbol = src.symbol AND tgt.prediction_ts = src.prediction_ts
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
