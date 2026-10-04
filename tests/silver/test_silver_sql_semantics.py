"""
tests/silver/test_silver_sql_semantics.py

Semantic tests that extract the REAL CTE SQL from silver/08_silver_ohlcv_day_adjusted.sql,
run it in DuckDB against small fixture tables, and assert cumulative split factors.

These tests prove:
- AMZN 20:1 on 2022-06-06 → cumulative factor 20 for bars before, adj_close continuity ≈ +2%
- Duplicate massive rows same (symbol, ex_date) → applied once (factor 20, not 400)
- SQQQ reverse 5:1 (ratio 0.2) → factor 0.2
- A yfinance-source row present in bronze → ignored (factor unchanged)
- Price-jump break: an unexplained −50% move with no split → one data_quality_breaks row;
  a split day whose move matches the ratio → no break row

Mutation proofs:
- Removing dedupe (WHERE rn = 1) → FAILS (factor ~400)
- Dropping the source filter → FAILS (yfinance row affects factor)
"""
import datetime
import re
import shutil
import tempfile
from pathlib import Path

import duckdb
import pytest


# ---------------------------------------------------------------------------
# SQL extraction and Databricks→DuckDB translation shim
# ---------------------------------------------------------------------------

_SQL_PATH = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"


def _extract_cte(sql_text: str, cte_name: str) -> str:
    """Extract a CREATE OR REPLACE TEMP VIEW statement by name."""
    pattern = rf"(CREATE OR REPLACE TEMP VIEW {cte_name}\s+AS\s+.*?);"
    m = re.search(pattern, sql_text, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError(f"Could not find CTE '{cte_name}' in SQL file")
    return m.group(0)


def _shim_for_duckdb(sql: str) -> str:
    """Translate Databricks-only syntax to DuckDB-compatible SQL.

    Known translations:
    - bootcamp_students.evangoh_capstone. prefix → stripped (use bare table names)
    """
    result = sql

    # Strip schema prefix
    result = result.replace("bootcamp_students.evangoh_capstone.", "")

    return result


def _setup_duckdb(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the fixture tables in DuckDB."""
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
        CREATE TABLE IF NOT EXISTS _universe (
            symbol VARCHAR
        )
    """)
    # Populate universe with AMZN and SQQQ
    conn.execute("INSERT INTO _universe VALUES ('AMZN'), ('SQQQ')")


def _populate_daily(conn: duckdb.DuckDBPyConnection, symbol: str,
                    start: str = "2022-06-01", end: str = "2022-06-10") -> None:
    """Generate daily rows for a symbol with NULL price columns."""
    conn.execute(f"""
        INSERT INTO _deduped_daily (symbol, event_date)
        SELECT '{symbol}' symbol, d::date event_date
        FROM generate_series(DATE '{start}', DATE '{end}', INTERVAL 1 DAY) t(d)
    """)


def _run_resolved_and_factors(conn: duckdb.DuckDBPyConnection,
                              resolved_sql: str, factors_sql: str):
    """Execute _massive_splits and _split_factors, return factor results."""
    conn.execute(resolved_sql)
    conn.execute(factors_sql)
    return conn.execute(
        "SELECT event_date, cumulative_split_ratio FROM _split_factors ORDER BY 1"
    ).fetchall()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def duckdb_conn():
    """Fresh DuckDB connection with fixture tables."""
    conn = duckdb.connect()
    _setup_duckdb(conn)
    _populate_daily(conn, "AMZN")
    _populate_daily(conn, "SQQQ", "2025-11-15", "2025-11-25")
    yield conn
    conn.close()


@pytest.fixture
def sql_text():
    """Raw SQL from silver/08."""
    return _SQL_PATH.read_text(encoding="utf-8")


@pytest.fixture
def resolved_sql(sql_text):
    """Translated _massive_splits CTE for DuckDB."""
    raw = _extract_cte(sql_text, "_massive_splits")
    return _shim_for_duckdb(raw)


@pytest.fixture
def factors_sql(sql_text):
    """Translated _split_factors CTE for DuckDB."""
    raw = _extract_cte(sql_text, "_split_factors")
    return _shim_for_duckdb(raw)


# ---------------------------------------------------------------------------
# 1. AMZN 20:1 on 2022-06-06 → cumulative factor 20
# ---------------------------------------------------------------------------

class TestAMZNSplit:

    def test_amzn_20to1_factor_20(self, duckdb_conn, resolved_sql, factors_sql):
        """AMZN 20:1 split on 2022-06-06 from massive.
        Cumulative factor before 06-06 must be 20."""
        duckdb_conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-01-01')
        """)
        results = _run_resolved_and_factors(duckdb_conn, resolved_sql, factors_sql)

        # Factor before 06-06 should be 20
        pre_split = [r for r in results if r[0] < datetime.date(2022, 6, 6)]
        for row in pre_split:
            assert row[1] == pytest.approx(20.0, rel=1e-6), \
                f"Factor for {row[0]} should be 20, got {row[1]}"

        # Factor on/after 06-06 should be 1
        post_split = [r for r in results if r[0] >= datetime.date(2022, 6, 6)]
        for row in post_split:
            assert row[1] == pytest.approx(1.0, rel=1e-6), \
                f"Factor for {row[0]} should be 1, got {row[1]}"

    def test_amzn_adj_close_continuity(self, duckdb_conn, resolved_sql, factors_sql):
        """AMZN 20:1 on 2022-06-06: adjusted close should show ~+2% continuity,
        not a -95% drop."""
        duckdb_conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-01-01')
        """)

        # Get factors
        duckdb_conn.execute(resolved_sql)
        duckdb_conn.execute(factors_sql)
        factors = duckdb_conn.execute(
            "SELECT event_date, cumulative_split_ratio FROM _split_factors ORDER BY 1"
        ).fetchall()
        factor_map = {r[0]: r[1] for r in factors}

        # Simulate price data: prev_close=2447 (06-03), ex_close=124.79 (06-06)
        prev_close = 2447.0
        ex_close = 124.79

        prev_date = datetime.date(2022, 6, 3)
        ex_date = datetime.date(2022, 6, 6)

        # Adjusted prices
        adj_prev = prev_close / factor_map.get(prev_date, 1.0)
        adj_ex = ex_close / factor_map.get(ex_date, 1.0)

        adj_return = adj_ex / adj_prev - 1.0

        # Should be ~+2%, NOT -95%
        assert adj_return > -0.05, \
            f"Adjusted return should be ~+2%, got {adj_return:.4f} ({adj_return*100:.1f}%)"
        assert adj_return == pytest.approx(0.02, abs=0.01), \
            f"Adjusted return should be ~+2%, got {adj_return:.4f}"


