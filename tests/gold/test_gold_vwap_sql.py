"""tests/gold/test_gold_vwap_sql.py

Extracts the REAL session VWAP computation from gold/01_gold_ohlcv_features.sql,
runs it in DuckDB against small fixture tables, and asserts:
- Session VWAP uses typical price when vendor vwap is NULL
- Session VWAP is trailing (volume-weighted cumulative)
- Zero-volume bar keeps prior session VWAP
- Day boundary resets session VWAP (not blended)
- Bar with vendor vwap uses vendor vwap instead of typical price
- vwap_deviation derives from session_vwap
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[2]
SQL_PATH = REPO / "gold" / "01_gold_ohlcv_features.sql"


def _extract_lagged_cte(sql_path: Path = SQL_PATH) -> str:
    """Extract just the `lagged` CTE from the gold SQL, adapted for DuckDB."""
    text = sql_path.read_text(encoding="utf-8")
    # The lagged CTE starts at "WITH lagged AS (" and ends before "returns AS ("
    start = text.index("WITH lagged AS (")
    end = text.index("  returns AS (")
    sql = text[start:end].rstrip().rstrip(",")
    sql = sql.replace("bootcamp_students.evangoh_capstone.silver_ohlcv", "silver_ohlcv")
    sql = sql.replace("AND symbol IN (SELECT symbol FROM universe)", "")
    sql = sql.replace("AND DATE(event_ts) >= '{date_start}' AND DATE(event_ts) < '{date_end}'", "")
    return sql


def _extract_full_feats_cte(sql_path: Path = SQL_PATH) -> str:
    """Extract the full CTE chain (lagged -> returns -> feats) from the gold SQL.

    Returns the WITH clause adapted for DuckDB, ready to be used as a CTE
    in a SELECT statement."""
    text = sql_path.read_text(encoding="utf-8")
    start = text.index("WITH lagged AS (")
    # Find the end of the feats CTE: the closing paren of feats AS ( ... )
    # is the line before the outer SELECT.
    outer_select_idx = text.index("\n  SELECT\n    symbol,\n    event_ts")
    cte_text = text[start:outer_select_idx]
    cte_text = cte_text.replace("bootcamp_students.evangoh_capstone.silver_ohlcv", "silver_ohlcv")
    cte_text = cte_text.replace("AND symbol IN (SELECT symbol FROM universe)", "")
    cte_text = cte_text.replace("AND DATE(event_ts) >= '{date_start}' AND DATE(event_ts) < '{date_end}'", "")
    cte_text = cte_text.replace("current_timestamp()", "CURRENT_TIMESTAMP")
    return cte_text


def _setup_duckdb(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the silver_ohlcv fixture table."""
    conn.execute("""
        CREATE TABLE silver_ohlcv (
            symbol VARCHAR,
            event_ts TIMESTAMP,
            timespan VARCHAR,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            vwap DOUBLE
        )
    """)


def _run_lagged(conn: duckdb.DuckDBPyConnection, sql: str):
    """Execute the lagged CTE and return rows with session_vwap and vwap_deviation.

    session_vwap is computed in the lagged CTE. vwap_deviation is derived in
    Python since it's a simple formula and lets us test session_vwap directly.
    The sql is a full CTE definition like "WITH lagged AS (...)". We prepend
    a SELECT that references it.
    """
    full_sql = f"{sql} SELECT symbol, event_ts, session_vwap, close FROM lagged ORDER BY symbol, event_ts"
    result = conn.execute(full_sql).fetchall()
    # Derive vwap_deviation in Python
    rows = []
    for r in result:
        sv = r[2]  # session_vwap
        close = r[3]
        vwap_dev = (close - sv) / sv if sv else None
        rows.append((r[0], r[1], sv, vwap_dev))
    return rows


def _run_vwap_deviation_sql(conn: duckdb.DuckDBPyConnection):
    """Execute the REAL vwap_deviation expression from gold/01 via the full CTE chain.

    Extracts lagged -> returns -> feats from the gold SQL and SELECTs
    vwap_deviation from feats, joined with session_vwap from returns.
    Returns (symbol, event_ts, session_vwap, vwap_deviation) rows."""
    cte_sql = _extract_full_feats_cte()
    full_sql = (
        f"{cte_sql}\n"
        "SELECT r.symbol, r.event_ts, r.session_vwap, f.vwap_deviation "
        "FROM returns r "
        "JOIN feats f ON r.symbol = f.symbol AND r.event_ts = f.event_ts "
        "ORDER BY r.symbol, r.event_ts"
    )
    result = conn.execute(full_sql).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in result]


