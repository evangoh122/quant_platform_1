"""
tests/db/test_xbrl_queries.py

Unit tests for db/xbrl_queries.asof_facts() using a fake spark session
that records the SQL and args for verification.
"""
import datetime
from unittest.mock import MagicMock

from db.xbrl_queries import asof_facts


class FakeSpark:
    """Records sql() calls for assertions."""

    def __init__(self):
        self.calls = []

    def sql(self, query, args=None):
        self.calls.append({"query": query, "args": args})
        return MagicMock()  # Return a mock DataFrame


class TestAsofFacts:

    def test_basic_call_records_sql_and_args(self):
        """asof_facts(spark, as_of) calls spark.sql with production SQL and bound args."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts)

        assert len(spark.calls) == 1
        call = spark.calls[0]
        assert "silver_sec_xbrl_facts" in call["query"]
        assert "information_available_ts" in call["query"]
        assert "quality_status" in call["query"]
        assert "ROW_NUMBER" in call["query"]
        assert call["args"]["as_of"] == ts
        assert call["args"]["limit"] == 1000

    def test_no_fstring_values_in_sql(self):
        """SQL must use :name placeholders, not f-string interpolated values."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts, ticker="AAPL")

        call = spark.calls[0]
        sql = call["query"]
        # Must NOT contain the literal ticker value in the SQL string
        assert "AAPL" not in sql, f"SQL must not contain literal values: {sql[:300]}"
        # Must contain the placeholder
        assert ":ticker" in sql

    def test_ticker_filter(self):
        """Ticker filter is appended when provided."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts, ticker="AAPL")

        call = spark.calls[0]
        assert "UPPER(ticker) = UPPER(:ticker)" in call["query"]
        assert call["args"]["ticker"] == "AAPL"

    def test_concept_filter(self):
        """Concept filter is appended when provided."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts, concept="Revenue")

        call = spark.calls[0]
        assert "UPPER(concept) = UPPER(:concept)" in call["query"]
        assert call["args"]["concept"] == "Revenue"

    def test_combined_filters(self):
        """Multiple filters are combined with AND."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts, ticker="MSFT", concept="NetIncome")

        call = spark.calls[0]
        sql = call["query"]
        assert "UPPER(ticker) = UPPER(:ticker)" in sql
        assert "UPPER(concept) = UPPER(:concept)" in sql
        assert "AND" in sql
        assert call["args"]["ticker"] == "MSFT"
        assert call["args"]["concept"] == "NetIncome"

    def test_limit_clamped(self):
        """Limit is clamped to 1–5000."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts, limit=99999)
        assert spark.calls[0]["args"]["limit"] == 5000

        spark = FakeSpark()
        asof_facts(spark, as_of=ts, limit=0)
        assert spark.calls[0]["args"]["limit"] == 1

    def test_default_as_of(self):
        """When as_of is None, a timestamp is generated (not None)."""
        spark = FakeSpark()

        asof_facts(spark)

        call = spark.calls[0]
        assert call["args"]["as_of"] is not None
        assert isinstance(call["args"]["as_of"], datetime.datetime)

    def test_returns_dataframe(self):
        """asof_facts returns whatever spark.sql returns (a DataFrame)."""
        spark = FakeSpark()
        mock_df = MagicMock()
        spark.sql = lambda q, args=None: mock_df

        result = asof_facts(spark, as_of=datetime.datetime(2025, 1, 1))
        assert result is mock_df

    def test_production_sql_is_used(self):
        """The SQL comes from silver/09_silver_sec_xbrl_facts_asof.sql, not a hardcoded copy."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts)

        sql = spark.calls[0]["query"]
        # Production SQL has these column names
        assert "f.entity_name" in sql or "entity_name" in sql
        assert "f.description" in sql or "description" in sql
        assert "f.value_raw" in sql or "value_raw" in sql
        # Production SQL uses ROW_NUMBER with the full partition key
        assert "COALESCE(period_start, '')" in sql
        assert "COALESCE(period_end, '')" in sql
        assert "COALESCE(instant, '')" in sql


# ---------------------------------------------------------------------------
# DuckDB-executable tests — prove the generated SQL actually runs
# ---------------------------------------------------------------------------

import re
from pathlib import Path

import duckdb
import pytest


_ASOF_SQL_PATH = Path(__file__).resolve().parents[2] / "silver" / "09_silver_sec_xbrl_facts_asof.sql"


def _shim_for_duckdb(sql: str) -> str:
    """Translate Databricks syntax to DuckDB-compatible SQL."""
    result = sql
    result = result.replace("{catalog}.{schema}.", "")
    result = result.replace("bootcamp_students.evangoh_capstone.", "")
    result = result.replace("current_timestamp()", "current_timestamp")
    return result


def _translate_spark_to_duckdb_params(sql: str) -> str:
    """Translate :name Spark placeholders to $name DuckDB named params."""
    return re.sub(r':(\w+)', r'$\1', sql)


def _build_asof_facts_sql(ticker=None, concept=None, limit=1000):
    """Replicate the query-building logic from asof_facts() for testing."""
    base_sql = _shim_for_duckdb(_ASOF_SQL_PATH.read_text(encoding="utf-8").strip())

    extra_filters = []
    if ticker is not None:
        extra_filters.append("UPPER(ticker) = UPPER(:ticker)")
    if concept is not None:
        extra_filters.append("UPPER(concept) = UPPER(:concept)")

    if extra_filters:
        where_clause = " AND ".join(extra_filters)
        sql = f"SELECT * FROM ({base_sql}) _asof_filtered WHERE {where_clause} LIMIT :limit"
    else:
        sql = f"{base_sql} LIMIT :limit"

    return _translate_spark_to_duckdb_params(sql)


def _setup_silver_table(conn):
    """Create and populate silver_sec_xbrl_facts for DuckDB asof tests."""
    conn.execute("""
        CREATE TABLE silver_sec_xbrl_facts (
            cik VARCHAR, entity_name VARCHAR, ticker VARCHAR, taxonomy VARCHAR,
            concept VARCHAR, label VARCHAR, description VARCHAR, unit VARCHAR,
            value_raw VARCHAR, value_decimal DOUBLE, period_start VARCHAR,
            period_end VARCHAR, instant VARCHAR, fiscal_year INTEGER,
            fiscal_period VARCHAR, form_type VARCHAR, accession_number VARCHAR,
            filed_date VARCHAR, frame VARCHAR, payload_hash VARCHAR,
            source_updated_at VARCHAR, first_observed_at TIMESTAMP,
            last_observed_at TIMESTAMP, information_available_ts TIMESTAMP,
            quality_status VARCHAR, processed_ts TIMESTAMP
        )
    """)

    rows = [
        # AAPL / REVENUE / 2025-Q1 — two filings, latest at 2025-02-01
        ("0000320193", "Apple Inc.", "AAPL", "us-gaap", "REVENUE", "Revenue",
         "Total revenue", "USD", "394B", 394328000000.0, "2024-09-29", "2024-12-28",
         None, 2025, "Q1", "10-K", "0001-01", "2025-01-15", None, None, None,
         datetime.datetime(2025, 1, 16, 8, 0, 0), datetime.datetime(2025, 2, 1, 0, 0, 0),
         datetime.datetime(2025, 1, 15, 10, 0, 0), "ok", None),
        ("0000320193", "Apple Inc.", "AAPL", "us-gaap", "REVENUE", "Revenue",
         "Total revenue", "USD", "395B", 395000000000.0, "2024-09-29", "2024-12-28",
         None, 2025, "Q1", "10-K", "0001-02", "2025-01-20", None, None, None,
         datetime.datetime(2025, 2, 1, 0, 0, 0), datetime.datetime(2025, 2, 1, 0, 0, 0),
         datetime.datetime(2025, 1, 20, 10, 0, 0), "ok", None),
        # AAPL / NETINCOME / 2025-Q1
        ("0000320193", "Apple Inc.", "AAPL", "us-gaap", "NETINCOME", "NetIncome",
         "Net income", "USD", "100B", 100000000000.0, "2024-09-29", "2024-12-28",
         None, 2025, "Q1", "10-K", "0001-01", "2025-01-15", None, None, None,
         datetime.datetime(2025, 1, 16, 8, 0, 0), datetime.datetime(2025, 1, 16, 8, 0, 0),
         datetime.datetime(2025, 1, 15, 10, 0, 0), "ok", None),
        # MSFT / REVENUE / 2025-Q2
        ("0000789019", "Microsoft Corp", "MSFT", "us-gaap", "REVENUE", "Revenue",
         "Total revenue", "USD", "200B", 200000000000.0, "2024-10-01", "2024-12-31",
         None, 2025, "Q2", "10-Q", "0002-01", "2025-03-15", None, None, None,
         datetime.datetime(2025, 3, 16, 8, 0, 0), datetime.datetime(2025, 3, 16, 8, 0, 0),
         datetime.datetime(2025, 3, 15, 14, 0, 0), "ok", None),
    ]

    for row in rows:
        conn.execute("""
            INSERT INTO silver_sec_xbrl_facts (
                cik, entity_name, ticker, taxonomy, concept, label, description,
                unit, value_raw, value_decimal, period_start, period_end, instant,
                fiscal_year, fiscal_period, form_type, accession_number, filed_date,
                frame, payload_hash, source_updated_at, first_observed_at,
                last_observed_at, information_available_ts, quality_status, processed_ts
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, list(row))


