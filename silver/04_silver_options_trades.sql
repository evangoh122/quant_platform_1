-- silver_options_trades: bronze_options_trades -> silver_options_trades
--
-- Source decision: silver_options_trades is fed from bronze_options_trades
-- (60,068 real trade records carrying minute-bar OHLCV + trade_count + vwap).
-- bronze_options_day (146M rows) is a separate DAILY rollup keyed by
-- (contract_symbol, event_date) with a different column set that lacks the
-- minute `participant_ts` and `notional` semantics this target requires, so it
-- is NOT used here. Justified in the verdict.
--
-- Normalizes right -> 'C'/'P', computes notional = volume * close * 100
-- (contract multiplier). Idempotent: MERGE on dedup_hash.

MERGE INTO bootcamp_students.evangoh_capstone.silver_options_trades AS tgt
USING (
  SELECT
    option_symbol,
    underlying,
    expiry,
    strike,
    CASE WHEN lower(right) IN ('call', 'c') THEN 'C'
         WHEN lower(right) IN ('put', 'p')  THEN 'P'
         ELSE upper(right)
    END                                     AS right,
    open,
    high,
    low,
    close,
    CAST(volume AS INT)                     AS volume,
    CAST(trade_count AS INT)                AS trade_count,
    vwap,
    CAST(volume AS DOUBLE) * close * 100.0  AS notional,
    participant_ts,
    sha2(concat_ws('|', option_symbol, cast(participant_ts AS STRING),
                   coalesce(cast(sequence_id AS STRING), '')), 256) AS dedup_hash,
    current_timestamp()                     AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_options_trades
  WHERE underlying IN (SELECT symbol FROM universe)
    AND expiry IS NOT NULL AND strike IS NOT NULL AND right IS NOT NULL
    AND participant_ts IS NOT NULL
) AS src
ON tgt.dedup_hash = src.dedup_hash
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
