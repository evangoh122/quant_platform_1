-- gold_tradable_universe: bronze_ohlcv_day -> gold_tradable_universe
--
-- Point-in-time daily tradable universe. For each trading date t the universe
-- is the top ``universe_n`` (default 300) symbols by trailing 60-day median
-- dollar volume, computed ONLY from bars with event_date < t, plus a recency
-- filter (traded on each of the last 5 sessions) and a minimum history
-- (>= 252 sessions). The recency filter is what keeps delisted/stale names out
-- of the screen (QUANT_STRATEGIES.md / EXECUTION_PLAN.md "where Codex corrected
-- the spec" item 1): a naive top-N by raw ADV would otherwise admit names that
-- have since stopped trading.
--
-- Point-in-time key. The universe for date t is computable only after the close
-- of the previous session (the last day whose bars it uses). So
-- information_available_ts = 16:00 America/New_York of the previous session,
-- converted to UTC (DST-aware), plus a publication buffer (same convention as
-- gold/02_gold_options_features.sql). A signal produced at day t's close is
-- therefore entitled to see the universe for day t+1 (which depends on data
-- through day t), and never the same day's universe.
--
-- Idempotent: MERGE on (trade_date, symbol).

CREATE TABLE IF NOT EXISTS bootcamp_students.evangoh_capstone.gold_tradable_universe (
  trade_date              DATE        NOT NULL,
  symbol                  STRING      NOT NULL,
  med_adv_60d             DOUBLE,
  adv_rank                INT,
  information_available_ts TIMESTAMP  NOT NULL,
  processed_ts            TIMESTAMP   NOT NULL
);

DECLARE OR REPLACE VARIABLE universe_n        INT DEFAULT 300;
DECLARE OR REPLACE VARIABLE pub_buffer_minutes INT DEFAULT 30;

MERGE INTO bootcamp_students.evangoh_capstone.gold_tradable_universe AS tgt
USING (
  WITH bars AS (
    SELECT
      symbol,
      event_date,
      close * volume AS dollar_volume
    FROM bootcamp_students.evangoh_capstone.bronze_ohlcv_day
    WHERE event_date IS NOT NULL
      AND close IS NOT NULL
      AND volume IS NOT NULL
      AND close > 0
  ),
  -- Dense calendar x symbols grid.  Every (symbol, market_date) pair exists
  -- even when the symbol did not trade that day (dollar_volume IS NULL).
  -- This prevents look-ahead: recency counts market sessions, not the
  -- symbol's own observation count.
  grid AS (
    SELECT symbol, market_date
    FROM (SELECT DISTINCT symbol FROM bars)
    CROSS JOIN (SELECT DISTINCT event_date AS market_date FROM bars)
    UNION
    SELECT symbol, event_date AS market_date
    FROM bars
  ),
  grid_bars AS (
    SELECT
      g.symbol,
      g.market_date AS event_date,
      b.dollar_volume
    FROM grid g
    LEFT JOIN bars b ON b.symbol = g.symbol AND b.event_date = g.market_date
  ),
  stats AS (
    SELECT
      symbol,
      event_date,
      PERCENTILE(dollar_volume, 0.5) OVER (
        PARTITION BY symbol ORDER BY event_date
        ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING
      ) AS med_adv_60d,
      COUNT(*) OVER (
        PARTITION BY symbol ORDER BY event_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
      ) AS history,
      -- Recency: count of the last 5 *market sessions* on which the symbol
      -- traded.  A symbol missing even one of the last 5 sessions is excluded.
      SUM(CASE WHEN dollar_volume IS NOT NULL THEN 1 ELSE 0 END) OVER (
        PARTITION BY symbol ORDER BY event_date
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
      ) AS recency
    FROM grid_bars
  ),
  qualified AS (
    SELECT symbol, event_date AS trade_date, med_adv_60d
    FROM stats
    WHERE history >= 252
      AND recency = 5
      AND med_adv_60d IS NOT NULL
  ),
  ranked AS (
    SELECT
      trade_date,
      symbol,
      med_adv_60d,
      ROW_NUMBER() OVER (
        PARTITION BY trade_date ORDER BY med_adv_60d DESC, symbol
      ) AS adv_rank
    FROM qualified
  ),
  cal AS (
    SELECT
      event_date,
      LAG(event_date) OVER (ORDER BY event_date) AS prev_date
    FROM (SELECT DISTINCT event_date FROM bars)
  )
  SELECT
    r.trade_date,
    r.symbol,
    r.med_adv_60d,
    CAST(r.adv_rank AS INT) AS adv_rank,
    convert_timezone('America/New_York', 'UTC',
        to_timestamp(concat(cast(c.prev_date AS STRING), ' 16:00:00')))
      + make_interval(0, 0, 0, 0, 0, pub_buffer_minutes, 0)
      AS information_available_ts,
    current_timestamp() AS processed_ts
  FROM ranked r
  JOIN cal c ON c.event_date = r.trade_date
  WHERE r.adv_rank <= universe_n
    AND c.prev_date IS NOT NULL
) AS src
ON tgt.trade_date = src.trade_date AND tgt.symbol = src.symbol
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
-- The universe is fully recomputed each run, so a (trade_date, symbol) no longer selected
-- must be removed; otherwise members admitted by an earlier, flawed rule would persist.
WHEN NOT MATCHED BY SOURCE THEN DELETE
