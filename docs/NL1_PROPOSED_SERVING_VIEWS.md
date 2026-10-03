# NL1 Proposed Serving Views

> **Proposal only — to be created by a Databricks admin/owner; this lane does not execute this DDL.**

This document proposes `CREATE VIEW` DDL for every approved serving view named by the NL1 semantic registry. An admin must replace catalog/schema placeholders before execution.

## Assumptions and conventions

- **Date grain:** All views are daily grain. No intraday data.
- **PIT safety:** Every view includes `information_available_ts` for point-in-time correctness. Queries must filter on `information_available_ts <= :query_timestamp` to avoid look-ahead bias.
- **Deduplication:** Source tables may contain multiple rows per (symbol, trade_date). Views use `ROW_NUMBER() OVER (PARTITION BY symbol, trade_date ORDER BY information_available_ts DESC) = 1` for as-of deduplication.
- **Adjustment:** Prices are split-adjusted. Volume is unadjusted.
- **Null rules:** Nulls in numeric fields indicate missing data; nulls are never interpolated.
- **Return formula:** `return_1d = (adj_close - LAG(adj_close) OVER (PARTITION BY symbol ORDER BY trade_date)) / LAG(adj_close) OVER (PARTITION BY symbol ORDER BY trade_date)`
- **Realized volatility:** 20-day rolling standard deviation of daily returns, annualized by `* SQRT(252)`.
- **Drawdown:** Running drawdown from peak: `(adj_close - MAX(adj_close) OVER (PARTITION BY symbol ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)) / MAX(adj_close) OVER (PARTITION BY symbol ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`
- **Momentum:** 20-day price momentum: `(adj_close / LAG(adj_close, 20) OVER (PARTITION BY symbol ORDER BY trade_date)) - 1`
- **Relative performance:** Difference between entity cumulative return and benchmark cumulative return over the same window.
- **iv_atm:** At-the-money implied volatility from options chain, as reported in `gold_options_features`.

## Grants

The future service principal receives:
- `USE CATALOG` on the target catalog
- `USE SCHEMA` on the target schema
- `SELECT` on dedicated serving views only, **not** on source Bronze/Silver/Gold tables

## Status

**DDL is unexecuted and unverified until owner action.**

---

## serve_daily_prices_v1

Daily adjusted close, OHLC, and volume.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_prices_v1 AS
SELECT
    symbol,
    trade_date,
    open AS open_price,
    high AS high_price,
    low AS low_price,
    close AS close_price,
    adj_close,
    volume,
    information_available_ts
FROM (
    SELECT
        symbol,
        trade_date,
        open,
        high,
        low,
        close,
        adj_close,
        volume,
        information_available_ts,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, trade_date
            ORDER BY information_available_ts DESC
        ) AS rn
    FROM ${catalog}.${schema}.bronze_ohlcv_day
) deduped
WHERE rn = 1;
```

**Source:** `bronze_ohlcv_day` (daily grain, 238M+ rows across all bronze tables).

---

## serve_daily_equity_metrics_v1

Daily derived equity metrics: return, realized volatility, drawdown, momentum.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_daily_equity_metrics_v1 AS
WITH daily_prices AS (
    SELECT
        symbol,
        trade_date,
        adj_close,
        information_available_ts
    FROM ${catalog}.${schema}.serve_daily_prices_v1
),
with_returns AS (
    SELECT
        symbol,
        trade_date,
        adj_close,
        information_available_ts,
        (adj_close - LAG(adj_close) OVER (PARTITION BY symbol ORDER BY trade_date))
            / LAG(adj_close) OVER (PARTITION BY symbol ORDER BY trade_date)
            AS return_1d
    FROM daily_prices
),
with_vol AS (
    SELECT
        *,
        STDDEV_SAMP(return_1d) OVER (
            PARTITION BY symbol
            ORDER BY trade_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) * SQRT(252) AS realized_vol_20d
    FROM with_returns
),
with_drawdown AS (
    SELECT
        *,
        (adj_close - MAX(adj_close) OVER (
            PARTITION BY symbol
            ORDER BY trade_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) / MAX(adj_close) OVER (
            PARTITION BY symbol
            ORDER BY trade_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS drawdown
    FROM with_vol
)
SELECT
    symbol,
    trade_date,
    adj_close,
    return_1d,
    realized_vol_20d,
    drawdown,
    (adj_close / LAG(adj_close, 20) OVER (PARTITION BY symbol ORDER BY trade_date)) - 1
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
        trade_date,
        return_1d,
        information_available_ts
    FROM ${catalog}.${schema}.serve_daily_equity_metrics_v1
),
benchmark_returns AS (
    SELECT
        trade_date,
        return_1d AS bench_return
    FROM ${catalog}.${schema}.serve_daily_equity_metrics_v1
    WHERE symbol = 'SPY'
)
SELECT
    e.symbol,
    e.trade_date,
    e.return_1d,
    e.return_1d - b.bench_return AS rel_perf,
    'SPY' AS benchmark,
    e.information_available_ts
FROM entity_returns e
JOIN benchmark_returns b ON e.trade_date = b.trade_date;
```

**Source:** Derived from `serve_daily_equity_metrics_v1`. Benchmark is a typed bounded parameter (SPY, QQQ, or RSP); the view defaults to SPY. Parameterized queries should substitute the benchmark symbol at query time.

---

## serve_options_metrics_v1

Daily implied volatility (iv_atm) for options-capable underlyings.

```sql
CREATE VIEW IF NOT EXISTS ${catalog}.${schema}.serve_options_metrics_v1 AS
SELECT
    symbol,
    trade_date,
    iv_atm,
    information_available_ts
FROM (
    SELECT
        symbol,
        trade_date,
        iv_atm,
        information_available_ts,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, trade_date
            ORDER BY information_available_ts DESC
        ) AS rn
    FROM ${catalog}.${schema}.gold_options_features
) deduped
WHERE rn = 1;
```

**Source:** `gold_options_features` (19,390 rows). Contains `iv_atm`, `put_call_ratio`, `iv_skew`, `iv_term_slope`.

---

## Identifier correspondence

All view and column identifiers match the registry YAML `approved_views` list:

| Registry identifier | DDL view name |
|---|---|
| `serve_daily_prices_v1` | `${catalog}.${schema}.serve_daily_prices_v1` |
| `serve_daily_equity_metrics_v1` | `${catalog}.${schema}.serve_daily_equity_metrics_v1` |
| `serve_relative_performance_v1` | `${catalog}.${schema}.serve_relative_performance_v1` |
| `serve_options_metrics_v1` | `${catalog}.${schema}.serve_options_metrics_v1` |