# Capstone write-up — Quant Platform

Status: submitted 2026-10-05 · Data figures last verified 2026-10-05 03:41 UTC (live `COUNT(*)`, see `row_counts_2026-10-05.tsv`)

## 1. Problem and product

Retail and small-team quant research usually stitches together market data, options data, regulatory filings and macro
series by hand, and silently leaks future information into backtests. This project builds one Databricks-native platform
that (a) ingests those sources at scale with point-in-time (PIT) timestamps, (b) serves them through a web application,
(c) lets an LLM-directed agent research a company and record its conclusions through validated writes, and (d) measures
application activity through an analytics pipeline back into the lakehouse.

## 2. Data sources (third-party APIs)

| Source | What | Landing table(s) | Volume |
|---|---|---|---|
| Massive / Polygon | Minute + daily equity bars, daily options aggregates, quotes/trades, stock splits | `bronze_ohlcv`, `bronze_ohlcv_day`, `bronze_options_day`, `bronze_options_quotes/trades`, `bronze_corporate_actions`, `bronze_economic_metrics` | 73.3M + 13.2M + 152.1M + … |
| SEC EDGAR | 10-K / 10-Q / 8-K / 6-K / 20-F filings, sections, XBRL facts | `bronze_sec_filings(_v2)`, `silver_sec_sections`, `silver_sec_entities` | 134K filing chunks, 49.7K entities |
| CFTC | Commitments of Traders (futures + combined) | `bronze_cftc_fut`, `bronze_cftc_com`, `silver_cot_positions` | 31.4K |
| Federal Reserve / FRED | Macro series | `bronze_fed_series` | 97.0K |

## 3. Big Data Vs

- **Volume:** 287.1M rows across the schema; 239.1M in bronze (`bronze_options_day` alone is 152.1M rows covering
  7,833 underlyings, 2024-09 → 2026-10).
- **Variety:** structured time series (prices, options, positioning, macro) and unstructured text (SEC filings chunked
  and embedded for retrieval), plus relational operational data in Lakebase.

## 4. Technologies and design

- **Spark / Delta (Unity Catalog):** PySpark ingestion on serverless jobs; bronze append-only with `ingest_ts`; silver
  dedup, quarantine, split adjustment from Massive corporate actions and `information_available_ts`; gold features,
  tradable universe (PIT), COT features, SEC chunk embeddings.
- **Databricks App:** FastAPI + React. Reads go through a SQL-warehouse adapter (named parameters, bounded `LIMIT`,
  statement timeout with cancel, bounded concurrency, schema contract checked against live `DESCRIBE`). Lakebase
  access is resilient: bounded connect, circuit breaker, read-only degraded mode, `/api/health` + `/api/health/trace`.
- **Lakebase (Postgres):** operational model — users/roles, watchlists, research notes, orders, executions, positions,
  agent actions, approvals (`db/migrations/001–004`).
- **Agent:** the workspace Foundation Model proposes a typed next action; a deterministic validator enforces a tool
  allowlist, argument schemas, role checks, request-scoped write authorisation and idempotency before any tool runs.
  Retrieved SEC text is passed as data, never as instructions. Writes are limited to `save_research_note`.
- **Analytics pipeline:** every Lakebase write appends to `analytics_outbox` in the same transaction; a watermarked,
  idempotent job MERGEs events into `analytics_agent_activity`, `analytics_watchlist_changes`, `analytics_order_funnel`
  and `analytics_usage_daily`, which the app's analytics API reads.
- **Retrieval:** hybrid BM25 + dense + reranker over SEC chunks with a PIT filter (`accepted_ts <= as_of`).

## 5. Architecture

See `architecture.png` (source `architecture.dot`).

## 6. Quality and evidence

- Offline test suite (~1,550 tests) plus frontend tests; mutation proofs required for every safety property.
- Multi-model review on every change, live validation against the workspace, CodeRabbit on each PR.
- Dependency audit (`pip-audit`, `npm audit`) and secret scanning in CI.

## 7. Limitations and next steps

- Universe-wide SEC ingest and retrieval coverage must be measured from the
  current deployment before making a coverage claim.
- The agent and analytics pipeline are minimal versions; next: more tools, scheduled analytics job, dashboard charts.
- Streaming DLT pipeline built but not deployed; IBKR paper execution is a scaffold.
- Strategy research is descriptive only (several results `BLOCKED_DATA`); no profitability is claimed.
