"""pipelines/lakebase_analytics.py — CDC analytics Delta runner.

Consumes the transactional outbox from Lakebase, MERGEs raw events into a
staging Delta table (``lakebase_change_events``), then idempotently computes
four analytics tables:

* ``analytics_agent_activity``  — UTC date × tool/action/status counts
* ``analytics_watchlist_changes`` — UTC date × symbol add/remove/net
* ``analytics_order_funnel``    — UTC date × funnel stage counts
* ``analytics_usage_daily``     — UTC date × retrieval/write tool totals

All normalization and aggregation logic is in **pure functions** that operate
on plain dictionaries so they can be tested without Spark or Databricks
credentials. Spark/DB resources are acquired only inside ``main()``.

Usage:
    python -m pipelines.lakebase_analytics --catalog X --schema Y
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

_p = globals().get("__file__") or sys.argv[0]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(_p))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lakebase_analytics")

# ── import guards (module must be importable without Spark/psycopg) ──────────

_has_pyspark = False
try:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        StructType, StructField, StringType, LongType,
        TimestampType, DoubleType,
    )
    _has_pyspark = True
except ImportError:
    pass

_has_psycopg = False
try:
    import psycopg
    _has_psycopg = True
except ImportError:
    pass


# ── constants ────────────────────────────────────────────────────────────────

DEFAULT_CATALOG = os.getenv("CATALOG", "bootcamp_students")
DEFAULT_SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "b15d3d6f837ba428")
DEFAULT_BATCH_SIZE = int(os.getenv("CDC_BATCH_SIZE", "5000"))

CHANGE_EVENTS_TABLE = "lakebase_change_events"
STATE_TABLE = "analytics_cdc_state"

# Order status → funnel stage mapping.
# Each status transition produces exactly one stage for the order's UTC date.
# An update that changes status produces a stage for the NEW status only
# (the old status's count is not incremented — no preimage double-counting).
_ORDER_FUNNEL_STAGES = [
    "intent", "approval", "submission", "fill", "cancellation", "rejection", "failure",
]
_STATUS_TO_STAGE = {
    "PENDING_APPROVAL": "intent",
    "APPROVED": "approval",
    "SUBMITTING": "submission",
    "SUBMITTED": "submission",
    "FILLED": "fill",
    "PARTIALLY_FILLED": "fill",
    "CANCELLED": "cancellation",
    "REJECTED": "rejection",
    "FAILED": "failure",
}

CHANGE_EVENTS_SCHEMA = None
STATE_SCHEMA = None
if _has_pyspark:
    CHANGE_EVENTS_SCHEMA = StructType([
        StructField("event_id", LongType(), False),
        StructField("source_table", StringType(), False),
        StructField("source_pk", StringType(), False),
        StructField("operation", StringType(), False),
        StructField("before_payload", StringType(), True),
        StructField("after_payload", StringType(), True),
        StructField("occurred_at", TimestampType(), False),
        StructField("ingested_at", TimestampType(), False),
    ])

    STATE_SCHEMA = StructType([
        StructField("run_id", StringType(), False),
        StructField("completed_at", StringType(), False),
        StructField("max_event_id", LongType(), False),
        StructField("pending_count", LongType(), False),
        StructField("source_target_lag_s", DoubleType(), False),
        StructField("status", StringType(), False),
    ])


# ── dataclass ────────────────────────────────────────────────────────────────

@dataclass
class OutboxEvent:
    event_id: int
    source_table: str
    source_pk: str
    operation: str
    before_payload: Optional[Dict[str, Any]]
    after_payload: Optional[Dict[str, Any]]
    occurred_at: datetime


# ── pure normalization ───────────────────────────────────────────────────────

def parse_event(row: Dict[str, Any]) -> OutboxEvent:
    """Parse a raw Postgres outbox row into an OutboxEvent."""
    bp = row.get("before_payload")
    ap = row.get("after_payload")
    return OutboxEvent(
        event_id=row["event_id"],
        source_table=row["source_table"],
        source_pk=row["source_pk"],
        operation=row["operation"],
        before_payload=json.loads(bp) if isinstance(bp, str) else bp,
        after_payload=json.loads(ap) if isinstance(ap, str) else ap,
        occurred_at=row["occurred_at"],
    )


def extract_date(dt: datetime) -> str:
    """Extract YYYY-MM-DD from a datetime in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


