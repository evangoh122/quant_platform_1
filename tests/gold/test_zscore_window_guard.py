"""tests/gold/test_zscore_window_guard.py — Fix 4: z-score minimum window gate.

Verifies that ``gold/02_gold_options_features.sql`` outputs NULL for
``volume_anomaly_zscore`` when fewer than 20 rows exist in the trailing window.

Two approaches:
  1. Regex scan: the production SQL must contain the count guard.
  2. DuckDB behavioral: extract the z-score expression from the production SQL
     and execute it on a tiny table to confirm rows with fewer than 20 data
     points get NULL z-score.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD_SQL = REPO_ROOT / "gold" / "02_gold_options_features.sql"


def test_gold_sql_contains_count_guard():
    """The production SQL must gate z-score on COUNT >= 20."""
    sql = GOLD_SQL.read_text()
    assert "vol_count" in sql, "vol_win CTE must compute vol_count"
    assert re.search(r"CASE\s+WHEN\s+vol_count\s*>=\s*20", sql) or \
           re.search(r"CASE\s+WHEN\s+vw\.vol_count\s*>=\s*20", sql), (
        "z-score expression must be gated by CASE WHEN vol_count >= 20"
    )
    assert "COUNT(total_volume) OVER w" in sql, (
        "vol_win CTE must include COUNT(total_volume) OVER w"
    )


def _extract_zscore_expression(sql_text: str) -> str:
    """Extract the z-score SELECT expression from the production SQL.

    Returns the expression used for volume_anomaly_zscore from the outer SELECT.
    Handles multi-line CASE expressions.
    """
    lines = sql_text.splitlines()
    # Find the line with "AS volume_anomaly_zscore" (the alias line)
    alias_idx = None
    for i, line in enumerate(lines):
        if "AS volume_anomaly_zscore" in line and not line.strip().startswith("--"):
            alias_idx = i
            break

    if alias_idx is None:
        raise ValueError("Could not find volume_anomaly_zscore alias in SQL")

    # Walk backwards to find the start of the expression (CASE WHEN or a single-line expr)
    start_idx = alias_idx
    for i in range(alias_idx, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("CASE"):
            start_idx = i
            break
        # Keep walking back for multi-line CASE/THEN/END
        if "CASE" in stripped:
            start_idx = i
            break

    # Extract the expression lines, clean up
    expr_lines = lines[start_idx:alias_idx + 1]
    expr = " ".join(l.strip() for l in expr_lines)
    # Remove trailing comma and the alias (we only need the expression)
    expr = expr.rstrip(",").strip()
    # Remove "AS volume_anomaly_zscore" suffix if present
    if expr.endswith("AS volume_anomaly_zscore"):
        expr = expr[: -len("AS volume_anomaly_zscore")].strip()
    return expr


def test_gold_sql_count_guard_produces_null_for_small_windows():
    """Behavioral: execute the z-score expression from the production SQL on a
    tiny DuckDB table. Rows 1-19 must have NULL z-score; row 20+ must have a
    non-NULL z-score."""
    duckdb = pytest.importorskip("duckdb")

    # Read the production SQL and extract the z-score expression
    sql_text = GOLD_SQL.read_text()
    zscore_expr = _extract_zscore_expression(sql_text)

    con = duckdb.connect(":memory:")

    # Create a table with 25 rows for one symbol
    con.execute("""
        CREATE TABLE day_data (
            symbol VARCHAR,
            d DATE,
            total_volume DOUBLE
        )
    """)
    for i in range(1, 26):
        d = f"2026-01-{i:02d}"
        con.execute(
            "INSERT INTO day_data VALUES (?, ?, ?)",
            ("AAPL", d, float(100 + i * 10)),
        )

    # Build the vol_win CTE and query using the production z-score expression
    # The production expression uses day.total_volume; adapt for direct vol_win select
    adapted_expr = zscore_expr.replace("day.total_volume", "vw.total_volume")
    # Ensure the CASE expression is on a single line (no embedded newlines)
    adapted_expr = " ".join(adapted_expr.split())
    query = (
        "WITH day AS ("
        "  SELECT symbol, d, total_volume FROM day_data"
        "),"
        " vol_win AS ("
        "  SELECT"
        "    symbol, d, total_volume,"
        "    AVG(total_volume) OVER w    AS avg_vol,"
        "    STDDEV(total_volume) OVER w AS std_vol,"
        "    COUNT(total_volume) OVER w  AS vol_count"
        "  FROM day"
        "  WINDOW w AS (PARTITION BY symbol ORDER BY d ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)"
        ") "
        "SELECT symbol, d, vol_count, " + adapted_expr + " AS volume_anomaly_zscore "
        "FROM vol_win vw ORDER BY d"
    )
    result = con.execute(query).fetchall()
    con.close()

    # First 19 rows: vol_count < 20, z-score must be NULL
    for row in result[:19]:
        assert row[3] is None, (
            f"Row for {row[1]} has vol_count={row[2]} but z-score is {row[3]}, expected NULL"
        )

    # Row 20+: vol_count >= 20, z-score should be non-NULL (since volumes vary)
    for row in result[19:]:
        assert row[3] is not None, (
            f"Row for {row[1]} has vol_count={row[2]} but z-score is NULL, expected non-NULL"
        )


def test_without_guard_zscore_is_non_null_early():
    """Negative control: without the count guard, early rows would have non-NULL
    z-scores (proving the guard is necessary)."""
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE day_data (
            symbol VARCHAR,
            d DATE,
            total_volume DOUBLE
        )
    """)
    for i in range(1, 26):
        d = f"2026-01-{i:02d}"
        con.execute(
            "INSERT INTO day_data VALUES (?, ?, ?)",
            ("AAPL", d, float(100 + i * 10)),
        )

    # Without the count guard
    result = con.execute("""
        WITH day AS (
            SELECT symbol, d, total_volume FROM day_data
        ),
        vol_win AS (
            SELECT
                symbol, d, total_volume,
                AVG(total_volume) OVER w    AS avg_vol,
                STDDEV(total_volume) OVER w AS std_vol,
                COUNT(total_volume) OVER w  AS vol_count
            FROM day
            WINDOW w AS (PARTITION BY symbol ORDER BY d ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
        )
        SELECT
            symbol, d, vol_count,
            (total_volume - avg_vol) / NULLIF(std_vol, 0) AS volume_anomaly_zscore
        FROM vol_win
        ORDER BY d
    """).fetchall()

    con.close()

    # Without guard, early rows (vol_count >= 2 since STDDEV needs >= 2) would have non-NULL
    early_non_null = [r for r in result[:19] if r[3] is not None]
    assert len(early_non_null) > 0, (
        "Negative control: without the guard, early rows should have non-NULL z-scores"
    )
