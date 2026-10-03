"""Streaming bronze: continuous landing of the production ``bronze_ohlcv`` table.

Reads the real ``bronze_ohlcv`` table as a stream (``spark.readStream.table``) — the
pipeline never owns or writes the source table. The source table's history is append-only
(``WRITE`` x3,066) plus ``OPTIMIZE`` (measured upstream; see README), so a streaming read
is safe without ``skipChangeCommits``. That assumption is noted here and in the README and
must be re-checked if the upstream writer ever starts emitting UPDATE/DELETE operations.

``dlt_bronze_ohlcv_stream`` is the append-only streaming copy that the rest of the
medallion reads from, stamped with a stream load time for latency measurement.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F


def _source_fqn() -> str:
    catalog = spark.conf.get("source_catalog", "bootcamp_students")
    schema = spark.conf.get("source_schema", "evangoh_capstone")
    table = spark.conf.get("source_table", "bronze_ohlcv")
    return f"{catalog}.{schema}.{table}"


@dp.table(
    name="dlt_bronze_ohlcv_stream",
    comment=(
        "Continuous streaming copy of the production bronze_ohlcv table, stamped "
        "with a stream load time for latency measurement. Never owns the source table."
    ),
    table_properties={
        "quality": "bronze",
        "pipelines.autoOptimize.zOrderCols": "symbol,event_ts",
    },
)
def dlt_bronze_ohlcv_stream():
    source = spark.readStream.table(_source_fqn())
    return source.withColumn("bronze_stream_loaded_ts", F.current_timestamp())
