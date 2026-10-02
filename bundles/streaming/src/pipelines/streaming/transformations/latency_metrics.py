"""Streaming latency metrics: p50/p95 per stage and end-to-end (velocity evidence).

Reads the gold stream and measures, over 1-minute event-time windows with a watermark,
the p50/p95 of:

  * bronze -> silver : silver_processed_ts - ingest_ts   (carried through gold)
  * silver -> gold   : gold_processed_ts   - silver_processed_ts
  * bronze -> gold   : gold_processed_ts   - ingest_ts   (end-to-end)

This is how the <60s provider-receipt-to-signal SLO is *measured* (not asserted) once
the owner chooses to run the pipeline. ``percentile_approx`` requires a Spark 3.x DBR
(DLT serverless provides this).
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

_METRICS_WATERMARK = "5 minutes"


@dp.table(
    name="dlt_latency_metrics",
    comment=(
        "Per-stage and end-to-end pipeline latency p50/p95 over 1-minute windows. "
        "Measures the <60s provider-receipt-to-signal SLO rather than asserting it."
    ),
    table_properties={"quality": "metrics"},
)
def dlt_latency_metrics():
    gold = dp.read_stream("dlt_gold_ohlcv_features")

    return (
        gold.withColumn(
            "bronze_to_silver_seconds",
            F.unix_timestamp("silver_processed_ts") - F.unix_timestamp("ingest_ts"),
        )
        .withColumn(
            "silver_to_gold_seconds",
            F.unix_timestamp("gold_processed_ts") - F.unix_timestamp("silver_processed_ts"),
        )
        .withColumn(
            "bronze_to_gold_seconds",
            F.unix_timestamp("gold_processed_ts") - F.unix_timestamp("ingest_ts"),
        )
        .withWatermark("gold_processed_ts", _METRICS_WATERMARK)
        .groupBy(F.window("gold_processed_ts", "1 minute"))
        .agg(
            F.percentile_approx("bronze_to_silver_seconds", 0.5).alias("bronze_to_silver_p50"),
            F.percentile_approx("bronze_to_silver_seconds", 0.95).alias("bronze_to_silver_p95"),
            F.percentile_approx("silver_to_gold_seconds", 0.5).alias("silver_to_gold_p50"),
            F.percentile_approx("silver_to_gold_seconds", 0.95).alias("silver_to_gold_p95"),
            F.percentile_approx("bronze_to_gold_seconds", 0.5).alias("bronze_to_gold_p50"),
            F.percentile_approx("bronze_to_gold_seconds", 0.95).alias("bronze_to_gold_p95"),
            F.count("*").alias("rows_measured"),
        )
        .withColumn("window_start", F.col("window.start"))
        .withColumn("window_end", F.col("window.end"))
        .drop("window")
    )