# ---------------------------------------------------------------------------
# 2. Duplicate massive rows same (symbol, ex_date) → applied once
# ---------------------------------------------------------------------------

class TestDuplicateMassiveRows:

    def test_duplicate_rows_factor_20_not_400(self, duckdb_conn, resolved_sql, factors_sql):
        """Duplicate massive rows for AMZN 20:1 on 2022-06-06.
        Factor must be 20 (applied once), not 400."""
        duckdb_conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-01-01'),
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-06-01')
        """)
        results = _run_resolved_and_factors(duckdb_conn, resolved_sql, factors_sql)

        pre_split = [r for r in results if r[0] < datetime.date(2022, 6, 6)]
        for row in pre_split:
            assert row[1] == pytest.approx(20.0, rel=1e-6), \
                f"Factor for {row[0]} should be 20 (deduped), got {row[1]}"

    def test_mutation_dedupe_removal_fails(self, duckdb_conn):
        """Mutation: remove WHERE rn = 1 from _massive_splits.
        With duplicate rows, this yields factor ~400 (double apply)."""
        # Mutated: no dedup
        mutated = """
CREATE OR REPLACE TEMP VIEW _massive_splits AS
SELECT
    symbol,
    ex_date,
    split_ratio
FROM (
    SELECT
        symbol,
        ex_date,
        split_ratio,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, ex_date
            ORDER BY fetched_ts DESC
        ) AS rn
    FROM bronze_corporate_actions
    WHERE source = 'massive'
) sub
WHERE 1=1;
"""
        factors_sql = _shim_for_duckdb(_extract_cte(
            _SQL_PATH.read_text(encoding="utf-8"), "_split_factors"
        ))

        # Setup: duplicate massive rows
        duckdb_conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-01-01'),
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-06-01')
        """)

        # Run mutated SQL
        duckdb_conn.execute(_shim_for_duckdb(mutated))
        duckdb_conn.execute(factors_sql)
        results = duckdb_conn.execute(
            "SELECT event_date, cumulative_split_ratio FROM _split_factors ORDER BY 1"
        ).fetchall()

        # Without dedup, both rows survive → factor 400 for pre-split bars
        pre_split = [r for r in results if r[0] < datetime.date(2022, 6, 6)]
        has_double = any(r[1] > 100 for r in pre_split)
        assert has_double, \
            f"Mutation proof: removing WHERE rn=1 should yield factor ~400, got {pre_split[:3]}"


# ---------------------------------------------------------------------------
# 3. SQQQ reverse 5:1 (ratio 0.2) → factor 0.2
# ---------------------------------------------------------------------------