# ── pure aggregation ─────────────────────────────────────────────────────────

def compute_agent_activity(events: List[OutboxEvent]) -> List[Dict[str, Any]]:
    """Compute agent_activity aggregates for the given events.

    Counts by (event_date, tool_name, action_type, status).
    Only processes agent_actions events.
    """
    rows: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for ev in events:
        if ev.source_table != "agent_actions":
            continue
        payload = ev.after_payload or {}
        dt = extract_date(ev.occurred_at)
        tool = payload.get("tool_name", "")
        action = payload.get("action_type", "")
        status = payload.get("status", "")
        key = (dt, tool, action, status)
        if key not in rows:
            rows[key] = {
                "event_date": dt,
                "tool_name": tool,
                "action_type": action,
                "status": status,
                "call_count": 0,
                "distinct_users": set(),
                "last_source_event_id": 0,
                "last_source_time": ev.occurred_at,
            }
        r = rows[key]
        r["call_count"] += 1
        uid = payload.get("user_id", "")
        if uid:
            r["distinct_users"].add(uid)
        if ev.event_id > r["last_source_event_id"]:
            r["last_source_event_id"] = ev.event_id
            r["last_source_time"] = ev.occurred_at

    result = []
    for r in rows.values():
        result.append({
            "event_date": r["event_date"],
            "tool_name": r["tool_name"],
            "action_type": r["action_type"],
            "status": r["status"],
            "call_count": r["call_count"],
            "distinct_users": len(r["distinct_users"]),
            "last_source_event_id": r["last_source_event_id"],
            "last_source_time": r["last_source_time"],
        })
    return result


def compute_watchlist_changes(events: List[OutboxEvent]) -> List[Dict[str, Any]]:
    """Compute watchlist_changes aggregates for the given events.

    Counts by (event_date, symbol): additions (insert/snapshot) and removals (delete).
    """
    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for ev in events:
        if ev.source_table != "watchlists":
            continue
        dt = extract_date(ev.occurred_at)
        payload = ev.after_payload or ev.before_payload or {}
        symbol = payload.get("symbol", "")
        key = (dt, symbol)
        if key not in rows:
            rows[key] = {
                "event_date": dt,
                "symbol": symbol,
                "additions": 0,
                "removals": 0,
                "distinct_users": set(),
                "last_source_event_id": 0,
                "last_source_time": ev.occurred_at,
            }
        r = rows[key]
        if ev.operation in ("insert", "snapshot"):
            r["additions"] += 1
        elif ev.operation == "delete":
            r["removals"] += 1
        uid = (ev.after_payload or ev.before_payload or {}).get("user_id", "")
        if uid:
            r["distinct_users"].add(uid)
        if ev.event_id > r["last_source_event_id"]:
            r["last_source_event_id"] = ev.event_id
            r["last_source_time"] = ev.occurred_at

    result = []
    for r in rows.values():
        result.append({
            "event_date": r["event_date"],
            "symbol": r["symbol"],
            "additions": r["additions"],
            "removals": r["removals"],
            "net_changes": r["additions"] - r["removals"],
            "distinct_users": len(r["distinct_users"]),
            "last_source_event_id": r["last_source_event_id"],
            "last_source_time": r["last_source_time"],
        })
    return result


