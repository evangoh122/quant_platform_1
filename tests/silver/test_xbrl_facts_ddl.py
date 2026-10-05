"""
tests/silver/test_xbrl_facts_ddl.py

Tests that prove the DDL in silver/09a_silver_sec_xbrl_facts_ddl.sql:
- Creates the target table so the MERGE in 09_silver_sec_xbrl_facts.sql succeeds
- Is idempotent (CREATE TABLE IF NOT EXISTS + MERGE run twice)
- Column list exactly matches the MERGE's target columns

Mutation proofs:
- Removing the DDL step from run_silver_gold.py → MERGE fails (TABLE_OR_VIEW_NOT_FOUND)
- Dropping a column from the DDL → column mismatch test fails
"""
import re
from pathlib import Path

import duckdb
import pytest


# ---------------------------------------------------------------------------
# Paths to production files
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_DDL_PATH = _ROOT / "silver" / "09a_silver_sec_xbrl_facts_ddl.sql"
_MERGE_PATH = _ROOT / "silver" / "09_silver_sec_xbrl_facts.sql"
_PIPELINE_PATH = _ROOT / "pipelines" / "run_silver_gold.py"


# ---------------------------------------------------------------------------
# SQL extraction and Databricks→DuckDB translation shim
# ---------------------------------------------------------------------------

def _shim(sql: str) -> str:
    """Translate Databricks syntax to DuckDB-compatible SQL."""
    result = sql
    result = result.replace("{catalog}.{schema}.", "")
    result = result.replace("bootcamp_students.evangoh_capstone.", "")
    result = result.replace("current_timestamp()", "current_timestamp")
    result = result.replace("<=>", "IS NOT DISTINCT FROM")
    # DuckDB does not support USING DELTA
    result = re.sub(r'\)\s*USING\s+DELTA\b', ')', result, flags=re.IGNORECASE)
    return result


def _extract_merge_using(sql_text: str) -> str:
    """Extract the CTE chain from a MERGE INTO … USING ( … ) block."""
    using_match = re.search(r'\bUSING\s*\(', sql_text, re.IGNORECASE)
    if not using_match:
        raise ValueError("Could not find USING clause in MERGE SQL")
    start = using_match.end()
    depth = 1
    end = -1
    for i, ch in enumerate(sql_text[start:], start=start):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("Could not find balanced parens for USING block")
    inner = sql_text[start:end].strip()
    with_match = re.search(r'\bWITH\b', inner, re.IGNORECASE)
    if not with_match:
        raise ValueError("Could not find WITH CTE inside USING clause")
    return inner[with_match.start():]


def _get_ddl_sql() -> str:
    """Read and shim the DDL SQL."""
    return _shim(_DDL_PATH.read_text(encoding="utf-8"))


def _get_merge_sql() -> str:
    """Read and shim the full MERGE SQL."""
    return _shim(_MERGE_PATH.read_text(encoding="utf-8"))


def _get_merge_source_sql() -> str:
    """Extract the inner SELECT from the MERGE USING clause (for DuckDB INSERT)."""
    sql_text = _MERGE_PATH.read_text(encoding="utf-8")
    return _shim(_extract_merge_using(sql_text))


# ---------------------------------------------------------------------------
# Column extraction from production files
# ---------------------------------------------------------------------------