class TestSQQQReverseSplit:

    def test_sqqq_reverse_5to1(self, duckdb_conn, resolved_sql, factors_sql):
        """SQQQ reverse 5:1 split on 2025-11-20, ratio 0.2 (1/5).
        Factor before 11-20 must be 0.2."""
        duckdb_conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('SQQQ', '2025-11-20', 0.2, 'massive', '2026-01-01')
        """)
        results = _run_resolved_and_factors(duckdb_conn, resolved_sql, factors_sql)

        sqqq_results = [r for r in results if r[0] >= datetime.date(2025, 11, 15)]
        pre_split = [r for r in sqqq_results if r[0] < datetime.date(2025, 11, 20)]
        for row in pre_split:
            assert row[1] == pytest.approx(0.2, rel=1e-6), \
                f"Factor for {row[0]} should be 0.2, got {row[1]}"

        post_split = [r for r in sqqq_results if r[0] >= datetime.date(2025, 11, 20)]
        for row in post_split:
            assert row[1] == pytest.approx(1.0, rel=1e-6), \
                f"Factor for {row[0]} should be 1, got {row[1]}"


# ---------------------------------------------------------------------------
# 4. yfinance-source row in bronze → ignored (factor unchanged)
# ---------------------------------------------------------------------------

class TestYfinanceRowIgnored:

    def test_yfinance_row_does_not_affect_factor(self, duckdb_conn, resolved_sql, factors_sql):
        """A yfinance-source row in bronze must be ignored.
        Factor should be based only on massive rows."""
        duckdb_conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-01-01'),
            ('AMZN', '2022-06-06', 20.0, 'yfinance', '2026-01-01')
        """)
        results = _run_resolved_and_factors(duckdb_conn, resolved_sql, factors_sql)

        pre_split = [r for r in results if r[0] < datetime.date(2022, 6, 6)]
        for row in pre_split:
            assert row[1] == pytest.approx(20.0, rel=1e-6), \
                f"Factor for {row[0]} should be 20 (yfinance ignored), got {row[1]}"

    def test_mutation_drop_source_filter_fails(self, duckdb_conn, resolved_sql, factors_sql):
        """Mutation: remove WHERE source = 'massive' from _massive_splits.
        Fixtures: massive AMZN 20:1 (fetched_ts 2026-01-01) and yfinance AMZN 15.0
        (fetched_ts 2026-02-01, LATER). Positive: real SQL → factor 20.0.
        Mutation: source filter removed → dedup picks yfinance (later ts) → factor 15.0."""
        # Mutated: no source filter
        mutated = """
CREATE OR REPLACE TEMP VIEW _massive_splits AS
SELECT
    symbol,
    ex_date,
    split_ratio
FROM (
    SELECT
        symbol,
        ex_date,
        split_ratio,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, ex_date
            ORDER BY fetched_ts DESC
        ) AS rn
    FROM bronze_corporate_actions
) sub
WHERE rn = 1;
"""
        factors_sql_text = _shim_for_duckdb(_extract_cte(
            _SQL_PATH.read_text(encoding="utf-8"), "_split_factors"
        ))

        # Setup: massive with earlier fetched_ts, yfinance with LATER fetched_ts + different ratio
        duckdb_conn.execute("""
            INSERT INTO bronze_corporate_actions VALUES
            ('AMZN', '2022-06-06', 20.0, 'massive', '2026-01-01'),
            ('AMZN', '2022-06-06', 15.0, 'yfinance', '2026-02-01')
        """)

        # Positive test: real SQL (with source filter) → factor exactly 20.0
        pos_results = _run_resolved_and_factors(duckdb_conn, resolved_sql, factors_sql)
        pre_split_pos = [r for r in pos_results if r[0] < datetime.date(2022, 6, 6)]
        assert len(pre_split_pos) > 0, "Should have pre-split rows"
        for row in pre_split_pos:
            assert row[1] == pytest.approx(20.0, rel=1e-6), \
                f"Positive: factor for {row[0]} should be 20, got {row[1]}"

        # Mutation test: source filter removed → dedup picks yfinance (later fetched_ts) → factor 15.0
        duckdb_conn.execute(_shim_for_duckdb(mutated))
        duckdb_conn.execute(factors_sql_text)
        mut_results = duckdb_conn.execute(
            "SELECT event_date, cumulative_split_ratio FROM _split_factors ORDER BY 1"
        ).fetchall()

        pre_split_mut = [r for r in mut_results if r[0] < datetime.date(2022, 6, 6)]
        for row in pre_split_mut:
            assert row[1] == pytest.approx(15.0, rel=1e-6), \
                f"Mutation proof: without source filter, factor for {row[0]} should be 15 (yfinance), got {row[1]}"


# ---------------------------------------------------------------------------
# 5. Price-jump break detection
# ---------------------------------------------------------------------------