class TestSessionVWAP:
    """Session VWAP: trailing volume-weighted average using typical price when vendor vwap is NULL."""

    def test_three_bars_null_vwap(self):
        """3 minute bars, vwap NULL, one day.
        bar1: (h,l,c,vol)=(11,9,10,100)  -> typical=10,  session_vwap=10
        bar2: (12,10,11,300)             -> typical=11,  session_vwap=(10*100+11*300)/400=10.75
        bar3: (13,11,12,0)               -> zero vol: session_vwap stays 10.75
        """
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL),
            ('AAA', '2026-01-05 09:32:00', 'minute', 10, 13, 11, 12, 0, NULL)
        """)
        sql = _extract_lagged_cte()
        rows = _run_lagged(conn, sql)
        assert len(rows) == 3

        # bar1: session_vwap = 10.0
        assert rows[0][2] == pytest.approx(10.0), f"bar1 session_vwap={rows[0][2]}"
        # bar2: session_vwap = (10*100 + 11*300) / 400 = 10.75
        assert rows[1][2] == pytest.approx(10.75), f"bar2 session_vwap={rows[1][2]}"
        # bar3: zero volume -> keeps prior session_vwap
        assert rows[2][2] == pytest.approx(10.75), f"bar3 session_vwap={rows[2][2]}"
        conn.close()

    def test_vwap_deviation_from_session_vwap(self):
        """vwap_deviation = (close - session_vwap) / NULLIF(session_vwap, 0).

        Uses the REAL expression from gold/01_gold_ohlcv_features.sql."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL)
        """)
        rows = _run_vwap_deviation_sql(conn)

        # bar1: session_vwap=10, vwap_deviation = (10-10)/10 = 0
        assert rows[0][2] == pytest.approx(10.0)
        assert rows[0][3] == pytest.approx(0.0), f"bar1 vwap_deviation={rows[0][3]}"
        # bar2: session_vwap=10.75, vwap_deviation = (11-10.75)/10.75
        expected = (11 - 10.75) / 10.75
        assert rows[1][3] == pytest.approx(expected), f"bar2 vwap_deviation={rows[1][3]}"
        conn.close()

    def test_second_day_resets(self):
        """A second day's first bar resets session VWAP (not blended with day 1)."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL),
            ('AAA', '2026-01-06 09:30:00', 'minute', 19, 21, 19, 20, 50, NULL)
        """)
        sql = _extract_lagged_cte()
        rows = _run_lagged(conn, sql)

        # day 1 bar1: session_vwap = 10
        assert rows[0][2] == pytest.approx(10.0)
        # day 1 bar2: session_vwap = 10.75
        assert rows[1][2] == pytest.approx(10.75)
        # day 2 bar1: session_vwap = 20 (typical price = (21+19+20)/3 = 20)
        assert rows[2][2] == pytest.approx(20.0), f"day2 bar1 session_vwap={rows[2][2]} (should reset)"
        conn.close()

    def test_vendor_vwap_used_when_present(self):
        """A bar with vendor vwap uses it instead of typical price."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, 10.5),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL)
        """)
        sql = _extract_lagged_cte()
        rows = _run_lagged(conn, sql)

        # bar1: vendor vwap=10.5, session_vwap = 10.5
        assert rows[0][2] == pytest.approx(10.5), f"bar1 session_vwap={rows[0][2]} (should use vendor vwap)"
        # bar2: typical=11, session_vwap = (10.5*100 + 11*300) / 400
        expected = (10.5 * 100 + 11 * 300) / 400
        assert rows[1][2] == pytest.approx(expected), f"bar2 session_vwap={rows[1][2]}"
        conn.close()

    def test_zero_volume_bar_keeps_prior(self):
        """Zero-volume bar does not change session VWAP."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 20, 30, 20, 25, 0, NULL),
            ('AAA', '2026-01-05 09:32:00', 'minute', 10, 12, 10, 11, 200, NULL)
        """)
        sql = _extract_lagged_cte()
        rows = _run_lagged(conn, sql)

        # bar1: session_vwap = 10
        assert rows[0][2] == pytest.approx(10.0)
        # bar2: zero volume -> keeps 10
        assert rows[1][2] == pytest.approx(10.0), f"bar2 session_vwap={rows[1][2]} (zero vol keeps prior)"
        # bar3: (10*100 + 11*200) / 300
        expected = (10 * 100 + 11 * 200) / 300
        assert rows[2][2] == pytest.approx(expected), f"bar3 session_vwap={rows[2][2]}"
        conn.close()


class TestMutationProofs:
    """Mutation tests that must FAIL for the correct implementation."""

    def test_mutation_no_typical_price_fallback(self):
        """Mutation: remove COALESCE fallback to typical price.
        With all vendor vwap NULL, session_vwap would be NULL instead of computed."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL)
        """)
        sql = _extract_lagged_cte()
        # Mutate: replace COALESCE(vwap, (high + low + close) / 3.0) with just vwap
        mutated = sql.replace(
            "COALESCE(vwap, (high + low + close) / 3.0)",
            "vwap"
        )
        rows = _run_lagged(conn, mutated)
        # With all NULL vendor vwap, session_vwap should be NULL
        assert rows[0][2] is None, \
            f"Mutation proof: without typical-price fallback, bar1 session_vwap={rows[0][2]} (should be NULL)"
        conn.close()

    def test_mutation_session_partition_no_date(self):
        """Mutation: remove DATE(event_ts) from session_vwap partition (blend days).
        Day 2's first bar would blend with day 1's bars."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL),
            ('AAA', '2026-01-06 09:30:00', 'minute', 19, 21, 19, 20, 50, NULL)
        """)
        sql = _extract_lagged_cte()
        # Targeted mutation: only remove DATE(event_ts) from the session_vwap line
        # The session_vwap SUM expression has the nested pattern with * volume)
        mutated = sql.replace(
            "SUM(volume) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS session_vwap",
            "SUM(volume) OVER (PARTITION BY symbol ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS session_vwap"
        )
        mutated = mutated.replace(
            "SUM(COALESCE(vwap, (high + low + close) / 3.0) * volume) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)",
            "SUM(COALESCE(vwap, (high + low + close) / 3.0) * volume) OVER (PARTITION BY symbol ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)"
        )
        rows = _run_lagged(conn, mutated)
        # day 2 bar1: without DATE partition, cumulative includes day 1's bars
        # typical day2 = 20, but blended: (10*100 + 11*300 + 20*50) / 450 = 11.78
        day2_vwap = rows[2][2]
        assert day2_vwap != pytest.approx(20.0), \
            f"Mutation proof: without DATE partition, day2 session_vwap={day2_vwap} (blended with day1)"
        conn.close()

    def test_mutation_rows_following_future_leak(self):
        """Mutation: ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING (future leak).
        A bar would see future bars' prices."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL)
        """)
        sql = _extract_lagged_cte()
        # Targeted mutation: only change PRECEDING to FOLLOWING on the session_vwap SUM lines
        mutated = sql.replace(
            "SUM(volume) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS session_vwap",
            "SUM(volume) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING), 0) AS session_vwap"
        )
        mutated = mutated.replace(
            "SUM(COALESCE(vwap, (high + low + close) / 3.0) * volume) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)",
            "SUM(COALESCE(vwap, (high + low + close) / 3.0) * volume) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)"
        )
        rows = _run_lagged(conn, mutated)
        # bar1 with FOLLOWING: sees bar1+bar2 = (10*100 + 11*300)/400 = 10.75
        # (not just bar1=10)
        assert rows[0][2] != pytest.approx(10.0), \
            f"Mutation proof: with FOLLOWING, bar1 session_vwap={rows[0][2]} (sees future)"
        conn.close()

    def test_mutation_vwap_deviation_uses_session_vwap_not_vwap(self):
        """Mutation: change vwap_deviation to absolute diff (close - session_vwap).
        The real expression is relative: (close - session_vwap) / NULLIF(session_vwap, 0).
        Mutation must produce different numeric output, not just a bind error."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('AAA', '2026-01-05 09:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('AAA', '2026-01-05 09:31:00', 'minute', 9, 12, 10, 11, 300, NULL)
        """)
        # Get the real vwap_deviation values
        real_rows = _run_vwap_deviation_sql(conn)

        # Mutate: change the expression from relative to absolute difference
        cte_sql = _extract_full_feats_cte()
        mutated = cte_sql.replace(
            "(close - session_vwap) / NULLIF(session_vwap, 0)",
            "close - session_vwap"
        )
        mutated_sql = (
            f"{mutated}\n"
            "SELECT r.symbol, r.event_ts, r.session_vwap, f.vwap_deviation "
            "FROM returns r "
            "JOIN feats f ON r.symbol = f.symbol AND r.event_ts = f.event_ts "
            "ORDER BY r.symbol, r.event_ts"
        )
        result = conn.execute(mutated_sql).fetchall()
        mutated_rows = [(r[0], r[1], r[2], r[3]) for r in result]

        # real: bar2 vwap_deviation = (11-10.75)/10.75 ≈ 0.0233
        # mutated: bar2 vwap_deviation = 11-10.75 = 0.25
        real_devs = [r[3] for r in real_rows]
        mutated_devs = [r[3] for r in mutated_rows]
        assert real_devs != mutated_devs, \
            f"Mutation proof: real={real_devs}, mutated={mutated_devs} — mutation not detected"
        conn.close()