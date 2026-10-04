# NL1 Proposed Serving Views

> **Proposal only — to be created by a Databricks admin/owner; this lane does not execute this DDL.**

This document proposes `CREATE VIEW` DDL for every approved serving view named by the NL1 semantic registry. An admin must replace catalog/schema placeholders before execution.

## Assumptions and conventions

- **Date grain:** All views are daily grain. No intraday data.
- **PIT safety:** Every view includes `information_available_ts` for point-in-time correctness. Queries must filter on `information_available_ts <= :query_timestamp` to avoid look-ahead bias.
- **Deduplication:** Source tables may contain multiple rows per (symbol, event_date). Views use `ROW_NUMBER() OVER (PARTITION BY symbol, event_date ORDER BY information_available_ts DESC) = 1` for as-of deduplication.
- **Adjustment:** When `silver_ohlcv_day_adjusted` is available (registry flag `adjusted_source_available: true`), views use `adj_close`, `adj_volume`, etc. from the adjusted source. `adj_*` levels are current-scale back-adjusted and approved for RETURNS. Price LEVELS shown historically are display values (disclose this). When the adjusted source is unavailable (default), views fall back to `bronze_ohlcv_day` with unadjusted prices and split-safety rejection.
- **Null rules:** Nulls in numeric fields indicate missing data; nulls are never interpolated. A `return_1d` that is NULL from the adjusted source indicates a data-quality break; such days are excluded from aggregates and disclosed.
- **Return formula (adjusted):** `return_1d` comes directly from `silver_ohlcv_day_adjusted.return_1d`. NULL values indicate data-quality breaks and are excluded from aggregates.
- **Return formula (unadjusted fallback):** `return_1d = (close - LAG(close) OVER (PARTITION BY symbol ORDER BY event_date)) / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date)` — NOTE: this uses unadjusted prices; split-safety rejection applies.
- **Realized volatility:** 20-day rolling standard deviation of daily returns, annualized by `* SQRT(252)`.
- **Drawdown:** Running drawdown from peak: `(close - MAX(close) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)) / MAX(close) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`
- **Momentum:** 20-day price momentum: `(close / LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_date)) - 1`
- **Relative performance:** Difference between entity cumulative return and benchmark cumulative return over the same window.
- **iv_atm:** At-the-money implied volatility from options chain, as reported in `gold_options_features`.
- **Daily PIT availability:** For daily bronze bars, `information_available_ts` is derived as `to_utc_timestamp(concat(event_date, ' 16:30:00'), 'America/New_York')` — i.e., 16:30 ET on the bar date, with DST handled by the timezone function.

## Grants

The future service principal receives:
- `USE CATALOG` on the target catalog
- `USE SCHEMA` on the target schema
- `SELECT` on dedicated serving views only, **not** on source Bronze/Silver/Gold tables

## Status

**DDL is unexecuted and unverified until owner action.**

---

## serve_daily_prices_v1

Daily adjusted (or unadjusted fallback) close, OHLC, and volume.

### Primary DDL — adjusted source (`adjusted_source_available: true`)

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_prices_v1 AS
WITH as_of_filtered AS (
    SELECT
        symbol,
        event_date,
        adj_open,
        adj_high,
        adj_low,
        adj_close,
        adj_volume,
        information_available_ts,
        processed_ts
    FROM ${catalog}.${schema}.silver_ohlcv_day_adjusted
    WHERE information_available_ts <= :as_of
),
deduped AS (
    SELECT
        symbol,
        event_date,
        adj_open,
        adj_high,
        adj_low,
        adj_close,
        adj_volume,
        information_available_ts,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, event_date
            ORDER BY processed_ts DESC
        ) AS rn
    FROM as_of_filtered
)
SELECT
    symbol,
    event_date,
    adj_open AS open_price,
    adj_high AS high_price,
    adj_low AS low_price,
    adj_close AS close_price,
    adj_volume AS volume,
    information_available_ts