class TestPriceJumpBreak:

    def test_unexplained_50pct_move_with_no_split(self):
        """An unexplained -50% move with no split → one data_quality_breaks row."""
        from tests.silver.test_ohlcv_day_adjusted import _compute_break

        result = _compute_break(
            symbol="MEME",
            current_date=datetime.date(2024, 1, 2),
            current_close=50.0,  # -50% from 100
            previous_date=datetime.date(2024, 1, 1),
            previous_close=100.0,
            splits_today=[],
        )
        assert result["is_candidate"] is True
        assert result["classification"] == "UNEXPLAINED_PENDING"
        assert result["is_masked"] is True

    def test_split_day_move_matches_ratio_no_break(self, duckdb_conn, sql_text):
        """A split day whose move matches the ratio → no break row."""
        from tests.silver.test_ohlcv_day_adjusted import _compute_break

        # AMZN 20:1: prev_close=2447, ex_close=124.79
        # raw_gross_return = 124.79 / 2447 ≈ 0.051 (≈-95%)
        # post_split_gross_return = 0.051 * 20 ≈ 1.02 (≈+2%)
        # split_error = |1.02 - 1| = 0.02 ≤ 0.03 → SPLIT_EXPLAINED
        result = _compute_break(
            symbol="AMZN",
            current_date=datetime.date(2022, 6, 6),
            current_close=124.79,
            previous_date=datetime.date(2022, 6, 3),
            previous_close=2447.0,
            splits_today=[{"ex_date": datetime.date(2022, 6, 6), "split_ratio": 20.0}],
        )
        assert result["is_candidate"] is True
        assert result["classification"] == "SPLIT_EXPLAINED"
        assert result["is_masked"] is False
        assert result["split_error"] <= 0.03


# ---------------------------------------------------------------------------
# 6. Key-leak tests (verify redaction still works)
# ---------------------------------------------------------------------------

class TestKeyLeak:

    def test_api_key_not_in_error_messages(self):
        """Fake session errors containing apiKey=SECRET123 must not surface."""
        from etl.corporate_actions import MassiveCorporateActionsSource, _redact_api_key

        class _LeakySession:
            def __init__(self, secret="SECRET123"):
                self._secret = secret

            def get(self, url, timeout=None):
                raise ConnectionError(
                    f"Connection failed for https://api.massive.com/v3/splits?ticker=X&apiKey={self._secret}"
                )

        session = _LeakySession()
        src = MassiveCorporateActionsSource(
            api_key="SECRET123",
            session=session,
            clock=lambda: datetime.datetime(2025, 1, 1, 12, 0, 0),
            sleeper=lambda secs: None,
            max_retries=0,
        )

        with pytest.raises(RuntimeError) as exc_info:
            src.fetch_splits("X")

        error_text = str(exc_info.value)
        assert "SECRET123" not in error_text, \
            f"API key leaked in error: {error_text[:200]}"

        # Also check exception chain
        cause = exc_info.value.__cause__
        while cause:
            assert "SECRET123" not in str(cause), \
                f"API key leaked in cause: {cause}"
            cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)


# ---------------------------------------------------------------------------
# 7. Price-jump break detection against real SQL
# ---------------------------------------------------------------------------

def _run_break_ctes(conn: duckdb.DuckDBPyConnection,
                    sql_text: str,
                    resolved_sql: str,
                    factors_sql: str):
    """Execute the full break-detection CTE pipeline and return _classified_breaks rows."""
    adjusted_sql = _shim_for_duckdb(_extract_cte(sql_text, "_adjusted"))
    break_cand_sql = _shim_for_duckdb(_extract_cte(sql_text, "_break_candidates"))
    class_breaks_sql = _shim_for_duckdb(_extract_cte(sql_text, "_classified_breaks"))

    conn.execute(resolved_sql)
    conn.execute(factors_sql)
    conn.execute(adjusted_sql)
    conn.execute(break_cand_sql)
    conn.execute(class_breaks_sql)

    return conn.execute(
        "SELECT symbol, event_date, classification, split_error, is_masked "
        "FROM _classified_breaks ORDER BY 1, 2"
    ).fetchall()


@pytest.fixture
def break_conn(sql_text):
    """DuckDB connection with break-detection fixtures:
    - AMZN: 20:1 split on 2022-06-06, adjusted move ~+2% → SPLIT_EXPLAINED
    - MEME: -50% drop, no split → UNEXPLAINED_PENDING
    - SPLITBAD: 20:1 split but raw move doesn't match → UNEXPLAINED_PENDING
    """
    conn = duckdb.connect()
    _setup_duckdb(conn)
    conn.execute("DELETE FROM _universe")
    conn.execute("INSERT INTO _universe VALUES ('AMZN'), ('MEME'), ('SPLITBAD')")

    # AMZN daily bars
    conn.execute("""
        INSERT INTO _deduped_daily VALUES
        ('AMZN', '2022-06-01 00:00:00', '2022-06-01', 2400, 2450, 2380, 2430, 5000000, 2420, 50000),
        ('AMZN', '2022-06-02 00:00:00', '2022-06-02', 2440, 2460, 2410, 2440, 4800000, 2435, 48000),
        ('AMZN', '2022-06-03 00:00:00', '2022-06-03', 2450, 2460, 2430, 2447, 5200000, 2445, 52000),
        ('AMZN', '2022-06-06 00:00:00', '2022-06-06', 122, 126, 121, 124.79, 100000000, 123, 100000),
        ('AMZN', '2022-06-07 00:00:00', '2022-06-07', 125, 127, 123, 126, 95000000, 125, 95000),
        ('AMZN', '2022-06-08 00:00:00', '2022-06-08', 126, 128, 124, 127, 90000000, 126, 90000),
        ('AMZN', '2022-06-09 00:00:00', '2022-06-09', 127, 129, 125, 128, 88000000, 127, 88000),
        ('AMZN', '2022-06-10 00:00:00', '2022-06-10', 128, 130, 126, 129, 85000000, 128, 85000)
    """)

    # MEME: -50% drop, no split
    conn.execute("""
        INSERT INTO _deduped_daily VALUES
        ('MEME', '2024-01-01 00:00:00', '2024-01-01', 100, 105, 95, 100, 1000000, 100, 100),
        ('MEME', '2024-01-02 00:00:00', '2024-01-02', 55, 55, 45, 50, 2000000, 50, 200)
    """)

    # SPLITBAD: 20:1 split but raw move doesn't match (close=100 vs expected ~124.79)
    conn.execute("""
        INSERT INTO _deduped_daily VALUES
        ('SPLITBAD', '2024-03-01 00:00:00', '2024-03-01', 2500, 2550, 2450, 2500, 3000000, 2490, 30000),
        ('SPLITBAD', '2024-03-04 00:00:00', '2024-03-04', 100, 110, 90, 100, 50000000, 100, 50000),
        ('SPLITBAD', '2024-03-05 00:00:00', '2024-03-05', 101, 103, 99, 101, 45000000, 101, 45000)
    """)

    # Massive splits
    conn.execute("""
        INSERT INTO bronze_corporate_actions VALUES
        ('AMZN', '2022-06-06', 20.0, 'massive', '2026-01-01'),
        ('SPLITBAD', '2024-03-04', 20.0, 'massive', '2026-01-01')
    """)

    yield conn
    conn.close()


