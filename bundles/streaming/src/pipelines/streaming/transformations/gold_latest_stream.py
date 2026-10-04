"""Streaming gold velocity path: per-bar, non-windowed latest-bar features.

The <60s provider-receipt-to-signal SLO is measured on this path. It is a per-bar,
**stateless** projection from ``dlt_silver_ohlcv``: no window, no watermark, no
``groupBy``, so every minute bar flows through to gold as it arrives (append mode).
The windowed path (``dlt_gold_ohlcv_features``) is not the SLO path — its emit delay
is at least the watermark (5 minutes) and is reported separately in
``dlt_latency_metrics``.

Per-bar features are computed from the single bar's own fields, so no row-based window
functions (invalid on streaming DataFrames) are required. A "return vs the previous
bar" would need bounded per-symbol state, which DLT continuous does not expose cleanly
without ``applyInPandasWithState``; per-bar flags and intrabar ratios are stateless and
fully sufficient to prove the velocity SLO.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.table(
    name="dlt_gold_ohlcv_latest",
    comment=(
        "Per-bar (non-windowed) latest-bar features emitted as each minute bar arrives. "
        "The <60s provider-to-signal SLO is measured on this velocity path. Stateless, "
        "so no watermark or window delay is introduced."
    ),
    table_properties={"quality": "gold"},
)
def dlt_gold_ohlcv_latest():
    silver = dp.read_stream("dlt_silver_ohlcv").filter("timespan = 'minute'")

    return (
        silver.withColumn(
            "intrabar_return",
            (F.col("close") - F.col("open")) / F.col("open"),
        )
        .withColumn(
            "bar_range",
            (F.col("high") - F.col("low")) / F.col("close"),
        )
        .withColumn(
            "close_vs_vwap",
            (F.col("close") - F.col("vwap")) / F.col("vwap"),
        )
        .withColumn(
            "is_up_bar",
            (F.col("close") >= F.col("open")).cast("boolean"),
        )
        .withColumn("gold_processed_ts", F.current_timestamp())
        .select(
            "symbol",
            "event_ts",
            "timespan",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "vwap",
            "trade_count",
            "intrabar_return",
            "bar_range",
            "close_vs_vwap",
            "is_up_bar",
            "information_available_ts",
            "ingest_ts",
            "silver_processed_ts",
            "gold_processed_ts",
        )
    )
