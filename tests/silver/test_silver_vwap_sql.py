"""tests/silver/test_silver_vwap_sql.py

Extracts the REAL _minute_vwap and _adjusted CTEs from silver/08_silver_ohlcv_day_adjusted.sql,
runs them in DuckDB against small fixture tables, and asserts:
- Symbol with minute bars -> vwap_source='minute_bars', value matches
- Symbol with vendor vwap -> vwap_source='vendor'
- Symbol without either -> NULL vwap and NULL source
- A 2:1 split before the bar -> adj_vwap = vwap/2
- A minute bar at 2026-03-10T01:00Z (ET 2026-03-09 21:00) lands on 2026-03-09

Mutation proofs run separately.
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

_SQL_PATH = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"


def _extract_cte(sql_text: str, cte_name: str) -> str:
    """Extract a CREATE OR REPLACE TEMP VIEW statement by name."""
    pattern = rf"(CREATE OR REPLACE TEMP VIEW {cte_name}\s+AS\s+.*?);"
    m = re.search(pattern, sql_text, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError(f"Could not find CTE '{cte_name}' in SQL file")
    return m.group(0)


def _shim_for_duckdb(sql: str) -> str:
    """Translate Databricks-only syntax to DuckDB-compatible SQL."""
    result = sql
    result = result.replace("bootcamp_students.evangoh_capstone.", "")
    # Replace CONVERT_TIMEZONE('UTC', 'America/New_York', event_ts) with DuckDB syntax
    result = result.replace(
        "DATE(CONVERT_TIMEZONE('UTC', 'America/New_York', event_ts))",
        "CAST(event_ts AT TIME ZONE 'UTC' AT TIME ZONE 'America/New_York' AS DATE)"
    )
    return result


def _setup_duckdb(conn: duckdb.DuckDBPyConnection) -> None:
    """Create fixture tables."""
    conn.execute("SET TimeZone='UTC'")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS silver_ohlcv (
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _deduped_daily (
            symbol VARCHAR,
            event_ts TIMESTAMP,
            event_date DATE,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            vwap DOUBLE,
            trade_count INT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze_corporate_actions (
            symbol VARCHAR,
            ex_date DATE,
            split_ratio DOUBLE,
            source VARCHAR,
            fetched_ts TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _universe (
            symbol VARCHAR
        )
    """)


@pytest.fixture
def sql_text():
    return _SQL_PATH.read_text(encoding="utf-8")


@pytest.fixture
def minute_vwap_sql(sql_text):
    raw = _extract_cte(sql_text, "_minute_vwap")
    return _shim_for_duckdb(raw)


