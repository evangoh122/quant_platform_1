# VERDICT: streaming-dlt — DeepSeek (builder)
**Status:** APPROVED
**Round:** 1

Built the self-contained continuous DLT bundle at `bundles/streaming/` per
`.agents/requests/BUILD-streaming-dlt.md`. Build only — nothing was deployed or run;
only `databricks bundle validate -t dev` was executed against the workspace (the one
command the request permits). Committed on `slice/streaming-dlt`.

## What was built

- `bundles/streaming/databricks.yml` — bundle `qp1-stream-streaming`, dev target
  (`mode: development`, `pipeline_development: true`), catalog `bootcamp_students`,
  schema `evangoh_capstone`. No credentials in config (profile comes from
  `~/.databrickscfg`).
- `bundles/streaming/resources/streaming_pipeline.pipeline.yml` — `serverless: true`,
  **`continuous: true`**, `development`, `photon: true`, `root_path` + `libraries` glob
  mirroring the proven reference bundle.
- `src/pipelines/streaming/helpers.py` — pure, dependency-free helpers (dedup key,
  availability timestamp, quarantine reasons).
- `transformations/{bronze,silver,gold,latency}_stream.py` — the four layers.
- `tests/test_helpers.py` + `tests/test_table_names.py` — offline tests.
- `README.md` — deploy/start/stop, marked "not yet run; bills while running".

Five tables declared, all `dlt_`-prefixed, none equal a real table:
`dlt_bronze_ohlcv_stream`, `dlt_silver_ohlcv`, `dlt_silver_ohlcv_quarantine`,
`dlt_gold_ohlcv_features`, `dlt_latency_metrics`.

## Requirement-by-requirement

1. **Source = real `bronze_ohlcv` read as a stream** — `bronze_stream.py` does
   `spark.readStream.table("bootcamp_students.evangoh_capstone.bronze_ohlcv")`
   (FQN from pipeline `configuration`, no hardcoded secrets). The append-only
   assumption (`WRITE` ×3,066 + `OPTIMIZE`, no UPDATE/DELETE) is noted in code and
   README with the re-check instruction if the upstream writer changes.
2. **Silver** — typed schema (string/timestamp/double/bigint/int), UTC event time,
   `information_available_ts = event_ts + bar interval` via `helpers.derive_information_available_ts`,
   dedup on `(symbol, event_ts, timespan)` with a **5-minute** event-time watermark
   (`dropDuplicates` after `withWatermark`), malformed rows → `dlt_silver_ohlcv_quarantine`
   via `@dp.expect_or_drop` (silver drops invalid, quarantine keeps invalid with the
   machine-readable `quarantine_reasons` array).
3. **Gold** — trailing features only, over a 15-min **sliding event-time window**
   (1-min slide) with a 5-min watermark — the streaming-native equivalent of
   `ROWS BETWEEN ... PRECEDING AND CURRENT ROW`. Row-window SQL from the batch layer is
   deliberately **not** copied (it is invalid on streaming DataFrames).
   `information_available_ts` = max carried per-bar IAT = window end (trailing, PIT-safe).
4. **Latency instrumentation** — `ingest_ts` carried from bronze; `silver_processed_ts`
   / `gold_processed_ts` stamped per row; `dlt_latency_metrics` computes p50/p95 for
   bronze→silver, silver→gold, and bronze→gold over 1-min windows via
   `percentile_approx` with a watermark.

## Blocking findings

None.

## Non-blocking notes

- **`dp.expect_or_drop` / `dp.read_stream` are resolved via the `dlt` fallback**, not
  runtime-verified: `pyspark.pipelines` locally raises `PIPELINES_NOT_SUPPORTED`
  (it can only import `dlt` inside a pipeline run). `bundle validate` passes but does
  not execute the decorators. The reference bundle proves `dp.table` /
  `dp.materialized_view` resolve the same way; `expect_or_drop` and `read_stream` are
  long-stable `dlt` names in the same namespace. Flagging for the Codex/Claude
  validators to confirm against the DLT API if they have a live pipeline.
- **`percentile_approx` in a streaming aggregation** requires a Spark 3.x DBR
  (serverless DLT provides this). Noted in `latency_metrics.py`.
- **Silver retains an always-empty `quarantine_reasons` column** (value `[]` for valid
  rows) so the `expect_or_drop` constraint can reference it. This is intentional
  lineage; a downstream `.drop()` would break the expectation.
- **Gold adds bounded window latency by design.** The <60s SLO fast path is
  bronze→silver (per-row); the windowed gold signal is naturally slower. Documented in
  the README so the velocity rubric is *measured*, not asserted.
- **`dropDuplicates` on normalized columns** could collapse two malformed rows that
  share a NULL `symbol` before `expect_or_drop` quarantines them — an irrelevant
  edge case (both are invalid), noted for completeness.

## Checks run

- `python3 -m py_compile src/pipelines/streaming/helpers.py src/pipelines/streaming/transformations/*.py` → **pass (exit 0)**
- `python3 -m pytest` (in `bundles/streaming/`) → **24 passed in 0.04s**
  (21 helper unit tests + 3 static table-name guards)
- `databricks bundle validate -t dev` (in `bundles/streaming/`) →
  ```
  Name: qp1-stream-streaming
  Target: dev
  Workspace:
    User: evangohsg@gmail.com
    Path: /Workspace/Users/evangohsg@gmail.com/.bundle/qp1-stream-streaming/dev
  Validation OK!
  ```
- Static guard asserts exactly the five `dlt_` tables and that none equals a real table
  name (`bronze_ohlcv`, `silver_ohlcv`, `silver_ohlcv_quarantine`,
  `silver_ohlcv_quarantine_batch`, `gold_ohlcv_features`).

## Not done (by request)

- No `databricks bundle deploy` / `run` / `pipelines start-update` — live resources
  untouched. If a deploy were needed to prove anything, that is out of scope for a
  build-only round.
