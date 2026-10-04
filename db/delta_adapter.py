"""
db/delta_adapter.py
Drop-in replacement for IBKR_workbench/db/database.py.
Provides get_connection() shim + direct Delta writers.
"""
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from datetime import datetime, timezone
from typing import List, Dict, Optional
import re

import os

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA  = os.getenv("SCHEMA", "evangoh_capstone")

def _fqn(table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{table}"

def _spark() -> SparkSession:
    return SparkSession.builder.getOrCreate()

def _now() -> datetime:
    return datetime.now(timezone.utc)

# DuckDB table name -> Delta table name
_TABLE_MAP = {
    "polygon_bars": "bronze_ohlcv",
    "polygon_snapshots": "bronze_ohlcv",
    "polygon_option_snapshots": "bronze_options_quotes",
    "polygon_option_bars": "bronze_options_trades",
    "edgar_filings": "bronze_sec_filings",
    "edgar_facts": "bronze_sec_filings",
    "cot_reports": "bronze_cot",
    "stock_quotes": "bronze_ohlcv",
    "option_quotes": "bronze_options_quotes",
}

def get_connection():
    """Drop-in for db.database.get_connection() — returns DeltaConnectionShim."""
    return DeltaConnectionShim()

class DeltaConnectionShim:
    """Mimics DuckDB connection; intercepts INSERT calls and routes to Delta."""
    def __init__(self):
        self._buffer = {}

    def execute(self, sql: str, params=None):
        m = re.match(r"INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+(\w+)", sql, re.IGNORECASE)
        if m and params:
            table = _TABLE_MAP.get(m.group(1), m.group(1))
            self._buffer.setdefault(table, []).append(params)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.flush()

    def flush(self):
        spark = _spark()
        for table, rows in self._buffer.items():
            if rows:
                df = spark.createDataFrame(rows)
                df.write.format("delta").mode("append").saveAsTable(_fqn(table))
        self._buffer.clear()

def write_bronze(table: str, rows: List[Dict]) -> int:
    if not rows: return 0
    spark = _spark()
    ts = _now()
    for r in rows: r["ingest_ts"] = ts
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("append").saveAsTable(_fqn(table))
    return len(rows)

def read_table(table: str, filters: Optional[str] = None, limit: int = 1000) -> DataFrame:
    df = _spark().table(_fqn(table))
    if filters: df = df.where(filters)
    return df.limit(limit)

def read_sql(query: str) -> DataFrame:
    return _spark().sql(query)

def latest_signals(symbol: Optional[str] = None, limit: int = 20) -> DataFrame:
    df = _spark().table(_fqn("gold_trading_signals"))
    if symbol: df = df.where(F.col("symbol") == symbol)
    return df.orderBy(F.col("prediction_ts").desc()).limit(limit)

def market_features(symbol: str, start_ts: str, end_ts: str) -> DataFrame:
    spark = _spark()
    ohlcv = spark.table(_fqn("gold_ohlcv_features")).where(
        (F.col("symbol") == symbol) & (F.col("feature_ts").between(start_ts, end_ts)))
    opts = spark.table(_fqn("gold_options_features")).where(
        (F.col("symbol") == symbol) & (F.col("feature_ts").between(start_ts, end_ts)))
    return ohlcv.join(opts, ["symbol", "feature_ts"], "left")
