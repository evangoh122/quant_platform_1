-- silver_ohlcv_day_adjusted: bronze_ohlcv_day + bronze_corporate_actions
--                           -> silver_ohlcv_day_adjusted + data_quality_breaks
--
-- Deterministic daily deduplication, split factor computation, globally
-- back-adjusted OHLC/VWAP/volume, break classification and masked returns.
--
-- Idempotent: MERGE on (symbol, event_date).  A newly ingested future split
-- necessarily changes older current-scale adjusted levels, so a matched
-- update is required (not insert-only).
--
-- The stored adj_* columns are GLOBAL/CURRENT-SCALE back-adjusted display
-- levels.  They are approved for computing returns (the same factor cancels
-- within a split-free interval, and across an ex-date the prior bar includes
-- the split while the ex-date bar does not).  They are NOT approved as
-- model price-level features at a historical observation time.
--
-- Break detection: a candidate is a consecutive observed bar pair with
-- abs(close/prev_close - 1) >= 0.40.  A candidate is explained by a
-- same-date split only if abs((close/prev_close)*split_ratio - 1) <= 0.03.
--
-- Source: massive only.  The _massive_splits CTE filters to source='massive'
-- and deduplicates to one row per (symbol, ex_date) — latest fetched_ts wins.
-- Any rows with another source are IGNORED (not deleted).  The existing
-- price-jump data_quality_breaks logic is the sanity check on Massive's data.

-- ============================================================
-- 1. Create data_quality_breaks table if not exists
-- ============================================================
CREATE TABLE IF NOT EXISTS bootcamp_students.evangoh_capstone.data_quality_breaks (
    symbol                  STRING    NOT NULL,
    event_date              DATE      NOT NULL,
    previous_event_date     DATE,
    previous_close          DOUBLE,
    close                   DOUBLE,
    raw_overnight_return    DOUBLE,
    matched_split_ratio     DOUBLE,
    post_split_gross_return DOUBLE,
    split_error             DOUBLE,
    classification          STRING    NOT NULL,
    reason                  STRING,
    is_masked               BOOLEAN   NOT NULL,
    reviewed_by             STRING,
    reviewed_ts             TIMESTAMP,
    detected_ts             TIMESTAMP NOT NULL,
    processed_ts            TIMESTAMP NOT NULL
) USING DELTA
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');


-- ============================================================
-- 2. Create silver_ohlcv_day_adjusted table if not exists
-- ============================================================
CREATE TABLE IF NOT EXISTS bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted (
    symbol                      STRING    NOT NULL,
    event_date                  DATE      NOT NULL,
    event_ts                    TIMESTAMP,
    open                        DOUBLE,
    high                        DOUBLE,
    low                         DOUBLE,
    close                       DOUBLE,
    volume                      BIGINT,
    vwap                        DOUBLE,
    trade_count                 INT,
    cumulative_split_ratio      DOUBLE,
    price_adjustment_factor     DOUBLE,
    adj_open                    DOUBLE,
    adj_high                    DOUBLE,
    adj_low                     DOUBLE,
    adj_close                   DOUBLE,
    adj_vwap                    DOUBLE,
    adj_volume                  DOUBLE,
    vwap_source                 STRING,
    raw_overnight_return        DOUBLE,
    adjusted_return_1d_unmasked DOUBLE,
    return_1d                   DOUBLE,
    is_data_quality_break       BOOLEAN,
    information_available_ts    TIMESTAMP,
    processed_ts                TIMESTAMP
) USING DELTA
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- Idempotent: add vwap_source column if table already exists without it
ALTER TABLE bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted
    ADD COLUMNS (vwap_source STRING);


