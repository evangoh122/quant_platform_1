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


# ── Canonical SQL query constants (used by production + schema contract) ──────

def _build_latest_signals_query(symbol: Optional[str] = None) -> tuple[str, Optional[Dict[str, Any]]]:
    """Build the latest_signals query. Returns (sql, params)."""
    query = f"SELECT * FROM {_fqn('gold_trading_signals')}"
    params: Optional[Dict[str, Any]] = None
    if symbol:
        query += " WHERE symbol = :symbol"
        params = {"symbol": symbol}
    query += " ORDER BY prediction_ts DESC"
    return query, params


def _build_market_features_daily_query(symbol: str, start_ts: str, end_ts: str) -> tuple[str, Dict[str, Any]]:
    """Build the market_features daily query. Returns (sql, params)."""
    query = (
        f"SELECT symbol, event_date, "
        f"adj_open AS open, adj_high AS high, adj_low AS low, "
        f"adj_close AS close, adj_volume AS volume, adj_vwap AS vwap, "
        f"return_1d "
        f"FROM {_fqn('silver_ohlcv_day_adjusted')} "
        f"WHERE symbol = :symbol AND event_date BETWEEN :start_ts AND :end_ts "
        f"ORDER BY event_date DESC"
    )
    params: Dict[str, Any] = {"symbol": symbol, "start_ts": start_ts, "end_ts": end_ts}
    return query, params


_INTRADAY_COLS = [
    "symbol", "feature_ts",
    "return_1m", "return_5m", "return_15m", "return_30m",
    "rvol_5m", "rvol_15m", "rvol_30m",
    "atr_14", "momentum_5m", "momentum_15m",
    "rsi_14", "vwap_deviation", "relative_volume",
    "dist_session_high", "dist_session_low",
]


def _build_market_features_intraday_query(symbol: str, start_ts: str, end_ts: str) -> tuple[str, Dict[str, Any]]:
    """Build the market_features_intraday query. Returns (sql, params)."""
    cols_sql = ", ".join(_INTRADAY_COLS)
    query = (
        f"SELECT {cols_sql} "
        f"FROM {_fqn('gold_ohlcv_features')} "
        f"WHERE symbol = :symbol AND feature_ts BETWEEN :start_ts AND :end_ts"
    )
    params: Dict[str, Any] = {"symbol": symbol, "start_ts": start_ts, "end_ts": end_ts}
    return query, params


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
_MAX_CONCURRENT_QUERIES = int(os.getenv("DATABRICKS_MAX_CONCURRENT_QUERIES", "10"))
_query_semaphore = __import__("threading").Semaphore(_MAX_CONCURRENT_QUERIES)

# ── connection warm-up state ─────────────────────────────────────────────────
# "idle" → never started | "warming" → background connect in flight
# "ready" → connection established | "error" → warm-up failed
_warm_state: str = "idle"
_warm_detail: str = ""
_warm_lock = __import__("threading").Lock()


def warm_warehouse_connection() -> None:
    """Kick off a background warehouse connect (non-blocking).

    Call at app startup.  The health probe reports ``warming`` (ok=False) while
    the first connect is in flight instead of a bare timeout.
    """
    global _warm_state, _warm_detail
    with _warm_lock:
        if _warm_state in ("warming", "ready"):
            return
        _warm_state = "warming"
        _warm_detail = "connecting"

    import threading as _t

    def _do_warm():
        global _warm_state, _warm_detail
        try:
            _get_warehouse_connection()
            with _warm_lock:
                _warm_state = "ready"
                _warm_detail = "reachable"
        except Exception as exc:  # noqa: BLE001
            with _warm_lock:
                _warm_state = "error"
                _warm_detail = type(exc).__name__

    _t.Thread(target=_do_warm, daemon=True, name="warehouse-warmup").start()


