# BUILD-REQUEST: streaming-dlt (round 1) — BUILD ONLY, DO NOT RUN

**Branch:** `slice/streaming-dlt` (worktree `/home/jianj/code/qp1-stream`, based on `slice/silver-gold`)
**Builder:** DeepSeek · **Validators:** Claude, then Codex
**Rubric:** §C Streaming, §3.2 Velocity (<60s provider-receipt-to-signal, 10–15s micro-batches,
p50/p95 measured per stage).

## Owner's instruction — read first

The owner asked to **build** a continuous Lakeflow Declarative Pipeline (DLT) **but not run it**.

- **Never run** `databricks bundle deploy`, `databricks bundle run`, `databricks pipelines start-update`,
  or any API call that creates, updates, or starts a pipeline. Deploying would change live
  workspace resources.
- The only workspace command you may run is `databricks bundle validate -t dev` (local
  validation). You may also read tables with databricks-connect serverless.
- If you believe a deploy is needed to prove something, stop and say so in your verdict.

## Why DLT continuous

Serverless Spark rejects `processingTime` triggers
(`INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED`; verified), so 10–15s micro-batches need a
continuous pipeline. Serverless DLT supports `continuous: true`.

## Reference (read-only — do not edit it)

An earlier exercise bundle lives at `/home/jianj/code/quant-trading-capstone` (not under
version control). Reuse its ideas/code by **copying** into this repo:
`resources/ohlcv_pipeline.pipeline.yml`, `src/pipelines/ohlcv/helpers.py` (388 lines),
`transformations/{bronze,silver,gold}_ohlcv*.py`. That bundle ingests a 5,850-row
**synthetic seed** via Auto Loader and declares tables named `bronze_ohlcv`, `silver_ohlcv`,
`gold_ohlcv_features` — the **real** production tables. Its last 12 runs failed because those
names were taken. **Your pipeline must never own or write a real table.**

## Build

Create a self-contained bundle at `bundles/streaming/`:

1. `databricks.yml` + `resources/streaming_pipeline.pipeline.yml`:
   `serverless: true`, **`continuous: true`**, dev target `development: true`, catalog
   `bootcamp_students`, schema `evangoh_capstone`, no credentials in config.
2. **Every table the pipeline declares is prefixed `dlt_`**
   (`dlt_bronze_ohlcv_stream`, `dlt_silver_ohlcv`, `dlt_silver_ohlcv_quarantine`,
   `dlt_gold_ohlcv_features`, `dlt_latency_metrics`).
3. **Source = the real `bronze_ohlcv`, read as a stream** (`spark.readStream.table(...)`), not
   the synthetic seed. Measured: its history is only appends (`WRITE` ×3,066) and `OPTIMIZE`,
   so a streaming read is safe without `skipChangeCommits`; note that assumption in code.
4. **Silver:** typed schema, UTC, dedup on the stable key with a **watermark of 2–5 minutes**
   (bounded state); malformed rows → `dlt_silver_ohlcv_quarantine` via DLT expectations
   (`expect_or_drop` + a quarantine table), with the reason recorded.
5. **Gold:** trailing features only. **Timestamp conventions — these caused four leaks in
   the batch layer; get them right:** minute bars are stamped at bar **start**, so
   `information_available_ts = event_ts + bar interval`; trailing windows only; never a
   whole-partition aggregate without `ORDER BY ... ROWS ... CURRENT ROW`. Note: streaming
   aggregations differ from batch windows — use event-time windows with watermarks; do not
   copy batch window SQL that is invalid in streaming.
6. **Latency instrumentation (velocity evidence):** carry `ingest_ts` from bronze and stamp
   `silver_processed_ts`, `gold_processed_ts` per row. `dlt_latency_metrics` (or a view)
   exposes per-stage and end-to-end latency with **p50/p95**. This is how the <60s SLO will be
   *measured* rather than asserted when the owner chooses to run it.

## Tests (offline)

- Static: parse every transformation file and assert every declared table name starts with
  `dlt_` and none equals a real table name.
- Unit tests for helper functions you keep (dedup key, availability timestamp, quarantine
  reason).
- `databricks bundle validate -t dev` output pasted (it must validate without deploying).

## Constraints

Do not modify `silver/`, `gold/` batch transforms, `ml/`, `agent/`, `db/`, `api/`,
`frontend/`, `conftest.py`, `pytest.ini`, `.agents/dispatch.sh`, or anything under
`/home/jianj/code/quant-trading-capstone`. Document how to deploy/start/stop it in
`bundles/streaming/README.md`, clearly marked "not yet run; bills while running".
**Commit your work.** Write `.agents/deepseek/VERDICT-streaming-dlt.md`.