def compute_order_funnel(events: List[OutboxEvent]) -> List[Dict[str, Any]]:
    """Compute order_funnel aggregates for the given events.

    Each order status transition increments the stage for that status.
    Updates count only the NEW status (no preimage double-counting).
    """
    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for ev in events:
        if ev.source_table != "orders":
            continue
        payload = ev.after_payload or ev.before_payload or {}
        dt = extract_date(ev.occurred_at)
        order_id = payload.get("order_id", "")

        if ev.operation == "insert":
            stage = _STATUS_TO_STAGE.get(payload.get("status", ""), "")
            if stage:
                key = (dt, stage)
                if key not in rows:
                    rows[key] = {"event_date": dt, "funnel_stage": stage,
                                 "stage_count": 0, "distinct_orders": set(),
                                 "last_source_event_id": 0, "last_source_time": ev.occurred_at}
                rows[key]["stage_count"] += 1
                rows[key]["distinct_orders"].add(order_id)
                if ev.event_id > rows[key]["last_source_event_id"]:
                    rows[key]["last_source_event_id"] = ev.event_id
                    rows[key]["last_source_time"] = ev.occurred_at

        elif ev.operation == "update":
            new_status = (ev.after_payload or {}).get("status", "")
            stage = _STATUS_TO_STAGE.get(new_status, "")
            if stage:
                key = (dt, stage)
                if key not in rows:
                    rows[key] = {"event_date": dt, "funnel_stage": stage,
                                 "stage_count": 0, "distinct_orders": set(),
                                 "last_source_event_id": 0, "last_source_time": ev.occurred_at}
                rows[key]["stage_count"] += 1
                rows[key]["distinct_orders"].add(order_id)
                if ev.event_id > rows[key]["last_source_event_id"]:
                    rows[key]["last_source_event_id"] = ev.event_id
                    rows[key]["last_source_time"] = ev.occurred_at

        elif ev.operation == "snapshot":
            stage = _STATUS_TO_STAGE.get(payload.get("status", ""), "")
            if stage:
                key = (dt, stage)
                if key not in rows:
                    rows[key] = {"event_date": dt, "funnel_stage": stage,
                                 "stage_count": 0, "distinct_orders": set(),
                                 "last_source_event_id": 0, "last_source_time": ev.occurred_at}
                rows[key]["stage_count"] += 1
                rows[key]["distinct_orders"].add(order_id)
                if ev.event_id > rows[key]["last_source_event_id"]:
                    rows[key]["last_source_event_id"] = ev.event_id
                    rows[key]["last_source_time"] = ev.occurred_at

    result = []
    for r in rows.values():
        result.append({
            "event_date": r["event_date"],
            "funnel_stage": r["funnel_stage"],
            "stage_count": r["stage_count"],
            "distinct_orders": len(r["distinct_orders"]),
            "last_source_event_id": r["last_source_event_id"],
            "last_source_time": r["last_source_time"],
        })
    return result


def compute_usage_daily(events: List[OutboxEvent]) -> List[Dict[str, Any]]:
    """Compute usage_daily aggregates for the given events.

    Splits agent_actions tool_name into retrieval vs write calls.
    Success = status 'success'/'ok'; failure = anything else.
    """
    rows: Dict[str, Dict[str, Any]] = {}
    for ev in events:
        if ev.source_table != "agent_actions":
            continue
        payload = ev.after_payload or {}
        dt = extract_date(ev.occurred_at)
        tool = payload.get("tool_name", "")
        status_val = payload.get("status", "").lower()
        is_write = any(kw in tool.lower() for kw in
                       ("insert", "update", "delete", "write", "create", "place"))
        is_success = status_val in ("success", "ok", "completed")

        if dt not in rows:
            rows[dt] = {
                "event_date": dt,
                "retrieval_calls": 0, "write_calls": 0,
                "success_count": 0, "failure_count": 0,
                "distinct_users": set(),
                "max_source_event_id": 0,
                "last_source_time": ev.occurred_at,
            }
        r = rows[dt]
        if is_write:
            r["write_calls"] += 1
        else:
            r["retrieval_calls"] += 1
        if is_success:
            r["success_count"] += 1
        else:
            r["failure_count"] += 1
        uid = payload.get("user_id", "")
        if uid:
            r["distinct_users"].add(uid)
        if ev.event_id > r["max_source_event_id"]:
            r["max_source_event_id"] = ev.event_id
            r["last_source_time"] = ev.occurred_at

    result = []
    for r in rows.values():
        result.append({
            "event_date": r["event_date"],
            "retrieval_calls": r["retrieval_calls"],
            "write_calls": r["write_calls"],
            "success_count": r["success_count"],
            "failure_count": r["failure_count"],
            "distinct_users": len(r["distinct_users"]),
            "max_source_event_id": r["max_source_event_id"],
            "last_source_time": r["last_source_time"],
        })
    return result


