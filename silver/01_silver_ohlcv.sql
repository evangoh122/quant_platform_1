-- silver_ohlcv: bronze_ohlcv -> silver_ohlcv
--
-- Enforces numeric types, UTC timestamps, is_regular_session flag,
-- bar_missing flag, mid price, dedup via dedup_hash, processed_ts.
--
-- Range rules (enforced by WHERE): high >= max(open, close),
-- low <= min(open, close), volume >= 0. Violating rows are routed to
-- silver_ohlcv_quarantine_batch by 02_silver_ohlcv_quarantine.sql.
--
-- Idempotent: MERGE on dedup_hash. Re-running does not duplicate rows.
-- Chunked by date partition by the orchestrator via {date_start}/{date_end}.

MERGE INTO bootcamp_students.evangoh_capstone.silver_ohlcv AS tgt
USING (
  SELECT
    symbol,
    event_ts,
    open,
    high,
    low,
    close,
    CAST(volume AS BIGINT)                      AS volume,
    vwap,
    CAST(trade_count AS INT)                    AS trade_count,
    timespan,
    (open + close) / 2.0                        AS mid,
    CASE
      WHEN timespan = 'day' THEN TRUE
      ELSE (hour(from_utc_timestamp(event_ts, 'America/New_York')) * 60
            + minute(from_utc_timestamp(event_ts, 'America/New_York')))
           BETWEEN 570 AND 960
    END                                          AS is_regular_session,
    FALSE                                        AS bar_missing,
    sha2(concat_ws('|', symbol, cast(event_ts AS STRING), timespan), 256)
                                                 AS dedup_hash,
    current_timestamp()                          AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_ohlcv
  WHERE open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
    AND high >= GREATEST(open, close)
    AND low  <= LEAST(open, close)
    AND COALESCE(volume, 0) >= 0
    AND DATE(event_ts) >= '{date_start}' AND DATE(event_ts) < '{date_end}'
) AS src
ON tgt.dedup_hash = src.dedup_hash
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
