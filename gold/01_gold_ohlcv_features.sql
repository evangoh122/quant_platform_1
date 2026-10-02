-- gold_ohlcv_features: silver_ohlcv -> gold_ohlcv_features
--
-- Computes minute-bar technical features. All lookback windows are partitioned
-- by (symbol, trading day) so returns/momentum/ATR/RSI do not leak across
-- sessions. session_high/session_low are trailing (ROWS BETWEEN UNBOUNDED
-- PRECEDING AND CURRENT ROW) so a bar never sees a later bar's high/low within
-- the same day. information_available_ts = event_ts (the bar close is when the
-- bar becomes observable) — this is the PIT key for market features.
--
-- Chunked by date partition by the orchestrator via {date_start}/{date_end}.
-- Idempotent: MERGE on (symbol, feature_ts).

MERGE INTO bootcamp_students.evangoh_capstone.gold_ohlcv_features AS tgt
USING (
  WITH lagged AS (
    SELECT
      symbol,
      event_ts,
      close,
      high,
      low,
      volume,
      vwap,
      close / NULLIF(LAG(close, 1)  OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts), 0) - 1 AS r1,
      close / NULLIF(LAG(close, 5)  OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts), 0) - 1 AS r5,
      close / NULLIF(LAG(close, 15) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts), 0) - 1 AS r15,
      close / NULLIF(LAG(close, 30) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts), 0) - 1 AS r30,
      MAX(high) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_high,
      MIN(low)  OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_low
    FROM bootcamp_students.evangoh_capstone.silver_ohlcv
    WHERE timespan = 'minute'
      AND symbol IN (SELECT symbol FROM universe)
      AND DATE(event_ts) >= '{date_start}' AND DATE(event_ts) < '{date_end}'
  ),
  returns AS (
    SELECT
      symbol, event_ts, close, high, low, volume, vwap,
      r1, r5, r15, r30,
      session_high, session_low,
      CASE WHEN r1 > 0 THEN r1 ELSE 0 END AS gain,
      CASE WHEN r1 < 0 THEN -r1 ELSE 0 END AS loss,
      high - low AS tr
    FROM lagged
  ),
  feats AS (
    SELECT
      symbol,
      event_ts,
      r1  AS return_1m,
      r5  AS return_5m,
      r15 AS return_15m,
      r30 AS return_30m,
      STDDEV(r1) OVER w5   AS rvol_5m,
      STDDEV(r1) OVER w15  AS rvol_15m,
      STDDEV(r1) OVER w30  AS rvol_30m,
      AVG(tr) OVER w14     AS atr_14,
      r5                   AS momentum_5m,
      r15                  AS momentum_15m,
      CASE
        WHEN AVG(loss) OVER w14 = 0 THEN 100.0
        ELSE 100.0 - 100.0 / (1.0 + (AVG(gain) OVER w14 / NULLIF(AVG(loss) OVER w14, 0)))
      END                  AS rsi_14,
      (close - vwap) / NULLIF(vwap, 0) AS vwap_deviation,
      volume / NULLIF(AVG(volume) OVER w20, 0) AS relative_volume,
      (close - session_high) / NULLIF(session_high, 0) AS dist_session_high,
      (close - session_low)  / NULLIF(session_low, 0)  AS dist_session_low,
      current_timestamp()   AS processed_ts
    FROM returns
    WINDOW
      w5  AS (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN 4  PRECEDING AND CURRENT ROW),
      w14 AS (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN 13 PRECEDING AND CURRENT ROW),
      w15 AS (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN 14 PRECEDING AND CURRENT ROW),
      w20 AS (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
      w30 AS (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
  )
  SELECT
    symbol,
    event_ts                                   AS feature_ts,
    event_ts                                   AS information_available_ts,
    return_1m, return_5m, return_15m, return_30m,
    rvol_5m, rvol_15m, rvol_30m,
    atr_14, momentum_5m, momentum_15m, rsi_14,
    vwap_deviation, relative_volume,
    dist_session_high, dist_session_low,
    processed_ts
  FROM feats
) AS src
ON tgt.symbol = src.symbol AND tgt.feature_ts = src.feature_ts
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