# ── Postgres I/O ─────────────────────────────────────────────────────────────

def claim_batch(conn: Any, batch_size: int) -> List[OutboxEvent]:
    """Claim a bounded batch of pending outbox events.

    Uses FOR UPDATE SKIP LOCKED to avoid contention with concurrent runners.
    Sets delivered_at to now() atomically so no other runner claims the same rows.
    """
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE analytics_outbox
        SET delivered_at = now(), attempt_count = attempt_count + 1
        WHERE event_id IN (
            SELECT event_id FROM analytics_outbox
            WHERE delivered_at IS NULL
            ORDER BY event_id
            FOR UPDATE SKIP LOCKED
            LIMIT %s
        )
        RETURNING event_id, source_table, source_pk, operation,
                  before_payload::TEXT, after_payload::TEXT, occurred_at
        """,
        (batch_size,),
    )
    rows = cur.fetchall()
    conn.commit()
    return [parse_event({
        "event_id": r[0], "source_table": r[1], "source_pk": r[2],
        "operation": r[3], "before_payload": r[4], "after_payload": r[5],
        "occurred_at": r[6],
    }) for r in rows]


def mark_delivered(conn: Any, event_ids: List[int]) -> None:
    """Confirm delivery for the given event IDs (already set during claim).

    This is a no-op in the current design because claim_batch already sets
    delivered_at. Kept for clarity and future extensibility.
    """
    pass


def mark_failed(conn: Any, event_ids: List[int], error: str) -> None:
    """Record a delivery failure for the given event IDs."""
    if not event_ids:
        return
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE analytics_outbox
        SET delivered_at = NULL, last_error = %s
        WHERE event_id = ANY(%s)
        """,
        (error[:500], event_ids),
    )
    conn.commit()


# ── Delta I/O ────────────────────────────────────────────────────────────────

def _fqn(catalog: str, schema: str, table: str) -> str:
    return f"{catalog}.{schema}.{table}"


def _ensure_table(spark: Any, table_fqn: str, df: Any) -> None:
    """Create the Delta target (empty, with df's schema) on first run so MERGE/DELETE work."""
    if not spark.catalog.tableExists(table_fqn):
        df.limit(0).write.format("delta").saveAsTable(table_fqn)