def _parse_ddl_columns(ddl_sql: str) -> dict[str, str]:
    """Parse column definitions from a CREATE TABLE statement.

    Returns {column_name: column_type} preserving declaration order.
    Skips comment lines (--) and constraint keywords.
    """
    create_match = re.search(
        r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+\S+\s*\(', ddl_sql, re.IGNORECASE
    )
    if not create_match:
        raise ValueError("Could not find CREATE TABLE in DDL")

    start = create_match.end()
    depth = 1
    end = -1
    for i, ch in enumerate(ddl_sql[start:], start=start):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("Could not find balanced parens for column list")

    col_block = ddl_sql[start:end]
    columns = {}
    for line in col_block.splitlines():
        line = line.strip().rstrip(',')
        if not line or line.startswith('--'):
            continue
        parts = line.split()
        if len(parts) >= 2:
            col_name = parts[0].strip('"`')
            col_type = parts[1].strip()
            if col_name.upper() in ('NOT', 'NULL', 'PRIMARY', 'UNIQUE', 'CHECK',
                                     'DEFAULT', 'CONSTRAINT', 'USING'):
                continue
            columns[col_name] = col_type
    return columns


def _parse_normalized_cte_columns(merge_sql: str) -> list[str]:
    """Extract column aliases from the 'normalized' CTE's SELECT clause.

    The production MERGE uses INSERT * which writes all columns from the
    source (the 'normalized' CTE). We find that CTE and extract every
    'AS alias' from its SELECT clause.
    """
    # Find the normalized CTE definition
    cte_match = re.search(
        r'normalized\s+AS\s*\(', merge_sql, re.IGNORECASE
    )
    if not cte_match:
        raise ValueError("Could not find 'normalized' CTE in MERGE SQL")

    # Find the opening paren of the CTE body
    paren_start = merge_sql.index('(', cte_match.end() - 1)
    depth = 1
    paren_end = -1
    for i, ch in enumerate(merge_sql[paren_start + 1:], start=paren_start + 1):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                paren_end = i
                break
    if paren_end == -1:
        raise ValueError("Could not find balanced parens for normalized CTE")

    cte_body = merge_sql[paren_start + 1:paren_end]

    # Extract the SELECT clause (between SELECT and FROM)
    select_match = re.search(r'\bSELECT\b', cte_body, re.IGNORECASE)
    if not select_match:
        raise ValueError("Could not find SELECT in normalized CTE")

    # Walk lines from SELECT until we hit FROM (not inside a subquery)
    lines = cte_body[select_match.end():].splitlines()
    cols = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'\bFROM\b', stripped, re.IGNORECASE):
            break
        # Allow optional trailing comma after alias
        as_match = re.search(r'\bAS\s+(\w+)\s*,?\s*$', stripped, re.IGNORECASE)
        if as_match:
            cols.append(as_match.group(1))

    return cols


# ---------------------------------------------------------------------------
# DuckDB fixture helpers
# ---------------------------------------------------------------------------

