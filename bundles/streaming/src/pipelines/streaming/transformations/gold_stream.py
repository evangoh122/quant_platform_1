"""Streaming gold: trailing OHLCV features over event-time windows.

Streaming aggregations cannot use the batch layer's row-based window functions
(``ROWS BETWEEN ... PRECEDING AND CURRENT ROW``) — those are invalid on streaming
DataFrames. Instead, trailing features are computed over sliding event-time windows
with a watermark, the streaming-native equivalent of a trailing window: a window is
only emitted once its end is past the watermark, so it can never see future bars.

Timestamp convention (the batch layer leaked here four times): minute bars are
stamped at bar **start**, so a bar's ``information_available_ts = event_ts + 60s``
(computed in silver and carried through). A trailing window over ``[t, t+15m)`` is
therefore only knowable at ``t+15m``; ``information_available_ts`` is the max of the
carried per-bar values, which equals the window end.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

_GOLD_WATERMARK = "5 minutes"
_WINDOW_SIZE = "15 minutes"
_WINDOW_SLIDE = "1 minute"


@dp.table(
    name="dlt_gold_ohlcv_features",
    comment=(
        "Trailing OHLCV features over a 15-minute sliding event-time window (1-minute "
        "slide). information_available_ts is the window end (event_ts + interval of the "
        "last bar), so joins on information_available_ts <= prediction_ts cannot leak "
        "future data."
    ),
    table_properties={"quality": "gold"},
)
def dlt_gold_ohlcv_features():
    silver = dp.read_stream("dlt_silver_ohlcv").filter("timespan = 'minute'")

    return (
        silver.withWatermark("event_ts", _GOLD_WATERMARK)
        .groupBy("symbol", F.window("event_ts", _WINDOW_SIZE, _WINDOW_SLIDE))
        .agg(
            F.max("high").alias("trailing_high_15m"),
            F.min("low").alias("trailing_low_15m"),
            F.stddev("close").alias("rvol_close_15m"),
            F.avg("volume").alias("avg_volume_15m"),
            F.count("event_ts").alias("bar_count"),
            F.max("information_available_ts").alias("information_available_ts"),
            F.max("silver_processed_ts").alias("silver_processed_ts"),
            F.min("ingest_ts").alias("ingest_ts"),
        )
        .withColumn("window_start", F.col("window.start"))
        .withColumn("window_end", F.col("window.end"))
        .withColumn("gold_processed_ts", F.current_timestamp())
        .drop("window")
        .select(
            "symbol",
            "window_start",
            "window_end",
            "trailing_high_15m",
            "trailing_low_15m",
            "rvol_close_15m",
            "avg_volume_15m",
            "bar_count",
            "information_available_ts",
            "ingest_ts",
            "silver_processed_ts",
            "gold_processed_ts",
        )
    )
