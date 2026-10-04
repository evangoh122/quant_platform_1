"""Tests for the _ddl_extract helper module.

Verifies that extract_view_sql correctly parses the production DDL markdown
and returns the expected SQL blocks for each view and variant.
"""

import re
from pathlib import Path

import pytest

from tests.analytics_nl._ddl_extract import extract_view_sql, list_views, to_duckdb

_DDL_PATH = Path(__file__).parent.parent.parent / "docs" / "NL1_PROPOSED_SERVING_VIEWS.md"


class TestExtractViewSql:
    """extract_view_sql must parse the DDL document correctly."""

    def test_list_views_returns_all_five(self):
        views = list_views()
        assert len(views) == 5
        assert "serve_daily_prices_v1" in views
        assert "serve_daily_equity_metrics_v1" in views
        assert "serve_relative_performance_v1" in views
        assert "serve_options_metrics_v1" in views
        assert "serve_bounded_daily_bars_v1" in views

    def test_extract_relative_performance_single_block(self):
        sql = extract_view_sql("serve_relative_performance_v1")
        assert "CREATE VIEW" in sql
        assert "serve_relative_performance_v1" in sql
        assert "BOOL_OR" in sql
        assert "entity_cumulative" in sql
        assert "benchmark_cumulative" in sql

    def test_extract_equity_metrics_adjusted(self):
        sql = extract_view_sql("serve_daily_equity_metrics_v1", variant="adjusted")
        assert "silver_ohlcv_day_adjusted" in sql
        assert "return_1d" in sql
        assert "STDDEV_SAMP" in sql

    def test_extract_equity_metrics_fallback(self):
        sql = extract_view_sql("serve_daily_equity_metrics_v1", variant="fallback")
        assert "bronze_ohlcv_day" not in sql  # fallback reads from serve_daily_prices_v1
        assert "LAG(close)" in sql
        assert "return_1d" in sql

    def test_extract_bounded_bars_adjusted(self):
        sql = extract_view_sql("serve_bounded_daily_bars_v1", variant="adjusted")
        assert "silver_ohlcv_day_adjusted" in sql
        assert "suspected_split" in sql
        assert "FALSE AS suspected_split" in sql

    def test_extract_bounded_bars_fallback(self):
        sql = extract_view_sql("serve_bounded_daily_bars_v1", variant="fallback")
        assert "bronze_ohlcv_day" in sql
        assert "suspected_split" in sql
        assert "LAG(close)" in sql

    def test_extract_options_metrics(self):
        sql = extract_view_sql("serve_options_metrics_v1")
        assert "gold_options_features" in sql
        assert "iv_atm" in sql

    def test_extract_invalid_view_raises(self):
        with pytest.raises(ValueError, match="not found"):
            extract_view_sql("nonexistent_view_v1")

    def test_extract_invalid_variant_raises(self):
        with pytest.raises(ValueError):
            extract_view_sql("serve_daily_equity_metrics_v1", variant="invalid_mode")

    def test_extract_with_doc_path_override(self, tmp_path):
        """doc_path parameter allows mutation testing with a copy."""
        fake_doc = tmp_path / "fake.md"
        fake_doc.write_text(
            "## serve_test_v1\n\n```sql\nSELECT 1;\n```\n"
        )
        sql = extract_view_sql("serve_test_v1", doc_path=fake_doc)
        assert sql == "SELECT 1;"


class TestToDuckdb:
    """to_duckdb must adapt Databricks SQL for DuckDB execution."""

    def test_named_parameter_substitution(self):
        sql = "SELECT * FROM t WHERE event_date >= :start_date AND x = :benchmark"
        result = to_duckdb(sql, params={":start_date": "'2024-01-01'", ":benchmark": "'SPY'"})
        assert ":start_date" not in result
        assert ":benchmark" not in result
        assert "'2024-01-01'" in result
        assert "'SPY'" in result

    def test_catalog_prefix_stripping(self):
        sql = "SELECT * FROM ${catalog}.${schema}.my_table"
        result = to_duckdb(sql)
        assert "${catalog}" not in result
        assert "${schema}" not in result
        assert "my_table" in result

    def test_to_utc_timestamp_conversion(self):
        sql = "WHERE to_utc_timestamp(concat(event_date, ' 16:30:00'), 'America/New_York') <= :as_of"
        result = to_duckdb(sql, params={":as_of": "'2025-01-01'"})
        assert "to_utc_timestamp" not in result
        assert "INTERVAL" in result
        assert "16 hours" in result

    def test_no_params_passes_through(self):
        sql = "SELECT 1"
        result = to_duckdb(sql)
        assert result == sql

    def test_relative_performance_full_extraction(self):
        """Full round-trip: extract, convert, verify structure."""
        sql = extract_view_sql("serve_relative_performance_v1")
        duckdb_sql = to_duckdb(sql, params={
            ":benchmark": "'SPY'",
            ":start_date": "'2024-01-01'",
            ":as_of": "'2025-01-01'",
        })
        # No Databricks artifacts remain
        assert "${catalog}" not in duckdb_sql
        assert ":benchmark" not in duckdb_sql
        assert ":start_date" not in duckdb_sql
        assert ":as_of" not in duckdb_sql
        # Production SQL structure preserved
        assert "BOOL_OR" in duckdb_sql
        assert "COALESCE" in duckdb_sql
        assert "GREATEST" in duckdb_sql

    def test_bounded_bars_fallback_extraction(self):
        """Bounded bars fallback: extract, convert, verify to_utc_timestamp is gone."""
        sql = extract_view_sql("serve_bounded_daily_bars_v1", variant="fallback")
        duckdb_sql = to_duckdb(sql, params={":as_of": "'2025-01-01'"})
        assert "to_utc_timestamp" not in duckdb_sql
        assert "INTERVAL" in duckdb_sql
        assert "suspected_split" in duckdb_sql