-- ============================================================
-- 3. Deduplicated daily source (latest ingest_ts per key)
-- ============================================================
CREATE OR REPLACE TEMP VIEW _deduped_daily AS
SELECT
    symbol,
    event_ts,
    -- Trading date = bronze's own event_date. Do NOT derive it from event_ts: recent bronze rows carry the
    -- previous session's 16:00 ET timestamp (e.g. event_date 2026-09-11 with event_ts 2026-09-10T20:00Z), and
    -- DATE(event_ts) is also session-timezone dependent — deriving it silently dropped those Fridays.
    event_date,
    open,
    high,
    low,
    close,
    CAST(volume AS BIGINT)  AS volume,
    vwap,
    CAST(trade_count AS INT) AS trade_count
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, event_date
            ORDER BY ingest_ts DESC NULLS LAST, event_ts DESC, source, source_file
        ) AS rn
    FROM bootcamp_students.evangoh_capstone.bronze_ohlcv_day
    WHERE timespan = 'day'
      AND event_date IS NOT NULL
      AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
      AND close > 0
      AND high >= GREATEST(open, close)
      AND low  <= LEAST(open, close)
      AND COALESCE(volume, 0) >= 0
) sub
WHERE rn = 1;


-- ============================================================
-- 4. Universe filter: only symbols in Gold + SPY/RSP/QQQ
-- ============================================================
CREATE OR REPLACE TEMP VIEW _universe AS
SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
FROM bootcamp_students.evangoh_capstone.gold_tradable_universe
WHERE symbol IS NOT NULL
UNION SELECT 'SPY'
UNION SELECT 'RSP'
UNION SELECT 'QQQ';


-- ============================================================
-- 4b. Minute-bar VWAP per (symbol, trading date)
--     Aggregates minute bars from silver_ohlcv to produce a
--     volume-weighted typical price per trading day (ET date).
--     Symbols with no minute bars get no rows here — they keep
--     NULL vwap (NEVER fabricate a daily proxy).
-- ============================================================
CREATE OR REPLACE TEMP VIEW _minute_vwap AS
SELECT
    symbol,
    DATE(from_utc_timestamp(event_ts, 'America/New_York')) AS trading_date,
    SUM(COALESCE(vwap, (high + low + close) / 3.0) * volume)
        / NULLIF(SUM(volume), 0) AS minute_vwap
FROM bootcamp_students.evangoh_capstone.silver_ohlcv
WHERE timespan = 'minute'
  AND volume > 0
GROUP BY symbol, DATE(from_utc_timestamp(event_ts, 'America/New_York'));


-- ============================================================
-- 4c. Massive splits: one row per (symbol, ex_date)
--     Filters to source='massive' only.  Deduplicates by
--     latest fetched_ts (Massive can return the same split
--     twice across runs).  Other sources are ignored.
-- ============================================================
CREATE OR REPLACE TEMP VIEW _massive_splits AS
SELECT
    symbol,
    ex_date,
    split_ratio
FROM (
    SELECT
        symbol,
        ex_date,
        split_ratio,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, ex_date
            ORDER BY fetched_ts DESC
        ) AS rn
    FROM bootcamp_students.evangoh_capstone.bronze_corporate_actions
    WHERE source = 'massive'
) sub
WHERE rn = 1;


-- ============================================================
-- 5. Cumulative split factors per (symbol, event_date)
--    cumulative_split_ratio(d) = PRODUCT(split_ratio for splits
--    where ex_date > d).  Uses log-sum-exp for numerical stability.
--    Uses _massive_splits (one row per symbol/ex_date).
-- ============================================================
CREATE OR REPLACE TEMP VIEW _split_factors AS
SELECT
    d.symbol,
    d.event_date,
    COALESCE(
        EXP(SUM(LN(COALESCE(s.split_ratio, 1.0)))),
        1.0
    ) AS cumulative_split_ratio
FROM (
    SELECT DISTINCT symbol, event_date
    FROM _deduped_daily
    WHERE symbol IN (SELECT symbol FROM _universe)
) d
LEFT JOIN _massive_splits s
    ON  s.symbol = d.symbol
    AND s.ex_date > d.event_date   -- strictly greater: ex-date bar is already on new basis
GROUP BY d.symbol, d.event_date;


