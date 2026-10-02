# PLAN-REQUEST: bronze-refresh — Codex plans, then four builders execute in parallel

**Owner's request:** "get the bronze pipeline to pull the latest data for Fed, COT, options and
equities — plan this with Codex and then divide and conquer."

**You (Codex) produce the PLAN only.** You have no network, so the coordinator measured the
facts below. Builders (DeepSeek ×2, MiMo ×2) will each own one source in a separate git
worktree, run concurrently, and execute against the live workspace.

## Measured facts (2026-10-03)

| Table | Source | Latest data | Last ingest | Rows |
| :-- | :-- | :-- | :-- | --: |
| `bronze_ohlcv` (equities, minute) | Massive S3 flat files `us_stocks_sip/minute_aggs_v1` | 2026-09-03 | 2026-09-04 | 72,678,354 |
| `bronze_ohlcv_day` (equities, daily) | Massive S3 `us_stocks_sip/day_aggs_v1` | 2026-09-04 | 2026-09-05 | 12,993,270 |
| `bronze_options_day` (options, daily) | Massive S3 (options day aggs) | 2026-09-04 | 2026-09-05 | 146,117,971 |
| `bronze_options_quotes` (IV/greeks snapshot) | Polygon/Massive REST snapshot | 2026-09-02 (single date) | 2026-09-02 | 61,882 |
| `bronze_cftc_fut`, `bronze_cftc_com` (COT) | CFTC Public Reporting Environment (no key) | report 2026-09-01 | 2026-09-05 | ~15.4k each |
| `bronze_economic_metrics` | Massive: financial_statement / forex / crypto / index | 2026-09-02 | 2026-09-02 | ~140k |
| **Fed data** | **does not exist** anywhere in the lakehouse | — | — | 0 |

- `massive_ingestion_log` (columns: source_file, dataset, status, row_count, started_at,
  completed_at, error_message): `us_stocks_sip/day_aggs_v1` 1,171 SUCCESS;
  `us_stocks_sip/minute_aggs_v1` 1,175 SUCCESS / 42 FAILED / 1 CANCELLED;
  `us_options_opra/minute_aggs_v1` 1 FAILED. Also `massive_daily_ingestion_log` exists.
- Bronze history is append-only (`WRITE` + `OPTIMIZE`); a streaming bundle reads `bronze_ohlcv`
  as a stream, so **bronze writes must remain appends** — no updates/deletes/overwrites.
- Credentials: Databricks secret scope **`evangoh_capstone`** has `massive_s3_access_key`,
  `massive_s3_secret_key`, `polygon_api_key`. Bug: `notebooks/02_ingest_sec_edgar.py` reads scope
  `"capstone"`, which **does not exist**.
- **FRED** public CSV works with no key: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF`
  (fed funds, latest 2026-09-30).
- Compute: databricks-connect serverless (`DatabricksSession.builder.serverless(True)`); no
  classic clusters. Serverless rejects interval streaming triggers — this is batch.
- `etl/extract_*` modules import on this branch (DuckDB writes retired; they raise if called).
  Production ingestion code lives in `notebooks/01_ingest_market_data.py`,
  `notebooks/02_ingest_sec_edgar.py`, and `notebooks/archive/00_project_setup.py`.
- Gold conventions to preserve: daily bars stamped at day start (available 16:00 NY + 30 min);
  minute bars stamped at bar start (available + 1 bar); sessions grouped by New York date.

## What the plan must specify

1. **One lane per source** — equities, options, COT, Fed — and for each: the exact code path
   (reuse which existing notebook/module functions; new module where none exists), target
   table(s), the incremental window (from each table's latest date to today), and the
   **idempotency/dedup key** so a re-run or overlap never duplicates rows in an append-only
   table (e.g. skip files already SUCCESS in `massive_ingestion_log`; anti-join on natural key).
2. **Fed lane design:** a new `bronze_fed_series` table (schema you propose) from FRED CSV for a
   specified series list relevant to the strategy (e.g. DFF, DGS2, DGS10, T10Y2Y, CPIAUCSL,
   UNRATE, ...) with **vintage/availability timing** — FRED values are revised and published
   with lags; say how `information_available_ts` is set and whether ALFRED vintages are needed.
3. **File ownership** so four concurrent builders never edit the same file. Shared files
   (`conftest.py`, `requirements*.txt`, common helpers) must have a single owner or be off-limits.
4. **Run order and safety:** bronze appends only; dry-run first (count what would be written),
   then write; verification queries per lane (new max date, row delta, no duplicate keys).
5. Credential handling (secrets scope, never printed) and the `"capstone"` scope bug.
6. Explicit non-goals: no silver/gold rebuild in this effort (separate step), no streaming
   pipeline run, no Lakebase.
7. Risks: Massive entitlement/quota limits, failed/partial files, FRED revisions, CFTC release
   timing.

Write the plan as markdown. Builders will receive their lane section verbatim, so make each
lane self-contained.
