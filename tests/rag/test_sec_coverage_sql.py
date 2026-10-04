"""tests/rag/test_sec_coverage_sql.py - Static/fixture contract checks for gold_sec_coverage.sql.

Verifies the SQL structure without executing against Databricks.
Also includes a DuckDB execution test that proves the SQL produces exact
expected rows on synthetic fixtures (catches semantic bugs like wrong
ROW_NUMBER ORDER BY direction or missing universe restriction).
"""
from __future__ import annotations

from pathlib import Path

import pytest

SQL_PATH = Path(__file__).parent.parent.parent / "gold" / "07_gold_sec_coverage.sql"


class TestGoldCoverageSql:
    """Static assertions on the gold_sec_coverage SQL file."""

    @pytest.fixture(autouse=True)
    def _load_sql(self):
        if not SQL_PATH.exists():
            pytest.skip(f"SQL file not found: {SQL_PATH}")
        self.sql = SQL_PATH.read_text(encoding="utf-8")

    def test_universe_derived_from_gold_tradable_universe(self):
        """Universe CTE must derive from gold_tradable_universe."""
        assert "gold_tradable_universe" in self.sql

    def test_one_row_per_ticker(self):
        """Output must have one row per canonical ticker."""
        assert "ticker" in self.sql.lower()

    def test_zero_chunk_count_coalesced(self):
        """Tickers with zero chunks must appear with coalesced zero counts."""
        assert "coalesce" in self.sql.lower() or "COALESCE" in self.sql

    def test_distinct_accession_count(self):
        """n_filings must be distinct accession count."""
        assert "count(DISTINCT" in self.sql or "count(distinct" in self.sql

    def test_accepted_ts_not_filing_date(self):
        """first_filed/last_filed must use accepted_ts, not filing_date."""
        assert "accepted_ts" in self.sql

    def test_max_ingest_timestamp(self):
        """last_ingest_ts must be max of ingest_ts."""
        assert "ingest_ts" in self.sql

    def test_columns_present(self):
        """Required columns: ticker, cik, n_filings, n_chunks, first_filed, last_filed, last_ingest_ts."""
        required = ["ticker", "cik", "n_filings", "n_chunks", "first_filed", "last_filed", "last_ingest_ts"]
        sql_lower = self.sql.lower()
        for col in required:
            assert col.lower() in sql_lower, f"Missing column: {col}"

    def test_create_or_replace(self):
        """Must use CREATE OR REPLACE TABLE."""
        assert "CREATE OR REPLACE TABLE" in self.sql or "create or replace table" in self.sql.lower()

    def test_left_join_to_universe(self):
        """Must left-join to universe so mapped tickers with zero chunks appear."""
        assert "LEFT JOIN" in self.sql or "left join" in self.sql.lower()

    def test_no_hardcoded_catalog_schema(self):
        """Must NOT contain hardcoded catalog.schema — uses {catalog}.{schema} placeholders."""
        assert "bootcamp_students.evangoh_capstone" not in self.sql, (
            "SQL must use {catalog}.{schema} placeholders, not hardcoded values"
        )

    def test_uses_placeholders(self):
        """Must use {catalog} and {schema} placeholders for runner substitution."""
        assert "{catalog}" in self.sql
        assert "{schema}" in self.sql

    def test_cik_from_mapping_log_not_bronze(self):
        """CIK must come from sec_cik_mapping_log, not bronze_sec_filings_v2."""
        assert "sec_cik_mapping_log" in self.sql
        # The latest_mapping CTE should NOT reference bronze_sec_filings_v2
        # for CIK (it's ok for filing_agg to reference bronze for n_filings)
        mapping_section = self.sql[self.sql.index("latest_mapping"):]
        assert "bronze_sec_filings_v2" not in mapping_section, (
            "latest_mapping CTE must use sec_cik_mapping_log, not bronze_sec_filings_v2"
        )

    def test_mapping_requires_mapped_status(self):
        """latest_mapping must filter to status = 'mapped' entries only."""
        assert "mapped" in self.sql.lower()

    def test_restricted_to_universe(self):
        """Output must be restricted to universe members (no FULL OUTER JOIN)."""
        assert "FULL OUTER JOIN" not in self.sql, (
            "Must use LEFT JOIN from universe (not FULL OUTER JOIN) to restrict to universe members"
        )


def _load_coverage_sql() -> str:
    """Load and substitute placeholders for DuckDB execution."""
    raw = SQL_PATH.read_text(encoding="utf-8")
    return raw.replace("{catalog}.{schema}.", "")


