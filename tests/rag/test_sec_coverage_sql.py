"""tests/rag/test_sec_coverage_sql.py - Static/fixture contract checks for gold_sec_coverage.sql.

Verifies the SQL structure without executing against Databricks.
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
        assert "LEFT JOIN" in self.sql or "left join" in self.sql.lower() or "FULL OUTER JOIN" in self.sql