"""
db/xbrl_queries.py — XBRL facts query helpers.

Provides asof_facts() for point-in-time retrieval of silver XBRL facts.
The PIT filter is mandatory even when as_of is omitted (defaults to now).

Every query uses parameterized :name placeholders through the delta adapter.
No string interpolation of user-supplied values.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")


def _fqn(table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{table}"


def asof_facts(
    as_of: Optional[datetime] = None,
    cik: Optional[str] = None,
    ticker: Optional[str] = None,
    concept: Optional[str] = None,
    taxonomy: Optional[str] = None,
    limit: int = 1000,
) -> tuple[str, Dict[str, Any]]:
    """Build a parameterized PIT query for silver_sec_xbrl_facts.

    Args:
        as_of: Point-in-time timestamp. Defaults to utcnow().
        cik: Filter by CIK.
        ticker: Filter by ticker (case-insensitive).
        concept: Filter by concept (case-insensitive).
        taxonomy: Filter by taxonomy (case-insensitive).
        limit: Row cap (1–5000, default 1000).

    Returns:
        (sql, params) tuple for execution via delta_adapter.

    The query filters:
        - information_available_ts <= as_of
        - quality_status = 'ok' (excludes unresolved_accession)
        - Latest value per (cik, taxonomy, concept, unit, period) ordered by
          information_available_ts DESC, filed_date DESC, accession_number DESC
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    limit = max(1, min(5000, limit))

    sql = f"""
    SELECT
        f.cik,
        f.entity_name,
        f.ticker,
        f.taxonomy,
        f.concept,
        f.label,
        f.unit,
        f.value_decimal,
        f.period_start,
        f.period_end,
        f.instant,
        f.fiscal_year,
        f.fiscal_period,
        f.form_type,
        f.accession_number,
        f.filed_date,
        f.frame,
        f.information_available_ts,
        f.quality_status
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY
                    cik,
                    taxonomy,
                    concept,
                    unit,
                    COALESCE(period_start, ''),
                    COALESCE(period_end, ''),
                    COALESCE(instant, ''),
                    COALESCE(CAST(fiscal_year AS STRING), ''),
                    COALESCE(fiscal_period, '')
                ORDER BY
                    information_available_ts DESC,
                    filed_date DESC,
                    accession_number DESC
            ) AS rn
        FROM {_fqn('silver_sec_xbrl_facts')}
        WHERE information_available_ts <= :as_of
          AND quality_status = 'ok'
    ) f
    WHERE f.rn = 1
    """

    params: Dict[str, Any] = {"as_of": as_of, "limit": limit}

    filters = []
    if cik is not None:
        filters.append("f.cik = :cik")
        params["cik"] = cik
    if ticker is not None:
        filters.append("UPPER(f.ticker) = UPPER(:ticker)")
        params["ticker"] = ticker
    if concept is not None:
        filters.append("UPPER(f.concept) = UPPER(:concept)")
        params["concept"] = concept
    if taxonomy is not None:
        filters.append("UPPER(f.taxonomy) = UPPER(:taxonomy)")
        params["taxonomy"] = taxonomy

    if filters:
        # Insert additional WHERE clauses into the outer query
        where_clause = " AND ".join(filters)
        sql = f"""
        SELECT * FROM (
            {sql}
        ) _asof_filtered
        WHERE {where_clause}
        LIMIT :limit
        """
    else:
        sql = f"{sql} LIMIT :limit"

    return sql.strip(), params