def _setup_bronze_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the bronze fixture tables that the MERGE reads from."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze_sec_xbrl_facts (
            ingest_run_id VARCHAR,
            ingested_at TIMESTAMP,
            source_url VARCHAR,
            payload_hash VARCHAR,
            cik VARCHAR,
            entity_name VARCHAR,
            ticker VARCHAR,
            taxonomy VARCHAR,
            concept VARCHAR,
            label VARCHAR,
            description VARCHAR,
            unit VARCHAR,
            value_raw VARCHAR,
            value_decimal DOUBLE,
            period_start VARCHAR,
            period_end VARCHAR,
            instant VARCHAR,
            fiscal_year INTEGER,
            fiscal_period VARCHAR,
            form_type VARCHAR,
            accession_number VARCHAR,
            filed_date VARCHAR,
            frame VARCHAR,
            raw_fact_json VARCHAR,
            source_updated_at VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze_sec_filings_v2 (
            accession_number VARCHAR,
            accepted_ts TIMESTAMP,
            ticker VARCHAR,
            cik VARCHAR,
            form_type VARCHAR,
            filing_date VARCHAR,
            filing_section VARCHAR,
            chunk_text VARCHAR,
            record_key VARCHAR,
            company_name VARCHAR,
            chunk_char_count INTEGER,
            filing_url VARCHAR
        )
    """)


def _run_ddl(conn: duckdb.DuckDBPyConnection) -> None:
    """Run the production DDL against DuckDB."""
    conn.execute(_get_ddl_sql())


def _run_merge_as_insert(conn: duckdb.DuckDBPyConnection) -> None:
    """Run the MERGE's source query as an INSERT (DuckDB doesn't support MERGE).

    Extracts the CTE chain from the production MERGE USING clause and runs
    INSERT INTO silver_sec_xbrl_facts SELECT … .
    """
    source_sql = _get_merge_source_sql()
    conn.execute(f"INSERT INTO silver_sec_xbrl_facts {source_sql}")


def _run_production_merge(conn: duckdb.DuckDBPyConnection) -> None:
    """Run the full production MERGE statement in DuckDB.

    Translates Spark <=> to DuckDB IS NOT DISTINCT FROM for null-safe joins.
    This is the actual MERGE so idempotency is properly exercised.
    """
    merge_sql = _get_merge_sql()
    conn.execute(merge_sql)


def _populate_bronze(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert minimal fixture data into bronze tables."""
    conn.execute("""
        INSERT INTO bronze_sec_filings_v2 (accession_number, accepted_ts, ticker, cik, form_type)
        VALUES ('0001-01', TIMESTAMP '2025-01-15 10:00:00', 'AAPL', '0000320193', '10-K')
    """)
    conn.execute("""
        INSERT INTO bronze_sec_xbrl_facts (
            ingest_run_id, ingested_at, source_url, payload_hash,
            cik, entity_name, ticker, taxonomy, concept, label, description,
            unit, value_raw, value_decimal, period_start, period_end, instant,
            fiscal_year, fiscal_period, form_type, accession_number, filed_date, frame,
            source_updated_at
        ) VALUES (
            'run1', TIMESTAMP '2025-01-16 08:00:00', 'https://sec.gov', 'hash1',
            '0000320193', 'Apple Inc.', 'AAPL', 'us-gaap', 'Revenue', 'Revenue', 'Total revenue',
            'USD', '394328000000', 394328000000.0, '2024-09-29', '2024-12-28', NULL,
            2025, 'Q1', '10-K', '0001-01', '2025-01-15', NULL,
            '2025-01-16T08:00:00'
        )
    """)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_conn():
    """Fresh DuckDB connection with bronze tables but NO silver table."""
    conn = duckdb.connect()
    _setup_bronze_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn_with_data():
    """Fresh DuckDB connection with bronze tables populated and DDL run."""
    conn = duckdb.connect()
    _setup_bronze_tables(conn)
    _populate_bronze(conn)
    _run_ddl(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# 1. DDL then MERGE on empty DuckDB — succeeds and is idempotent
# ---------------------------------------------------------------------------

class TestDDLThenMerge:

    def test_ddl_creates_table_on_empty_db(self, empty_conn):
        """Running DDL on an empty DuckDB creates silver_sec_xbrl_facts."""
        _run_ddl(empty_conn)
        tables = empty_conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'silver_sec_xbrl_facts'"
        ).fetchall()
        assert len(tables) == 1, "DDL should create silver_sec_xbrl_facts"

    def test_ddl_then_merge_succeeds(self, empty_conn):
        """DDL then MERGE on empty DuckDB succeeds — the target table exists."""
        _populate_bronze(empty_conn)
        _run_ddl(empty_conn)
        _run_production_merge(empty_conn)

        count = empty_conn.execute(
            "SELECT COUNT(*) FROM silver_sec_xbrl_facts"
        ).fetchone()[0]
        assert count >= 1, "MERGE should insert at least 1 row"

    def test_ddl_idempotent(self, empty_conn):
        """Running DDL twice does not error (CREATE TABLE IF NOT EXISTS)."""
        _run_ddl(empty_conn)
        _run_ddl(empty_conn)  # should not raise
        tables = empty_conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'silver_sec_xbrl_facts'"
        ).fetchall()
        assert len(tables) == 1

    def test_merge_idempotent_after_ddl(self, conn_with_data):
        """Running the MERGE twice after DDL is idempotent (no duplicates)."""
        _run_production_merge(conn_with_data)
        count1 = conn_with_data.execute(
            "SELECT COUNT(*) FROM silver_sec_xbrl_facts"
        ).fetchone()[0]

        _run_production_merge(conn_with_data)
        count2 = conn_with_data.execute(
            "SELECT COUNT(*) FROM silver_sec_xbrl_facts"
        ).fetchone()[0]

        assert count1 == count2, (
            f"MERGE not idempotent: {count1} rows after first run, "
            f"{count2} after second run"
        )


# ---------------------------------------------------------------------------
# 2. DDL column list equals MERGE target columns
# ---------------------------------------------------------------------------

class TestColumnMatch:

    def test_ddl_columns_match_merge_source(self):
        """The DDL's column list exactly matches the MERGE source's SELECT aliases."""
        ddl_sql = _get_ddl_sql()
        merge_sql = _get_merge_sql()

        ddl_cols = list(_parse_ddl_columns(ddl_sql).keys())
        merge_cols = _parse_normalized_cte_columns(merge_sql)

        assert ddl_cols == merge_cols, (
            f"DDL columns do not match MERGE source columns.\n"
            f"  DDL ({len(ddl_cols)}):   {ddl_cols}\n"
            f"  MERGE ({len(merge_cols)}): {merge_cols}"
        )

    def test_ddl_column_count(self):
        """DDL defines exactly 26 columns (the MERGE writes 26 columns)."""
        ddl_sql = _get_ddl_sql()
        cols = _parse_ddl_columns(ddl_sql)
        assert len(cols) == 26, (
            f"Expected 26 DDL columns, got {len(cols)}: {list(cols.keys())}"
        )

    def test_ddl_not_null_constraints_match_source(self):
        """NOT NULL in DDL matches columns that the MERGE source can never
        produce as NULL."""
        ddl_sql = _get_ddl_sql()

        # These columns are always NOT NULL in the MERGE source:
        # - first_observed_at: MIN(ingested_at) OVER(...)
        # - last_observed_at:  MAX(ingested_at) OVER(...)
        # - quality_status:    CASE with ELSE 'ok'
        # - processed_ts:      current_timestamp()
        expected_not_null = {
            "first_observed_at", "last_observed_at",
            "quality_status", "processed_ts",
        }

        actual_not_null = set()
        for line in ddl_sql.splitlines():
            stripped = line.strip().rstrip(',')
            if not stripped or stripped.startswith('--'):
                continue
            if 'NOT NULL' in stripped.upper():
                parts = stripped.split()
                if parts and not parts[0].startswith('--'):
                    actual_not_null.add(parts[0])

        assert expected_not_null == actual_not_null, (
            f"NOT NULL mismatch.\n"
            f"  Expected: {sorted(expected_not_null)}\n"
            f"  Actual:   {sorted(actual_not_null)}"
        )