FROM deduped
WHERE rn = 1;
```

### Fallback DDL — unadjusted source (`adjusted_source_available: false`)

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_prices_v1 AS
WITH as_of_filtered AS (
    SELECT
        symbol,
        event_date,
        open,
        high,
        low,
        close,
        volume,
        ingest_ts
    FROM ${catalog}.${schema}.bronze_ohlcv_day
    WHERE to_utc_timestamp(concat(event_date, ' 16:30:00'), 'America/New_York') <= :as_of
),
deduped AS (
    SELECT
        symbol,
        event_date,
        open,
        high,
        low,
        close,
        volume,
        to_utc_timestamp(concat(event_date, ' 16:30:00'), 'America/New_York')
            AS information_available_ts,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, event_date
            ORDER BY ingest_ts DESC
        ) AS rn
    FROM as_of_filtered
)
SELECT
    symbol,
    event_date,
    open AS open_price,
    high AS high_price,
    low AS low_price,
    close AS close_price,
    volume,
    information_available_ts
FROM deduped
WHERE rn = 1;
```

**Source:** `silver_ohlcv_day_adjusted` (primary) or `bronze_ohlcv_day` (fallback).

**Column notes:**
- `event_date` is the daily grain column (not `trade_date`).
- In the primary (adjusted) path, `close_price` maps to `adj_close` (current-scale back-adjusted). Historical price levels are display values, not model features.
- In the fallback (unadjusted) path, `close_price` maps to raw `close`. The registry marks `price_adjustment: unadjusted`.
- `information_available_ts` is sourced directly from the adjusted table, or derived as 16:30 America/New_York on `event_date` in the fallback.

---

## serve_daily_equity_metrics_v1

Daily derived equity metrics: return, realized volatility, drawdown, momentum.

### Primary DDL — adjusted source (`adjusted_source_available: true`)

When the adjusted source is available, `return_1d` comes from `silver_ohlcv_day_adjusted` (via the daily prices view). NULL `return_1d` values indicate data-quality breaks and are excluded from aggregates.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_equity_metrics_v1 AS
WITH daily_prices AS (
    SELECT
        symbol,
        event_date,
        close_price AS close,
        volume,
        information_available_ts
    FROM ${catalog}.${schema}.serve_daily_prices_v1
    WHERE information_available_ts <= :as_of
),
-- return_1d comes from the adjusted source; NULL = data-quality break
-- For views that need return_1d, join back to the adjusted source
returns_from_source AS (
    SELECT
        dp.symbol,
        dp.event_date,
        dp.close,
        GREATEST(dp.information_available_ts, adj.information_available_ts) AS information_available_ts,
        adj.return_1d
    FROM daily_prices dp
    LEFT JOIN (
        SELECT symbol, event_date, return_1d, information_available_ts,
               ROW_NUMBER() OVER (PARTITION BY symbol, event_date ORDER BY processed_ts DESC) AS rn
        FROM ${catalog}.${schema}.silver_ohlcv_day_adjusted
        WHERE information_available_ts <= :as_of
    ) adj ON dp.symbol = adj.symbol AND dp.event_date = adj.event_date AND adj.rn = 1
),
with_vol AS (
    SELECT
        symbol,
        event_date,
        close,
        information_available_ts,
        return_1d,
        STDDEV_SAMP(return_1d) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) * SQRT(252) AS realized_vol_20d,
        MAX(information_available_ts) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS realized_vol_20d_info_ts
    FROM returns_from_source
    WHERE return_1d IS NOT NULL  -- exclude data-quality breaks
),
with_drawdown AS (
    SELECT
        symbol,
        event_date,
        close,
        information_available_ts,
        return_1d,
        realized_vol_20d,
        realized_vol_20d_info_ts,
        (close - MAX(close) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) / MAX(close) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS drawdown,
        MAX(information_available_ts) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS drawdown_info_ts
    FROM with_vol
)
SELECT
    symbol,
    event_date,
    close,
    return_1d,
    realized_vol_20d,
    drawdown,
    (close / LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_date)) - 1
        AS momentum_20d,
    GREATEST(
        information_available_ts,
        realized_vol_20d_info_ts,
        drawdown_info_ts
    ) AS information_available_ts