-- ============================================================
-- 6. Adjusted prices and raw returns
-- ============================================================
CREATE OR REPLACE TEMP VIEW _adjusted AS
SELECT
    dd.symbol,
    dd.event_date,
    dd.event_ts,
    dd.open,
    dd.high,
    dd.low,
    dd.close,
    dd.volume,
    -- Resolved daily VWAP: vendor vwap if non-null, else minute-bar aggregate
    COALESCE(dd.vwap, mv.minute_vwap) AS resolved_vwap,
    dd.trade_count,
    COALESCE(sf.cumulative_split_ratio, 1.0) AS cumulative_split_ratio,
    1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0) AS price_adjustment_factor,
    -- Adjusted OHLCV
    dd.open  * (1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0))  AS adj_open,
    dd.high  * (1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0))  AS adj_high,
    dd.low   * (1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0))  AS adj_low,
    dd.close * (1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0))  AS adj_close,
    CASE WHEN COALESCE(dd.vwap, mv.minute_vwap) IS NOT NULL
         THEN COALESCE(dd.vwap, mv.minute_vwap) * (1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0))
         ELSE NULL
    END AS adj_vwap,
    dd.volume * COALESCE(sf.cumulative_split_ratio, 1.0) AS adj_volume,
    -- VWAP source provenance
    CASE
        WHEN dd.vwap IS NOT NULL THEN 'vendor'
        WHEN mv.minute_vwap IS NOT NULL THEN 'minute_bars'
        ELSE NULL
    END AS vwap_source,
    -- Raw overnight return (for break detection)
    dd.close / NULLIF(LAG(dd.close) OVER (PARTITION BY dd.symbol ORDER BY dd.event_date), 0)
        AS raw_gross_return,
    -- Lagged close for break evidence
    LAG(dd.close) OVER (PARTITION BY dd.symbol ORDER BY dd.event_date)
        AS previous_close,
    LAG(dd.event_date) OVER (PARTITION BY dd.symbol ORDER BY dd.event_date)
        AS previous_event_date,
    -- Adjusted returns
    dd.close * (1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0))
        / NULLIF(
            LAG(dd.close * (1.0 / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0)))
                OVER (PARTITION BY dd.symbol ORDER BY dd.event_date),
            0
        ) - 1.0 AS adjusted_return_1d_unmasked
FROM _deduped_daily dd
JOIN _universe u ON u.symbol = dd.symbol
LEFT JOIN _split_factors sf
    ON  sf.symbol = dd.symbol
    AND sf.event_date = dd.event_date
LEFT JOIN _minute_vwap mv
    ON  mv.symbol = dd.symbol
    AND mv.trading_date = dd.event_date;


-- ============================================================
-- 7. Break candidates: abs(raw_gross_return - 1) >= 0.40
--    Uses _massive_splits for same-day split detection.
-- ============================================================
CREATE OR REPLACE TEMP VIEW _break_candidates AS
SELECT
    a.symbol,
    a.event_date,
    a.previous_event_date,
    a.previous_close,
    a.close,
    a.raw_gross_return - 1.0 AS raw_overnight_return,
    a.raw_gross_return,
    -- Same-day split ratio (product of all splits on this ex_date)
    COALESCE(day_splits.day_split_ratio, 1.0) AS day_split_ratio,
    -- Post-split gross return
    a.raw_gross_return * COALESCE(day_splits.day_split_ratio, 1.0) AS post_split_gross_return,
    -- Split error
    ABS(a.raw_gross_return * COALESCE(day_splits.day_split_ratio, 1.0) - 1.0) AS split_error
FROM _adjusted a
LEFT JOIN (
    SELECT
        symbol,
        ex_date,
        EXP(SUM(LN(split_ratio))) AS day_split_ratio
    FROM _massive_splits
    GROUP BY symbol, ex_date
) day_splits
    ON  day_splits.symbol = a.symbol
    AND day_splits.ex_date = a.event_date
WHERE a.raw_gross_return IS NOT NULL
  AND a.previous_close IS NOT NULL
  AND ABS(a.raw_gross_return - 1.0) >= 0.40;


