-- gold_options_features: bronze_options_quotes -> gold_options_features
--
-- Daily per-underlying options features. IV metrics use implied_volatility and
-- delta from the source (bid/ask are entirely NULL in the source, so
-- avg_spread_pct is pulled from silver_options_quotes where available and is
-- otherwise NULL). ATM is proxied by max open_interest; 25-delta IV by the
-- option whose delta is nearest +/-0.25.
--
-- information_available_ts = MAX(participant_ts) of the day (last quote time).
-- Idempotent: MERGE on (symbol, feature_ts).

MERGE INTO bootcamp_students.evangoh_capstone.gold_options_features AS tgt
USING (
  WITH q AS (
    SELECT
      underlying AS symbol,
      DATE(participant_ts) AS d,
      participant_ts,
      right,
      strike,
      expiry,
      volume,
      open_interest,
      implied_volatility AS iv,
      delta
    FROM bootcamp_students.evangoh_capstone.bronze_options_quotes
    WHERE underlying IN (SELECT symbol FROM universe)
      AND underlying IS NOT NULL AND participant_ts IS NOT NULL
  ),
  atm AS (
    SELECT symbol, d, iv AS iv_atm
    FROM (
      SELECT symbol, d, iv,
        ROW_NUMBER() OVER (PARTITION BY symbol, d ORDER BY open_interest DESC NULLS LAST, strike) AS rn
      FROM q WHERE iv IS NOT NULL
    ) WHERE rn = 1
  ),
  p25 AS (
    SELECT symbol, d, iv AS iv_25d_put
    FROM (
      SELECT symbol, d, iv,
        ROW_NUMBER() OVER (PARTITION BY symbol, d ORDER BY ABS(delta - (-0.25)) ASC, strike) AS rn
      FROM q WHERE right = 'put' AND iv IS NOT NULL AND delta IS NOT NULL
    ) WHERE rn = 1
  ),
  c25 AS (
    SELECT symbol, d, iv AS iv_25d_call
    FROM (
      SELECT symbol, d, iv,
        ROW_NUMBER() OVER (PARTITION BY symbol, d ORDER BY ABS(delta - 0.25) ASC, strike) AS rn
      FROM q WHERE right = 'call' AND iv IS NOT NULL AND delta IS NOT NULL
    ) WHERE rn = 1
  ),
  term AS (
    SELECT symbol, d,
      near_iv - far_iv AS iv_term_slope
    FROM (
      SELECT symbol, d,
        AVG(iv) FILTER (WHERE expiry = min_expiry) AS near_iv,
        AVG(iv) FILTER (WHERE expiry = max_expiry) AS far_iv
      FROM (
        SELECT symbol, d, iv, expiry,
          MIN(expiry) OVER (PARTITION BY symbol, d) AS min_expiry,
          MAX(expiry) OVER (PARTITION BY symbol, d) AS max_expiry
        FROM q WHERE iv IS NOT NULL
      )
      GROUP BY symbol, d
    )
  ),
  oi_conc AS (
    SELECT symbol, d,
      SUM(CASE WHEN rnk <= 5 THEN open_interest ELSE 0 END) AS top5_oi,
      SUM(open_interest) AS total_oi
    FROM (
      SELECT symbol, d, strike, open_interest,
        ROW_NUMBER() OVER (PARTITION BY symbol, d ORDER BY open_interest DESC NULLS LAST) AS rnk
      FROM q WHERE open_interest IS NOT NULL
    )
    GROUP BY symbol, d
  ),
  spread AS (
    SELECT underlying AS symbol, DATE(participant_ts) AS d, AVG(spread_pct) AS avg_spread_pct
    FROM bootcamp_students.evangoh_capstone.silver_options_quotes
    WHERE spread_pct IS NOT NULL
    GROUP BY underlying, DATE(participant_ts)
  ),
  daily AS (
    SELECT
      symbol,
      d,
      MAX(participant_ts) AS last_ts,
      SUM(CASE WHEN right = 'put'  THEN volume ELSE 0 END) AS put_volume,
      SUM(CASE WHEN right = 'call' THEN volume ELSE 0 END) AS call_volume,
      SUM(delta * open_interest * 100.0) AS net_delta_exposure,
      SUM(volume) AS total_volume
    FROM q
    GROUP BY symbol, d
  ),
  vol_agg AS (
    SELECT symbol,
      AVG(total_volume) OVER (PARTITION BY symbol) AS avg_vol,
      STDDEV(total_volume) OVER (PARTITION BY symbol) AS std_vol
    FROM daily
  ),
  vol_stat AS (
    SELECT DISTINCT symbol, avg_vol, std_vol FROM vol_agg
  )
  SELECT
    daily.symbol,
    CAST(daily.d AS TIMESTAMP)                      AS feature_ts,
    daily.last_ts                                    AS information_available_ts,
    daily.put_volume                                 AS put_volume,
    daily.call_volume                                AS call_volume,
    daily.put_volume / NULLIF(daily.call_volume, 0)  AS put_call_ratio,
    atm.iv_atm                                       AS iv_atm,
    p25.iv_25d_put                                   AS iv_25d_put,
    c25.iv_25d_call                                  AS iv_25d_call,
    p25.iv_25d_put - c25.iv_25d_call                 AS iv_skew,
    term.iv_term_slope                               AS iv_term_slope,
    spread.avg_spread_pct                            AS avg_spread_pct,
    (daily.total_volume - vol_stat.avg_vol) / NULLIF(vol_stat.std_vol, 0) AS volume_anomaly_zscore,
    oi_conc.top5_oi / NULLIF(oi_conc.total_oi, 0)    AS oi_concentration,
    daily.net_delta_exposure                         AS net_delta_exposure,
    current_timestamp()                              AS processed_ts
  FROM daily
  LEFT JOIN atm    ON atm.symbol = daily.symbol AND atm.d = daily.d
  LEFT JOIN p25    ON p25.symbol = daily.symbol AND p25.d = daily.d
  LEFT JOIN c25    ON c25.symbol = daily.symbol AND c25.d = daily.d
  LEFT JOIN term   ON term.symbol = daily.symbol AND term.d = daily.d
  LEFT JOIN oi_conc ON oi_conc.symbol = daily.symbol AND oi_conc.d = daily.d
  LEFT JOIN spread ON spread.symbol = daily.symbol AND spread.d = daily.d
  LEFT JOIN vol_stat ON vol_stat.symbol = daily.symbol
) AS src
ON tgt.symbol = src.symbol AND tgt.feature_ts = src.feature_ts
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
