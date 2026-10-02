"""Streaming silver: validated, deduplicated OHLCV bars plus a quarantine table.

* Typed schema (string / timestamp / double / bigint / int), UTC event time.
* ``information_available_ts = event_ts + bar interval`` (minute bars stamped at start).
* Dedup on the stable business key ``(symbol, event_ts, timespan)`` with a 5-minute
  event-time watermark (bounded state).
* Malformed rows are routed to ``dlt_silver_ohlcv_quarantine`` via DLT expectations:
  the silver table uses ``expect_or_drop`` to drop invalid rows, and the quarantine
  table keeps the invalid rows with their machine-readable reasons.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StringType, TimestampType

import helpers

# Watermark on event time (bounded dedup state). Within the requested 2-5 minute band.
_SILVER_WATERMARK = "5 minutes"

# Columns passed to the validation UDF, in the exact order helpers.validate_bar reads.
_VALIDATION_FIELDS = (
    "symbol",
    "event_ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "trade_count",
    "timespan",
)

_VALIDATE = F.udf(
    lambda row: ["null_record"] if row is None else helpers.validate_bar(row.asDict(recursive=True)),
    ArrayType(StringType()),
)

_SYMBOL = F.udf(helpers.normalize_symbol, StringType())
_TIMESPAN = F.udf(helpers.normalize_timespan, StringType())
_DEDUP_HASH = F.udf(helpers.safe_dedup_hash, StringType())
_INFORMATION_AVAILABLE_TS = F.udf(helpers.safe_derive_information_available_ts, TimestampType())


def _typed_with_reasons():
    """Read the streaming bronze, apply a typed UTC schema, and attach the
    ``information_available_ts``, ``dedup_hash`` and ``quarantine_reasons`` columns.

    Shared by both the silver and quarantine tables so the valid/invalid split is
    computed once and identically.
    """
    bronze = dp.read_stream("dlt_bronze_ohlcv_stream")

    check = F.struct(*[F.col(field) for field in _VALIDATION_FIELDS])
    reasons = _VALIDATE(check)

    return (
        bronze.withColumn("symbol", _SYMBOL(F.col("symbol")))
        .withColumn("timespan", _TIMESPAN(F.col("timespan")))
        .withColumn("open", F.col("open").cast("double"))
        .withColumn("high", F.col("high").cast("double"))
        .withColumn("low", F.col("low").cast("double"))
        .withColumn("close", F.col("close").cast("double"))
        .withColumn("volume", F.col("volume").cast("bigint"))
        .withColumn("vwap", F.col("vwap").cast("double"))
        .withColumn("trade_count", F.col("trade_count").cast("int"))
        .withColumn("information_available_ts", _INFORMATION_AVAILABLE_TS(F.col("event_ts"), F.col("timespan")))
        .withColumn("dedup_hash", _DEDUP_HASH(F.col("symbol"), F.col("event_ts"), F.col("timespan")))
        .withColumn("quarantine_reasons", reasons)
    )


@dp.table(
    name="dlt_silver_ohlcv",
    comment=(
        "Validated, deduplicated OHLCV bars (streaming). information_available_ts = "
        "event_ts + bar interval; dedup on (symbol, event_ts, timespan) with a 5-minute "
        "watermark; malformed rows are quarantined to dlt_silver_ohlcv_quarantine."
    ),
    table_properties={"quality": "silver", "delta.enableChangeDataFeed": "true"},
)
@dp.expect_or_drop("valid_bar", "size(quarantine_reasons) = 0")
def dlt_silver_ohlcv():
    return (
        _typed_with_reasons()
        .withWatermark("event_ts", _SILVER_WATERMARK)
        .dropDuplicates(list(helpers.BUSINESS_KEY_FIELDS))
        .withColumn("silver_processed_ts", F.current_timestamp())
        # quarantine_reasons is retained (always []) for lineage; see module docstring.
        .select(
            "symbol",
            "event_ts",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "vwap",
            "trade_count",
            "timespan",
            "information_available_ts",
            "dedup_hash",
            "ingest_ts",
            "silver_processed_ts",
            "quarantine_reasons",
        )
    )


@dp.table(
    name="dlt_silver_ohlcv_quarantine",
    comment=(
        "Raw OHLCV bars rejected by validation, retained with machine-readable "
        "quarantine reasons instead of being dropped."
    ),
    table_properties={"quality": "quarantine"},
)
@dp.expect_or_drop("invalid_bar", "size(quarantine_reasons) > 0")
def dlt_silver_ohlcv_quarantine():
    return _typed_with_reasons().select(
        "symbol",
        "event_ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "trade_count",
        "timespan",
        "source",
        "ingest_ts",
        "raw_payload",
        "quarantine_reasons",
        "bronze_stream_loaded_ts",
    )
