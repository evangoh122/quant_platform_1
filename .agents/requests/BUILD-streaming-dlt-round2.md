# BUILD-REQUEST: streaming-dlt — ROUND 2 (latency measurement and the velocity path)

**Branch:** `slice/streaming-dlt` · **Builder:** DeepSeek · **Validators:** Claude, then Codex
**Still BUILD ONLY.** Same rule as round 1: no deploy, no run, no pipeline create/update/start.
Only `databricks bundle validate -t dev`.

## Round 1 verified — keep it
Nothing deployed (no new pipeline, no `dlt_*` tables, old bundle untouched). Config is
continuous + serverless; all five tables `dlt_`-prefixed; source is the real `bronze_ohlcv`;
`information_available_ts = event_ts + bar interval`; gold windows are event-time with a
watermark and take `max(information_available_ts)`. No junk committed.

## Defect 1 — end-to-end latency measures the wrong event
`gold_stream.py:48` carries `min(ingest_ts)` — the **earliest** bar in a 15-minute window —
and `latency_metrics.py:43` computes `gold_processed_ts - ingest_ts`. That latency includes up
to 15 minutes of window length, so the <60s SLO would read as failed even for an instant
pipeline. Provider-receipt-to-signal is measured from the **event that completes the
output**: carry `max(ingest_ts)` (the latest contributing bar) and measure from that. Keep
`min(ingest_ts)` only if you also label it as a separate "window span" metric.

## Defect 2 — the windowed path cannot meet <60s by construction
In append mode a windowed aggregation with a 5-minute watermark emits a window only after
the watermark passes its end — at least ~5 minutes after its last bar. The rubric asks for
both 2–5 minutes allowed lateness **and** <60s provider-to-signal; one windowed path cannot
satisfy both.

Separate the two concerns explicitly:
- **Velocity path** (what the <60s SLO is measured on): a per-bar, non-windowed stream from
  `dlt_silver_ohlcv` to a gold "latest bar features" output that emits as each bar arrives
  (stateless or short-state transformations only — e.g. per-bar return vs the previous bar
  via a bounded stateful approach, or flags). Measure end-to-end latency here.
- **Windowed path** (15-minute rolling features with 2–5 min lateness): keep it, and report
  its emit delay honestly as a separate metric — it is not the SLO path.
- `dlt_latency_metrics` must report both, clearly labelled, with p50/p95.

If you conclude the per-bar path cannot be built correctly in DLT without a run, say so with
reasons rather than shipping something unverifiable.

## Defect 3 — document the trade-off
`bundles/streaming/README.md` must state which path the <60s SLO applies to, the expected
lower bound on the windowed path's emit delay (≈ watermark), and that numbers are unmeasured
until the owner runs it.

## Tests
- Unit test: end-to-end latency for a window uses the latest contributing bar's `ingest_ts`
  (construct a window where min and max differ by 10 minutes; assert the metric reflects max).
- Static test still passes: every declared table is `dlt_`-prefixed.
- `databricks bundle validate -t dev` output pasted.

Do not touch anything outside `bundles/streaming/` and `.agents/deepseek/`.
**Commit your work.** Write `.agents/deepseek/VERDICT-streaming-dlt-round2.md`.
