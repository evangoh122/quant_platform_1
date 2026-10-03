"""Streaming latency metrics: p50/p95 for the velocity and windowed paths.

Reads both gold outputs and measures latency over 1-minute event-time windows with a
watermark, labelled by ``path``:

  * ``velocity``  (``dlt_gold_ohlcv_latest``)   — the <60s provider-to-signal SLO path
  * ``windowed``  (``dlt_gold_ohlcv_features``) — 15-minute rolling features; its emit
    delay is at least the watermark (5 minutes) by construction, so it is *not* the
    SLO path.

For both paths the provider-to-signal latency is ``gold_processed_ts - ingest_ts`` where
``ingest_ts`` is the bar that completes the output: the single bar for the velocity path,
and the latest (max) contributing bar for the windowed path. The windowed path also
reports its emit delay (``gold_processed_ts - information_available_ts``) and window span
(``max ingest_ts - min ingest_ts``) as separate metrics.

This measures the SLO rather than asserting it. ``percentile_approx`` requires a
Spark 3.x DBR (DLT serverless provides this).
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

_METRICS_WATERMARK = "5 minutes"

_SHARED_COLUMNS = [
    "path",
    "gold_processed_ts",
    "provider_to_signal_seconds",
    "silver_to_gold_seconds",
    "bronze_to_silver_seconds",
    "emit_delay_seconds",
    "window_span_seconds",
]


def _velocity_rows():
    latest = dp.read_stream("dlt_gold_ohlcv_latest")
    return (
        latest.withColumn("path", F.lit("velocity"))
        .withColumn(
            "provider_to_signal_seconds",
            F.unix_timestamp("gold_processed_ts") - F.unix_timestamp("ingest_ts"),
        )
        .withColumn(
            "silver_to_gold_seconds",
            F.unix_timestamp("gold_processed_ts") - F.unix_timestamp("silver_processed_ts"),
        )
        .withColumn(
            "bronze_to_silver_seconds",
            F.unix_timestamp("silver_processed_ts") - F.unix_timestamp("ingest_ts"),
        )
        # A per-bar path has no window, so emit delay / window span are not defined.
        .withColumn("emit_delay_seconds", F.lit(None).cast("long"))
        .withColumn("window_span_seconds", F.lit(None).cast("long"))
        .select(*_SHARED_COLUMNS)
    )


def _windowed_rows():
    gold = dp.read_stream("dlt_gold_ohlcv_features")
    return (
        gold.withColumn("path", F.lit("windowed"))
        .withColumn(
            "provider_to_signal_seconds",
            F.unix_timestamp("gold_processed_ts") - F.unix_timestamp("ingest_ts"),
        )
        .withColumn(
            "silver_to_gold_seconds",
            F.unix_timestamp("gold_processed_ts") - F.unix_timestamp("silver_processed_ts"),
        )
        .withColumn(
            "bronze_to_silver_seconds",
            F.unix_timestamp("silver_processed_ts") - F.unix_timestamp("ingest_ts"),
        )
        .withColumn(
            "emit_delay_seconds",
            F.unix_timestamp("gold_processed_ts")
            - F.unix_timestamp("information_available_ts"),
        )
        .withColumn(
            "window_span_seconds",
            F.unix_timestamp("ingest_ts") - F.unix_timestamp("first_bar_ingest_ts"),
        )
        .select(*_SHARED_COLUMNS)
    )


@dp.table(
    name="dlt_latency_metrics",
    comment=(
        "Per-stage and end-to-end latency p50/p95 over 1-minute windows, labelled by "
        "path: 'velocity' (per-bar, the <60s provider-to-signal SLO path) and 'windowed' "
        "(15-minute rolling features; emit delay is at least the watermark). Measures "
        "the SLO rather than asserting it."
    ),
    table_properties={"quality": "metrics"},
)
def dlt_latency_metrics():
    rows = _velocity_rows().unionByName(_windowed_rows())

    return (
        rows.withWatermark("gold_processed_ts", _METRICS_WATERMARK)
        .groupBy("path", F.window("gold_processed_ts", "1 minute"))
        .agg(
            F.percentile_approx("provider_to_signal_seconds", 0.5).alias("provider_to_signal_p50"),
            F.percentile_approx("provider_to_signal_seconds", 0.95).alias("provider_to_signal_p95"),
            F.percentile_approx("silver_to_gold_seconds", 0.5).alias("silver_to_gold_p50"),
            F.percentile_approx("silver_to_gold_seconds", 0.95).alias("silver_to_gold_p95"),
            F.percentile_approx("bronze_to_silver_seconds", 0.5).alias("bronze_to_silver_p50"),
            F.percentile_approx("bronze_to_silver_seconds", 0.95).alias("bronze_to_silver_p95"),
            F.percentile_approx("emit_delay_seconds", 0.5).alias("emit_delay_p50"),
            F.percentile_approx("emit_delay_seconds", 0.95).alias("emit_delay_p95"),
            F.percentile_approx("window_span_seconds", 0.5).alias("window_span_p50"),
            F.percentile_approx("window_span_seconds", 0.95).alias("window_span_p95"),
            F.count("*").alias("rows_measured"),
        )
        .withColumn("window_start", F.col("window.start"))
        .withColumn("window_end", F.col("window.end"))
        .drop("window")
    )