FROM with_drawdown;
```

### Fallback DDL — unadjusted source (`adjusted_source_available: false`)

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_equity_metrics_v1 AS
WITH daily_prices AS (
    SELECT
        symbol,
        event_date,
        close_price AS close,
        information_available_ts
    FROM ${catalog}.${schema}.serve_daily_prices_v1
    WHERE information_available_ts <= :as_of
),
with_returns AS (
    SELECT
        symbol,
        event_date,
        close,
        information_available_ts,
        (close - LAG(close) OVER (PARTITION BY symbol ORDER BY event_date))
            / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date)
            AS return_1d
    FROM daily_prices
),
with_vol AS (
    SELECT
        symbol,
        event_date,
        close,
        information_available_ts,
        return_1d,
        STDDEV_SAMP(return_1d) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) * SQRT(252) AS realized_vol_20d,
        MAX(information_available_ts) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS realized_vol_20d_info_ts
    FROM with_returns
),
with_drawdown AS (
    SELECT
        symbol,
        event_date,
        close,
        information_available_ts,
        return_1d,
        realized_vol_20d,
        realized_vol_20d_info_ts,
        (close - MAX(close) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) / MAX(close) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS drawdown,
        MAX(information_available_ts) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS drawdown_info_ts
    FROM with_vol
)
SELECT
    symbol,
    event_date,
    close,
    return_1d,
    realized_vol_20d,
    drawdown,
    (close / LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_date)) - 1
        AS momentum_20d,
    GREATEST(
        information_available_ts,
        realized_vol_20d_info_ts,
        drawdown_info_ts
    ) AS information_available_ts
FROM with_drawdown;
```

**Source:** Derived from `serve_daily_prices_v1`.

**Column notes:**
- In adjusted mode, `return_1d` is sourced from `silver_ohlcv_day_adjusted.return_1d`. NULL values (data-quality breaks) are excluded from the CTE before volatility/drawdown computation.
- In fallback mode, `return_1d` is computed from unadjusted `close` prices. Split-safety rejection (policy layer) prevents queries over known/suspected splits.

---

## serve_relative_performance_v1

