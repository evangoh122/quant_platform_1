"""
db/delta_adapter.py
Drop-in replacement for IBKR_workbench/db/database.py.
Provides get_connection() shim + direct Delta writers + SQL warehouse reader.

Backend selection:
  * When pyspark is available → use SparkSession (notebooks, local dev).
  * When pyspark is absent → use databricks-sql-connector against a SQL warehouse
    (Databricks Apps production). Warehouse ID from DATABRICKS_WAREHOUSE_ID env,
    default b15d3d6f837ba428. Auth via Databricks SDK default chain.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "b15d3d6f837ba428")
WAREHOUSE_TIMEOUT_S = int(os.getenv("DATABRICKS_WAREHOUSE_TIMEOUT", "30"))

_has_pyspark = False
try:
    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql import functions as F
    _has_pyspark = True
except ImportError:
    pass

# ── warehouse availability flag ───────────────────────────────────────────────

def _warehouse_available() -> bool:
    """Return True if the SQL warehouse backend can be used."""
    try:
        from databricks import sql as dbsql  # noqa: F401
        return True
    except ImportError:
        return False


def _fqn(table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{table}"


def _spark():  # type: ignore[return-type]
    if not _has_pyspark:
        raise ImportError("pyspark not installed; use SQL warehouse backend")
    from pyspark.sql import SparkSession
    return SparkSession.builder.getOrCreate()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── SQL warehouse backend ─────────────────────────────────────────────────────

_warehouse_conn = None
_warehouse_lock = __import__("threading").Lock()


def _get_warehouse_connection():
    """Get or create a pooled warehouse connection (thread-safe singleton)."""
    global _warehouse_conn
    with _warehouse_lock:
        if _warehouse_conn is not None:
            try:
                # Test if still alive
                _warehouse_conn.cursor().execute("SELECT 1").close()
                return _warehouse_conn
            except Exception:  # noqa: BLE001
                try:
                    _warehouse_conn.close()
                except Exception:  # noqa: BLE001
                    pass
                _warehouse_conn = None

        from databricks import sql as dbsql
        from databricks.sdk import WorkspaceClient

        # Auth via SDK default chain (service principal on Databricks Apps)
        ws = WorkspaceClient()
        creds = ws.config.authenticate

        _warehouse_conn = dbsql.connect(
            server_hostname=ws.config.host,
            http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
            credentials_provider=lambda: creds,
            _enable_complex_types=True,
        )
        return _warehouse_conn


def _warehouse_query(
    query: str,
    params: Optional[Tuple[Any, ...]] = None,
    *,
    timeout: int = WAREHOUSE_TIMEOUT_S,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Execute a parameterized query on the SQL warehouse. Returns list of dicts.

    Parameters are passed as %s placeholders (databricks-sql-connector style).
    The query is bounded by LIMIT and has a statement timeout.
    """
    from api.diagnostics import stage

    # Enforce bounded LIMIT if not already present
    if limit and "LIMIT" not in query.upper():
        query = f"{query.rstrip(';')} LIMIT {int(limit)}"

    conn = _get_warehouse_connection()
    with stage("warehouse_query", table=_extract_table_name(query)):
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()


def _extract_table_name(query: str) -> str:
    """Best-effort extraction of table name from a query for diagnostics."""
    m = re.search(r"FROM\s+([\w.]+)", query, re.IGNORECASE)
    return m.group(1) if m else "unknown"


def check_warehouse_health() -> Tuple[bool, str]:
    """Probe the SQL warehouse with SELECT 1. Returns (ok, detail)."""
    try:
        if not _warehouse_available():
            return False, "databricks-sql-connector not installed"
        rows = _warehouse_query("SELECT 1", timeout=5, limit=1)
        ok = len(rows) == 1
        return (ok, "reachable" if ok else "no response")
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:80]}"


