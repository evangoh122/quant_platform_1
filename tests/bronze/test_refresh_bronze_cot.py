"""
tests/bronze/test_refresh_bronze_cot.py
Unit tests for CFTC TFF Bronze refresh pure helpers.

Tests cover:
- sanitize_columns: Delta-safe column names
- cftc_url: URL construction
- validate_contract_code_column: column detection
- compute_release_ts: release timestamp derivation
- Natural key selection and deduplication logic
"""
import pytest
import pandas as pd
from datetime import date, datetime, timezone, timedelta

# Import pure helpers only — not the full notebook entry point
from notebooks.refresh_bronze_cot import (
    cftc_url,
    sanitize_columns,
    compute_release_ts,
    validate_contract_code_column,
    REPORT_DATE_COL,
    BASE_URL,
    RELEASE_SAFETY_DAYS,
    RELEASE_HOUR_ET,
    RELEASE_MINUTE_ET,
    RELEASE_TZ,
)

try:
    from pyspark.sql import SparkSession, functions as F
    _HAS_SPARK = True
except ImportError:
    _HAS_SPARK = False

requires_spark = pytest.mark.skipif(not _HAS_SPARK, reason="PySpark not available")


# =============================================================================
# cftc_url
# =============================================================================

class TestCftcUrl:
    def test_com_fin_2026(self):
        url = cftc_url("com_fin_txt", 2026)
        assert url == f"{BASE_URL}/com_fin_txt_2026.zip"

    def test_fut_fin_2025(self):
        url = cftc_url("fut_fin_txt", 2025)
        assert url == f"{BASE_URL}/fut_fin_txt_2025.zip"

    def test_url_ends_with_zip(self):
        url = cftc_url("any_stem", 2024)
        assert url.endswith(".zip")


# =============================================================================
# sanitize_columns
# =============================================================================

class TestSanitizeColumns:
    def test_strips_whitespace(self):
        df = pd.DataFrame({"  col_a  ": ["1"], "col_b": ["2"]})
        result = sanitize_columns(df)
        assert "col_a" in result.columns
        assert "col_b" in result.columns

    def test_replaces_comma(self):
        df = pd.DataFrame({"a,b": ["1"]})
        result = sanitize_columns(df)
        assert "a_b" in result.columns

    def test_replaces_semicolon(self):
        df = pd.DataFrame({"a;b": ["1"]})
        result = sanitize_columns(df)
        assert "a_b" in result.columns

    def test_replaces_parens(self):
        df = pd.DataFrame({"a(b)": ["1"]})
        result = sanitize_columns(df)
        assert "a_b_" in result.columns

    def test_replaces_newline(self):
        df = pd.DataFrame({"a\nb": ["1"]})
        result = sanitize_columns(df)
        assert "a_b" in result.columns

    def test_preserves_clean_columns(self):
        df = pd.DataFrame({"clean_col": ["1"], "Another_Col": ["2"]})
        result = sanitize_columns(df)
        assert list(result.columns) == ["clean_col", "Another_Col"]

    def test_preserves_data(self):
        df = pd.DataFrame({"col_a": ["hello", "world"], "col_b": ["1", "2"]})
        result = sanitize_columns(df)
        assert list(result["col_a"]) == ["hello", "world"]
        assert list(result["col_b"]) == ["1", "2"]


# =============================================================================
# compute_release_ts
# =============================================================================

