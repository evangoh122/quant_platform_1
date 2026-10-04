-- gold_options_features: bronze_options_day -> gold_options_features
--
-- Daily per-underlying options features, re-sourced (round 3) from
-- bronze_options_day — the 146M-row daily options history (503 dates,
-- 7,770 underlyings) — instead of bronze_options_quotes (a one-day snapshot).
--
-- SOURCE SPLIT (documented, not hidden):
--   bronze_options_day carries per-contract daily volume and trade_count but
--   has NO implied-volatility, greeks, or open interest. Those fields exist
--   ONLY in bronze_options_quotes / silver_options_quotes, which are a
--   SINGLE-DAY snapshot (2026-09-02, 12 underlyings).
--
-- Therefore:
--   * put_volume / call_volume / put_call_ratio / volume_anomaly_zscore are
--     built across ALL 503 dates from bronze_options_day.
--   * iv_atm / iv_25d_put / iv_25d_call / iv_skew / iv_term_slope /
--     oi_concentration / net_delta_exposure / avg_spread_pct are populated
--     for the single snapshot date only (LEFT JOIN from the quotes snapshot)
--     and are NULL for every other date. They are NOT forward-filled,
--     interpolated, or synthesised: a forward-filled IV across 503 days would
--     be fabricated data and would silently corrupt any model trained on it.
--
-- volume_anomaly_zscore is a trailing 20-day rolling z-score of total daily
-- option volume per underlying (ROWS BETWEEN 19 PRECEDING AND CURRENT ROW);
-- the first ~19 days of each symbol are NULL (insufficient history for a
-- sample standard deviation).
--
-- information_available_ts (round 5 fix): the provider stamps a daily options
-- bar at the START of the day (event_ts = 04:00/05:00 UTC = midnight New York),
-- but the bar's volume covers the WHOLE session. A feature row for day d is
-- therefore NOT observable until that session closes. Availability is set to
-- 16:00 America/New_York on day d, converted to UTC (DST-aware), plus a
-- publication buffer (named constant opt_pub_buffer_minutes, default 30):
--
--     convert_timezone('America/New_York', 'UTC',
--         to_timestamp(concat(cast(event_date AS STRING), ' 16:00:00')))
--       + make_interval(0, 0, 0, 0, 0, opt_pub_buffer_minutes, 0)
--
--   -> summer (EDT) 20:30 UTC, winter (EST) 21:30 UTC.
--
-- NOTE: the request suggested to_utc_timestamp(<d> 16:00, 'America/New_York'),
-- but on this workspace to_utc_timestamp is deprecated and double-converts via
-- the session timezone, returning 04:00/05:00 UTC (the SAME start-of-day bug)
-- instead of 20:00/21:00 UTC. convert_timezone(source, target, ts) is the
-- ANSI-standard DST-aware function and yields the correct values (verified).
--
-- information_available_ts is NOT NULL and PIT-safe (<= any end-of-day
-- prediction_ts; a same-day intraday prediction at, e.g., 15:00 UTC no longer
-- sees day d's options because 20:30 UTC > 15:00 UTC).
-- Idempotent: MERGE on (symbol, feature_ts).
--

DECLARE OR REPLACE VARIABLE opt_pub_buffer_minutes INT DEFAULT 30;

-- Note on the fixed 16-column schema (docs/DATA_SCHEMAS.md): round 3 also
-- suggested an option-volume-to-equity-volume ratio, term/strike structure of
-- volume, and trade_count flow intensity. Those have no column in the fixed
-- gold_options_features schema; adding columns would violate the "schemas must
-- match docs/DATA_SCHEMAS.md exactly" mandate, so they are deliberately
-- omitted. No silver_options_day staging table was invented for the same
-- reason (no such table exists in the target schema).

MERGE INTO bootcamp_students.evangoh_capstone.gold_options_features AS tgt
USING (
  WITH day AS (
    SELECT
      underlying AS symbol,
      event_date AS d,
      convert_timezone('America/New_York', 'UTC',
          to_timestamp(concat(cast(event_date AS STRING), ' 16:00:00')))
        + make_interval(0, 0, 0, 0, 0, opt_pub_buffer_minutes, 0)
        AS information_available_ts,
      SUM(CASE WHEN UPPER(right) = 'PUT'  THEN volume ELSE 0 END) AS put_volume,
      SUM(CASE WHEN UPPER(right) = 'CALL' THEN volume ELSE 0 END) AS call_volume,
      SUM(volume) AS total_volume
    FROM bootcamp_students.evangoh_capstone.bronze_options_day
    WHERE underlying IN (SELECT symbol FROM universe)
      AND underlying IS NOT NULL
      AND event_date IS NOT NULL
      AND event_ts IS NOT NULL
    GROUP BY underlying, event_date
  ),
  vol_win AS (
    SELECT
      symbol, d, total_volume,
      AVG(total_volume) OVER w    AS avg_vol,
      STDDEV(total_volume) OVER w AS std_vol
    FROM day
    WINDOW w AS (PARTITION BY symbol ORDER BY d ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
  ),
  -- Snapshot-only IV/greek/OI/delta source (single date, 12 underlyings).
  q AS (
    SELECT
      underlying AS symbol,
      DATE(participant_ts) AS d,
      right, strike, expiry, open_interest,
      implied_volatility AS iv, delta
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
      FROM q WHERE UPPER(right) = 'PUT' AND iv IS NOT NULL AND delta IS NOT NULL
    ) WHERE rn = 1
  ),
  c25 AS (
    SELECT symbol, d, iv AS iv_25d_call
    FROM (
      SELECT symbol, d, iv,
        ROW_NUMBER() OVER (PARTITION BY symbol, d ORDER BY ABS(delta - 0.25) ASC, strike) AS rn
      FROM q WHERE UPPER(right) = 'CALL' AND iv IS NOT NULL AND delta IS NOT NULL
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
  snap_daily AS (
    SELECT symbol, d,
      SUM(delta * open_interest * 100.0) AS net_delta_exposure
    FROM q
    GROUP BY symbol, d
  ),
  snap AS (
    SELECT s.symbol, s.d,
      atm.iv_atm,
      p25.iv_25d_put,
      c25.iv_25d_call,
      p25.iv_25d_put - c25.iv_25d_call AS iv_skew,
      term.iv_term_slope,
      spread.avg_spread_pct,
      oi_conc.top5_oi / NULLIF(oi_conc.total_oi, 0) AS oi_concentration,
      s.net_delta_exposure
    FROM snap_daily s
    LEFT JOIN atm     ON atm.symbol = s.symbol AND atm.d = s.d
    LEFT JOIN p25     ON p25.symbol = s.symbol AND p25.d = s.d
    LEFT JOIN c25     ON c25.symbol = s.symbol AND c25.d = s.d
    LEFT JOIN term    ON term.symbol = s.symbol AND term.d = s.d
    LEFT JOIN spread  ON spread.symbol = s.symbol AND spread.d = s.d
    LEFT JOIN oi_conc ON oi_conc.symbol = s.symbol AND oi_conc.d = s.d
  )
  SELECT
    day.symbol,
    CAST(day.d AS TIMESTAMP)                              AS feature_ts,
    day.information_available_ts                          AS information_available_ts,
    day.put_volume                                        AS put_volume,
    day.call_volume                                       AS call_volume,
    day.put_volume / NULLIF(day.call_volume, 0)           AS put_call_ratio,
    snap.iv_atm                                           AS iv_atm,
    snap.iv_25d_put                                       AS iv_25d_put,
    snap.iv_25d_call                                      AS iv_25d_call,
    snap.iv_skew                                          AS iv_skew,
    snap.iv_term_slope                                    AS iv_term_slope,
    snap.avg_spread_pct                                   AS avg_spread_pct,
    (day.total_volume - vw.avg_vol) / NULLIF(vw.std_vol, 0) AS volume_anomaly_zscore,
    snap.oi_concentration                                 AS oi_concentration,
    snap.net_delta_exposure                               AS net_delta_exposure,
    current_timestamp()                                   AS processed_ts
  FROM day
  LEFT JOIN vol_win vw ON vw.symbol = day.symbol AND vw.d = day.d
  LEFT JOIN snap     ON snap.symbol = day.symbol AND snap.d = day.d
) AS src
ON tgt.symbol = src.symbol AND tgt.feature_ts = src.feature_ts
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