class TestMinuteVWAP:
    """_minute_vwap: per (symbol, trading_date) aggregation from minute bars."""

    def test_symbol_with_minute_bars(self, minute_vwap_sql):
        """Symbol with minute bars -> minute_vwap computed correctly."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        # Two minute bars for SPY on 2026-01-05
        # bar1: typical=(11+9+10)/3=10, vol=100 -> VW contribution 1000
        # bar2: typical=(12+10+11)/3=11, vol=300 -> VW contribution 3300
        # minute_vwap = 4300/400 = 10.75
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('SPY', '2026-01-05 14:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('SPY', '2026-01-05 14:31:00', 'minute', 9, 12, 10, 11, 300, NULL)
        """)
        conn.execute(minute_vwap_sql)
        rows = conn.execute(
            "SELECT symbol, trading_date, minute_vwap FROM _minute_vwap ORDER BY 1"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "SPY"
        assert rows[0][2] == pytest.approx(10.75), f"minute_vwap={rows[0][2]}"
        conn.close()

    def test_vendor_vwap_used_over_typical(self, minute_vwap_sql):
        """When vendor vwap is present, it's used instead of typical price."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        # bar1: vendor vwap=10.5, vol=100 -> 1050
        # bar2: no vendor vwap, typical=11, vol=300 -> 3300
        # minute_vwap = 4350/400 = 10.875
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('SPY', '2026-01-05 14:30:00', 'minute', 8, 11, 9, 10, 100, 10.5),
            ('SPY', '2026-01-05 14:31:00', 'minute', 9, 12, 10, 11, 300, NULL)
        """)
        conn.execute(minute_vwap_sql)
        rows = conn.execute(
            "SELECT minute_vwap FROM _minute_vwap"
        ).fetchall()
        expected = (10.5 * 100 + 11 * 300) / 400
        assert rows[0][0] == pytest.approx(expected), f"minute_vwap={rows[0][0]}"
        conn.close()

    def test_zero_volume_bars_excluded(self, minute_vwap_sql):
        """Bars with volume=0 are excluded from the aggregation (WHERE volume > 0)."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        # bar1: vol=100, typical=10 -> 1000
        # bar2: vol=0 (excluded)
        # minute_vwap = 1000/100 = 10.0
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('SPY', '2026-01-05 14:30:00', 'minute', 8, 11, 9, 10, 100, NULL),
            ('SPY', '2026-01-05 14:31:00', 'minute', 20, 30, 20, 25, 0, NULL)
        """)
        conn.execute(minute_vwap_sql)
        rows = conn.execute("SELECT minute_vwap FROM _minute_vwap").fetchall()
        assert rows[0][0] == pytest.approx(10.0), f"minute_vwap={rows[0][0]} (zero vol excluded)"
        conn.close()

    def test_et_date_boundary(self, minute_vwap_sql):
        """A minute bar at 2026-03-10T01:00Z (ET 2026-03-09 21:00) lands on 2026-03-09."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        # 01:00 UTC = 21:00 ET previous day (during EST, UTC-5)
        # 2026-03-10 01:00 UTC = 2026-03-09 20:00 EST (before DST switch on Mar 8)
        # Actually 2026-03-10 is after DST starts (Mar 8), so EDT = UTC-4
        # 2026-03-10 01:00 UTC = 2026-03-09 21:00 EDT
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('SPY', '2026-03-10 01:00:00', 'minute', 8, 11, 9, 10, 100, NULL)
        """)
        conn.execute(minute_vwap_sql)
        rows = conn.execute(
            "SELECT trading_date FROM _minute_vwap"
        ).fetchall()
        import datetime
        assert rows[0][0] == datetime.date(2026, 3, 9), \
            f"trading_date={rows[0][0]} (should be 2026-03-09 ET)"
        conn.close()