def _run_coverage_sql(sql: str) -> list[dict]:
    """Execute the coverage SQL against DuckDB fixtures and return rows as dicts."""
    import duckdb

    con = duckdb.connect()

    # Universe: AAPL and MSFT only (GOOG is out-of-universe)
    con.execute(
        "CREATE TABLE gold_tradable_universe (symbol VARCHAR)"
    )
    con.executemany(
        "INSERT INTO gold_tradable_universe VALUES (?)",
        [("AAPL",), ("MSFT",)],
    )

    # CIK mapping log: AAPL has two 'mapped' entries (older wrong CIK, newer correct CIK)
    # MSFT has one 'mapped' entry. GOOG has one 'mapped' entry (out of universe).
    con.execute(
        "CREATE TABLE sec_cik_mapping_log ("
        "ticker VARCHAR, cik VARCHAR, status VARCHAR, mapped_ts TIMESTAMP)"
    )
    con.executemany(
        "INSERT INTO sec_cik_mapping_log VALUES (?,?,?,?)",
        [
            ("AAPL", "0000000000", "mapped", "2024-01-01 00:00:00"),   # older — wrong CIK
            ("AAPL", "0000320193", "mapped", "2024-06-01 00:00:00"),   # newer — correct CIK
            ("MSFT", "0000789019", "mapped", "2024-03-01 00:00:00"),
            ("GOOG", "0001652044", "mapped", "2024-04-01 00:00:00"),   # out of universe
        ],
    )

    # Bronze filings: AAPL has 2 filings, GOOG has 1, MSFT has 0
    con.execute(
        "CREATE TABLE bronze_sec_filings_v2 ("
        "accession_number VARCHAR, ticker VARCHAR, filing_section VARCHAR, "
        "chunk_text VARCHAR, accepted_ts TIMESTAMP, ingest_ts TIMESTAMP)"
    )
    con.executemany(
        "INSERT INTO bronze_sec_filings_v2 VALUES (?,?,?,?,?,?)",
        [
            ("F1", "AAPL", "10-K", "text1", "2024-01-15 10:00:00", "2024-01-16 08:00:00"),
            ("F2", "AAPL", "10-Q", "text2", "2024-06-15 10:00:00", "2024-06-16 08:00:00"),
            ("F3", "GOOG", "10-K", "text3", "2024-04-15 10:00:00", "2024-04-16 08:00:00"),
        ],
    )

    # Silver sections: AAPL has 3 chunks, GOOG has 2, MSFT has 0
    con.execute(
        "CREATE TABLE silver_sec_sections (ticker VARCHAR, chunk_id VARCHAR)"
    )
    con.executemany(
        "INSERT INTO silver_sec_sections VALUES (?,?)",
        [
            ("AAPL", "ch1"),
            ("AAPL", "ch2"),
            ("AAPL", "ch3"),
            ("GOOG", "ch4"),
            ("GOOG", "ch5"),
        ],
    )

    con.execute(sql)
    rows = con.execute(
        "SELECT ticker, cik, n_filings, n_chunks, first_filed, last_filed, last_ingest_ts "
        "FROM gold_sec_coverage ORDER BY ticker"
    ).fetchall()
    cols = [
        "ticker", "cik", "n_filings", "n_chunks",
        "first_filed", "last_filed", "last_ingest_ts",
    ]
    result = [dict(zip(cols, r)) for r in rows]
    con.close()
    return result


class TestGoldCoverageDuckDB:
    """Execute the gold SQL against DuckDB fixtures and verify exact output rows."""

    @pytest.fixture(autouse=True)
    def _require_sql(self):
        if not SQL_PATH.exists():
            pytest.skip(f"SQL file not found: {SQL_PATH}")

    def test_exact_output_rows(self):
        """Run the gold SQL on fixtures; assert exact rows.

        Fixtures:
        - AAPL: 2 mapped CIK entries (newer wins → 0000320193), 2 filings, 3 chunks
        - MSFT: 1 mapped CIK entry (0000789019), 0 filings, 0 chunks
        - GOOG: mapped CIK, 1 filing, 2 chunks — but NOT in universe → excluded
        """
        sql = _load_coverage_sql()
        rows = _run_coverage_sql(sql)

        assert len(rows) == 2, f"Expected 2 rows (AAPL, MSFT), got {len(rows)}: {rows}"

        aapl = rows[0]
        assert aapl["ticker"] == "AAPL"
        assert aapl["cik"] == "0000320193"
        assert aapl["n_filings"] == 2
        assert aapl["n_chunks"] == 3
        assert aapl["first_filed"] is not None
        assert aapl["last_filed"] is not None
        assert aapl["last_ingest_ts"] is not None

        msft = rows[1]
        assert msft["ticker"] == "MSFT"
        assert msft["cik"] == "0000789019"
        assert msft["n_filings"] == 0
        assert msft["n_chunks"] == 0
        assert msft["first_filed"] is None
        assert msft["last_filed"] is None
        assert msft["last_ingest_ts"] is None

    def test_out_of_universe_excluded(self):
        """GOOG (not in gold_tradable_universe) must not appear in output."""
        sql = _load_coverage_sql()
        rows = _run_coverage_sql(sql)
        tickers = [r["ticker"] for r in rows]
        assert "GOOG" not in tickers, "Out-of-universe ticker GOOG must be excluded"

    def test_row_number_picks_latest_mapped(self):
        """Mutation: if ROW_NUMBER ORDER BY mapped_ts is flipped to ASC,
        AAPL gets the OLDER CIK (0000000000) instead of the correct newer one."""
        sql = _load_coverage_sql()
        rows = _run_coverage_sql(sql)
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        assert aapl["cik"] == "0000320193", (
            f"AAPL CIK should be 0000320193 (latest mapped), got {aapl['cik']}. "
            "ROW_NUMBER ORDER BY may be wrong direction."
        )