-- ============================================================
-- 8. Classification
-- ============================================================
CREATE OR REPLACE TEMP VIEW _classified_breaks AS
SELECT
    bc.*,
    CASE
        -- Explained by a same-date split (within 3% tolerance)
        WHEN bc.day_split_ratio != 1.0 AND bc.split_error <= 0.03
            THEN 'SPLIT_EXPLAINED'
        -- Has a same-date split but residual is too large
        WHEN bc.day_split_ratio != 1.0 AND bc.split_error > 0.03
            THEN 'UNEXPLAINED_PENDING'
        -- No matching split at all
        ELSE 'UNEXPLAINED_PENDING'
    END AS classification,
    CASE
        WHEN bc.day_split_ratio != 1.0 AND bc.split_error <= 0.03
            THEN 'same-date split within 3% tolerance'
        WHEN bc.day_split_ratio != 1.0 AND bc.split_error > 0.03
            THEN 'same-date split but residual exceeds 3%'
        ELSE 'no matching split event'
    END AS reason,
    CASE
        WHEN bc.day_split_ratio != 1.0 AND bc.split_error <= 0.03
            THEN FALSE  -- SPLIT_EXPLAINED: not masked
        ELSE TRUE       -- UNEXPLAINED_PENDING: masked until reviewed
    END AS is_masked
FROM _break_candidates bc;


-- ============================================================
-- 9. Merge data_quality_breaks (preserve reviewed decisions)
--    Break candidates only (source mismatches no longer exist).
-- ============================================================
MERGE INTO bootcamp_students.evangoh_capstone.data_quality_breaks AS tgt
USING (
    SELECT
        cb.symbol,
        cb.event_date,
        cb.previous_event_date,
        cb.previous_close,
        cb.close,
        cb.raw_overnight_return,
        cb.day_split_ratio     AS matched_split_ratio,
        cb.post_split_gross_return,
        cb.split_error,
        cb.classification,
        cb.reason,
        cb.is_masked,
        current_timestamp()    AS detected_ts,
        current_timestamp()    AS processed_ts
    FROM _classified_breaks cb
) AS src
ON tgt.symbol = src.symbol AND tgt.event_date = src.event_date
-- Only update UNREVIEWED rows; preserve manual review decisions
WHEN MATCHED AND tgt.reviewed_by IS NULL THEN UPDATE SET
    tgt.previous_event_date     = src.previous_event_date,
    tgt.previous_close          = src.previous_close,
    tgt.close                   = src.close,
    tgt.raw_overnight_return    = src.raw_overnight_return,
    tgt.matched_split_ratio     = src.matched_split_ratio,
    tgt.post_split_gross_return = src.post_split_gross_return,
    tgt.split_error             = src.split_error,
    tgt.classification          = src.classification,
    tgt.reason                  = src.reason,
    tgt.is_masked               = src.is_masked,
    tgt.processed_ts            = src.processed_ts
WHEN NOT MATCHED THEN INSERT (
    symbol, event_date, previous_event_date, previous_close, close,
    raw_overnight_return, matched_split_ratio, post_split_gross_return,
    split_error, classification, reason, is_masked,
    reviewed_by, reviewed_ts,
    detected_ts, processed_ts
) VALUES (
    src.symbol, src.event_date, src.previous_event_date, src.previous_close, src.close,
    src.raw_overnight_return, src.matched_split_ratio, src.post_split_gross_return,
    src.split_error, src.classification, src.reason, src.is_masked,
    NULL, NULL,
    src.detected_ts, src.processed_ts
)


