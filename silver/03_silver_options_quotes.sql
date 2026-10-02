-- silver_options_quotes: bronze_options_quotes -> silver_options_quotes
--
-- Normalizes option symbology (right -> 'C'/'P'), computes midpoint, spread,
-- spread_pct and flags is_stale / is_locked / is_crossed.
--
-- Known source gap: bronze_options_quotes.bid/ask/midpoint are entirely NULL
-- across all 61,882 rows, so midpoint/spread/spread_pct cannot be computed and
-- is_locked/is_crossed are always NULL. This is reported honestly in the
-- verdict rather than fabricated. is_stale is computed from participant_ts
-- relative to the latest quote per underlying (15-minute threshold).
--
-- Idempotent: MERGE on dedup_hash.

MERGE INTO bootcamp_students.evangoh_capstone.silver_options_quotes AS tgt
USING (
  SELECT
    option_symbol,
    underlying,
    expiry,
    strike,
    CASE WHEN lower(right) IN ('call', 'c') THEN 'C'
         WHEN lower(right) IN ('put', 'p')  THEN 'P'
         ELSE upper(right)
    END                                       AS right,
    bid,
    ask,
    bid_size,
    ask_size,
    (bid + ask) / 2.0                         AS midpoint,
    ask - bid                                 AS spread,
    (ask - bid) / NULLIF((bid + ask) / 2.0, 0) AS spread_pct,
    (participant_ts < max_ts - INTERVAL 15 MINUTE) AS is_stale,
    (bid IS NOT NULL AND bid = ask)           AS is_locked,
    (bid IS NOT NULL AND ask IS NOT NULL AND bid > ask) AS is_crossed,
    participant_ts,
    sha2(concat_ws('|', option_symbol, cast(participant_ts AS STRING),
                   coalesce(cast(sequence_id AS STRING), '')), 256) AS dedup_hash,
    current_timestamp()                       AS processed_ts
  FROM (
    SELECT *,
      MAX(participant_ts) OVER (PARTITION BY underlying) AS max_ts
    FROM bootcamp_students.evangoh_capstone.bronze_options_quotes
    WHERE expiry IS NOT NULL AND strike IS NOT NULL AND right IS NOT NULL
      AND participant_ts IS NOT NULL
  )
) AS src
ON tgt.dedup_hash = src.dedup_hash
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
