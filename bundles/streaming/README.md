# `bundles/streaming` — continuous OHLCV streaming pipeline (DLT)

A self-contained Databricks bundle that streams the production `bronze_ohlcv` table
through a bronze → silver → gold medallion as a **continuous** Lakeflow Declarative
Pipeline (DLT). Every table it declares is prefixed `dlt_` so it can never own or write
a real production table.

> **Not yet run. Bills while running.** This bundle has only been validated locally
> (`databricks bundle validate -t dev`). Deploying/starting it creates live workspace
> resources and accrues compute cost until stopped. See [Deploy](#deploy) below.

## Why continuous

Serverless Spark rejects `processingTime` triggers
(`INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED`), so 10–15s micro-batches cannot be driven
by `processingTime`. Serverless DLT supports `continuous: true`, which is what this
bundle uses.

## Tables (all `dlt_`-prefixed)

| Table                         | Layer       | Purpose                                                            |
| :---------------------------- | :---------- | :----------------------------------------------------------------- |
| `dlt_bronze_ohlcv_stream`     | bronze      | Streaming copy of `bronze_ohlcv` + stream load time                |
| `dlt_silver_ohlcv`            | silver      | Typed, UTC, deduplicated, PIT-stamped bars                         |
| `dlt_silver_ohlcv_quarantine` | quarantine  | Malformed rows with machine-readable reasons                       |
| `dlt_gold_ohlcv_features`     | gold        | Trailing features over a 15-min sliding event-time window          |
| `dlt_latency_metrics`         | metrics     | Per-stage + end-to-end latency p50/p95 (velocity evidence)         |

## Source assumption (re-check before running)

The source is the production `bootcamp_students.evangoh_capstone.bronze_ohlcv`, read as
a stream (`spark.readStream.table(...)`). Its history was measured to be append-only
(`WRITE` ×3,066) plus `OPTIMIZE` — no UPDATE/DELETE — so a streaming read is safe
**without** `skipChangeCommits`. If the upstream writer ever starts emitting
UPDATE/DELETE operations, `dlt_bronze_ohlcv_stream` must add
`.option("skipChangeCommits", "true")` (and the author of that change must re-verify
the history). This assumption is also noted in `bronze_stream.py`.

## Timestamp conventions (four batch-layer leaks avoided)

Minute bars are stamped at bar **start** (Polygon convention). Therefore:

- `information_available_ts = event_ts + bar interval` (60s for minute bars), computed
  in silver and carried to gold.
- Gold uses **trailing event-time windows** with a watermark — the streaming-native
  equivalent of `ROWS BETWEEN ... PRECEDING AND CURRENT ROW`. Row-based window
  functions are invalid on streaming DataFrames, so the batch gold's window SQL is
  deliberately **not** copied.
- No whole-partition aggregate without `ORDER BY ... ROWS ... CURRENT ROW` (batch) /
  watermark-bounded event-time window (streaming).

## Latency instrumentation (velocity evidence)

`ingest_ts` is carried from bronze; `silver_processed_ts` and `gold_processed_ts` are
stamped per row. `dlt_latency_metrics` exposes p50/p95 for bronze→silver,
silver→gold, and bronze→gold (end-to-end) over 1-minute windows. This measures the
<60s provider-receipt-to-signal SLO rather than asserting it. Note the fast path is
bronze→silver (per-row); gold adds a bounded window delay by design.

## Layout

```
bundles/streaming/
├── databricks.yml
├── resources/streaming_pipeline.pipeline.yml
├── pyproject.toml
├── src/pipelines/streaming/
│   ├── helpers.py                # pure, dependency-free (unit-tested)
│   └── transformations/
│       ├── bronze_stream.py
│       ├── silver_stream.py
│       ├── gold_stream.py
│       └── latency_metrics.py
└── tests/
    ├── test_helpers.py
    └── test_table_names.py
```

## Deploy

Do **not** run these unless you have chosen to start the pipeline (it bills while
running). Only `validate` has been run for this deliverable.

```bash
cd bundles/streaming
databricks bundle validate -t dev          # local validation only (safe)
databricks bundle deploy -t dev            # NOT RUN — creates workspace resources
databricks bundle run streaming_dlt_pipeline -t dev   # NOT RUN — starts a continuous pipeline
```

To stop a running pipeline: use the Databricks UI (or `databricks pipelines stop`),
then remove the bundle with `databricks bundle destroy -t dev`. A `continuous: true`
pipeline runs until explicitly stopped.

## Tests (offline)

```bash
cd bundles/streaming
python3 -m pytest -q
```

## Non-goals

- Does not modify `silver/`, `gold/` batch transforms, `ml/`, `agent/`, `db/`, `api/`,
  `frontend/`, `conftest.py`, `pytest.ini`, or anything under `quant-trading-capstone`.
- Does not replicate the full batch feature set (RSI, session high/low via row windows)
  — those require row-based window functions that are invalid in streaming.