# ── DuckDB table name -> Delta table name ─────────────────────────────────────

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
    if not rows:
        return 0
    spark = _spark()
    ts = _now()
    for r in rows:
        r["ingest_ts"] = ts
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("append").saveAsTable(_fqn(table))
    return len(rows)


def read_table(table: str, filters: Optional[str] = None, limit: int = 1000) -> Any:
    """Read from a Delta/warehouse table.

    Uses pyspark when available, otherwise falls back to SQL warehouse.
    """
    if _has_pyspark:
        df = _spark().table(_fqn(table))
        if filters:
            df = df.where(filters)
        return df.limit(limit)

    # Warehouse fallback — build parameterized query
    query = f"SELECT * FROM {_fqn(table)}"
    if filters:
        query = f"SELECT * FROM {_fqn(table)} WHERE {filters}"
    return _warehouse_query(query, limit=limit)


def read_sql(query: str) -> Any:
    """Execute a SQL query.

    Uses pyspark when available, otherwise falls back to SQL warehouse.
    """
    if _has_pyspark:
        return _spark().sql(query)

    # Warehouse fallback
    return _warehouse_query(query, limit=5000)


def latest_signals(symbol: Optional[str] = None, limit: int = 20) -> Any:
    """Read latest trading signals. Auto-selects pyspark or warehouse backend."""
    if _has_pyspark:
        df = _spark().table(_fqn("gold_trading_signals"))
        if symbol:
            df = df.where(F.col("symbol") == symbol)
        return df.orderBy(F.col("prediction_ts").desc()).limit(limit)

    # Warehouse fallback
    query = f"SELECT * FROM {_fqn('gold_trading_signals')}"
    params = None
    if symbol:
        query += " WHERE symbol = %s"
        params = (symbol,)
    query += " ORDER BY prediction_ts DESC"
    return _warehouse_query(query, params=params, limit=limit)


def market_features(symbol: str, start_ts: str, end_ts: str, *, limit: int = 5000) -> Any:
    """Read OHLCV + options features. Auto-selects pyspark or warehouse backend."""
    if _has_pyspark:
        spark = _spark()
        ohlcv_cols = ["symbol", "feature_ts", "open", "high", "low", "close", "volume", "vwap"]
        opts_cols = ["symbol", "feature_ts", "expiry", "atm_iv", "skew", "put_call_ratio", "volume_anomaly"]
        ohlcv = spark.table(_fqn("gold_ohlcv_features")).where(
            (F.col("symbol") == symbol) & (F.col("feature_ts").between(start_ts, end_ts))
        ).select(*ohlcv_cols)
        opts = spark.table(_fqn("gold_options_features")).where(
            (F.col("symbol") == symbol) & (F.col("feature_ts").between(start_ts, end_ts))
        ).select(*opts_cols)
        return ohlcv.join(opts, ["symbol", "feature_ts"], "left").limit(limit)

    # Warehouse fallback — two separate queries (no Spark join available)
    ohlcv_query = (
        f"SELECT symbol, feature_ts, open, high, low, close, volume, vwap "
        f"FROM {_fqn('gold_ohlcv_features')} "
        f"WHERE symbol = %s AND feature_ts BETWEEN %s AND %s"
    )
    opts_query = (
        f"SELECT symbol, feature_ts, expiry, atm_iv, skew, put_call_ratio, volume_anomaly "
        f"FROM {_fqn('gold_options_features')} "
        f"WHERE symbol = %s AND feature_ts BETWEEN %s AND %s"
    )
    params = (symbol, start_ts, end_ts)
    ohlcv_rows = _warehouse_query(ohlcv_query, params=params, limit=limit)
    opts_rows = _warehouse_query(opts_query, params=params, limit=limit)

    # Merge by (symbol, feature_ts)
    opts_by_key = {(r["symbol"], r["feature_ts"]): r for r in opts_rows}
    merged = []
    for row in ohlcv_rows:
        key = (row.get("symbol"), row.get("feature_ts"))
        opt = opts_by_key.get(key, {})
        merged.append({**row, **opt})
    return merged