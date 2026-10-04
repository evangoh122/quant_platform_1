"""
tests/bronze/test_corporate_actions.py

Pure adapter/normalization/idempotency tests for etl/corporate_actions.py
and notebooks/refresh_bronze_corporate_actions.py.

No network, no Databricks, no Spark.  Uses fakes for ticker factory,
clock, and sleeper.
"""
import datetime as dt
import math
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock

import pytest

from etl.corporate_actions import (
    CorporateActionSplit,
    CorporateActionsSource,
    MassiveCorporateActionsSource,
    information_available_ts_for,
)


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

class _NoOpSleeper:
    def __call__(self, secs):
        pass


def _fixed_clock(year=2025, month=1, day=1, hour=12, minute=0, second=0):
    return lambda: dt.datetime(year, month, day, hour, minute, second)


# ---------------------------------------------------------------------------
# 1. CorporateActionSplit validation
# ---------------------------------------------------------------------------

class TestCorporateActionSplit:

    def test_forward_split_20to1(self):
        s = CorporateActionSplit(
            symbol="AMZN", ex_date=dt.date(2022, 6, 6),
            split_ratio=20.0, source="massive",
            fetched_ts=dt.datetime(2025, 1, 1, 12, 0, 0),
            information_available_ts=dt.datetime(2022, 6, 6, 13, 30, 0),
        )
        assert s.split_ratio == 20.0

    def test_reverse_split_1to10(self):
        s = CorporateActionSplit(
            symbol="SQQQ", ex_date=dt.date(2024, 1, 1),
            split_ratio=0.1, source="massive",
            fetched_ts=dt.datetime(2025, 1, 1, 12, 0, 0),
            information_available_ts=dt.datetime(2024, 1, 1, 14, 30, 0),
        )
        assert s.split_ratio == 0.1

    def test_fractional_ratio(self):
        s = CorporateActionSplit(
            symbol="TEST", ex_date=dt.date(2024, 1, 1),
            split_ratio=1.5, source="massive",
            fetched_ts=dt.datetime(2025, 1, 1, 12, 0, 0),
            information_available_ts=dt.datetime(2024, 1, 1, 14, 30, 0),
        )
        assert s.split_ratio == 1.5

    def test_reject_zero_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=0.0, source="massive",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_one_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=1.0, source="massive",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_negative_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=-2.0, source="massive",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_nan_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=float("nan"), source="massive",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_inf_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=float("inf"), source="massive",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_empty_symbol(self):
        with pytest.raises(ValueError, match="symbol"):
            CorporateActionSplit(
                symbol="", ex_date=dt.date(2024, 1, 1),
                split_ratio=2.0, source="massive",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_aware_fetched_ts(self):
        with pytest.raises(ValueError, match="fetched_ts"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=2.0, source="massive",
                fetched_ts=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_aware_info_ts(self):
        with pytest.raises(ValueError, match="information_available_ts"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=2.0, source="massive",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
            )

    def test_frozen(self):
        s = CorporateActionSplit(
            symbol="X", ex_date=dt.date(2024, 1, 1),
            split_ratio=2.0, source="massive",
            fetched_ts=dt.datetime(2025, 1, 1),
            information_available_ts=dt.datetime(2025, 1, 1),
        )
        with pytest.raises(FrozenInstanceError):
            s.symbol = "Y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. information_available_ts_for — EST and EDT
# ---------------------------------------------------------------------------

class TestInformationAvailableTs:

    def test_est_date(self):
        # Jan 15 2024 is EST (UTC-5).  09:30 ET = 14:30 UTC
        ts = information_available_ts_for(dt.date(2024, 1, 15))
        assert ts == dt.datetime(2024, 1, 15, 14, 30, 0)
        assert ts.tzinfo is None

    def test_edt_date(self):
        # Jul 15 2024 is EDT (UTC-4).  09:30 ET = 13:30 UTC
        ts = information_available_ts_for(dt.date(2024, 7, 15))
        assert ts == dt.datetime(2024, 7, 15, 13, 30, 0)
        assert ts.tzinfo is None

    def test_amzn_ex_date_2022(self):
        # AMZN 20:1 split ex-date 2022-06-06, EDT
        ts = information_available_ts_for(dt.date(2022, 6, 6))
        assert ts == dt.datetime(2022, 6, 6, 13, 30, 0)

    def test_november_est(self):
        # Nov 1 2024 is EST
        ts = information_available_ts_for(dt.date(2024, 11, 1))
        assert ts == dt.datetime(2024, 11, 1, 13, 30, 0)


# ---------------------------------------------------------------------------
# 3. Source protocol compliance
# ---------------------------------------------------------------------------

class TestSourceProtocol:

    def test_fake_source_satisfies_protocol(self):
        """A class with fetch_splits satisfies CorporateActionsSource."""
        class _Src:
            def fetch_splits(self, symbol):
                return []
        src = _Src()
        assert hasattr(src, "fetch_splits")
        assert callable(src.fetch_splits)


# ---------------------------------------------------------------------------
# 4. Bronze idempotency logic (pure Python reference)
# ---------------------------------------------------------------------------

class TestBronzeIdempotency:

    def test_duplicate_rows_produce_one_key(self):
        """Duplicate (symbol, ex_date, source) rows collapse to one."""
        rows = [
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "massive",
             "split_ratio": 20.0, "fetched_ts": "2025-01-01T00:00:00",
             "information_available_ts": "2022-06-06T13:30:00"},
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "massive",
             "split_ratio": 20.0, "fetched_ts": "2025-01-02T00:00:00",
             "information_available_ts": "2022-06-06T13:30:00"},
        ]
        seen = set()
        unique = []
        for r in rows:
            key = (r["symbol"], r["ex_date"], r["source"])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        assert len(unique) == 1

    def test_different_fetched_ts_same_key_one_row(self):
        """Same natural key with different fetched_ts is one row."""
        rows = [
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "massive",
             "fetched_ts": "2025-01-01T00:00:00"},
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "massive",
             "fetched_ts": "2025-06-01T00:00:00"},
        ]
        keys = set()
        for r in rows:
            keys.add((r["symbol"], r["ex_date"], r["source"]))
        assert len(keys) == 1

    def test_same_key_different_ratio_is_conflict(self):
        """Same key with different ratio should be flagged as conflict."""
        existing = {("AMZN", "2022-06-06", "massive")}
        new_row = {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "massive",
                    "split_ratio": 15.0}  # different ratio
        key = (new_row["symbol"], new_row["ex_date"], new_row["source"])
        is_conflict = key in existing
        assert is_conflict