Daily entity relative performance vs benchmark.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_relative_performance_v1 AS
WITH entity_returns AS (
    SELECT
        symbol,
        event_date,
        return_1d,
        information_available_ts
    FROM ${catalog}.${schema}.serve_daily_equity_metrics_v1
    WHERE event_date >= :start_date
      AND information_available_ts <= :as_of
),
benchmark_returns AS (
    SELECT
        event_date,
        return_1d AS bench_return,
        information_available_ts AS bench_info_ts
    FROM ${catalog}.${schema}.serve_daily_equity_metrics_v1
    WHERE symbol = :benchmark
      AND event_date >= :start_date
      AND information_available_ts <= :as_of
),
entity_cumulative AS (
    SELECT
        symbol,
        event_date,
        return_1d,
        information_available_ts,
        -- Guard: GREATEST(1 + return_1d, 1e-10) prevents LN(0) or LN(negative).
        -- Assumption: daily returns on positive-priced equities are bounded
        -- above -1 (price cannot go below 0). NULL data-quality breaks are
        -- excluded by the WHERE clause. The guard is defensive only.
        EXP(SUM(LN(GREATEST(1 + return_1d, 1e-10))) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) - 1 AS cumulative_return,
        MAX(information_available_ts) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS entity_info_ts
    FROM entity_returns
    WHERE return_1d IS NOT NULL
),
benchmark_cumulative AS (
    SELECT
        event_date,
        bench_return,
        bench_info_ts,
        EXP(SUM(LN(GREATEST(1 + bench_return, 1e-10))) OVER (
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) - 1 AS bench_cumulative_return,
        MAX(bench_info_ts) OVER (
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS bench_max_info_ts
    FROM benchmark_returns
    WHERE bench_return IS NOT NULL
)
SELECT
    e.symbol,
    e.event_date,
    e.return_1d,
    e.cumulative_return - b.bench_cumulative_return AS rel_perf,
    :benchmark AS benchmark,
    GREATEST(e.entity_info_ts, b.bench_max_info_ts) AS information_available_ts
FROM entity_cumulative e
JOIN benchmark_cumulative b ON e.event_date = b.event_date;
```

**Source:** Derived from `serve_daily_equity_metrics_v1`. Benchmark is a typed bounded parameter (SPY, QQQ, or RSP); the view takes the benchmark as a `:benchmark` bind parameter. The view takes a `:start_date` bind parameter to anchor the cumulative return window to the requested period (not inception-to-date). Cumulative return is computed as `EXP(SUM(LN(1 + return_1d)))` over the window from `:start_date`, and relative performance is entity cumulative minus benchmark cumulative. Output `information_available_ts` is the GREATEST of entity and benchmark availability to ensure PIT safety.

---

## serve_options_metrics_v1

Daily implied volatility (iv_atm) and put/call ratio for options-capable underlyings.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_options_metrics_v1 AS
WITH as_of_filtered AS (
    SELECT
        symbol,
        feature_ts,
        iv_atm,
        put_call_ratio,
        information_available_ts
    FROM ${catalog}.${schema}.gold_options_features
    WHERE information_available_ts <= :as_of
),
deduped AS (
    SELECT
        symbol,
        feature_ts,
        iv_atm,
        put_call_ratio,
        information_available_ts,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, feature_ts
            ORDER BY information_available_ts DESC
        ) AS rn
    FROM as_of_filtered
)
SELECT
    symbol,
    feature_ts,
    iv_atm,
    put_call_ratio,
    information_available_ts
FROM deduped
WHERE rn = 1;
```

**Source:** `gold_options_features` (19,390 rows). Contains `iv_atm`, `put_call_ratio`, `iv_skew`, `iv_term_slope`.

**Column notes:**
- `feature_ts` is the grain column for options features (not `trade_date`).
- `information_available_ts` is sourced directly from `gold_options_features` (already computed upstream).

---

## serve_bounded_daily_bars_v1

Bounded Silver daily bars for price/volume drill-downs on ≤10 named tickers over ≤2 years.

### Primary DDL — adjusted source (`adjusted_source_available: true`)

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_bounded_daily_bars_v1 AS
WITH as_of_filtered AS (
    SELECT
        symbol,
        event_date,
        adj_open,
        adj_high,
        adj_low,
        adj_close,
        adj_volume,
        information_available_ts,
        processed_ts
    FROM ${catalog}.${schema}.silver_ohlcv_day_adjusted
    WHERE information_available_ts <= :as_of
),
deduped AS (
    SELECT
        symbol,
        event_date,
        adj_open,
        adj_high,
        adj_low,
        adj_close,
        adj_volume,
        information_available_ts,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, event_date
            ORDER BY processed_ts DESC
        ) AS rn
    FROM as_of_filtered
)
SELECT
    symbol,
    event_date,
    adj_open AS open_price,
    adj_high AS high_price,
    adj_low AS low_price,
    adj_close AS close_price,
    adj_volume AS volume,
    information_available_ts,
    FALSE AS suspected_split
FROM deduped
WHERE rn = 1;
```

### Fallback DDL — unadjusted source (`adjusted_source_available: false`)

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_bounded_daily_bars_v1 AS
WITH as_of_filtered AS (
    SELECT
        symbol,
        event_date,
        open,
        high,
        low,
        close,
        volume,
        ingest_ts
    FROM ${catalog}.${schema}.bronze_ohlcv_day
    WHERE to_utc_timestamp(concat(event_date, ' 16:30:00'), 'America/New_York') <= :as_of
),
deduped AS (
    SELECT
        symbol,
        event_date,
        open,
        high,
        low,
        close,
        volume,
        to_utc_timestamp(concat(event_date, ' 16:30:00'), 'America/New_York')
            AS information_available_ts,
        CASE
            WHEN LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) > 0
                 AND ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 1) >= 0.4
                 AND (
                     ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 0.1) < 0.03
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 0.5) < 0.015
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 1.0/3.0) < 0.01
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 0.25) < 0.01
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 0.2) < 0.008
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 0.05) < 0.005
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 2.0) < 0.06
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 3.0) < 0.09
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 4.0) < 0.12
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 5.0) < 0.15
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 10.0) < 0.3
                     OR ABS(close / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date) - 20.0) < 0.6
                 )
            THEN TRUE
            ELSE FALSE
        END AS suspected_split,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, event_date
            ORDER BY ingest_ts DESC
        ) AS rn
    FROM as_of_filtered
)
SELECT
    symbol,
    event_date,
    open AS open_price,
    high AS high_price,
    low AS low_price,
    close AS close_price,
    volume,
    information_available_ts,
    suspected_split
FROM deduped
WHERE rn = 1;
```

**Source:** `silver_ohlcv_day_adjusted` (primary) or `bronze_ohlcv_day` (fallback). Silver constraints: ≤10 tickers, ≤2 years, ≤10,000 rows.

**Column notes:**
- `event_date` is the daily grain column (not `trade_date`).
- In the primary (adjusted) path, `close_price` maps to `adj_close` (current-scale back-adjusted). `suspected_split` is always FALSE because the adjusted source has already handled corporate actions.
- In the fallback (unadjusted) path, `close_price` maps to raw `close`. `suspected_split` detects potential splits.
- `information_available_ts` is sourced directly from the adjusted table, or derived as 16:30 America/New_York on `event_date` in the fallback.

---

## known_splits (proposed DDL — to be populated by owner/admin)

```sql
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.known_splits (
    symbol       STRING NOT NULL COMMENT 'Ticker symbol',
    ex_date      DATE NOT NULL COMMENT 'Ex-date of the split',
    ratio        DOUBLE NOT NULL COMMENT 'Split ratio (e.g. 10.0 for 10:1 forward split)',
    source       STRING NOT NULL COMMENT 'Data source (e.g. SEC, vendor name)',
    ingested_ts  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
COMMENT 'Known stock splits for corporate-action safety. To be populated by owner/admin.'
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');
```

**Status:** Proposed. Must be populated by the data owner before corporate-action rejection can be enforced at query time.

---

## Corporate-action safety policy

Prices in `bronze_ohlcv_day` are **unadjusted**. Stock splits create fake returns (e.g. NVDA 10:1 in June 2024 → approximately −90% overnight). The system has two modes controlled by the registry flag `adjusted_source_available`:

### Adjusted mode (`adjusted_source_available: true`)

When `silver_ohlcv_day_adjusted` is available, views use adjusted prices and returns:

1. **Adjusted returns:** `return_1d` comes from `silver_ohlcv_day_adjusted.return_1d`. These are split-adjusted and safe for return/volatility/drawdown/momentum/relative_performance calculations.
2. **Data-quality breaks:** A `return_1d` that is NULL indicates a data-quality break. Such days are excluded from aggregates (volatility, drawdown) and disclosed to the user.
3. **Price levels:** `adj_close` levels are current-scale back-adjusted. Historical price levels are display values — they are not model features. Disclose this assumption.
4. **No split rejection needed:** The adjusted source has already handled corporate actions, so split-safety rejection is not applied.

### Fallback mode (`adjusted_source_available: false`, default)

When `silver_ohlcv_day_adjusted` is not available, the system falls back to unadjusted prices with split-safety rejection:

1. **Known splits rejection:** NL1 policy rejects any intent using `return`, `realized_volatility`, `drawdown`, `momentum`, or `relative_performance` over a date range that contains a row in `known_splits` for any requested symbol. Reason code: `unadjusted_corporate_action`. No SQL is emitted.

2. **Suspected split detection:** The `serve_bounded_daily_bars_v1` view exposes a `suspected_split` boolean column. Queries over affected metrics should reject windows containing `suspected_split = TRUE` rows, with the same reason code.

3. **Price trend exception:** `price.trend` may show raw `close`, with a disclosed assumption: "unadjusted prices — corporate actions may cause discontinuities."

4. **Empty known_splits:** With an empty `known_splits` table, only the detector rule applies. The policy still checks `known_splits` defensively (empty table → no rejections from this rule).

---

## Silver vs Gold routing

| Metric × Operation | Layer | Served from | Constraints |
|---|---|---|---|
| `price.trend` | silver | `serve_bounded_daily_bars_v1` | ≤10 tickers, ≤2 years, ≤10k rows |
| `volume.trend` | silver | `serve_bounded_daily_bars_v1` | ≤10 tickers, ≤2 years, ≤10k rows |
| All other pairs | gold | Gold serving views (`silver_ohlcv_day_adjusted` primary, `bronze_ohlcv_day` fallback) | ≤10 years, ≤5k rows |

---

## Identifier correspondence

All view and column identifiers match the registry YAML `approved_views` list:

| Registry identifier | DDL view name |
|---|---|
| `serve_daily_prices_v1` | `${catalog}.${schema}.serve_daily_prices_v1` |
| `serve_daily_equity_metrics_v1` | `${catalog}.${schema}.serve_daily_equity_metrics_v1` |
| `serve_relative_performance_v1` | `${catalog}.${schema}.serve_relative_performance_v1` |
| `serve_options_metrics_v1` | `${catalog}.${schema}.serve_options_metrics_v1` |
| `serve_bounded_daily_bars_v1` | `${catalog}.${schema}.serve_bounded_daily_bars_v1` |