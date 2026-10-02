-- silver_ohlcv_quarantine_batch: capture malformed bronze_ohlcv rows.
--
-- The pre-existing `silver_ohlcv_quarantine` is a STREAMING_TABLE and cannot
-- accept batch INSERTs (it errors with STREAMING_TABLE_NEEDS_REFRESH). Batch
-- backfill therefore writes quarantined rows to this MANAGED table instead.
-- Rows landing here violate at least one range/NULL rule:
--   high < max(open,close), low > min(open,close), volume < 0,
--   or NULL open/high/low/close.
--
-- Idempotent: MERGE on (dedup_hash, quarantine_reason).

CREATE TABLE IF NOT EXISTS bootcamp_students.evangoh_capstone.silver_ohlcv_quarantine_batch (
  symbol             STRING,
  event_ts           TIMESTAMP,
  open               DOUBLE,
  high               DOUBLE,
  low                DOUBLE,
  close              DOUBLE,
  volume             BIGINT,
  vwap               DOUBLE,
  trade_count        INT,
  timespan           STRING,
  source             STRING,
  source_file        STRING,
  ingest_ts          TIMESTAMP,
  quarantine_reason  STRING,
  dedup_hash         STRING,
  processed_ts       TIMESTAMP
)
USING DELTA;

MERGE INTO bootcamp_students.evangoh_capstone.silver_ohlcv_quarantine_batch AS tgt
USING (
  SELECT
    symbol,
    event_ts,
    open,
    high,
    low,
    close,
    CAST(volume AS BIGINT)   AS volume,
    vwap,
    CAST(trade_count AS INT) AS trade_count,
    timespan,
    source,
    source_file,
    ingest_ts,
    CASE
      WHEN open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL THEN 'null_price'
      WHEN high < GREATEST(open, close)                               THEN 'high_below_open_close'
      WHEN low  > LEAST(open, close)                                  THEN 'low_above_open_close'
      WHEN volume < 0                                                 THEN 'negative_volume'
      ELSE 'unknown'
    END                     AS quarantine_reason,
    sha2(concat_ws('|', 'quarantine', symbol, cast(event_ts AS STRING), timespan, source), 256)
                            AS dedup_hash,
    current_timestamp()     AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_ohlcv
  WHERE symbol IN (SELECT symbol FROM universe)
    AND (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
      OR high < GREATEST(open, close)
      OR low  > LEAST(open, close)
      OR volume < 0)
) AS src
ON tgt.dedup_hash = src.dedup_hash AND tgt.quarantine_reason = src.quarantine_reason
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