def get_warm_state() -> tuple[str, str]:
    """Return (state, detail) of the background warm-up."""
    with _warm_lock:
        return _warm_state, _warm_detail


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
    params: Optional[Dict[str, Any]] = None,
    *,
    timeout: int = WAREHOUSE_TIMEOUT_S,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Execute a parameterized query on the SQL warehouse. Returns list of dicts.

    Parameters use native named placeholders: ``:name`` markers with a dict
    (``cursor.execute("... WHERE symbol = :symbol", {"symbol": s})``).
    The query is bounded by LIMIT and has a statement timeout enforced via a
    daemon thread (the connector has no native statement timeout).

    On timeout, ``cursor.cancel()`` is called to abort the in-flight query on
    the warehouse, then the cursor is closed.  A bounded semaphore caps
    concurrent in-flight queries so stuck calls cannot pile up.  The semaphore
    slot is held until the worker actually finishes (released in the worker's
    finally block), so timed-out workers do not leak slots.
    """
    import threading as _threading
    from api.diagnostics import stage

    # Enforce bounded LIMIT on SELECT statements only (not DESCRIBE/SHOW/SET)
    _upper = query.lstrip().upper()
    if limit and "LIMIT" not in _upper and _upper.startswith("SELECT"):
        query = f"{query.rstrip(';')} LIMIT {int(limit)}"

    # Acquire semaphore slot — blocks if _MAX_CONCURRENT_QUERIES are in flight.
    # Acquire BEFORE connection creation so the slot bounds total concurrency
    # including the connect + liveness check.
    if not _query_semaphore.acquire(timeout=timeout):
        raise TimeoutError(
            f"Warehouse query semaphore wait timed out after {timeout}s: "
            f"{_extract_table_name(query)}"
        )

    worker_started = False
    try:
        with stage("warehouse_query", table=_extract_table_name(query)):
            result: List[Dict[str, Any]] = []
            error: list[Exception] = []
            cursor_ref: list = []

            def _execute():
                try:
                    # Connection creation + liveness inside the worker so it
                    # is bounded by the thread join timeout.
                    conn = _get_warehouse_connection()
                    cursor = conn.cursor()
                    cursor_ref.append(cursor)
                    cursor.execute(query, params)
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    rows = cursor.fetchall()
                    result.extend(dict(zip(columns, row)) for row in rows)
                except Exception as exc:
                    error.append(exc)
                finally:
                    if cursor_ref:
                        try:
                            cursor_ref[0].close()
                        except Exception:  # noqa: BLE001
                            pass
                    # Release semaphore only when the worker is done, so a
                    # timed-out worker does not leak a slot.
                    _query_semaphore.release()

            t = _threading.Thread(target=_execute, daemon=True)
            t.start()
            worker_started = True
            t.join(timeout=timeout)

            if t.is_alive():
                # Cancel the in-flight query on the warehouse
                if cursor_ref:
                    try:
                        cursor_ref[0].cancel()
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        cursor_ref[0].close()
                    except Exception:  # noqa: BLE001
                        pass
                raise TimeoutError(
                    f"Warehouse query timed out after {timeout}s: "
                    f"{_extract_table_name(query)}"
                )

            if error:
                raise error[0]

            return result
    except BaseException:
        # Once the worker has started it owns the slot and releases it in its
        # own finally (even after a timeout, when the query finally returns).
        # Release here only if we failed before the worker started, otherwise a
        # timed-out query would free its slot twice and exceed the bound.
        if not worker_started:
            _query_semaphore.release()
        raise


def _extract_table_name(query: str) -> str:
    """Best-effort extraction of table name from a query for diagnostics."""
    m = re.search(r"FROM\s+([\w.]+)", query, re.IGNORECASE)
    return m.group(1) if m else "unknown"


def as_dicts(result: Any) -> List[Dict[str, Any]]:
    """Normalize a query result to list[dict].

    Handles both pyspark DataFrames (via .collect() + .asDict()) and plain
    lists-of-dicts returned by the warehouse backend.
    """
    if isinstance(result, list):
        return result
    # pyspark DataFrame — collect and convert
    try:
        return [r.asDict() for r in result.collect()]
    except AttributeError:
        return []


def check_warehouse_health() -> Tuple[bool, str]:
    """Probe the SQL warehouse with SELECT 1. Returns (ok, detail).

    Reports ``warming`` (ok=False) while the background connect is in flight.
    The warming check runs first so that a background connect in progress is
    never masked by a transient import-detection issue.
    """
    try:
        state, detail = get_warm_state()
        if state == "warming":
            return False, "connecting"
        if not _warehouse_available():
            return False, "databricks-sql-connector not installed"
        rows = _warehouse_query("SELECT 1", timeout=5, limit=1)
        ok = len(rows) == 1
        return (ok, "reachable" if ok else "no response")
    except Exception as exc:  # noqa: BLE001
        return False, type(exc).__name__


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
    query, params = _build_latest_signals_query(symbol)
    return _warehouse_query(query, params=params, limit=limit)


def market_features(symbol: str, start_ts: str, end_ts: str, *, limit: int = 5000) -> Any:
    """Read daily bars from silver_ohlcv_day_adjusted (split-adjusted).

    Uses ``adj_*`` columns aliased to the wire names expected by the frontend.
    Auto-selects pyspark or warehouse backend.
    """
    if _has_pyspark:
        spark = _spark()
        daily_cols = [
            "symbol",
            "event_date",
            F.col("adj_open").alias("open"),
            F.col("adj_high").alias("high"),
            F.col("adj_low").alias("low"),
            F.col("adj_close").alias("close"),
            F.col("adj_volume").alias("volume"),
            F.col("adj_vwap").alias("vwap"),
            F.col("return_1d"),
        ]
        df = spark.table(_fqn("silver_ohlcv_day_adjusted")).where(
            (F.col("symbol") == symbol) & (F.col("event_date").between(start_ts, end_ts))
        ).select(*daily_cols)
        return df.limit(limit)

    # Warehouse fallback
    daily_query, params = _build_market_features_daily_query(symbol, start_ts, end_ts)
    return _warehouse_query(daily_query, params=params, limit=limit)


def market_features_intraday(symbol: str, start_ts: str, end_ts: str, *, limit: int = 5000) -> Any:
    """Read intraday features from gold_ohlcv_features.

    Returns the real columns: returns, rvol, atr, momentum, rsi, vwap_deviation, etc.
    Auto-selects pyspark or warehouse backend.
    """
    if _has_pyspark:
        spark = _spark()
        df = spark.table(_fqn("gold_ohlcv_features")).where(
            (F.col("symbol") == symbol) & (F.col("feature_ts").between(start_ts, end_ts))
        ).select(*_INTRADAY_COLS)
        return df.limit(limit)

    # Warehouse fallback
    query, params = _build_market_features_intraday_query(symbol, start_ts, end_ts)
    return _warehouse_query(query, params=params, limit=limit)


# ── analytics table readers ──────────────────────────────────────────────────

_ANALYTICS_TABLES = {
    "agent_activity": "analytics_agent_activity",
    "watchlist_changes": "analytics_watchlist_changes",
    "order_funnel": "analytics_order_funnel",
    "usage_daily": "analytics_usage_daily",
    "model_performance": "analytics_model_performance",
    "latency": "analytics_latency",
    "stream_freshness": "analytics_stream_freshness",
}


def read_analytics_table(section: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Read bounded recent rows from an analytics Delta table.

    Returns list of dicts. Raises ValueError for unknown sections.
    """
    table = _ANALYTICS_TABLES.get(section)
    if table is None:
        raise ValueError(f"unknown analytics section: {section!r}")

    if _has_pyspark:
        spark = _spark()
        try:
            df = spark.table(_fqn(table))
            rows = [r.asDict() for r in df.limit(limit).collect()]
        except Exception:
            return []
        return rows

    # Warehouse fallback
    query = f"SELECT * FROM {_fqn(table)} ORDER BY event_date DESC"
    try:
        return _warehouse_query(query, limit=limit)
    except Exception:
        return []


def read_analytics_cdc_state() -> Optional[Dict[str, Any]]:
    """Read the latest CDC pipeline state row."""
    if _has_pyspark:
        spark = _spark()
        try:
            df = spark.table(_fqn("analytics_cdc_state"))
            rows = [r.asDict() for r in df.limit(1).collect()]
            return rows[0] if rows else None
        except Exception:
            return None

    try:
        rows = _warehouse_query(
            f"SELECT * FROM {_fqn('analytics_cdc_state')} LIMIT 1", limit=1
        )
        return rows[0] if rows else None
    except Exception:
        return None