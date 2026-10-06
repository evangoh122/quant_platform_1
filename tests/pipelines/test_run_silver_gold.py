"""tests/pipelines/test_run_silver_gold.py

Tests for ensure_day_adjusted_columns in pipelines/run_silver_gold.py.

Uses a fake Spark session to verify idempotent column-addition behavior:
- Column missing -> one ALTER issued
- Column present -> no ALTER
- Table unreadable -> no ALTER, no raise
"""
from __future__ import annotations

import pytest


class _FakeTable:
    """Minimal table stub with a .columns attribute."""

    def __init__(self, columns: list[str]):
        self.columns = columns


class _FakeSpark:
    """Fake Spark session that records sql() calls and supports table()."""

    def __init__(self, columns: list[str] | None = None, table_error: Exception | None = None):
        self._columns = columns
        self._table_error = table_error
        self.sql_calls: list[str] = []

    def table(self, name: str):
        if self._table_error is not None:
            raise self._table_error
        return _FakeTable(self._columns or [])

    def sql(self, query: str):
        self.sql_calls.append(query)


# Patch FQN so the test doesn't depend on env vars.
@pytest.fixture(autouse=True)
def _patch_fqn(monkeypatch):
    import pipelines.run_silver_gold as mod
    monkeypatch.setattr(mod, "FQN", "test_cat.test_schema")


class TestEnsureDayAdjustedColumns:

    def test_column_missing_issues_alter(self):
        """vwap_source missing -> one ALTER TABLE ADD COLUMNS issued."""
        from pipelines.run_silver_gold import ensure_day_adjusted_columns

        spark = _FakeSpark(columns=["symbol", "event_date", "close"])
        ensure_day_adjusted_columns(spark)

        assert len(spark.sql_calls) == 1
        assert "ALTER TABLE" in spark.sql_calls[0]
        assert "vwap_source" in spark.sql_calls[0]
        assert "STRING" in spark.sql_calls[0]

    def test_column_present_no_alter(self):
        """vwap_source already present -> no ALTER issued."""
        from pipelines.run_silver_gold import ensure_day_adjusted_columns

        spark = _FakeSpark(columns=["symbol", "event_date", "vwap_source"])
        ensure_day_adjusted_columns(spark)

        assert len(spark.sql_calls) == 0

    def test_table_unreadable_no_raise(self):
        """Table not readable -> skip silently, no raise, no ALTER."""
        from pipelines.run_silver_gold import ensure_day_adjusted_columns

        spark = _FakeSpark(table_error=Exception("Table not found"))
        ensure_day_adjusted_columns(spark)

        assert len(spark.sql_calls) == 0

    def test_mutation_always_alter_fails_present_test(self):
        """Mutation: if ensure_day_adjusted_columns always issues ALTER,
        the 'present' test would fail because sql_calls would be non-empty."""
        from pipelines.run_silver_gold import ensure_day_adjusted_columns

        spark = _FakeSpark(columns=["symbol", "event_date", "vwap_source"])
        ensure_day_adjusted_columns(spark)

        # This assertion proves the mutation (always ALTER) would fail
        assert len(spark.sql_calls) == 0, \
            f"Mutation proof: column present but ALTER was issued: {spark.sql_calls}"

    def test_alter_uses_correct_table_name(self):
        """ALTER targets silver_ohlcv_day_adjusted, not gold_model_features."""
        from pipelines.run_silver_gold import ensure_day_adjusted_columns

        spark = _FakeSpark(columns=["symbol"])
        ensure_day_adjusted_columns(spark)

        assert "silver_ohlcv_day_adjusted" in spark.sql_calls[0]
        assert "gold_model_features" not in spark.sql_calls[0]

    def test_multiple_missing_columns(self):
        """If DAY_ADJUSTED_COLUMNS had multiple entries, all missing are added."""
        from pipelines.run_silver_gold import ensure_day_adjusted_columns, DAY_ADJUSTED_COLUMNS

        # Temporarily add a fake column to test multi-column behavior
        original = dict(DAY_ADJUSTED_COLUMNS)
        try:
            DAY_ADJUSTED_COLUMNS["fake_col"] = "INT"
            spark = _FakeSpark(columns=["symbol"])
            ensure_day_adjusted_columns(spark)

            assert len(spark.sql_calls) == 1
            assert "vwap_source" in spark.sql_calls[0]
            assert "fake_col" in spark.sql_calls[0]
        finally:
            DAY_ADJUSTED_COLUMNS.clear()
            DAY_ADJUSTED_COLUMNS.update(original)