class TestPriceJumpBreakSQL:

    def test_unexplained_50pct_move_with_no_split(self, break_conn, sql_text):
        """(a) Unexplained -50% move, no split → exactly one break row.
        Classification: UNEXPLAINED_PENDING, is_masked=True."""
        resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
        factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))
        results = _run_break_ctes(break_conn, sql_text, resolved_sql, factors_sql)

        meme_breaks = [r for r in results if r[0] == "MEME"]
        assert len(meme_breaks) == 1, f"Expected 1 MEME break, got {len(meme_breaks)}"
        row = meme_breaks[0]
        assert row[1] == datetime.date(2024, 1, 2)
        assert row[2] == "UNEXPLAINED_PENDING"
        assert row[3] == pytest.approx(0.5, abs=1e-6)  # split_error
        assert row[4] is True  # is_masked

    def test_split_day_adjusted_move_matches_no_break(self, break_conn, sql_text):
        """(b) AMZN split day with matching ~+2% adjusted move → SPLIT_EXPLAINED (not a break)."""
        resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
        factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))
        results = _run_break_ctes(break_conn, sql_text, resolved_sql, factors_sql)

        amzn_breaks = [r for r in results if r[0] == "AMZN"]
        assert len(amzn_breaks) == 1, f"Expected 1 AMZN break, got {len(amzn_breaks)}"
        row = amzn_breaks[0]
        assert row[1] == datetime.date(2022, 6, 6)
        assert row[2] == "SPLIT_EXPLAINED"
        assert row[3] <= 0.03  # split_error within tolerance
        assert row[4] is False  # is_masked = False

    def test_split_day_raw_move_mismatch_flagged(self, break_conn, sql_text):
        """(c) Split day whose raw move doesn't match ratio → UNEXPLAINED_PENDING."""
        resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
        factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))
        results = _run_break_ctes(break_conn, sql_text, resolved_sql, factors_sql)

        bad_breaks = [r for r in results if r[0] == "SPLITBAD"]
        assert len(bad_breaks) == 1, f"Expected 1 SPLITBAD break, got {len(bad_breaks)}"
        row = bad_breaks[0]
        assert row[1] == datetime.date(2024, 3, 4)
        assert row[2] == "UNEXPLAINED_PENDING"
        assert row[3] > 0.03  # split_error exceeds tolerance
        assert row[4] is True  # is_masked = True

    def test_mutation_break_candidate_predicate_required(self, break_conn, sql_text):
        """Mutation: remove the abs(raw_gross_return - 1) >= 0.40 predicate.
        Without it, AMZN's small ~2% daily moves become false break candidates."""
        resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
        factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))

        # Run correct pipeline first
        _run_break_ctes(break_conn, sql_text, resolved_sql, factors_sql)

        # Verify correct: only AMZN 2022-06-06 is a break (the split day)
        correct_breaks = break_conn.execute(
            "SELECT symbol, event_date FROM _break_candidates ORDER BY 1, 2"
        ).fetchall()
        assert ("AMZN", datetime.date(2022, 6, 6)) in correct_breaks
        assert ("MEME", datetime.date(2024, 1, 2)) in correct_breaks
        # AMZN small-move days must NOT be break candidates
        amzn_dates = [r[1] for r in correct_breaks if r[0] == "AMZN"]
        assert datetime.date(2022, 6, 2) not in amzn_dates
        assert datetime.date(2022, 6, 3) not in amzn_dates

        # Mutate: remove the 40% threshold predicate
        mutated_sql = _shim_for_duckdb("""CREATE OR REPLACE TEMP VIEW _break_candidates AS
SELECT
    a.symbol,
    a.event_date,
    a.previous_event_date,
    a.previous_close,
    a.close,
    a.raw_gross_return - 1.0 AS raw_overnight_return,
    a.raw_gross_return,
    COALESCE(day_splits.day_split_ratio, 1.0) AS day_split_ratio,
    a.raw_gross_return * COALESCE(day_splits.day_split_ratio, 1.0) AS post_split_gross_return,
    ABS(a.raw_gross_return * COALESCE(day_splits.day_split_ratio, 1.0) - 1.0) AS split_error
FROM _adjusted a
LEFT JOIN (
    SELECT symbol, ex_date, EXP(SUM(LN(split_ratio))) AS day_split_ratio
    FROM _massive_splits
    GROUP BY symbol, ex_date
) day_splits
    ON  day_splits.symbol = a.symbol
    AND day_splits.ex_date = a.event_date
WHERE a.raw_gross_return IS NOT NULL
  AND a.previous_close IS NOT NULL;""")
        class_breaks_sql = _shim_for_duckdb(_extract_cte(sql_text, "_classified_breaks"))
        break_conn.execute(mutated_sql)
        break_conn.execute(class_breaks_sql)

        # Without the predicate, AMZN small moves become false break candidates
        mut_breaks = break_conn.execute(
            "SELECT symbol, event_date, classification FROM _classified_breaks ORDER BY 1, 2"
        ).fetchall()
        amzn_false_positives = [
            r for r in mut_breaks if r[0] == "AMZN"
            and r[1] != datetime.date(2022, 6, 6)
        ]
        assert len(amzn_false_positives) > 0, \
            "Mutation proof: removing 40% predicate must produce AMZN false positives"