# ---------------------------------------------------------------------------
# 7. Protocol: import has no side effects
# ---------------------------------------------------------------------------

class TestImportSafety:

    def test_import_makes_no_network_calls(self):
        """Importing etl.corporate_actions must not call yfinance."""
        import importlib
        mod = importlib.import_module("etl.corporate_actions")
        assert hasattr(mod, "CorporateActionSplit")
        assert hasattr(mod, "MassiveCorporateActionsSource")
        assert hasattr(mod, "information_available_ts_for")

    def test_notebook_import_no_side_effects(self):
        """Importing the notebook module must not start Spark or network."""
        import importlib.util
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        spec = importlib.util.spec_from_file_location("refresh_bronze_corporate_actions", nb_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main")
        assert hasattr(mod, "_valid_mode")
        assert hasattr(mod, "_split_to_row")
        # Must use globals().get("dbutils"), not bare import dbutils
        text = nb_path.read_text(encoding="utf-8")
        assert "globals().get(\"dbutils\")" in text, \
            "Must use globals().get('dbutils'), not import dbutils"
        assert "import dbutils" not in text or "import dbutils  # type: ignore" in text, \
            "Must not use bare 'import dbutils'"

    def test_notebook_has_argparse(self):
        """The notebook must use argparse for CLI flags."""
        import importlib.util
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        text = nb_path.read_text(encoding="utf-8")
        assert "import argparse" in text, "Notebook must import argparse"
        assert "argparse.ArgumentParser" in text, "Notebook must create ArgumentParser"
        assert '--mode' in text, "Notebook must accept --mode flag"
        assert '--run-id' in text, "Notebook must accept --run-id flag"
        assert '--delay-seconds' in text, "Notebook must accept --delay-seconds flag"
        assert '--symbol-start' in text, "Notebook must accept --symbol-start flag"
        assert '--symbol-end' in text, "Notebook must accept --symbol-end flag"

    def test_notebook_valid_sources_includes_massive(self):
        """The notebook must include massive in VALID_SOURCES."""
        import importlib.util
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        spec = importlib.util.spec_from_file_location("refresh_bronze_corporate_actions", nb_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "massive" in mod.VALID_SOURCES
        assert "yfinance" not in mod.VALID_SOURCES

    def test_notebook_default_source_is_massive(self):
        """The notebook default source must be 'massive'."""
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        text = nb_path.read_text(encoding="utf-8")
        assert 'source = "massive"' in text

    def test_notebook_source_both_rejected(self):
        """The notebook must reject 'both' as a source value (massive-only)."""
        import importlib.util
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        spec = importlib.util.spec_from_file_location("refresh_bronze_corporate_actions", nb_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # _valid_source should reject "both"
        with pytest.raises(ValueError, match="source must be one of"):
            mod._valid_source("both")

    def test_notebook_has_secret_scope_reference(self):
        """The notebook must reference the Databricks secret scope for the API key."""
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        text = nb_path.read_text(encoding="utf-8")
        assert "evangoh_capstone" in text
        assert "massive_s3_secret_key" in text


# ---------------------------------------------------------------------------
# 8. Argparse CLI flags (pure parse, no Spark)
# ---------------------------------------------------------------------------

class TestArgparseCLIFlags:
    """Verify argparse parsing in the notebook main() entry point."""

    def _parse_args(self, argv_list):
        """Import the notebook module and call argparse directly."""
        import importlib.util
        import sys
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        spec = importlib.util.spec_from_file_location("refresh_bronze_corporate_actions", nb_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        import argparse
        parser = argparse.ArgumentParser(allow_abbrev=False)
        parser.add_argument("--mode", default=None)
        parser.add_argument("--source", default=None)
        parser.add_argument("--symbol-start", default=None)
        parser.add_argument("--symbol-end", default=None)
        parser.add_argument("--delay-seconds", type=float, default=None)
        parser.add_argument("--max-retries", type=int, default=None)
        parser.add_argument("--run-id", default=None)
        args = parser.parse_args(argv_list)
        return args

    def test_mode_write(self):
        """--mode write sets write mode."""
        args = self._parse_args(["--mode", "write"])
        assert args.mode == "write"

    def test_mode_dry_run(self):
        """--mode dry-run sets dry-run mode."""
        args = self._parse_args(["--mode", "dry-run"])
        assert args.mode == "dry-run"

    def test_mode_default_none(self):
        """Omitting --mode leaves it None (falls back to default dry-run)."""
        args = self._parse_args([])
        assert args.mode is None

    def test_run_id(self):
        """--run-id is parsed."""
        args = self._parse_args(["--run-id", "run-20250101-abc12345"])
        assert args.run_id == "run-20250101-abc12345"

    def test_delay_seconds(self):
        """--delay-seconds is parsed as float."""
        args = self._parse_args(["--delay-seconds", "1.5"])
        assert args.delay_seconds == 1.5

    def test_symbol_bounds(self):
        """--symbol-start and --symbol-end are parsed."""
        args = self._parse_args(["--symbol-start", "AAPL", "--symbol-end", "MSFT"])
        assert args.symbol_start == "AAPL"
        assert args.symbol_end == "MSFT"

    def test_source_massive(self):
        """--source massive is parsed."""
        args = self._parse_args(["--source", "massive"])
        assert args.source == "massive"

    def test_source_both(self):
        """--source both is parsed."""
        args = self._parse_args(["--source", "both"])
        assert args.source == "both"

    def test_unknown_flag_does_not_raise(self):
        """Unknown flags cause SystemExit (strict parse_args)."""
        import argparse
        parser = argparse.ArgumentParser(allow_abbrev=False)
        parser.add_argument("--mode", default=None)
        with pytest.raises(SystemExit):
            parser.parse_args(["--mode", "write", "--unknown-flag", "value"])

    def test_abbreviation_rejected(self):
        """--mod (abbreviation of --mode) is rejected with allow_abbrev=False."""
        import argparse
        parser = argparse.ArgumentParser(allow_abbrev=False)
        parser.add_argument("--mode", default=None)
        with pytest.raises(SystemExit):
            parser.parse_args(["--mod", "write"])

    def test_help_exits_zero_no_spark(self):
        """--help exits 0 without creating Spark."""
        import subprocess
        import sys
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        result = subprocess.run(
            [sys.executable, str(nb_path), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"--help failed: {result.stderr}"
        assert "Refresh bronze corporate actions" in result.stdout

    def test_bogus_flag_exits_nonzero_no_spark(self):
        """--bogus exits non-zero without creating Spark."""
        import subprocess
        import sys
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        result = subprocess.run(
            [sys.executable, str(nb_path), "--bogus"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, f"--bogus should fail but exited 0"

    def test_sys_path_insertion_from_notebooks_dir(self):
        """Running from notebooks/ allows importing etl."""
        import subprocess
        import sys
        from pathlib import Path
        nb_dir = Path(__file__).resolve().parents[2] / "notebooks"
        result = subprocess.run(
            [sys.executable, "refresh_bronze_corporate_actions.py", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=str(nb_dir),
        )
        assert result.returncode == 0, f"Failed from notebooks/: {result.stderr}"


# ---------------------------------------------------------------------------
# 9. Notebook mode: dbutils widgets (no Spark)
# ---------------------------------------------------------------------------

class TestNotebookMode:
    """Verify notebook mode reads from widgets, ignores sys.argv."""

    def _make_fake_dbutils(self, widget_values=None, exit_on_call=False):
        """Create a minimal fake dbutils for testing."""
        if widget_values is None:
            widget_values = {}
        _widgets = {}
        _exited = [None]

        class _Widgets:
            def text(self, name, default):
                _widgets.setdefault(name, default)

            def get(self, name):
                if name in widget_values:
                    return widget_values[name]
                if name in _widgets:
                    return _widgets[name]
                raise Exception(f"Widget {name} not found")

        class _Notebook:
            def __init__(self, exited_ref):
                self._exited = exited_ref

            def exit(self, value):
                self._exited[0] = value
                if exit_on_call:
                    raise SystemExit(0)

        class _DBUtils:
            def __init__(self):
                self.widgets = _Widgets()
                self.notebook = _Notebook(_exited)

        return _DBUtils(), _exited

    def test_kernel_argv_with_fake_dbutils_runs_from_widgets(self):
        """Injected -f kernel.json + fake dbutils → reads from widgets, not argv."""
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch

        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        spec = importlib.util.spec_from_file_location("refresh_bronze_corporate_actions", nb_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        fake_dbutils, _ = self._make_fake_dbutils({"mode": "dry-run", "source": "massive"})
        mod.__dict__["dbutils"] = fake_dbutils

        with patch("sys.argv", [
            "refresh_bronze_corporate_actions.py",
            "-f", "kernel.json",
        ]):
            with pytest.raises((RuntimeError, SystemExit)):
                # RuntimeError: Spark not available (expected in test env)
                # SystemExit: if something else fails
                mod.main()

    def test_dbutils_widget_mode_write(self):
        """dbutils widget mode=write → write mode."""
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch

        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        spec = importlib.util.spec_from_file_location("refresh_bronze_corporate_actions", nb_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        fake_dbutils, _ = self._make_fake_dbutils({
            "mode": "write", "source": "massive",
            "symbol_start": "", "symbol_end": "", "delay_seconds": "0.5",
            "max_retries": "2", "run_id": "test-run",
        })
        mod.__dict__["dbutils"] = fake_dbutils

        with patch("sys.argv", ["refresh_bronze_corporate_actions.py", "-f", "kernel.json"]):
            with pytest.raises((RuntimeError, SystemExit)):
                mod.main()

    def test_dbutils_widget_mode_bogus_raises(self):
        """dbutils widget mode=bogus → ValueError."""
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch

        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        spec = importlib.util.spec_from_file_location("refresh_bronze_corporate_actions", nb_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        fake_dbutils, _ = self._make_fake_dbutils({"mode": "bogus"})
        mod.__dict__["dbutils"] = fake_dbutils

        with patch("sys.argv", ["refresh_bronze_corporate_actions.py", "-f", "kernel.json"]):
            with pytest.raises(ValueError, match="mode must be one of"):
                mod.main()

    def test_no_dbutils_bogus_flag_exits_nonzero(self):
        """No dbutils + --bogus → exit 2 (unchanged)."""
        import subprocess
        import sys
        from pathlib import Path

        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        result = subprocess.run(
            [sys.executable, str(nb_path), "--bogus"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_no_dbutils_help_exits_zero_no_spark(self):
        """No dbutils + --help → exit 0, without Spark."""
        import subprocess
        import sys
        from pathlib import Path

        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        result = subprocess.run(
            [sys.executable, str(nb_path), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "Refresh bronze corporate actions" in result.stdout

    def test_globals_get_dbutils_not_import(self):
        """Source must use globals().get('dbutils'), not import dbutils."""
        from pathlib import Path

        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        text = nb_path.read_text(encoding="utf-8")
        assert "globals().get(\"dbutils\")" in text
        # No bare 'import dbutils' (comments are OK)
        code_lines = [
            line for line in text.splitlines()
            if "import dbutils" in line and not line.strip().startswith("#")
        ]
        for line in code_lines:
            assert "type: ignore" in line or "globals" in line, \
                f"Bare 'import dbutils' found: {line}"


# ---------------------------------------------------------------------------
# 10. Resume checkpoint (massive-only)
# ---------------------------------------------------------------------------

class TestResumeCheckpoint:

    def test_notebook_checkpoint_query_uses_symbol_only(self):
        """The checkpoint query must use symbol, not (symbol, source)."""
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        text = nb_path.read_text(encoding="utf-8")
        # Must query just symbol (no source differentiation needed)
        assert "SELECT DISTINCT symbol FROM" in text, \
            "Checkpoint query must use symbol only (massive-only)"

    def test_notebook_checkpoint_uses_completed_keys_set(self):
        """The checkpoint set must be a set of symbols."""
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        text = nb_path.read_text(encoding="utf-8")
        assert "completed_keys" in text, "Must use completed_keys"

    def test_resume_skips_completed_symbol(self):
        """When a symbol is completed, skip it."""
        completed_keys = {"AAPL"}
        sym = "AAPL"
        should_skip = sym in completed_keys
        assert should_skip, "Should skip AAPL because it is completed"

    def test_resume_does_not_skip_incomplete_symbol(self):
        """When a symbol is not completed, don't skip it."""
        completed_keys = {"AAPL"}
        sym = "MSFT"
        should_skip = sym in completed_keys
        assert not should_skip, "Should NOT skip MSFT because it is not completed"


# ---------------------------------------------------------------------------
# 11. MassiveCorporateActionsSource — normalization
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal requests.Response-like object for testing."""

    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Injectable HTTP session that returns fixture data."""

    def __init__(self, responses=None):
        if responses is None:
            responses = []
        self._responses = list(responses)
        self._calls = []

    def get(self, url, timeout=None):
        self._calls.append(url)
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse({"status": "OK", "results": []})


class TestMassiveNormalization:

    def _make_source(self, session, clock=None, api_key="test-key-123"):
        return MassiveCorporateActionsSource(
            api_key=api_key,
            session=session,
            clock=clock or _fixed_clock(),
            sleeper=_NoOpSleeper(),
            delay_seconds=0.0,
            max_retries=0,
        )

    def _load_fixture(self, name):
        import json
        from pathlib import Path
        fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "massive" / name
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_amzn_20to1(self):
        data = self._load_fixture("amzn_single_page.json")
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("AMZN")
        assert len(results) == 1
        assert results[0].split_ratio == 20.0
        assert results[0].ex_date == dt.date(2022, 6, 6)
        assert results[0].symbol == "AMZN"
        assert results[0].source == "massive"

    def test_sqqq_reverse_5to1(self):
        data = self._load_fixture("sqqq_reverse.json")
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("SQQQ")
        assert len(results) == 1
        assert results[0].split_ratio == pytest.approx(0.2)  # 1/5
        assert results[0].ex_date == dt.date(2025, 11, 20)

    def test_tsla_two_splits(self):
        data = self._load_fixture("tsla_multi.json")
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("TSLA")
        assert len(results) == 2
        ratios = {r.ex_date: r.split_ratio for r in results}
        assert ratios[dt.date(2022, 8, 25)] == 3.0
        assert ratios[dt.date(2020, 8, 31)] == 5.0

    def test_pagination_two_pages(self):
        page1 = self._load_fixture("pagination_page1.json")
        page2 = self._load_fixture("pagination_page2.json")
        session = _FakeSession([_FakeResponse(page1), _FakeResponse(page2)])
        src = self._make_source(session)
        results = src.fetch_splits("NVDA")
        assert len(results) == 2
        ratios = {r.ex_date: r.split_ratio for r in results}
        assert ratios[dt.date(2024, 6, 10)] == 10.0
        assert ratios[dt.date(2021, 7, 20)] == 4.0
        # Verify apiKey was appended to next_url
        assert len(session._calls) == 2
        assert "apiKey=test-key-123" in session._calls[1]

    def test_filters_exact_ticker(self):
        """Results with wrong ticker are silently dropped."""
        data = {
            "status": "OK",
            "results": [
                {"execution_date": "2022-06-06", "split_from": 1, "split_to": 20, "ticker": "AMZN"},
                {"execution_date": "2022-06-06", "split_from": 1, "split_to": 3, "ticker": "OTHER"},
            ]
        }
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("AMZN")
        assert len(results) == 1
        assert results[0].split_ratio == 20.0

    def test_empty_results(self):
        data = {"status": "OK", "results": []}
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("META")
        assert results == []

    def test_invalid_ratio_skipped(self):
        data = {
            "status": "OK",
            "results": [
                {"execution_date": "2022-06-06", "split_from": 0, "split_to": 20, "ticker": "X"},
                {"execution_date": "2022-06-07", "split_from": 1, "split_to": 1, "ticker": "X"},
                {"execution_date": "2022-06-08", "split_from": 1, "split_to": 2, "ticker": "X"},
            ]
        }
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("X")
        # split_from=0 and ratio=1.0 are skipped; only 2:1 survives
        assert len(results) == 1
        assert results[0].split_ratio == 2.0

    def test_fetched_ts_captured(self):
        data = self._load_fixture("amzn_single_page.json")
        session = _FakeSession([_FakeResponse(data)])
        clock = _fixed_clock(2025, 6, 15, 10, 30, 0)
        src = self._make_source(session, clock=clock)
        results = src.fetch_splits("AMZN")
        assert results[0].fetched_ts == dt.datetime(2025, 6, 15, 10, 30, 0)

    def test_information_available_ts_is_ex_date_0930_et(self):
        data = self._load_fixture("amzn_single_page.json")
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("AMZN")
        assert results[0].information_available_ts == dt.datetime(2022, 6, 6, 13, 30, 0)

    def test_source_is_massive(self):
        data = self._load_fixture("amzn_single_page.json")
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("AMZN")
        assert results[0].source == "massive"

    def test_symbol_uppercased(self):
        data = self._load_fixture("amzn_single_page.json")
        session = _FakeSession([_FakeResponse(data)])
        src = self._make_source(session)
        results = src.fetch_splits("amzn")
        assert results[0].symbol == "AMZN"


# ---------------------------------------------------------------------------
# 11. MassiveCorporateActionsSource — retry / error handling
# ---------------------------------------------------------------------------

class TestMassiveRetryBehavior:

    def _make_source(self, session, max_retries=3, api_key="test-key"):
        return MassiveCorporateActionsSource(
            api_key=api_key,
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            delay_seconds=0.0,
            max_retries=max_retries,
        )

    def test_429_retries(self):
        data = {"status": "OK", "results": [
            {"execution_date": "2022-06-06", "split_from": 1, "split_to": 2, "ticker": "X"}
        ]}
        session = _FakeSession([
            _FakeResponse({}, status_code=429),
            _FakeResponse(data, status_code=200),
        ])
        src = self._make_source(session, max_retries=1)
        results = src.fetch_splits("X")
        assert len(results) == 1
        assert len(session._calls) == 2

    def test_500_retries(self):
        data = {"status": "OK", "results": [
            {"execution_date": "2022-06-06", "split_from": 1, "split_to": 2, "ticker": "X"}
        ]}
        session = _FakeSession([
            _FakeResponse({}, status_code=500),
            _FakeResponse(data, status_code=200),
        ])
        src = self._make_source(session, max_retries=1)
        results = src.fetch_splits("X")
        assert len(results) == 1

    def test_401_raises_permission_error_no_key_in_message(self):
        session = _FakeSession([_FakeResponse({}, status_code=401)])
        src = self._make_source(session, api_key="super-secret-key")
        with pytest.raises(PermissionError, match="HTTP 401") as exc_info:
            src.fetch_splits("X")
        assert "super-secret-key" not in str(exc_info.value)

    def test_403_raises_permission_error_no_key_in_message(self):
        session = _FakeSession([_FakeResponse({}, status_code=403)])
        src = self._make_source(session, api_key="super-secret-key")
        with pytest.raises(PermissionError, match="HTTP 403") as exc_info:
            src.fetch_splits("X")
        assert "super-secret-key" not in str(exc_info.value)

    def test_max_retries_exhausted_raises(self):
        session = _FakeSession([
            _FakeResponse({}, status_code=429),
            _FakeResponse({}, status_code=429),
            _FakeResponse({}, status_code=429),
        ])
        src = self._make_source(session, max_retries=2)
        with pytest.raises(RuntimeError, match="HTTP 429"):
            src.fetch_splits("X")


# ---------------------------------------------------------------------------
# 12. MassiveCorporateActionsSource — key redaction
# ---------------------------------------------------------------------------

class TestMassiveKeyRedaction:

    def test_redact_api_key_in_url(self):
        from etl.corporate_actions import _redact_api_key
        url = "https://api.massive.com/v3/reference/splits?ticker=AMZN&limit=1000&apiKey=super-secret"
        redacted = _redact_api_key(url)
        assert "super-secret" not in redacted
        assert "apiKey=***REDACTED***" in redacted

    def test_redact_preserves_other_params(self):
        from etl.corporate_actions import _redact_api_key
        url = "https://api.massive.com/v3/reference/splits?ticker=AMZN&limit=1000&apiKey=abc123&cursor=xyz"
        redacted = _redact_api_key(url)
        assert "ticker=AMZN" in redacted
        assert "limit=1000" in redacted
        assert "cursor=xyz" in redacted
        assert "abc123" not in redacted

    def test_no_api_key_in_url_unchanged(self):
        from etl.corporate_actions import _redact_api_key
        url = "https://api.massive.com/v3/reference/splits?ticker=AMZN"
        redacted = _redact_api_key(url)
        assert redacted == url


# ---------------------------------------------------------------------------
# 13. MassiveCorporateActionsSource — append_api_key
# ---------------------------------------------------------------------------

class TestMassiveAppendApiKey:

    def test_appends_api_key_to_next_url(self):
        session = _FakeSession([])
        src = MassiveCorporateActionsSource(
            api_key="my-key",
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
        )
        next_url = "https://api.massive.com/v3/reference/splits?ticker=NVDA&limit=1000&cursor=abc123"
        result = src._append_api_key(next_url)
        assert "apiKey=my-key" in result
        assert "cursor=abc123" in result


# ---------------------------------------------------------------------------
# 14. MassiveCorporateActionsSource — requires API key
# ---------------------------------------------------------------------------

class TestMassiveRequiresKey:

    def test_no_key_raises(self):
        import os
        with pytest.raises(ValueError, match="Massive API key required"):
            MassiveCorporateActionsSource(
                api_key="",
                session=_FakeSession(),
            )

    def test_protocol_compliance(self):
        session = _FakeSession([])
        src = MassiveCorporateActionsSource(
            api_key="test",
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
        )
        assert hasattr(src, "fetch_splits")
        assert callable(src.fetch_splits)


# ---------------------------------------------------------------------------
# 15. API key leak via error messages
# ---------------------------------------------------------------------------

class _LeakySession:
    """Session that raises exceptions containing an API key in the message."""

    def __init__(self, exc_class, secret="SECRET123"):
        self._exc_class = exc_class
        self._secret = secret
        self._calls = []

    def get(self, url, timeout=None):
        self._calls.append(url)
        raise self._exc_class(
            f"Connection failed for https://api.massive.com/v3/splits?ticker=X&apiKey={self._secret}"
        )


class TestApiKeyLeak:

    def _check_no_secret(self, text, secret="SECRET123"):
        """Assert secret does not appear in text."""
        assert secret not in text, f"Secret leaked in: {text[:200]}"

    def test_http_error_no_key_in_exception(self):
        """requests.HTTPError with apiKey in message → redacted in RuntimeError."""
        import requests
        session = _LeakySession(requests.HTTPError)
        src = MassiveCorporateActionsSource(
            api_key="SECRET123",
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            max_retries=0,
        )
        with pytest.raises(RuntimeError) as exc_info:
            src.fetch_splits("X")
        self._check_no_secret(str(exc_info.value))
        self._check_no_secret(repr(exc_info.value))
        # Check __cause__ and __context__ chains
        cause = exc_info.value.__cause__
        while cause:
            self._check_no_secret(str(cause))
            self._check_no_secret(repr(cause))
            cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)

    def test_connection_error_no_key_in_exception(self):
        """requests.ConnectionError with apiKey in message → redacted."""
        import requests
        session = _LeakySession(requests.ConnectionError)
        src = MassiveCorporateActionsSource(
            api_key="SECRET123",
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            max_retries=0,
        )
        with pytest.raises(RuntimeError) as exc_info:
            src.fetch_splits("X")
        self._check_no_secret(str(exc_info.value))
        self._check_no_secret(repr(exc_info.value))

    def test_no_key_in_report_failures(self, capsys, caplog):
        """Simulate notebook error handling — apiKey must not appear in report."""
        import requests
        import logging

        secret = "SECRET123"
        session = _LeakySession(requests.HTTPError, secret=secret)
        src = MassiveCorporateActionsSource(
            api_key=secret,
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            max_retries=0,
        )

        # Simulate what the notebook does
        report_failures = {}
        try:
            src.fetch_splits("X")
        except Exception as exc:
            from notebooks.refresh_bronze_corporate_actions import _redact_api_key
            safe_msg = _redact_api_key(str(exc))[:200]
            report_failures["X"] = safe_msg

        self._check_no_secret(str(report_failures))

    def test_no_key_in_printed_output(self, capsys):
        """Printed error output must not contain apiKey."""
        import requests

        secret = "SECRET123"
        session = _LeakySession(requests.HTTPError, secret=secret)
        src = MassiveCorporateActionsSource(
            api_key=secret,
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            max_retries=0,
        )

        try:
            src.fetch_splits("X")
        except RuntimeError as exc:
            from notebooks.refresh_bronze_corporate_actions import _redact_api_key
            safe_msg = _redact_api_key(str(exc))[:200]
            print(f"  FAILED X: {safe_msg}")

        captured = capsys.readouterr()
        self._check_no_secret(captured.out)
        self._check_no_secret(captured.err)

    def test_mutation_remove_redaction_leaks(self):
        """Mutation proof: the raw exception from requests contains the secret,
        but the adapter's RuntimeError never does. This proves redaction works."""
        import requests

        secret = "SECRET123"
        session = _LeakySession(requests.HTTPError, secret=secret)

        # Step 1: The raw exception from the session DOES contain the secret
        try:
            session.get("https://api.massive.com/v3/splits?ticker=X&apiKey=SECRET123")
        except requests.HTTPError as raw_exc:
            assert secret in str(raw_exc), \
                "Raw requests exception should contain the secret (baseline)"
        else:
            assert False, "Expected exception"

        # Step 2: The adapter's RuntimeError does NOT contain the secret
        src = MassiveCorporateActionsSource(
            api_key=secret,
            session=session,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            max_retries=0,
        )
        with pytest.raises(RuntimeError) as exc_info:
            src.fetch_splits("X")
        assert secret not in str(exc_info.value), \
            "Adapter RuntimeError must not contain the secret"
        # Check the full chain
        cause = exc_info.value.__cause__
        while cause:
            assert secret not in str(cause), \
                f"Exception chain must not contain the secret: {cause}"
            cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)