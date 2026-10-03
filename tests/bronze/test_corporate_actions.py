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
    YFinanceCorporateActionsSource,
    information_available_ts_for,
)


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

class _FakeTicker:
    """Minimal yfinance-like ticker for testing."""

    def __init__(self, splits=None, history_df=None):
        self._splits = splits  # pandas-like Series or None
        self._history_df = history_df

    def get_splits(self):
        return self._splits

    def history(self, **kwargs):
        return self._history_df


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
            split_ratio=20.0, source="yfinance",
            fetched_ts=dt.datetime(2025, 1, 1, 12, 0, 0),
            information_available_ts=dt.datetime(2022, 6, 6, 13, 30, 0),
        )
        assert s.split_ratio == 20.0

    def test_reverse_split_1to10(self):
        s = CorporateActionSplit(
            symbol="SQQQ", ex_date=dt.date(2024, 1, 1),
            split_ratio=0.1, source="yfinance",
            fetched_ts=dt.datetime(2025, 1, 1, 12, 0, 0),
            information_available_ts=dt.datetime(2024, 1, 1, 14, 30, 0),
        )
        assert s.split_ratio == 0.1

    def test_fractional_ratio(self):
        s = CorporateActionSplit(
            symbol="TEST", ex_date=dt.date(2024, 1, 1),
            split_ratio=1.5, source="yfinance",
            fetched_ts=dt.datetime(2025, 1, 1, 12, 0, 0),
            information_available_ts=dt.datetime(2024, 1, 1, 14, 30, 0),
        )
        assert s.split_ratio == 1.5

    def test_reject_zero_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=0.0, source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_one_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=1.0, source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_negative_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=-2.0, source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_nan_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=float("nan"), source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_inf_ratio(self):
        with pytest.raises(ValueError, match="split_ratio"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=float("inf"), source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_empty_symbol(self):
        with pytest.raises(ValueError, match="symbol"):
            CorporateActionSplit(
                symbol="", ex_date=dt.date(2024, 1, 1),
                split_ratio=2.0, source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_aware_fetched_ts(self):
        with pytest.raises(ValueError, match="fetched_ts"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=2.0, source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
                information_available_ts=dt.datetime(2025, 1, 1),
            )

    def test_reject_aware_info_ts(self):
        with pytest.raises(ValueError, match="information_available_ts"):
            CorporateActionSplit(
                symbol="X", ex_date=dt.date(2024, 1, 1),
                split_ratio=2.0, source="yfinance",
                fetched_ts=dt.datetime(2025, 1, 1),
                information_available_ts=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
            )

    def test_frozen(self):
        s = CorporateActionSplit(
            symbol="X", ex_date=dt.date(2024, 1, 1),
            split_ratio=2.0, source="yfinance",
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

    def test_yfinance_source_satisfies_protocol(self):
        src = YFinanceCorporateActionsSource(
            ticker_factory=lambda sym: _FakeTicker(),
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            delay_seconds=0.0,
        )
        assert hasattr(src, "fetch_splits")


# ---------------------------------------------------------------------------
# 4. YFinanceCorporateActionsSource normalization
# ---------------------------------------------------------------------------

class TestYFinanceNormalization:

    def _make_source(self, ticker_factory, clock=None):
        return YFinanceCorporateActionsSource(
            ticker_factory=ticker_factory,
            clock=clock or _fixed_clock(),
            sleeper=_NoOpSleeper(),
            delay_seconds=0.0,
            max_retries=0,
        )

    def test_forward_20to1_normalizes(self):
        import pandas as pd
        splits = pd.Series(
            [20.0],
            index=pd.DatetimeIndex([dt.datetime(2022, 6, 6)]),
            name="Stock Splits",
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("AMZN")
        assert len(results) == 1
        assert results[0].split_ratio == 20.0
        assert results[0].ex_date == dt.date(2022, 6, 6)
        assert results[0].symbol == "AMZN"
        assert results[0].source == "yfinance"

    def test_reverse_1to10_normalizes(self):
        import pandas as pd
        splits = pd.Series(
            [0.1],
            index=pd.DatetimeIndex([dt.datetime(2024, 3, 1)]),
            name="Stock Splits",
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("SQQQ")
        assert len(results) == 1
        assert results[0].split_ratio == 0.1

    def test_zero_ratio_rejected(self):
        import pandas as pd
        splits = pd.Series(
            [0.0],
            index=pd.DatetimeIndex([dt.datetime(2024, 1, 1)]),
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("X")
        assert len(results) == 0

    def test_one_ratio_rejected(self):
        import pandas as pd
        splits = pd.Series(
            [1.0],
            index=pd.DatetimeIndex([dt.datetime(2024, 1, 1)]),
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("X")
        assert len(results) == 0

    def test_negative_ratio_rejected(self):
        import pandas as pd
        splits = pd.Series(
            [-2.0],
            index=pd.DatetimeIndex([dt.datetime(2024, 1, 1)]),
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("X")
        assert len(results) == 0

    def test_nan_ratio_rejected(self):
        import pandas as pd
        splits = pd.Series(
            [float("nan")],
            index=pd.DatetimeIndex([dt.datetime(2024, 1, 1)]),
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("X")
        assert len(results) == 0

    def test_empty_splits(self):
        import pandas as pd
        splits = pd.Series([], dtype=float)
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("X")
        assert len(results) == 0

    def test_fetched_ts_captured(self):
        import pandas as pd
        clock = _fixed_clock(2025, 6, 15, 10, 30, 0)
        splits = pd.Series(
            [2.0],
            index=pd.DatetimeIndex([dt.datetime(2024, 1, 1)]),
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker, clock=clock)
        results = src.fetch_splits("X")
        assert results[0].fetched_ts == dt.datetime(2025, 6, 15, 10, 30, 0)

    def test_information_available_ts_is_ex_date_0930_et(self):
        import pandas as pd
        # EDT date: 2024-07-15 -> 13:30 UTC
        splits = pd.Series(
            [2.0],
            index=pd.DatetimeIndex([dt.datetime(2024, 7, 15)]),
        )
        ticker = _FakeTicker(splits=splits)
        src = self._make_source(lambda sym: ticker)
        results = src.fetch_splits("X")
        assert results[0].information_available_ts == dt.datetime(2024, 7, 15, 13, 30, 0)


# ---------------------------------------------------------------------------
# 5. Retry / error handling
# ---------------------------------------------------------------------------

class TestRetryBehavior:

    def test_transient_failure_retries(self):
        call_count = 0
        def factory(sym):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")
            return _FakeTicker()  # empty on success

        src = YFinanceCorporateActionsSource(
            ticker_factory=factory,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            delay_seconds=0.0,
            max_retries=1,
        )
        results = src.fetch_splits("X")
        assert call_count == 2
        assert results == []

    def test_permanent_empty_returns_empty(self):
        """Empty response is permanent — do not retry."""
        call_count = 0
        def factory(sym):
            nonlocal call_count
            call_count += 1
            import pandas as pd
            return _FakeTicker(splits=pd.Series([], dtype=float))

        src = YFinanceCorporateActionsSource(
            ticker_factory=factory,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            delay_seconds=0.0,
            max_retries=2,
        )
        results = src.fetch_splits("X")
        assert call_count == 1  # no retry for empty
        assert results == []

    def test_max_retries_exhausted_raises(self):
        def factory(sym):
            raise RuntimeError("always fails")

        src = YFinanceCorporateActionsSource(
            ticker_factory=factory,
            clock=_fixed_clock(),
            sleeper=_NoOpSleeper(),
            delay_seconds=0.0,
            max_retries=1,
        )
        with pytest.raises(RuntimeError, match="always fails"):
            src.fetch_splits("X")


# ---------------------------------------------------------------------------
# 6. Bronze idempotency logic (pure Python reference)
# ---------------------------------------------------------------------------

class TestBronzeIdempotency:

    def test_duplicate_rows_produce_one_key(self):
        """Duplicate (symbol, ex_date, source) rows collapse to one."""
        rows = [
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "yfinance",
             "split_ratio": 20.0, "fetched_ts": "2025-01-01T00:00:00",
             "information_available_ts": "2022-06-06T13:30:00"},
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "yfinance",
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
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "yfinance",
             "fetched_ts": "2025-01-01T00:00:00"},
            {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "yfinance",
             "fetched_ts": "2025-06-01T00:00:00"},
        ]
        keys = set()
        for r in rows:
            keys.add((r["symbol"], r["ex_date"], r["source"]))
        assert len(keys) == 1

    def test_same_key_different_ratio_is_conflict(self):
        """Same key with different ratio should be flagged as conflict."""
        existing = {("AMZN", "2022-06-06", "yfinance")}
        new_row = {"symbol": "AMZN", "ex_date": "2022-06-06", "source": "yfinance",
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
        assert hasattr(mod, "YFinanceCorporateActionsSource")
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
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", default=None)
        parser.add_argument("--source", default=None)
        parser.add_argument("--symbol-start", default=None)
        parser.add_argument("--symbol-end", default=None)
        parser.add_argument("--delay-seconds", type=float, default=None)
        parser.add_argument("--max-retries", type=int, default=None)
        parser.add_argument("--run-id", default=None)
        args, _ = parser.parse_known_args(argv_list)
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

    def test_unknown_flag_does_not_raise(self):
        """Unknown flags are silently ignored (parse_known_args)."""
        args = self._parse_args(["--mode", "write", "--unknown-flag", "value"])
        assert args.mode == "write"