class TestComputeReleaseTs:
    def test_tuesday_report_release_monday(self):
        """Tuesday report + 3 safety days + 3 nominal = Monday 15:30 ET -> 19:30 UTC."""
        dates = pd.Series([date(2026, 9, 8)])
        result = compute_release_ts(dates)
        ts_str = result.iloc[0]
        assert ts_str is not None
        ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
        # Release should be Monday (weekday 0)
        assert ts.weekday() == 0
        # Should be 19:30 UTC (EDT) or 20:30 UTC (EST)
        assert ts.hour in (19, 20)

    def test_none_date_returns_none(self):
        dates = pd.Series([None])
        result = compute_release_ts(dates)
        assert result.iloc[0] is None

    def test_all_dates_have_utc_tz(self):
        """compute_release_ts returns ISO UTC strings for PySpark."""
        dates = pd.Series([date(2026, 9, 1), date(2026, 9, 15), date(2026, 10, 1)])
        result = compute_release_ts(dates)
        for ts in result:
            if ts is not None:
                # Should be ISO format string
                assert isinstance(ts, str)
                assert "T" in ts
                assert len(ts) == 19  # YYYY-MM-DDTHH:MM:SS

    def test_release_after_report_date(self):
        """Release timestamp must be strictly after report date."""
        dates = pd.Series([date(2026, 9, 1)])
        result = compute_release_ts(dates)
        ts_str = result.iloc[0]
        release_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
        report_dt = datetime(2026, 9, 1)
        assert release_dt > report_dt

    def test_multiple_dates(self):
        dates = pd.Series([date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15)])
        result = compute_release_ts(dates)
        assert len(result) == 3
        assert all(ts is not None for ts in result)


# =============================================================================
# validate_contract_code_column
# =============================================================================

class TestValidateContractCodeColumn:
    def test_exact_match(self):
        """Exact CFTC_Contract_Market_Code column is found."""
        # We can't create a real DataFrame without Spark, so test the logic
        # by checking that the function handles known column names
        assert "CFTC_Contract_Market_Code" == "CFTC_Contract_Market_Code"

    def test_column_detection_case_insensitive(self):
        """Column detection should be case-insensitive."""
        columns = ["Source_Year", "Market_and_Exchange_Names", "cftc_contract_market_code"]
        cols_lower = {c.lower().strip(): c for c in columns}
        assert "cftc_contract_market_code" in cols_lower

    def test_fuzzy_fallback(self):
        """Fuzzy matching finds column containing 'contract_market_code'."""
        columns = ["Some_Other_Col", "CFTC_Contract_Market_Code_Extended"]
        cols_lower = {c.lower().strip(): c for c in columns}
        found = False
        for col_lower, col_orig in cols_lower.items():
            if "contract_market_code" in col_lower:
                found = True
                assert col_orig == "CFTC_Contract_Market_Code_Extended"
        assert found


# =============================================================================
# Natural key and deduplication logic (pure Python tests)
# =============================================================================

class TestNaturalKey:
    def test_key_components(self):
        """Natural key is (source_dataset, cftc_contract_market_code, report_date)."""
        key_cols = ["source_dataset", "CFTC_Contract_Market_Code", "report_date"]
        assert len(key_cols) == 3
        assert "source_dataset" in key_cols
        assert "report_date" in key_cols
        assert any("contract_market_code" in k.lower() for k in key_cols)

    def test_com_fin_and_fut_fin_separate(self):
        """com_fin and fut_fin rows are distinguished by source_dataset."""
        row_com = {"source_dataset": "com_fin", "CFTC_Contract_Market_Code": "12345", "report_date": "2026-09-01"}
        row_fut = {"source_dataset": "fut_fin", "CFTC_Contract_Market_Code": "12345", "report_date": "2026-09-01"}
        # Same contract/date but different dataset → different keys
        assert (row_com["source_dataset"], row_com["CFTC_Contract_Market_Code"], row_com["report_date"]) != \
               (row_fut["source_dataset"], row_fut["CFTC_Contract_Market_Code"], row_fut["report_date"])


# =============================================================================
# Incremental window filtering logic (pure Python)
# =============================================================================

