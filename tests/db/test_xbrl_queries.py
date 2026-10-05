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
        assert "UPPER(f.ticker) = UPPER(:ticker)" in call["query"]
        assert call["args"]["ticker"] == "AAPL"

    def test_concept_filter(self):
        """Concept filter is appended when provided."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts, concept="Revenue")

        call = spark.calls[0]
        assert "UPPER(f.concept) = UPPER(:concept)" in call["query"]
        assert call["args"]["concept"] == "Revenue"

    def test_combined_filters(self):
        """Multiple filters are combined with AND."""
        spark = FakeSpark()
        ts = datetime.datetime(2025, 6, 15, 12, 0, 0)

        asof_facts(spark, as_of=ts, ticker="MSFT", concept="NetIncome")

        call = spark.calls[0]
        sql = call["query"]
        assert "UPPER(f.ticker) = UPPER(:ticker)" in sql
        assert "UPPER(f.concept) = UPPER(:concept)" in sql
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