class TestAsofFactsDuckDB:
    """Execute the generated SQL in DuckDB to prove it is valid."""

    def test_no_filters(self):
        """asof_facts with no ticker/concept filters returns all rows."""
        conn = duckdb.connect()
        _setup_silver_table(conn)

        sql = _build_asof_facts_sql()
        results = conn.execute(sql, {"as_of": "2025-12-31 23:59:59", "limit": 1000}).fetchall()

        # 3 unique (cik,taxonomy,concept,unit,period) combos after PIT dedup
        # (two AAPL/REVENUE rows collapse to 1 via ROW_NUMBER)
        assert len(results) == 3, f"Expected 3 rows, got {len(results)}"
        conn.close()

    def test_ticker_filter(self):
        """Ticker filter restricts to matching ticker only."""
        conn = duckdb.connect()
        _setup_silver_table(conn)

        sql = _build_asof_facts_sql(ticker="AAPL")
        results = conn.execute(sql, {
            "as_of": "2025-12-31 23:59:59", "limit": 1000, "ticker": "AAPL"
        }).fetchall()

        # AAPL has Revenue + NetIncome = 2 distinct concepts
        assert len(results) == 2, f"Expected 2 AAPL rows, got {len(results)}"
        tickers = {r[2] for r in results}
        assert tickers == {"AAPL"}, f"Expected only AAPL, got {tickers}"
        conn.close()

    def test_concept_filter(self):
        """Concept filter restricts to matching concept only."""
        conn = duckdb.connect()
        _setup_silver_table(conn)

        sql = _build_asof_facts_sql(concept="Revenue")
        results = conn.execute(sql, {
            "as_of": "2025-12-31 23:59:59", "limit": 1000, "concept": "Revenue"
        }).fetchall()

        # Revenue for AAPL + MSFT = 2 rows
        assert len(results) == 2, f"Expected 2 Revenue rows, got {len(results)}"
        concepts = {r[4] for r in results}
        assert concepts == {"REVENUE"}, f"Expected only REVENUE, got {concepts}"
        conn.close()

    def test_both_filters(self):
        """Combined ticker + concept filter returns only matching rows."""
        conn = duckdb.connect()
        _setup_silver_table(conn)

        sql = _build_asof_facts_sql(ticker="AAPL", concept="Revenue")
        results = conn.execute(sql, {
            "as_of": "2025-12-31 23:59:59", "limit": 1000,
            "ticker": "AAPL", "concept": "Revenue"
        }).fetchall()

        assert len(results) == 1, f"Expected 1 row (AAPL Revenue), got {len(results)}"
        assert results[0][2] == "AAPL"
        assert results[0][4] == "REVENUE"
        # Latest filing (0001-02 at 2025-01-20) should win
        assert results[0][9] == 395000000000.0, f"Expected 395B, got {results[0][9]}"
        conn.close()

    def test_mutation_f_alias_breaks_filters(self):
        """Mutation: putting f. prefix back on filter columns causes DuckDB error."""
        conn = duckdb.connect()
        _setup_silver_table(conn)

        base_sql = _shim_for_duckdb(_ASOF_SQL_PATH.read_text(encoding="utf-8").strip())
        # Mutated: use f. prefix (the original bug)
        broken_sql = _translate_spark_to_duckdb_params(
            f"SELECT * FROM ({base_sql}) _asof_filtered "
            f"WHERE UPPER(f.ticker) = UPPER(:ticker) LIMIT :limit"
        )

        with pytest.raises(duckdb.BinderException, match="f"):
            conn.execute(broken_sql, {
                "as_of": "2025-12-31 23:59:59", "limit": 1000, "ticker": "AAPL"
            }).fetchall()
        conn.close()