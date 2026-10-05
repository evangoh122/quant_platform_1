"""
db/xbrl_queries.py — XBRL facts query helpers.

Provides asof_facts() for point-in-time retrieval of silver XBRL facts.
The PIT filter is mandatory even when as_of is omitted (defaults to now).

The base SQL is read from silver/09_silver_sec_xbrl_facts_asof.sql — the
single source of truth for the as-of selection rule.

Every query uses parameterized :name placeholders via spark.sql(args={...}).
No string interpolation of user-supplied values.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_ASOF_SQL_PATH = Path(__file__).resolve().parents[1] / "silver" / "09_silver_sec_xbrl_facts_asof.sql"


def _load_asof_sql() -> str:
    """Load the production as-of SQL from the silver directory."""
    return _ASOF_SQL_PATH.read_text(encoding="utf-8").strip()


def asof_facts(
    spark,
    as_of: Optional[datetime] = None,
    ticker: Optional[str] = None,
    concept: Optional[str] = None,
    limit: int = 1000,
):
    """Execute a parameterized PIT query for silver_sec_xbrl_facts.

    Args:
        spark: Spark session.
        as_of: Point-in-time timestamp. Defaults to utcnow().
        ticker: Filter by ticker (case-insensitive).
        concept: Filter by concept (case-insensitive).
        limit: Row cap (1–5000, default 1000).

    Returns:
        Spark DataFrame with the as-of facts.

    The query filters:
        - information_available_ts <= as_of
        - quality_status = 'ok' (excludes unresolved_accession)
        - Latest value per (cik, taxonomy, concept, unit, period) ordered by
          information_available_ts DESC, filed_date DESC, accession_number DESC
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    limit = max(1, min(5000, limit))

    base_sql = _load_asof_sql()

    # Build optional filter clauses
    extra_filters = []
    args: Dict[str, Any] = {"as_of": as_of}
    if ticker is not None:
        extra_filters.append("UPPER(ticker) = UPPER(:ticker)")
        args["ticker"] = ticker
    if concept is not None:
        extra_filters.append("UPPER(concept) = UPPER(:concept)")
        args["concept"] = concept

    if extra_filters:
        where_clause = " AND ".join(extra_filters)
        sql = f"SELECT * FROM ({base_sql}) _asof_filtered WHERE {where_clause} LIMIT :limit"
    else:
        sql = f"{base_sql} LIMIT :limit"

    args["limit"] = limit

    return spark.sql(sql, args=args)