def merge_events_to_delta(spark: Any, events: List[OutboxEvent],
                          catalog: str, schema: str) -> None:
    """MERGE raw events into lakebase_change_events by event_id."""
    if not events:
        return
    now = datetime.now(timezone.utc)
    rows = [{
        "event_id": ev.event_id,
        "source_table": ev.source_table,
        "source_pk": ev.source_pk,
        "operation": ev.operation,
        "before_payload": json.dumps(ev.before_payload) if ev.before_payload else None,
        "after_payload": json.dumps(ev.after_payload) if ev.after_payload else None,
        "occurred_at": ev.occurred_at,
        "ingested_at": now,
    } for ev in events]

    df = spark.createDataFrame(rows, schema=CHANGE_EVENTS_SCHEMA)
    target = _fqn(catalog, schema, CHANGE_EVENTS_TABLE)
    _ensure_table(spark, target, df)

    df.createOrReplaceTempView("_staging_events")
    spark.sql(f"""
        MERGE INTO {target} t
        USING _staging_events s
        ON t.event_id = s.event_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)


def compute_affected_dates(events: List[OutboxEvent]) -> Set[str]:
    """Extract distinct UTC dates affected by the event batch."""
    dates: Set[str] = set()
    for ev in events:
        dates.add(extract_date(ev.occurred_at))
        if ev.before_payload:
            # For updates/deletes, the before payload's occurred_at is the same
            # event timestamp, so no additional date extraction needed.
            pass
    return dates


def query_events_for_dates(spark: Any, dates: Set[str],
                           catalog: str, schema: str) -> List[OutboxEvent]:
    """Query all events for the given UTC dates from lakebase_change_events.

    This ensures recomputation sees ALL events for a date, not just the current
    batch (handles replays and late deliveries).
    """
    if not dates:
        return []
    date_list = ",".join(f"'{d}'" for d in sorted(dates))
    target = _fqn(catalog, schema, CHANGE_EVENTS_TABLE)
    df = spark.sql(f"""
        SELECT event_id, source_table, source_pk, operation,
               before_payload, after_payload, occurred_at
        FROM {target}
        WHERE date(occurred_at) IN ({date_list})
        ORDER BY event_id
    """)
    rows = [r.asDict() for r in df.collect()]
    return [parse_event(r) for r in rows]


def _delete_and_insert(spark: Any, df: Any, table_fqn: str,
                       dates: Set[str]) -> None:
    """Delete affected dates from target table, then insert new aggregates.

    This is the safest idempotent upsert for analytics tables that have
    composite natural keys (event_date + other dimensions). Deleting by date
    first and inserting fresh aggregates avoids MERGE key complexity.
    """
    if not dates:
        return
    date_list = ",".join(f"'{d}'" for d in sorted(dates))
    _ensure_table(spark, table_fqn, df)
    df.createOrReplaceTempView("_staging_upsert")
    spark.sql(f"DELETE FROM {table_fqn} WHERE event_date IN ({date_list})")
    spark.sql(f"INSERT INTO {table_fqn} SELECT * FROM _staging_upsert")


def upsert_analytics(spark: Any, agent_activity: List[Dict], watchlist_changes: List[Dict],
                     order_funnel: List[Dict], usage_daily: List[Dict],
                     dates: Set[str], catalog: str, schema: str) -> None:
    """Delete affected dates and insert fresh aggregates for all four tables."""
    if not dates:
        return

    # Agent activity
    if agent_activity:
        df = spark.createDataFrame(agent_activity)
        df = df.fillna({"distinct_users": 0, "last_source_event_id": 0})
        _delete_and_insert(spark, df,
                           _fqn(catalog, schema, "analytics_agent_activity"), dates)

    # Watchlist changes
    if watchlist_changes:
        df = spark.createDataFrame(watchlist_changes)
        df = df.fillna({"distinct_users": 0, "last_source_event_id": 0})
        _delete_and_insert(spark, df,
                           _fqn(catalog, schema, "analytics_watchlist_changes"), dates)

    # Order funnel
    if order_funnel:
        df = spark.createDataFrame(order_funnel)
        df = df.fillna({"distinct_orders": 0, "last_source_event_id": 0})
        _delete_and_insert(spark, df,
                           _fqn(catalog, schema, "analytics_order_funnel"), dates)

    # Usage daily
    if usage_daily:
        df = spark.createDataFrame(usage_daily)
        df = df.fillna({"distinct_users": 0, "max_source_event_id": 0})
        _delete_and_insert(spark, df,
                           _fqn(catalog, schema, "analytics_usage_daily"), dates)


def record_state(spark: Any, run_id: str, max_event_id: int,
                 pending_count: int, lag_s: float, status: str,
                 catalog: str, schema: str) -> None:
    """Upsert the CDC pipeline state row."""
    now = datetime.now(timezone.utc).isoformat()
    df = spark.createDataFrame([{
        "run_id": run_id,
        "completed_at": now,
        "max_event_id": max_event_id,
        "pending_count": pending_count,
        "source_target_lag_s": lag_s,
        "status": status,
    }], schema=STATE_SCHEMA)
    table_fqn = _fqn(catalog, schema, STATE_TABLE)
    _ensure_table(spark, table_fqn, df)
    df.createOrReplaceTempView("_staging_state")
    spark.sql(f"""
        MERGE INTO {table_fqn} t
        USING _staging_state s
        ON t.run_id = s.run_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)