class TestAdjustedVWAPSource:
    """_adjusted: vwap_source column and resolved VWAP."""

    def _run_adjusted(self, conn, sql_text):
        """Run the full _adjusted pipeline and return rows."""
        resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
        factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))
        minute_vwap_sql = _shim_for_duckdb(_extract_cte(sql_text, "_minute_vwap"))
        adjusted_sql = _shim_for_duckdb(_extract_cte(sql_text, "_adjusted"))

        conn.execute(resolved_sql)
        conn.execute(factors_sql)
        conn.execute(minute_vwap_sql)
        conn.execute(adjusted_sql)
        return conn.execute(
            "SELECT symbol, event_date, resolved_vwap, adj_vwap, vwap_source "
            "FROM _adjusted ORDER BY symbol, event_date"
        ).fetchall()

    def test_vendor_vwap_source(self, sql_text):
        """Symbol with vendor vwap -> vwap_source='vendor'."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("INSERT INTO _universe VALUES ('AAPL')")
        conn.execute("""
            INSERT INTO _deduped_daily VALUES
            ('AAPL', '2026-01-05 00:00:00', '2026-01-05', 100, 105, 95, 100, 1000000, 102.5, 50000)
        """)
        rows = self._run_adjusted(conn, sql_text)
        assert len(rows) == 1
        assert rows[0][2] == pytest.approx(102.5), f"vwap={rows[0][2]}"
        assert rows[0][4] == "vendor", f"vwap_source={rows[0][4]}"
        conn.close()

    def test_minute_bars_vwap_source(self, sql_text):
        """Symbol with minute bars but no vendor vwap -> vwap_source='minute_bars'."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("INSERT INTO _universe VALUES ('SPY')")
        conn.execute("""
            INSERT INTO _deduped_daily VALUES
            ('SPY', '2026-01-05 00:00:00', '2026-01-05', 100, 105, 95, 100, 1000000, NULL, 50000)
        """)
        # Minute bars: typical=(105+95+100)/3=100, vol=200
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('SPY', '2026-01-05 14:30:00', 'minute', 95, 105, 95, 100, 200, NULL)
        """)
        rows = self._run_adjusted(conn, sql_text)
        assert len(rows) == 1
        assert rows[0][2] == pytest.approx(100.0), f"vwap={rows[0][2]}"
        assert rows[0][4] == "minute_bars", f"vwap_source={rows[0][4]}"
        conn.close()

    def test_no_vwap_source_null(self, sql_text):
        """Symbol without vendor vwap or minute bars -> NULL vwap, NULL source."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("INSERT INTO _universe VALUES ('NODATA')")
        conn.execute("""
            INSERT INTO _deduped_daily VALUES
            ('NODATA', '2026-01-05 00:00:00', '2026-01-05', 100, 105, 95, 100, 1000000, NULL, 50000)
        """)
        rows = self._run_adjusted(conn, sql_text)
        assert len(rows) == 1
        assert rows[0][2] is None, f"vwap={rows[0][2]} (should be NULL)"
        assert rows[0][3] is None, f"adj_vwap={rows[0][3]} (should be NULL)"
        assert rows[0][4] is None, f"vwap_source={rows[0][4]} (should be NULL)"
        conn.close()

    def test_split_adjusts_vwap(self, sql_text):
        """A 2:1 split before the bar -> adj_vwap = vwap / 2."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("INSERT INTO _universe VALUES ('SPLITCO')")
        conn.execute("""
            INSERT INTO _deduped_daily VALUES
            ('SPLITCO', '2026-01-05 00:00:00', '2026-01-05', 200, 210, 190, 200, 1000000, 205, 50000),
            ('SPLITCO', '2026-01-06 00:00:00', '2026-01-06', 105, 110, 100, 105, 2000000, 107, 60000)
        """)
        conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('SPLITCO', '2026-01-06', 2.0, 'massive', '2026-01-01')
        """)
        rows = self._run_adjusted(conn, sql_text)
        by_date = {r[1]: r for r in rows}
        # Before split: cum=2, adj_vwap = 205/2 = 102.5
        r = by_date[__import__('datetime').date(2026, 1, 5)]
        assert r[3] == pytest.approx(102.5), f"adj_vwap={r[3]} (should be 205/2)"
        # After split: cum=1, adj_vwap = 107
        r = by_date[__import__('datetime').date(2026, 1, 6)]
        assert r[3] == pytest.approx(107.0), f"adj_vwap={r[3]}"
        conn.close()