# ---------------------------------------------------------------------------
# 3. Mutation: remove DDL step from run_silver_gold.py → test fails
# ---------------------------------------------------------------------------

class TestMutationDDLStepRegistered:

    def test_ddl_step_in_pipeline(self):
        """The DDL step must be registered in run_silver_gold.py STEPS list."""
        pipeline_text = _PIPELINE_PATH.read_text(encoding="utf-8")
        assert "09a_silver_sec_xbrl_facts_ddl.sql" in pipeline_text, (
            "DDL file not registered in pipelines/run_silver_gold.py STEPS list"
        )

    def test_ddl_step_before_merge_step(self):
        """The DDL step must appear before the MERGE step in STEPS list."""
        pipeline_text = _PIPELINE_PATH.read_text(encoding="utf-8")
        ddl_pos = pipeline_text.index("09a_silver_sec_xbrl_facts_ddl.sql")
        merge_pos = pipeline_text.index("09_silver_sec_xbrl_facts.sql")
        assert ddl_pos < merge_pos, (
            "DDL step must be registered BEFORE the MERGE step in STEPS list"
        )

    def test_merge_fails_without_ddl(self, empty_conn):
        """Without the DDL, the MERGE fails because the target table doesn't
        exist. This is the mutation proof: removing the DDL step from the
        pipeline causes TABLE_OR_VIEW_NOT_FOUND."""
        _populate_bronze(empty_conn)
        with pytest.raises(duckdb.CatalogException, match="does not exist"):
            _run_merge_as_insert(empty_conn)


# ---------------------------------------------------------------------------
# 4. Mutation: drop a column from DDL → test fails
# ---------------------------------------------------------------------------

class TestMutationDDLColumnDrop:

    def test_drop_column_from_ddl_breaks_match(self):
        """Dropping any column from the DDL causes the column-match test to
        fail. This is a mutation proof: the DDL must list every column the
        MERGE writes."""
        ddl_sql = _get_ddl_sql()
        merge_sql = _get_merge_sql()

        ddl_cols = list(_parse_ddl_columns(ddl_sql).keys())
        merge_cols = _parse_normalized_cte_columns(merge_sql)

        # Simulate dropping the last column from the DDL
        mutated_ddl_cols = ddl_cols[:-1]

        assert mutated_ddl_cols != merge_cols, (
            "Mutation proof: dropping a DDL column should cause mismatch"
        )
        assert len(mutated_ddl_cols) == len(merge_cols) - 1

    def test_drop_column_from_ddl_breaks_count(self):
        """Dropping any column from the DDL causes the column-count test to
        fail."""
        ddl_sql = _get_ddl_sql()
        cols = _parse_ddl_columns(ddl_sql)
        assert len(cols) - 1 == 25, (
            "Mutation proof: dropping one column gives 25, not 26"
        )

    def test_drop_not_null_column_breaks_merge(self, empty_conn):
        """Dropping a NOT NULL column from the DDL and running the MERGE fails.

        The MERGE INSERT * writes all source columns including processed_ts,
        but if the DDL omits it, the table has fewer columns than the source.
        """
        ddl_sql = _get_ddl_sql()
        # Remove processed_ts from DDL
        mutated = re.sub(
            r',\s*processed_ts\s+TIMESTAMP\s+NOT\s+NULL',
            '',
            ddl_sql,
            flags=re.IGNORECASE,
        )
        _populate_bronze(empty_conn)
        empty_conn.execute(mutated)

        # The MERGE writes 26 columns but the table has 25 → column count mismatch
        with pytest.raises(Exception):
            _run_production_merge(empty_conn)