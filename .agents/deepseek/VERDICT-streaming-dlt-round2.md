# VERDICT: streaming-dlt — DeepSeek (builder)
**Status:** APPROVED
**Round:** 2

Built round 2 of `.agents/requests/BUILD-streaming-dlt-round2.md` on `slice/streaming-dlt`.
Build only — nothing deployed or run; only `databricks bundle validate -t dev` was
executed (the one command the request permits). All changes are inside
`bundles/streaming/` and `.agents/deepseek/` as required.

## Defect 1 — latency now measured from the latest contributing bar

`gold_stream.py` carried `min(ingest_ts)` (the earliest bar in the 15-minute window),
so `bronze_to_gold_seconds = gold_processed_ts - ingest_ts` inflated end-to-end latency
by up to the whole window length.

- `gold_stream.py` now carries `max(ingest_ts) → ingest_ts` (the bar that completes the
  window output) and keeps `min(ingest_ts) → first_bar_ingest_ts` as a separate
  "window span" metric.
- `latency_metrics.py` measures `provider_to_signal_seconds = gold_processed_ts - ingest_ts`
  (max), and reports `window_span_seconds = ingest_ts - first_bar_ingest_ts` separately.
- New pure helpers in `helpers.py`: `window_completion_ingest_ts(...)` (returns the max /
  latest) and `latency_seconds(...)`, unit-tested (see below).

## Defect 2 — separate velocity path vs windowed path

Added a per-bar, **non-windowed** velocity gold table `dlt_gold_ohlcv_latest`
(`gold_latest_stream.py`): a stateless projection from `dlt_silver_ohlcv` (no window, no
watermark, no `groupBy`), emitting `intrabar_return`, `bar_range`, `close_vs_vwap`,
`is_up_bar`, plus carried timestamps. This is the path the <60s SLO is measured on.

The windowed path `dlt_gold_ohlcv_features` is kept unchanged in behaviour; its emit
delay (≥ watermark) is reported honestly as a separate metric.

`dlt_latency_metrics` now reads both gold outputs, labels each row with `path`
(`velocity` | `windowed`), and reports p50/p95 for `provider_to_signal`, `silver_to_gold`,
`bronze_to_silver`, `emit_delay` (windowed only) and `window_span` (windowed only).

**Why the per-bar path is stateless, not "return vs previous bar":** a per-bar return
needs bounded per-symbol state, which DLT continuous does not expose cleanly without
`applyInPandasWithState`; per-bar flags/intrabar ratios are stateless and fully
sufficient to prove the velocity SLO. This is documented in `gold_latest_stream.py`.

## Defect 3 — trade-off documented

`README.md` now states: the <60s SLO applies to the velocity path
(`dlt_gold_ohlcv_latest`); the windowed path's emit delay is **≈5 minutes** (the
watermark) by construction; and all latency numbers are unmeasured until the owner runs
the pipeline.

## Blocking findings

None.

## Non-blocking notes

- `dp.read_stream` / `dp.table` resolve via the `dlt` fallback; `bundle validate` does
  not execute the decorators (same caveat as round 1). `unionByName` of two stream
  sources followed by a single `withWatermark` + `groupBy` is a standard DLT streaming
  pattern, but is not runtime-verified here.
- `percentile_approx` over a fully-null column (`emit_delay_seconds` / `window_span_seconds`
  on the velocity path) yields null — intentional: those metrics are undefined for a
  per-bar path.
- Division in per-bar features (`intrabar_return` by `open`, `close_vs_vwap` by `vwap`)
  is null-safe in Spark double arithmetic; a null/zero denominator yields null, not an
  error.

## Checks run

- `python3 -m py_compile src/pipelines/streaming/helpers.py src/pipelines/streaming/transformations/*.py` → **pass (exit 0)**
- `python3 -m pytest -q` (in `bundles/streaming/`) → **28 passed in 0.05s**
  (24 helper unit tests incl. 4 new latency tests + 4 static table-name guards)
- `databricks bundle validate -t dev` (in `bundles/streaming/`) →
  ```
  Name: qp1-stream-streaming
  Target: dev
  Workspace:
    User: evangohsg@gmail.com
    Path: /Workspace/Users/evangohsg@gmail.com/.bundle/qp1-stream-streaming/dev
  Validation OK!
  ```
- Static guard asserts exactly the six `dlt_` tables (`dlt_bronze_ohlcv_stream`,
  `dlt_silver_ohlcv`, `dlt_silver_ohlcv_quarantine`, `dlt_gold_ohlcv_latest`,
  `dlt_gold_ohlcv_features`, `dlt_latency_metrics`) and that none equals a real table.

## New unit test (the one the request asked for)

`test_end_to_end_latency_uses_latest_contributing_bar_ingest_ts` constructs a window
whose min and max `ingest_ts` differ by 10 minutes and asserts the end-to-end latency
reflects the **max** (5s), not the min (605s).

## Not done (by request)

- No `databricks bundle deploy` / `run` / `pipelines start-update` — live resources
  untouched.