class TestMutationProofs:
    """Mutation tests for silver VWAP logic."""

    def test_mutation_no_minute_vwap_fallback(self, sql_text):
        """Mutation: remove _minute_vwap join.
        Symbol with no vendor vwap would get NULL vwap instead of minute-bar aggregate."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("INSERT INTO _universe VALUES ('SPY')")
        conn.execute("""
            INSERT INTO _deduped_daily VALUES
            ('SPY', '2026-01-05 00:00:00', '2026-01-05', 100, 105, 95, 100, 1000000, NULL, 50000)
        """)
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('SPY', '2026-01-05 14:30:00', 'minute', 95, 105, 95, 100, 200, NULL)
        """)

        # Run the full pipeline
        resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
        factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))
        minute_vwap_sql = _shim_for_duckdb(_extract_cte(sql_text, "_minute_vwap"))
        adjusted_sql = _shim_for_duckdb(_extract_cte(sql_text, "_adjusted"))

        conn.execute(resolved_sql)
        conn.execute(factors_sql)
        conn.execute(minute_vwap_sql)
        conn.execute(adjusted_sql)

        # Correct: vwap should be 100.0 from minute bars
        correct = conn.execute(
            "SELECT resolved_vwap, vwap_source FROM _adjusted WHERE symbol='SPY'"
        ).fetchall()
        assert correct[0][0] == pytest.approx(100.0), f"Correct vwap={correct[0][0]}"
        assert correct[0][1] == "minute_bars"

        # Mutated: remove the minute_vwap join from _adjusted
        mutated_adjusted = adjusted_sql.replace(
            "LEFT JOIN _minute_vwap mv\n    ON  mv.symbol = dd.symbol\n    AND mv.trading_date = dd.event_date;",
            ""
        )
        mutated_adjusted = mutated_adjusted.replace(
            "COALESCE(dd.vwap, mv.minute_vwap)",
            "dd.vwap"
        )
        mutated_adjusted = mutated_adjusted.replace(
            "WHEN mv.minute_vwap IS NOT NULL THEN 'minute_bars'",
            "WHEN FALSE THEN 'minute_bars'"
        )
        conn.execute(mutated_adjusted)
        mutated = conn.execute(
            "SELECT resolved_vwap, vwap_source FROM _adjusted WHERE symbol='SPY'"
        ).fetchall()
        assert mutated[0][0] is None, \
            f"Mutation proof: without minute_vwap join, vwap={mutated[0][0]} (should be NULL)"
        conn.close()

    def test_mutation_utc_date_instead_of_et(self, sql_text):
        """Mutation: use UTC date instead of ET in _minute_vwap.
        A bar at 01:00 UTC would land on wrong trading date."""
        conn = duckdb.connect()
        _setup_duckdb(conn)
        conn.execute("INSERT INTO _universe VALUES ('SPY')")
        conn.execute("""
            INSERT INTO _deduped_daily VALUES
            ('SPY', '2026-03-09 00:00:00', '2026-03-09', 100, 105, 95, 100, 1000000, NULL, 50000),
            ('SPY', '2026-03-10 00:00:00', '2026-03-10', 102, 107, 97, 102, 1000000, NULL, 50000)
        """)
        # This bar at 01:00 UTC on Mar 10 = 21:00 ET on Mar 9 -> should be Mar 9
        conn.execute("""
            INSERT INTO silver_ohlcv VALUES
            ('SPY', '2026-03-10 01:00:00', 'minute', 95, 105, 95, 100, 200, NULL)
        """)

        # Run correct pipeline
        resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
        factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))
        minute_vwap_sql = _shim_for_duckdb(_extract_cte(sql_text, "_minute_vwap"))
        adjusted_sql = _shim_for_duckdb(_extract_cte(sql_text, "_adjusted"))

        conn.execute(resolved_sql)
        conn.execute(factors_sql)
        conn.execute(minute_vwap_sql)
        conn.execute(adjusted_sql)

        # Correct: minute bar lands on Mar 9
        correct = conn.execute(
            "SELECT event_date, vwap_source FROM _adjusted WHERE symbol='SPY' ORDER BY event_date"
        ).fetchall()
        import datetime
        mar9 = [r for r in correct if r[0] == datetime.date(2026, 3, 9)]
        mar10 = [r for r in correct if r[0] == datetime.date(2026, 3, 10)]
        assert mar9[0][1] == "minute_bars", f"Correct: Mar 9 vwap_source={mar9[0][1]}"
        assert mar10[0][1] is None, f"Correct: Mar 10 vwap_source={mar10[0][1]}"

        # Mutated: use UTC date instead of ET
        mutated_mv = minute_vwap_sql.replace(
            "CAST(event_ts AT TIME ZONE 'UTC' AT TIME ZONE 'America/New_York' AS DATE)",
            "CAST(event_ts AS DATE)"
        )
        conn.execute(mutated_mv)
        conn.execute(adjusted_sql)
        mutated = conn.execute(
            "SELECT event_date, vwap_source FROM _adjusted WHERE symbol='SPY' ORDER BY event_date"
        ).fetchall()
        mar9_mut = [r for r in mutated if r[0] == datetime.date(2026, 3, 9)]
        mar10_mut = [r for r in mutated if r[0] == datetime.date(2026, 3, 10)]
        # With UTC date, the bar lands on Mar 10 instead of Mar 9
        assert mar10_mut[0][1] == "minute_bars", \
            f"Mutation proof: UTC date puts bar on Mar 10 (should be Mar 9)"
        assert mar9_mut[0][1] is None, \
            f"Mutation proof: UTC date loses minute bars for Mar 9"
        conn.close()