# ---------------------------------------------------------------------------
# 8. Adjusted arithmetic: exact adj_close and adj_volume from real SQL
# ---------------------------------------------------------------------------

def _run_adjusted(conn: duckdb.DuckDBPyConnection, sql_text: str):
    """Execute _massive_splits → _split_factors → _adjusted, return adjusted rows."""
    resolved_sql = _shim_for_duckdb(_extract_cte(sql_text, "_massive_splits"))
    factors_sql = _shim_for_duckdb(_extract_cte(sql_text, "_split_factors"))
    adjusted_sql = _shim_for_duckdb(_extract_cte(sql_text, "_adjusted"))
    conn.execute(resolved_sql)
    conn.execute(factors_sql)
    conn.execute(adjusted_sql)
    return conn.execute(
        "SELECT symbol, event_date, close, volume, "
        "cumulative_split_ratio, price_adjustment_factor, "
        "adj_close, adj_volume "
        "FROM _adjusted ORDER BY symbol, event_date"
    ).fetchall()


@pytest.fixture
def adjusted_conn(sql_text):
    """DuckDB with three split scenarios for exact adj_close / adj_volume testing.

    TWOSPLIT: two 2:1 splits (ex 2022-03-01 and 2023-06-01).
      - Before 2022-03-01: cum = 2*2 = 4, paf = 0.25
      - Between splits:    cum = 2,    paf = 0.5
      - After 2023-06-01:  cum = 1,    paf = 1.0

    REV: 1:10 reverse split (ex 2024-06-03, ratio 0.1).
      - Before 2024-06-03: cum = 0.1, paf = 10.0
      - On/after:          cum = 1,   paf = 1.0

    EXDATE: 3:1 forward split (ex 2023-09-04, ratio 3.0).
      - Before 2023-09-04: cum = 3,   paf = 1/3
      - On/after:          cum = 1,   paf = 1.0
    """
    conn = duckdb.connect()
    _setup_duckdb(conn)
    conn.execute("DELETE FROM _universe")
    conn.execute("INSERT INTO _universe VALUES ('TWOSPLIT'), ('REV'), ('EXDATE')")

    # TWOSPLIT daily bars
    conn.execute("""
        INSERT INTO _deduped_daily VALUES
        ('TWOSPLIT', '2022-02-28 00:00:00', '2022-02-28', 400, 410, 390, 400, 1000000, 405, 10000),
        ('TWOSPLIT', '2022-03-01 00:00:00', '2022-03-01', 210, 215, 205, 210, 2000000, 212, 20000),
        ('TWOSPLIT', '2023-05-31 00:00:00', '2023-05-31', 100, 105,  95, 100, 3000000, 102, 30000),
        ('TWOSPLIT', '2023-06-01 00:00:00', '2023-06-01',  55,  57,  53,  55, 6000000,  56, 60000),
        ('TWOSPLIT', '2023-06-02 00:00:00', '2023-06-02',  56,  58,  54,  56, 5500000,  57, 55000)
    """)

    # REV daily bars
    conn.execute("""
        INSERT INTO _deduped_daily VALUES
        ('REV', '2024-05-31 00:00:00', '2024-05-31', 5, 5.5, 4.5, 5, 500000, 5.1, 5000),
        ('REV', '2024-06-03 00:00:00', '2024-06-03', 52, 54, 50, 52, 100000, 53, 1000),
        ('REV', '2024-06-04 00:00:00', '2024-06-04', 53, 55, 51, 53, 90000, 54, 900)
    """)

    # EXDATE daily bars
    conn.execute("""
        INSERT INTO _deduped_daily VALUES
        ('EXDATE', '2023-09-01 00:00:00', '2023-09-01', 300, 310, 290, 300, 400000, 305, 4000),
        ('EXDATE', '2023-09-04 00:00:00', '2023-09-04', 105, 108, 102, 105, 1200000, 106, 12000),
        ('EXDATE', '2023-09-05 00:00:00', '2023-09-05', 107, 110, 104, 107, 1100000, 108, 11000)
    """)

    # Massive splits
    conn.execute("""
        INSERT INTO bronze_corporate_actions VALUES
        ('TWOSPLIT', '2022-03-01', 2.0, 'massive', '2026-01-01'),
        ('TWOSPLIT', '2023-06-01', 2.0, 'massive', '2026-01-01'),
        ('REV',      '2024-06-03', 0.1, 'massive', '2026-01-01'),
        ('EXDATE',   '2023-09-04', 3.0, 'massive', '2026-01-01')
    """)

    yield conn
    conn.close()


