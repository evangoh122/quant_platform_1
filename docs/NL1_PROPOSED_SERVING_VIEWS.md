# NL1 Proposed Serving Views

> **Proposal only — to be created by a Databricks admin/owner; this lane does not execute this DDL.**

This document proposes `CREATE VIEW` DDL for every approved serving view named by the NL1 semantic registry. An admin must replace catalog/schema placeholders before execution.

## Assumptions and conventions

- **Date grain:** All views are daily grain. No intraday data.
- **PIT safety:** Every view includes `information_available_ts` for point-in-time correctness. Queries must filter on `information_available_ts <= :query_timestamp` to avoid look-ahead bias.
- **Deduplication:** Source tables may contain multiple rows per (symbol, event_date). Views use `ROW_NUMBER() OVER (PARTITION BY symbol, event_date ORDER BY information_available_ts DESC) = 1` for as-of deduplication.
- **Adjustment:** Prices are UNADJUSTED. The `close` column is used directly; there is no `adj_close`. Price `price_adjustment` is `unadjusted`. Volume is unadjusted.
- **Null rules:** Nulls in numeric fields indicate missing data; nulls are never interpolated.
- **Return formula:** `return_1d = (close - LAG(close) OVER (PARTITION BY symbol ORDER BY event_date)) / LAG(close) OVER (PARTITION BY symbol ORDER BY event_date)` — NOTE: this uses unadjusted prices; see corporate-action safety below.
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

Daily unadjusted close, OHLC, and volume.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_prices_v1 AS
SELECT
    symbol,
    event_date,
    open AS open_price,
    high AS high_price,
    low AS low_price,
    close AS close_price,
    close AS adj_close,
    volume,
    information_available_ts
FROM (
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
    FROM ${catalog}.${schema}.bronze_ohlcv_day
) deduped
WHERE rn = 1;
```

**Source:** `bronze_ohlcv_day` (daily grain, 238M+ rows across all bronze tables).

**Column notes:**
- `event_date` is the daily grain column (not `trade_date`).
- `close` is the unadjusted close price. The view aliases it as `adj_close` for backward compatibility with downstream consumers; the registry marks `price_adjustment: unadjusted`.
- `information_available_ts` is derived as 16:30 America/New_York on `event_date`, converted to UTC.

---

## serve_daily_equity_metrics_v1

Daily derived equity metrics: return, realized volatility, drawdown, momentum.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_equity_metrics_v1 AS
WITH daily_prices AS (
    SELECT
        symbol,
        event_date,
        close,
        information_available_ts
    FROM ${catalog}.${schema}.serve_daily_prices_v1
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
        ) * SQRT(252) AS realized_vol_20d
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
        (close - MAX(close) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) / MAX(close) OVER (
            PARTITION BY symbol
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS drawdown
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
    information_available_ts
FROM with_drawdown;
```

**Source:** Derived from `serve_daily_prices_v1`.

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
),
benchmark_returns AS (
    SELECT
        event_date,
        return_1d AS bench_return
    FROM ${catalog}.${schema}.serve_daily_equity_metrics_v1
    WHERE symbol = 'SPY'
)
SELECT
    e.symbol,
    e.event_date,
    e.return_1d,
    e.return_1d - b.bench_return AS rel_perf,
    'SPY' AS benchmark,
    e.information_available_ts
FROM entity_returns e
JOIN benchmark_returns b ON e.event_date = b.event_date;
```

**Source:** Derived from `serve_daily_equity_metrics_v1`. Benchmark is a typed bounded parameter (SPY, QQQ, or RSP); the view defaults to SPY. Parameterized queries should substitute the benchmark symbol at query time.

---

## serve_options_metrics_v1

Daily implied volatility (iv_atm) and put/call ratio for options-capable underlyings.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_options_metrics_v1 AS
SELECT
    symbol,
    feature_ts,
    iv_atm,
    put_call_ratio,
    information_available_ts
FROM (
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
    FROM ${catalog}.${schema}.gold_options_features
) deduped
WHERE rn = 1;
```

**Source:** `gold_options_features` (19,390 rows). Contains `iv_atm`, `put_call_ratio`, `iv_skew`, `iv_term_slope`.

**Column notes:**
- `feature_ts` is the grain column for options features (not `trade_date`).
- `information_available_ts` is sourced directly from `gold_options_features` (already computed upstream).

---

## serve_bounded_daily_bars_v1

Bounded Silver daily bars for price/volume drill-downs on ≤10 named tickers over ≤2 years.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_bounded_daily_bars_v1 AS
SELECT
    symbol,
    event_date,
    open AS open_price,
    high AS high_price,
    low AS low_price,
    close AS close_price,
    close AS adj_close,
    volume,
    information_available_ts,
    suspected_split
FROM (
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
    FROM ${catalog}.${schema}.bronze_ohlcv_day
) deduped
WHERE rn = 1;
```

**Source:** `bronze_ohlcv_day` (daily grain). Silver constraints: ≤10 tickers, ≤2 years, ≤10,000 rows.

**Column notes:**
- `event_date` is the daily grain column (not `trade_date`).
- `close` is the unadjusted close price, aliased as `adj_close` for backward compatibility.
- `information_available_ts` is derived as 16:30 America/New_York on `event_date`.
- `suspected_split` is a boolean detector that flags rows where the overnight price change is ≥ 40% and the ratio is within 3% of a common split ratio (1/k or k for k ∈ {2, 3, 4, 5, 10, 20}). Queries over return/volatility/drawdown windows should check for `suspected_split = TRUE` and reject if found.

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

Prices in `bronze_ohlcv_day` are **unadjusted**. Stock splits create fake returns (e.g. NVDA 10:1 in June 2024 → approximately −90% overnight). Until a governed split source exists:

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
| All other pairs | gold | Gold serving views | ≤10 years, ≤5k rows |

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