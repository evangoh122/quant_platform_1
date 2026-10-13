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
    anti_join_new_rows,
    detect_revision_conflicts,
    to_bronze,
    filter_report_window,
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


@pytest.fixture(scope="session")
def spark():
    """Create a local Spark session for tests."""
    from unittest.mock import MagicMock

    try:
        from pyspark.sql import SparkSession
        session = (
            SparkSession.builder
            .master("local[2]")
            .appName("test_bronze_cot")
            .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
    except Exception:
        pytest.skip("No local PySpark session available")
    if isinstance(session, MagicMock):
        pytest.skip("Spark session is a MagicMock (sys.modules pollution from another test module)")
    yield session


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

    def test_dst_edt_summer(self):
        """Summer date: 15:30 EDT = 19:30 UTC."""
        dates = pd.Series([date(2026, 7, 7)])
        result = compute_release_ts(dates)
        ts = datetime.strptime(result.iloc[0], "%Y-%m-%dT%H:%M:%S")
        assert ts.hour == 19 and ts.minute == 30

    def test_dst_est_winter(self):
        """Winter date: 15:30 EST = 20:30 UTC."""
        dates = pd.Series([date(2026, 1, 6)])
        result = compute_release_ts(dates)
        ts = datetime.strptime(result.iloc[0], "%Y-%m-%dT%H:%M:%S")
        assert ts.hour == 20 and ts.minute == 30


# =============================================================================
# validate_contract_code_column
# =============================================================================

class TestValidateContractCodeColumn:
    def test_exact_match(self):
        """Exact CFTC_Contract_Market_Code column is found by validate_contract_code_column."""
        df = pd.DataFrame({
            "CFTC_Contract_Market_Code": ["001"],
            "Market_and_Exchange_Names": ["FOO"],
        })
        result = validate_contract_code_column(df, "test_ds")
        assert result == "CFTC_Contract_Market_Code"

    def test_case_insensitive_match(self):
        """Lowercase variant is found case-insensitively."""
        df = pd.DataFrame({
            "Source_Year": ["2026"],
            "cftc_contract_market_code": ["002"],
        })
        result = validate_contract_code_column(df, "test_ds")
        assert result == "cftc_contract_market_code"

    def test_fuzzy_fallback(self):
        """Fuzzy fallback finds column containing 'contract_market_code'."""
        df = pd.DataFrame({
            "Some_Other_Col": ["x"],
            "CFTC_Contract_Market_Code_Extended": ["003"],
        })
        result = validate_contract_code_column(df, "test_ds")
        assert result == "CFTC_Contract_Market_Code_Extended"

    def test_raises_when_missing(self):
        """RuntimeError raised when no contract code column exists."""
        df = pd.DataFrame({"Random_Col": ["x"]})
        with pytest.raises(RuntimeError, match="no stable CFTC contract market code"):
            validate_contract_code_column(df, "test_ds")


# =============================================================================
# Natural key and deduplication logic (pure Python tests)
# =============================================================================

class TestNaturalKey:
    @requires_spark
    def test_anti_join_filters_existing_keys(self, spark):
        """anti_join_new_rows keeps only rows whose key is absent from target."""
        contract_code_col = "CFTC_Contract_Market_Code"
        incoming = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
            ("com_fin", "002", "2026-09-01"),
            ("com_fin", "003", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        target = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        result = anti_join_new_rows(incoming, target, None, contract_code_col)
        result_codes = sorted([r[contract_code_col] for r in result.collect()])
        assert result_codes == ["002", "003"]

    @requires_spark
    def test_anti_join_deduplicates_incoming(self, spark):
        """anti_join_new_rows deduplicates the incoming batch."""
        contract_code_col = "CFTC_Contract_Market_Code"
        incoming = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
            ("com_fin", "001", "2026-09-01"),
            ("com_fin", "002", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        target = incoming.filter("1=0")  # empty DF with same schema
        result = anti_join_new_rows(incoming, target, None, contract_code_col)
        assert result.count() == 2

    @requires_spark
    def test_com_fin_and_fut_fin_separate_keys(self, spark):
        """com_fin and fut_fin rows with same code/date are different keys."""
        contract_code_col = "CFTC_Contract_Market_Code"
        incoming = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
            ("fut_fin", "001", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        target = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        result = anti_join_new_rows(incoming, target, None, contract_code_col)
        assert result.count() == 1
        assert result.collect()[0]["source_dataset"] == "fut_fin"


# =============================================================================
# Incremental window filtering — exercises filter_report_window()
# =============================================================================

class TestIncrementalWindow:
    """Tests that call the production filter_report_window() function.

    These guard the off-by-one bug (>= vs >) at refresh_bronze_cot.py:408.
    Reverting >= to > in production MUST cause test_filter_on_max_plus_one to fail.
    """

    def _make_pdf(self, dates):
        """Build a minimal DataFrame with a report-date column."""
        raw = [d.strftime("%Y-%m-%d") for d in dates]
        return pd.DataFrame({REPORT_DATE_COL: raw})

    def test_filter_includes_start_date(self):
        """start_date itself is included in the window."""
        pdf = self._make_pdf([date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 8)])
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))
        assert len(result) == 2
        assert result[REPORT_DATE_COL].tolist() == ["2026-09-01", "2026-09-08"]

    def test_filter_includes_end_date(self):
        """end_date itself is included in the window."""
        pdf = self._make_pdf([date(2026, 9, 8), date(2026, 10, 3), date(2026, 10, 10)])
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))
        assert len(result) == 2
        assert result[REPORT_DATE_COL].tolist() == ["2026-09-08", "2026-10-03"]

    def test_filter_on_max_plus_one(self):
        """A report dated exactly max+1 day must be included.

        This is the critical regression test: if production used > instead of
        >=, this row would be silently dropped.
        """
        max_date = date(2026, 10, 3)
        max_plus_one = max_date + timedelta(days=1)
        pdf = self._make_pdf([max_date, max_plus_one])
        result = filter_report_window(pdf, max_plus_one, max_plus_one)
        assert len(result) == 1
        assert result[REPORT_DATE_COL].iloc[0] == max_plus_one.strftime("%Y-%m-%d")

    def test_filter_excludes_before_start(self):
        """Rows before start_date are excluded."""
        pdf = self._make_pdf([date(2026, 8, 1), date(2026, 8, 15)])
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))
        assert len(result) == 0

    def test_filter_empty_input(self):
        """Empty DataFrame returns empty result."""
        pdf = pd.DataFrame({REPORT_DATE_COL: []})
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))
        assert len(result) == 0

    def test_invalid_date_excluded(self):
        """Unparseable date strings are coerced to NaT and filtered out."""
        pdf = pd.DataFrame({REPORT_DATE_COL: ["2026-09-01", "not-a-date", "2026-10-03"]})
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))
        assert len(result) == 2

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace in date strings is handled."""
        pdf = pd.DataFrame({REPORT_DATE_COL: ["  2026-09-01  ", "2026-10-03 "]})
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))
        assert len(result) == 2

    def test_missing_column_raises(self):
        """DataFrame without the report-date column raises KeyError."""
        pdf = pd.DataFrame({"other_col": ["2026-09-01"]})
        with pytest.raises(KeyError):
            filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))


# =============================================================================
# Report date parsing — exercises filter_report_window() parsing path
# =============================================================================

class TestReportDateParsing:
    """Tests that the parsing inside filter_report_window handles edge cases."""

    def test_iso_date_format(self):
        """Standard YYYY-MM-DD parses and filters correctly."""
        pdf = pd.DataFrame({REPORT_DATE_COL: ["2026-09-01"]})
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 9, 1))
        assert len(result) == 1

    def test_invalid_date_returns_nat_excluded(self):
        """Invalid date string produces NaT, which is filtered out."""
        pdf = pd.DataFrame({REPORT_DATE_COL: ["not-a-date"]})
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 10, 3))
        assert len(result) == 0

    def test_whitespace_stripped_before_parse(self):
        """Whitespace is stripped before parsing, so date is found in window."""
        pdf = pd.DataFrame({REPORT_DATE_COL: ["  2026-09-01  "]})
        result = filter_report_window(pdf, date(2026, 9, 1), date(2026, 9, 1))
        assert len(result) == 1


# =============================================================================
# Idempotency — duplicate detection logic (pure Python)
# =============================================================================

class TestIdempotency:
    @requires_spark
    def test_detect_revision_conflicts(self, spark):
        """detect_revision_conflicts counts rows with existing keys."""
        contract_code_col = "CFTC_Contract_Market_Code"
        incoming = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
            ("com_fin", "002", "2026-09-01"),
            ("com_fin", "003", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        target = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
            ("com_fin", "002", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        conflicts = detect_revision_conflicts(incoming, target, contract_code_col)
        assert conflicts == 2

    @requires_spark
    def test_detect_revision_conflicts_zero(self, spark):
        """detect_revision_conflicts returns 0 when no key overlap."""
        contract_code_col = "CFTC_Contract_Market_Code"
        incoming = spark.createDataFrame([
            ("com_fin", "003", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        target = spark.createDataFrame([
            ("com_fin", "001", "2026-09-01"),
        ], ["source_dataset", contract_code_col, "report_date"])
        conflicts = detect_revision_conflicts(incoming, target, contract_code_col)
        assert conflicts == 0

    @requires_spark
    def test_to_bronze_adds_derived_columns(self, spark):
        """to_bronze adds report_date, release_ts, source_dataset, ingest_ts."""
        pdf = pd.DataFrame({
            REPORT_DATE_COL: ["2026-09-01", "2026-09-08"],
            "Market_and_Exchange_Names": ["CME E-MINI S&P 500", "CBOE VOLATILITY INDEX"],
            "CFTC_Contract_Market_Code": ["13874P", "1170E1"],
        })
        from datetime import datetime, timezone
        ingest_ts = datetime.now(timezone.utc)
        result = to_bronze(pdf, dataset="com_fin", url="https://example.com/test.zip", ingest_ts=ingest_ts, spark=spark)
        assert "report_date" in result.columns
        assert "release_ts" in result.columns
        assert "source_dataset" in result.columns
        assert "ingest_ts" in result.columns
        assert "report_year" in result.columns
        assert result.count() == 2
        row = result.collect()[0]
        assert row["source_dataset"] == "com_fin"
        assert row["source_file"] == "https://example.com/test.zip"

    @requires_spark
    def test_to_bronze_report_date_not_null(self, spark):
        """to_bronze parses report_date as non-null for valid inputs."""
        pdf = pd.DataFrame({
            REPORT_DATE_COL: ["2026-09-01"],
            "CFTC_Contract_Market_Code": ["001"],
        })
        from datetime import datetime, timezone
        ingest_ts = datetime.now(timezone.utc)
        result = to_bronze(pdf, dataset="test", url="https://example.com", ingest_ts=ingest_ts, spark=spark)
        row = result.collect()[0]
        assert row["report_date"] is not None


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


# =============================================================================
# Spark acquisition (runtime-aware; no .serverless on plain SparkSession.builder)
# =============================================================================

class TestCotSparkAcquisition:
    def test_ambient_session_when_databricks_runtime_set(self, monkeypatch):
        """Inside a Databricks runtime use SparkSession.builder.getOrCreate()."""
        import sys
        import types

        monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")

        calls = []

        class FakeBuilder:
            def getOrCreate(self):
                calls.append("getOrCreate")
                return "AMBIENT_SESSION"

        class FakeSparkSession:
            builder = FakeBuilder()

        fake_pyspark = types.ModuleType("pyspark")
        fake_sql = types.ModuleType("pyspark.sql")
        fake_sql.SparkSession = FakeSparkSession
        fake_pyspark.sql = fake_sql
        monkeypatch.setitem(sys.modules, "pyspark", fake_pyspark)
        monkeypatch.setitem(sys.modules, "pyspark.sql", fake_sql)

        import notebooks.refresh_bronze_cot as cot_mod
        result = cot_mod._get_spark()
        assert result == "AMBIENT_SESSION"
        assert calls == ["getOrCreate"]

    def test_connect_session_outside_runtime(self, monkeypatch):
        """Outside the runtime create a serverless DatabricksSession."""
        import sys
        import types

        monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)

        calls = []

        class FakeBuilder:
            def serverless(self, flag):
                calls.append(("serverless", flag))
                return self

            def getOrCreate(self):
                calls.append("getOrCreate")
                return "CONNECT_SESSION"

        class FakeDatabricksSession:
            builder = FakeBuilder()

        fake_dbx = types.ModuleType("databricks")
        fake_connect = types.ModuleType("databricks.connect")
        fake_connect.DatabricksSession = FakeDatabricksSession
        monkeypatch.setitem(sys.modules, "databricks", fake_dbx)
        monkeypatch.setitem(sys.modules, "databricks.connect", fake_connect)

        import notebooks.refresh_bronze_cot as cot_mod
        result = cot_mod._get_spark()
        assert result == "CONNECT_SESSION"
        assert ("serverless", True) in calls

    def test_never_calls_serverless_on_plain_spark_session_builder(self):
        """Static scan: no ``SparkSession.builder.serverless`` in the module.

        Plain ``SparkSession.builder`` has no ``.serverless`` attribute in the
        Databricks runtime (AttributeError), so acquisition must be runtime
        aware instead.
        """
        from pathlib import Path

        import notebooks.refresh_bronze_cot as cot_mod
        src = Path(cot_mod.__file__).read_text(encoding="utf-8")
        assert "SparkSession.builder.serverless" not in src
        assert "DatabricksSession.builder.serverless(True)" in src


# =============================================================================
# _build_cot_headers: env -> Databricks secret, fail-closed, no value leaks
# =============================================================================

class TestBuildCotHeaders:
    def test_env_wins_over_secret(self, monkeypatch):
        """CFTC_USER_EMAIL from CLI/env is used and the secret is not read."""
        monkeypatch.setenv("CFTC_USER_EMAIL", "env-reader@quantdesk.io")
        secret_calls = []

        def _fake_secret(key_name):
            secret_calls.append(key_name)
            return "secret-reader@quantdesk.io"

        monkeypatch.setattr(
            "notebooks.refresh_bronze_cot._get_secret", _fake_secret
        )

        import notebooks.refresh_bronze_cot as cot_mod
        headers = cot_mod._build_cot_headers()
        assert headers == {
            "User-Agent": "capstone-research (evangoh) env-reader@quantdesk.io"
        }
        assert secret_calls == []

    def test_secret_fallback_when_env_empty(self, monkeypatch):
        """Empty env falls back to scope evangoh_capstone key cftc_user_email."""
        monkeypatch.delenv("CFTC_USER_EMAIL", raising=False)
        seen = {}

        def _fake_secret(key_name):
            seen["key"] = key_name
            return "ops-duty@quantdesk.io"

        monkeypatch.setattr(
            "notebooks.refresh_bronze_cot._get_secret", _fake_secret
        )

        import notebooks.refresh_bronze_cot as cot_mod
        headers = cot_mod._build_cot_headers()
        assert headers["User-Agent"].endswith("ops-duty@quantdesk.io")
        assert seen["key"] == "cftc_user_email"

    def test_secret_read_via_dbutils_uses_scope_and_plaintext(self, monkeypatch):
        """Notebook mode: dbutils.secrets.get(scope, key) returns plaintext."""
        import notebooks.refresh_bronze_cot as cot_mod

        seen = {}

        class _Secrets:
            def get(self, scope, key):
                seen["scope"] = scope
                seen["key"] = key
                return "notebook-reader@quantdesk.io"

        class _Dbutils:
            secrets = _Secrets()

        monkeypatch.setitem(cot_mod.__dict__, "dbutils", _Dbutils())
        value = cot_mod._get_secret("cftc_user_email")
        assert value == "notebook-reader@quantdesk.io"
        assert seen == {"scope": "evangoh_capstone", "key": "cftc_user_email"}

    def test_secret_read_via_sdk_decodes_base64(self, monkeypatch):
        """CLI mode: WorkspaceClient().secrets.get_secret().value is base64."""
        import base64
        import sys
        import types

        import notebooks.refresh_bronze_cot as cot_mod

        email = "sdk-reader@quantdesk.io"
        seen = {}

        class _GetSecretResponse:
            value = base64.b64encode(email.encode("utf-8")).decode("ascii")

        class _Secrets:
            def get_secret(self, scope, key):
                seen["scope"] = scope
                seen["key"] = key
                return _GetSecretResponse()

        class _WorkspaceClient:
            def __init__(self, profile=None):
                seen["profile"] = profile
                self.secrets = _Secrets()

        fake_sdk = types.ModuleType("databricks.sdk")
        fake_sdk.WorkspaceClient = _WorkspaceClient
        monkeypatch.setitem(sys.modules, "databricks.sdk", fake_sdk)
        monkeypatch.delitem(cot_mod.__dict__, "dbutils", raising=False)
        value = cot_mod._get_secret("cftc_user_email")
        assert value == email
        assert seen["scope"] == "evangoh_capstone"
        assert seen["key"] == "cftc_user_email"

    def test_neither_env_nor_secret_raises(self, monkeypatch):
        """Fail closed when neither source provides an email."""
        monkeypatch.delenv("CFTC_USER_EMAIL", raising=False)

        def _missing(key_name):
            raise RuntimeError("secret unavailable")

        monkeypatch.setattr(
            "notebooks.refresh_bronze_cot._get_secret", _missing
        )

        import notebooks.refresh_bronze_cot as cot_mod
        with pytest.raises(ValueError, match="CFTC_USER_EMAIL must be set"):
            cot_mod._build_cot_headers()

    def test_placeholder_from_env_rejected(self, monkeypatch):
        monkeypatch.setenv("CFTC_USER_EMAIL", "user@example.com")
        import notebooks.refresh_bronze_cot as cot_mod
        with pytest.raises(ValueError, match="CFTC_USER_EMAIL must be set"):
            cot_mod._build_cot_headers()

    def test_placeholder_from_secret_rejected(self, monkeypatch):
        monkeypatch.delenv("CFTC_USER_EMAIL", raising=False)
        monkeypatch.setattr(
            "notebooks.refresh_bronze_cot._get_secret",
            lambda key_name: "test@example.org",
        )
        import notebooks.refresh_bronze_cot as cot_mod
        with pytest.raises(ValueError, match="CFTC_USER_EMAIL must be set"):
            cot_mod._build_cot_headers()

    def test_value_never_in_logs_or_exception_text(self, monkeypatch, capsys):
        """Canary: the resolved email must not leak into logs or exceptions."""
        canary = "canary-9f31c2@quantdesk.io"
        monkeypatch.delenv("CFTC_USER_EMAIL", raising=False)
        monkeypatch.setattr(
            "notebooks.refresh_bronze_cot._get_secret", lambda key_name: canary
        )

        import notebooks.refresh_bronze_cot as cot_mod
        headers = cot_mod._build_cot_headers()
        assert canary in headers["User-Agent"]  # by design, in the header only
        out, err = capsys.readouterr()
        assert canary not in out
        assert canary not in err

    def test_invalid_value_never_in_exception_text(self, monkeypatch, capsys):
        """Canary: an invalid value must not be echoed in the error."""
        canary = "canary-77aa@example.com"
        monkeypatch.setenv("CFTC_USER_EMAIL", canary)

        import notebooks.refresh_bronze_cot as cot_mod
        with pytest.raises(ValueError) as excinfo:
            cot_mod._build_cot_headers()
        assert canary not in str(excinfo.value)
        out, err = capsys.readouterr()
        assert canary not in out
        assert canary not in err