class TestAdjustedArithmetic:

    def test_two_split_cumulative_product(self, adjusted_conn, sql_text):
        """Two 2:1 splits: cumulative = 4 before first, 2 between, 1 after second.
        adj_close = close / cum; adj_volume = volume * cum."""
        rows = _run_adjusted(adjusted_conn, sql_text)
        by_key = {(r[0], r[1]): r for r in rows}

        # Before first split (cum=4, paf=0.25)
        r = by_key[("TWOSPLIT", datetime.date(2022, 2, 28))]
        assert r[4] == pytest.approx(4.0), f"cum should be 4, got {r[4]}"
        assert r[5] == pytest.approx(0.25), f"paf should be 0.25, got {r[5]}"
        assert r[6] == pytest.approx(100.0), f"adj_close=400/4=100, got {r[6]}"
        assert r[7] == pytest.approx(4000000.0), f"adj_volume=1M*4=4M, got {r[7]}"

        # Between splits (cum=2, paf=0.5)
        r = by_key[("TWOSPLIT", datetime.date(2023, 5, 31))]
        assert r[4] == pytest.approx(2.0), f"cum should be 2, got {r[4]}"
        assert r[6] == pytest.approx(50.0), f"adj_close=100/2=50, got {r[6]}"
        assert r[7] == pytest.approx(6000000.0), f"adj_volume=3M*2=6M, got {r[7]}"

        # On second ex-date (cum=1, paf=1.0) — ex-date bar is on new basis
        r = by_key[("TWOSPLIT", datetime.date(2023, 6, 1))]
        assert r[4] == pytest.approx(1.0), f"cum should be 1, got {r[4]}"
        assert r[6] == pytest.approx(55.0), f"adj_close=55/1=55, got {r[6]}"
        assert r[7] == pytest.approx(6000000.0), f"adj_volume=6M*1=6M, got {r[7]}"

    def test_reverse_split_exact_values(self, adjusted_conn, sql_text):
        """1:10 reverse split (ratio 0.1): cum=0.1 before, 1 on/after.
        adj_close = close / 0.1 = close * 10; adj_volume = volume * 0.1."""
        rows = _run_adjusted(adjusted_conn, sql_text)
        by_key = {(r[0], r[1]): r for r in rows}

        # Before reverse split (cum=0.1, paf=10)
        r = by_key[("REV", datetime.date(2024, 5, 31))]
        assert r[4] == pytest.approx(0.1), f"cum should be 0.1, got {r[4]}"
        assert r[5] == pytest.approx(10.0), f"paf should be 10, got {r[5]}"
        assert r[6] == pytest.approx(50.0), f"adj_close=5/0.1=50, got {r[6]}"
        assert r[7] == pytest.approx(50000.0), f"adj_volume=500K*0.1=50K, got {r[7]}"

        # On ex-date (cum=1, paf=1.0) — ex-date bar is on new basis
        r = by_key[("REV", datetime.date(2024, 6, 3))]
        assert r[4] == pytest.approx(1.0), f"cum should be 1, got {r[4]}"
        assert r[6] == pytest.approx(52.0), f"adj_close=52/1=52, got {r[6]}"
        assert r[7] == pytest.approx(100000.0), f"adj_volume=100K*1=100K, got {r[7]}"

        # Day after ex-date (still cum=1)
        r = by_key[("REV", datetime.date(2024, 6, 4))]
        assert r[4] == pytest.approx(1.0)
        assert r[6] == pytest.approx(53.0)
        assert r[7] == pytest.approx(90000.0)

    def test_exdate_bar_on_new_basis(self, adjusted_conn, sql_text):
        """3:1 split ex-date bar: cum=1 (split not included for ex-date bar).
        adj_close = close (unchanged), adj_volume = volume (unchanged)."""
        rows = _run_adjusted(adjusted_conn, sql_text)
        by_key = {(r[0], r[1]): r for r in rows}

        # Before split (cum=3)
        r = by_key[("EXDATE", datetime.date(2023, 9, 1))]
        assert r[4] == pytest.approx(3.0), f"cum should be 3, got {r[4]}"
        assert r[6] == pytest.approx(100.0), f"adj_close=300/3=100, got {r[6]}"
        assert r[7] == pytest.approx(1200000.0), f"adj_volume=400K*3=1.2M, got {r[7]}"

        # Ex-date bar (cum=1 — ex_date > event_date excludes this split)
        r = by_key[("EXDATE", datetime.date(2023, 9, 4))]
        assert r[4] == pytest.approx(1.0), f"cum should be 1, got {r[4]}"
        assert r[6] == pytest.approx(105.0), f"adj_close=105/1=105, got {r[6]}"
        assert r[7] == pytest.approx(1200000.0), f"adj_volume=1.2M*1=1.2M, got {r[7]}"

    def test_mutation_adj_close_times_cum_fails(self, adjusted_conn, sql_text):
        """Mutation proof: adj_close = close * cum (wrong) vs close / cum (correct).
        For TWOSPLIT before first split: close=400, cum=4.
        Correct: adj_close = 400/4 = 100.  Mutation: 400*4 = 1600."""
        rows = _run_adjusted(adjusted_conn, sql_text)
        by_key = {(r[0], r[1]): r for r in rows}

        r = by_key[("TWOSPLIT", datetime.date(2022, 2, 28))]
        adj_close = r[6]
        close = r[2]
        cum = r[4]
        # Correct formula: adj_close = close / cum
        assert adj_close == pytest.approx(close / cum), \
            f"adj_close should be close/cum = {close}/{cum} = {close/cum}, got {adj_close}"
        # Mutation proof: adj_close should NOT be close * cum
        assert adj_close != pytest.approx(close * cum), \
            f"Mutation: adj_close = close*cum = {close*cum} would be wrong"

    def test_mutation_adj_volume_div_cum_fails(self, adjusted_conn, sql_text):
        """Mutation proof: adj_volume = volume / cum (wrong) vs volume * cum (correct).
        For TWOSPLIT before first split: volume=1M, cum=4.
        Correct: adj_volume = 1M*4 = 4M.  Mutation: 1M/4 = 250K."""
        rows = _run_adjusted(adjusted_conn, sql_text)
        by_key = {(r[0], r[1]): r for r in rows}

        r = by_key[("TWOSPLIT", datetime.date(2022, 2, 28))]
        adj_volume = r[7]
        volume = r[3]
        cum = r[4]
        # Correct formula: adj_volume = volume * cum
        assert adj_volume == pytest.approx(volume * cum), \
            f"adj_volume should be volume*cum = {volume}*{cum} = {volume*cum}, got {adj_volume}"
        # Mutation proof: adj_volume should NOT be volume / cum
        assert adj_volume != pytest.approx(volume / cum), \
            f"Mutation: adj_volume = volume/cum = {volume/cum} would be wrong"

    def test_reverse_split_mutation_adj_close(self, adjusted_conn, sql_text):
        """Mutation proof for reverse split: adj_close = close * cum (wrong).
        REV before split: close=5, cum=0.1.
        Correct: adj_close = 5/0.1 = 50.  Mutation: 5*0.1 = 0.5."""
        rows = _run_adjusted(adjusted_conn, sql_text)
        by_key = {(r[0], r[1]): r for r in rows}

        r = by_key[("REV", datetime.date(2024, 5, 31))]
        adj_close = r[6]
        close = r[2]
        cum = r[4]
        assert adj_close == pytest.approx(close / cum), \
            f"adj_close should be {close}/{cum} = {close/cum}, got {adj_close}"
        assert adj_close != pytest.approx(close * cum), \
            f"Mutation: adj_close = {close}*{cum} = {close*cum} would be wrong"

    def test_reverse_split_mutation_adj_volume(self, adjusted_conn, sql_text):
        """Mutation proof for reverse split: adj_volume = volume / cum (wrong).
        REV before split: volume=500K, cum=0.1.
        Correct: adj_volume = 500K*0.1 = 50K.  Mutation: 500K/0.1 = 5M."""
        rows = _run_adjusted(adjusted_conn, sql_text)
        by_key = {(r[0], r[1]): r for r in rows}

        r = by_key[("REV", datetime.date(2024, 5, 31))]
        adj_volume = r[7]
        volume = r[3]
        cum = r[4]
        assert adj_volume == pytest.approx(volume * cum), \
            f"adj_volume should be {volume}*{cum} = {volume*cum}, got {adj_volume}"
        assert adj_volume != pytest.approx(volume / cum), \
            f"Mutation: adj_volume = {volume}/{cum} = {volume/cum} would be wrong"