-- ============================================================
-- 10. Merge silver_ohlcv_day_adjusted
-- ============================================================
;
MERGE INTO bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted AS tgt
USING (
    SELECT
        a.symbol,
        a.event_date,
        a.event_ts,
        a.open,
        a.high,
        a.low,
        a.close,
        a.volume,
        a.resolved_vwap                AS vwap,
        a.trade_count,
        a.cumulative_split_ratio,
        a.price_adjustment_factor,
        a.adj_open,
        a.adj_high,
        a.adj_low,
        a.adj_close,
        a.adj_vwap,
        a.adj_volume,
        a.vwap_source,
        a.raw_gross_return - 1.0                        AS raw_overnight_return,
        a.adjusted_return_1d_unmasked,
        -- Canonical return: NULL when active break is masked
        CASE
            WHEN br.event_date IS NOT NULL AND br.is_masked = TRUE
                THEN NULL
            ELSE a.adjusted_return_1d_unmasked
        END                                              AS return_1d,
        CASE
            WHEN br.event_date IS NOT NULL AND br.is_masked = TRUE
                THEN TRUE
            ELSE FALSE
        END                                              AS is_data_quality_break,
        -- Daily bar availability: 16:30 ET on the bar date, converted to UTC
        to_utc_timestamp(
            to_timestamp(concat(cast(a.event_date AS STRING), ' 16:30:00')),
            'America/New_York'
        )                                                AS information_available_ts,
        current_timestamp()                              AS processed_ts
    FROM _adjusted a
    LEFT JOIN bootcamp_students.evangoh_capstone.data_quality_breaks br
        ON  br.symbol = a.symbol
        AND br.event_date = a.event_date
        AND br.is_masked = TRUE
        AND br.classification IN ('UNEXPLAINED_PENDING', 'CONFIRMED_DATA_BREAK')
) AS src
ON tgt.symbol = src.symbol AND tgt.event_date = src.event_date
WHEN MATCHED THEN UPDATE SET
    tgt.symbol                      = src.symbol,
    tgt.event_date                  = src.event_date,
    tgt.event_ts                    = src.event_ts,
    tgt.open                        = src.open,
    tgt.high                        = src.high,
    tgt.low                         = src.low,
    tgt.close                       = src.close,
    tgt.volume                      = src.volume,
    tgt.vwap                        = src.vwap,
    tgt.trade_count                 = src.trade_count,
    tgt.cumulative_split_ratio      = src.cumulative_split_ratio,
    tgt.price_adjustment_factor     = src.price_adjustment_factor,
    tgt.adj_open                    = src.adj_open,
    tgt.adj_high                    = src.adj_high,
    tgt.adj_low                     = src.adj_low,
    tgt.adj_close                   = src.adj_close,
    tgt.adj_vwap                    = src.adj_vwap,
    tgt.adj_volume                  = src.adj_volume,
    tgt.vwap_source                 = src.vwap_source,
    tgt.raw_overnight_return        = src.raw_overnight_return,
    tgt.adjusted_return_1d_unmasked = src.adjusted_return_1d_unmasked,
    tgt.return_1d                   = src.return_1d,
    tgt.is_data_quality_break       = src.is_data_quality_break,
    tgt.information_available_ts    = src.information_available_ts,
    tgt.processed_ts                = src.processed_ts
WHEN NOT MATCHED THEN INSERT (
    symbol, event_date, event_ts,
    open, high, low, close,
    volume, vwap, trade_count,
    cumulative_split_ratio, price_adjustment_factor,
    adj_open, adj_high, adj_low, adj_close, adj_vwap, adj_volume,
    vwap_source,
    raw_overnight_return, adjusted_return_1d_unmasked, return_1d,
    is_data_quality_break, information_available_ts, processed_ts
) VALUES (
    src.symbol, src.event_date, src.event_ts,
    src.open, src.high, src.low, src.close,
    src.volume, src.vwap, src.trade_count,
    src.cumulative_split_ratio, src.price_adjustment_factor,
    src.adj_open, src.adj_high, src.adj_low, src.adj_close, src.adj_vwap, src.adj_volume,
    src.vwap_source,
    src.raw_overnight_return, src.adjusted_return_1d_unmasked, src.return_1d,
    src.is_data_quality_break, src.information_available_ts, src.processed_ts
)
-- The source is the full adjusted history for every universe symbol, so any target row it no longer produces is
-- stale (e.g. rows written under an earlier, wrong date derivation) and must be removed.
WHEN NOT MATCHED BY SOURCE THEN DELETE