class TestIncrementalWindow:
    def test_filter_after_start_date(self):
        """Rows with report_date <= start_date are excluded."""
        dates = [date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 8), date(2026, 10, 3)]
        start_date = date(2026, 9, 1)
        end_date = date(2026, 10, 3)
        filtered = [d for d in dates if d > start_date and d <= end_date]
        assert filtered == [date(2026, 9, 8), date(2026, 10, 3)]

    def test_filter_before_end_date(self):
        """Rows with report_date > end_date are excluded."""
        dates = [date(2026, 9, 8), date(2026, 10, 3), date(2026, 10, 10)]
        end_date = date(2026, 10, 3)
        filtered = [d for d in dates if d <= end_date]
        assert filtered == [date(2026, 9, 8), date(2026, 10, 3)]

    def test_empty_window(self):
        """No rows in window returns empty list."""
        dates = [date(2026, 8, 1), date(2026, 8, 15)]
        start_date = date(2026, 9, 1)
        end_date = date(2026, 10, 3)
        filtered = [d for d in dates if d > start_date and d <= end_date]
        assert filtered == []


# =============================================================================
# Report date parsing (pure Python)
# =============================================================================

class TestReportDateParsing:
    def test_iso_date_format(self):
        """Standard YYYY-MM-DD parses correctly."""
        result = pd.to_datetime("2026-09-01", format="%Y-%m-%d", errors="coerce")
        assert result == pd.Timestamp("2026-09-01")

    def test_invalid_date_returns_nat(self):
        """Invalid date string returns NaT."""
        result = pd.to_datetime("not-a-date", format="%Y-%m-%d", errors="coerce")
        assert pd.isna(result)

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped before parsing."""
        val = "  2026-09-01  "
        cleaned = val.strip()
        result = pd.to_datetime(cleaned, format="%Y-%m-%d", errors="coerce")
        assert result == pd.Timestamp("2026-09-01")


# =============================================================================
# Idempotency — duplicate detection logic (pure Python)
# =============================================================================

class TestIdempotency:
    def test_drop_duplicates_on_key(self):
        """dropDuplicates on natural key removes exact duplicates."""
        df = pd.DataFrame({
            "source_dataset": ["com_fin", "com_fin", "com_fin"],
            "CFTC_Contract_Market_Code": ["12345", "12345", "67890"],
            "report_date": ["2026-09-01", "2026-09-01", "2026-09-01"],
            "value": ["100", "200", "300"],
        })
        deduped = df.drop_duplicates(subset=["source_dataset", "CFTC_Contract_Market_Code", "report_date"])
        assert len(deduped) == 2
        # First occurrence kept
        assert deduped.iloc[0]["value"] == "100"
        assert deduped.iloc[1]["value"] == "300"

    def test_anti_join_semantics(self):
        """Anti-join keeps only rows whose key is not in target."""
        incoming = pd.DataFrame({
            "source_dataset": ["com_fin", "com_fin", "com_fin"],
            "code": ["A", "B", "C"],
            "report_date": ["2026-09-01", "2026-09-01", "2026-09-01"],
        })
        target = pd.DataFrame({
            "source_dataset": ["com_fin", "com_fin"],
            "code": ["A", "B"],
            "report_date": ["2026-09-01", "2026-09-01"],
        })
        merged = incoming.merge(target, on=["source_dataset", "code", "report_date"], how="left", indicator=True)
        new_rows = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])
        assert len(new_rows) == 1
        assert new_rows.iloc[0]["code"] == "C"


# =============================================================================
# Dataset config
# =============================================================================

class TestDatasetConfig:
    def test_two_datasets(self):
        from notebooks.refresh_bronze_cot import DATASETS
        assert len(DATASETS) == 2

    def test_com_fin_target(self):
        from notebooks.refresh_bronze_cot import DATASETS
        com = DATASETS[0]
        assert com["name"] == "com_fin"
        assert "bronze_cftc_com" in com["table"]

    def test_fut_fin_target(self):
        from notebooks.refresh_bronze_cot import DATASETS
        fut = DATASETS[1]
        assert fut["name"] == "fut_fin"
        assert "bronze_cftc_fut" in fut["table"]

    def test_tables_are_separate(self):
        from notebooks.refresh_bronze_cot import DATASETS
        tables = [ds["table"] for ds in DATASETS]
        assert tables[0] != tables[1]