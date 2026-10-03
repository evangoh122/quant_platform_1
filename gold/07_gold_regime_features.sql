-- gold_regime_features: bronze_ohlcv_day -> gold_regime_features
--
-- Daily, market-wide breadth / divergence regime features from SPY / RSP / QQQ
-- daily closes (QUANT_STRATEGIES.md §2.1 and §2.3). One row per trading date.
--
--   rsp_spy_ratio_t    = close(RSP)_t / close(SPY)_t
--   rsp_spy_ratio_sma50 = SMA(rsp_spy_ratio, 50)     (trailing)
--   rsp_spy_ratio_zscore_252 = 252-day z-score        (trailing, full window)
--   rsp_spy_ratio_slope_20d = ratio_t / ratio_{t-20} - 1
--   breadth_regime     = BROAD  if ratio > sma50 and slope > 0
--                        NARROW if ratio < sma50 and slope < 0
--                        else MIXED
--   qqq_spy_20d        = return(QQQ, 20d) - return(SPY, 20d)
--   rsp_spy_20d        = return(RSP, 20d) - return(SPY, 20d)
--
-- All windows are trailing (never see the future). information_available_ts is
-- the session close (16:00 America/New_York + 30 min buffer, DST-aware) of the
-- reference date — the same convention as gold/02_gold_options_features.sql.
-- RSP's equal weighting structurally tilts it toward Industrials/Financials/
-- Materials relative to SPY, so the RSP-vs-SPY spread is a *proxy* for cyclical
-- breadth, not a true factor decomposition (stated honestly in §2.3).
--
-- Idempotent: MERGE on (trade_date).

CREATE TABLE IF NOT EXISTS bootcamp_students.evangoh_capstone.gold_regime_features (
  trade_date               DATE        NOT NULL,
  rsp_spy_ratio            DOUBLE,
  rsp_spy_ratio_sma50      DOUBLE,
  rsp_spy_ratio_zscore_252 DOUBLE,
  rsp_spy_ratio_slope_20d  DOUBLE,
  breadth_regime           STRING,
  qqq_spy_20d              DOUBLE,
  rsp_spy_20d              DOUBLE,
  information_available_ts TIMESTAMP   NOT NULL,
  processed_ts             TIMESTAMP   NOT NULL
);

DECLARE OR REPLACE VARIABLE pub_buffer_minutes INT DEFAULT 30;

MERGE INTO bootcamp_students.evangoh_capstone.gold_regime_features AS tgt
USING (
  WITH etf AS (
    SELECT symbol, event_date, close
    FROM bootcamp_students.evangoh_capstone.bronze_ohlcv_day
    WHERE symbol IN ('SPY', 'RSP', 'QQQ')
      AND close IS NOT NULL
      AND close > 0
  ),
  wide AS (
    SELECT
      event_date,
      MAX(CASE WHEN symbol = 'SPY' THEN close END) AS spy,
      MAX(CASE WHEN symbol = 'RSP' THEN close END) AS rsp,
      MAX(CASE WHEN symbol = 'QQQ' THEN close END) AS qqq
    FROM etf
    GROUP BY event_date
  ),
  ratio AS (
    SELECT
      event_date AS trade_date,
      spy, rsp, qqq,
      rsp / NULLIF(spy, 0) AS rsp_spy_ratio
    FROM wide
  ),
  win AS (
    SELECT
      trade_date,
      spy, rsp, qqq,
      rsp_spy_ratio,
      -- Partial-window guard: SMA50 is NULL unless the full 50-row window
      -- has non-NULL rsp_spy_ratio values (matches pandas min_periods=50).
      CASE WHEN COUNT(rsp_spy_ratio) OVER (
        ORDER BY trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
      ) >= 50 THEN
        AVG(rsp_spy_ratio) OVER (
          ORDER BY trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
        )
      END AS rsp_spy_ratio_sma50,
      rsp_spy_ratio / NULLIF(
        LAG(rsp_spy_ratio, 20) OVER (ORDER BY trade_date), 0
      ) - 1 AS rsp_spy_ratio_slope_20d,
      qqq / NULLIF(LAG(qqq, 20) OVER (ORDER BY trade_date), 0) - 1
        - (spy / NULLIF(LAG(spy, 20) OVER (ORDER BY trade_date), 0) - 1)
        AS qqq_spy_20d,
      rsp / NULLIF(LAG(rsp, 20) OVER (ORDER BY trade_date), 0) - 1
        - (spy / NULLIF(LAG(spy, 20) OVER (ORDER BY trade_date), 0) - 1)
        AS rsp_spy_20d,
      CASE
        WHEN COUNT(rsp_spy_ratio) OVER (
          ORDER BY trade_date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
        ) >= 252 THEN
          (rsp_spy_ratio - AVG(rsp_spy_ratio) OVER (
            ORDER BY trade_date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
          )) / NULLIF(STDDEV(rsp_spy_ratio) OVER (
            ORDER BY trade_date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
          ), 0)
      END AS rsp_spy_ratio_zscore_252
    FROM ratio
  ),
  feats AS (
    SELECT
      trade_date,
      rsp_spy_ratio,
      rsp_spy_ratio_sma50,
      rsp_spy_ratio_zscore_252,
      rsp_spy_ratio_slope_20d,
      CASE
        WHEN rsp_spy_ratio > rsp_spy_ratio_sma50 AND rsp_spy_ratio_slope_20d > 0 THEN 'BROAD'
        WHEN rsp_spy_ratio < rsp_spy_ratio_sma50 AND rsp_spy_ratio_slope_20d < 0 THEN 'NARROW'
        ELSE 'MIXED'
      END AS breadth_regime,
      qqq_spy_20d,
      rsp_spy_20d,
      convert_timezone('America/New_York', 'UTC',
          to_timestamp(concat(cast(trade_date AS STRING), ' 16:00:00')))
        + make_interval(0, 0, 0, 0, 0, pub_buffer_minutes, 0)
        AS information_available_ts,
      current_timestamp() AS processed_ts
    FROM win
  )
  SELECT
    trade_date,
    rsp_spy_ratio,
    rsp_spy_ratio_sma50,
    rsp_spy_ratio_zscore_252,
    rsp_spy_ratio_slope_20d,
    breadth_regime,
    qqq_spy_20d,
    rsp_spy_20d,
    information_available_ts,
    processed_ts
  FROM feats
) AS src
ON tgt.trade_date = src.trade_date
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