# ── main pipeline ────────────────────────────────────────────────────────────

def run_pipeline(spark: Any, conn: Any, catalog: str, schema: str,
                 batch_size: int) -> bool:
    """Execute one pipeline run. Returns True if there may be more events."""
    from datetime import timezone
    run_id = datetime.now(timezone.utc).isoformat()
    log.info("pipeline run %s batch_size=%d", run_id, batch_size)

    # 1. Claim batch
    events = claim_batch(conn, batch_size)
    log.info("claimed %d events", len(events))
    if not events:
        record_state(spark, run_id, 0, 0, 0.0, "idle", catalog, schema)
        return False

    try:
        # 2. MERGE into lakebase_change_events
        merge_events_to_delta(spark, events, catalog, schema)
        max_eid = max(e.event_id for e in events)
        log.info("merged %d events into %s (max_event_id=%d)",
                 len(events), CHANGE_EVENTS_TABLE, max_eid)

        # 3. Compute affected dates
        affected = compute_affected_dates(events)
        log.info("affected dates: %s", sorted(affected))

        # 4. Query all events for affected dates (handles replays)
        all_events = query_events_for_dates(spark, affected, catalog, schema)
        log.info("total events for affected dates: %d", len(all_events))

        # 5. Compute aggregates
        aa = compute_agent_activity(all_events)
        wc = compute_watchlist_changes(all_events)
        of_ = compute_order_funnel(all_events)
        ud = compute_usage_daily(all_events)
        log.info("aggregates: agent_activity=%d watchlist=%d funnel=%d usage=%d",
                 len(aa), len(wc), len(of_), len(ud))

        # 6. Upsert analytics tables
        upsert_analytics(spark, aa, wc, of_, ud, affected, catalog, schema)
        log.info("analytics tables updated")

        # 7. Record state
        lag = (datetime.now(timezone.utc) - events[-1].occurred_at).total_seconds()
        record_state(spark, run_id, max_eid, 0, lag, "success", catalog, schema)

    except Exception as exc:
        log.error("pipeline failed: %s", exc)
        eids = [e.event_id for e in events]
        mark_failed(conn, eids, str(exc))
        record_state(spark, run_id, 0, len(events), 0.0, "error", catalog, schema)
        raise

    return len(events) >= batch_size


def main() -> None:
    parser = argparse.ArgumentParser(description="Lakebase analytics CDC runner")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--warehouse-id", default=WAREHOUSE_ID)
    args = parser.parse_args()

    if not _has_pyspark:
        log.error("pyspark not installed")
        sys.exit(1)
    if not _has_psycopg:
        log.error("psycopg not installed")
        sys.exit(1)

    # Acquire Spark (only inside main)
    from pipelines._runtime import get_spark
    spark = get_spark()

    # Acquire Postgres connection
    conn_str = os.environ.get("LAKEBASE_URL", "")
    if not conn_str:
        log.error("LAKEBASE_URL not set")
        sys.exit(1)
    conn = psycopg.connect(conn_str)

    try:
        has_more = run_pipeline(spark, conn, args.catalog, args.schema,
                                args.batch_size)
        log.info("pipeline complete (has_more=%s)", has_more)
    finally:
        conn.close()


if __name__ == "__main__":
    main()