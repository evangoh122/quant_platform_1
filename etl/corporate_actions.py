"""etl/corporate_actions.py — source-neutral corporate-action ingestion.

Defines an immutable normalized split record and a source protocol so that
providers (yfinance, Polygon, …) can be swapped without changing downstream
normalization or Bronze writing logic.

Import-safe: no Spark, dbutils, or network calls at module level.  All I/O
happens inside adapter methods that accept injectable dependencies.
"""
from __future__ import annotations

import datetime as dt
import math
import time as _time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Sequence


# ---------------------------------------------------------------------------
# Normalized record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CorporateActionSplit:
    """Immutable corporate-action split record.

    ``split_ratio`` is new-shares / old-shares:  20.0 for a 20:1 forward
    split, 0.1 for a 1:10 reverse split.  Fractional ratios are preserved
    exactly as ``float`` (DOUBLE in the warehouse).
    """
    symbol: str
    ex_date: dt.date
    split_ratio: float
    source: str
    fetched_ts: dt.datetime       # naive UTC
    information_available_ts: dt.datetime  # naive UTC

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not isinstance(self.ex_date, dt.date):
            raise TypeError(f"ex_date must be a date, got {type(self.ex_date)}")
        if not math.isfinite(self.split_ratio) or self.split_ratio <= 0 or self.split_ratio == 1.0:
            raise ValueError(
                f"split_ratio must be finite, positive, and != 1.0; got {self.split_ratio}"
            )
        if self.fetched_ts.tzinfo is not None:
            raise ValueError("fetched_ts must be naive UTC (no tzinfo)")
        if self.information_available_ts.tzinfo is not None:
            raise ValueError("information_available_ts must be naive UTC (no tzinfo)")


# ---------------------------------------------------------------------------
# Source protocol
# ---------------------------------------------------------------------------

class CorporateActionsSource(Protocol):
    """Protocol that every corporate-action source adapter must satisfy."""

    def fetch_splits(self, symbol: str) -> list[CorporateActionSplit]:
        """Return all known splits for *symbol*, normalized."""
        ...


# ---------------------------------------------------------------------------
# Helpers — timezone / availability
# ---------------------------------------------------------------------------

def information_available_ts_for(ex_date: dt.date) -> dt.datetime:
    """Return the naive-UTC timestamp at which a split becomes available.

    Conservative assumption: market open on the ex-date, i.e. 09:30
    America/New_York, converted to UTC respecting DST.
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # Python < 3.9 backport
        from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

    ny = ZoneInfo("America/New_York")
    local = dt.datetime(ex_date.year, ex_date.month, ex_date.day, 9, 30, 0, tzinfo=ny)
    utc = local.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return utc


# ---------------------------------------------------------------------------
# yfinance adapter
# ---------------------------------------------------------------------------

# Minimum delay between consecutive yfinance requests (seconds).
_MIN_DELAY = 0.5


class YFinanceCorporateActionsSource:
    """yfinance-backed split source.

    Constructor accepts injectable dependencies so tests can inject fakes::

        YFinanceCorporateActionsSource(
            ticker_factory=lambda sym: fake_ticker,
            clock=lambda: dt.datetime(2025, 1, 1, 12, 0, 0),
            sleeper=lambda secs: None,
            delay_seconds=0.0,
            max_retries=2,
        )

    Production defaults use the real ``yfinance`` library, wall clock, and
    ``time.sleep``.
    """

    def __init__(
        self,
        ticker_factory: Optional[Callable[[str], Any]] = None,
        clock: Optional[Callable[[], dt.datetime]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        delay_seconds: float = _MIN_DELAY,
        max_retries: int = 2,
    ) -> None:
        if ticker_factory is not None:
            self._ticker_factory = ticker_factory
        else:
            import yfinance as _yf
            self._ticker_factory = lambda sym: _yf.Ticker(sym)
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
        self._sleeper = sleeper or _time.sleep
        self._delay = max(delay_seconds, _MIN_DELAY)
        self._max_retries = max(0, max_retries)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_splits(self, symbol: str) -> list[CorporateActionSplit]:
        """Fetch and normalize all splits for *symbol*.

        Uses ``get_splits()`` when available, otherwise falls back to
        ``history(period="max", actions=True, auto_adjust=False)`` and
        extracts the ``Stock Splits`` column.  Never infers a split from
        price data.  Never consumes yfinance ``Adj Close``.
        """
        raw = self._fetch_raw_splits(symbol)
        fetched_ts = self._clock()
        out: list[CorporateActionSplit] = []
        for ex_date, ratio in raw:
            if not self._is_valid_ratio(ratio):
                continue
            try:
                avail = information_available_ts_for(ex_date)
            except Exception:
                continue
            out.append(CorporateActionSplit(
                symbol=symbol.upper().strip(),
                ex_date=ex_date,
                split_ratio=float(ratio),
                source="yfinance",
                fetched_ts=fetched_ts,
                information_available_ts=avail,
            ))
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_raw_splits(self, symbol: str) -> list[tuple[dt.date, float]]:
        """Return ``[(ex_date, ratio), …]`` from the yfinance provider.

        Retries transient failures with exponential back-off; does **not**
        retry clearly permanent empty/not-found responses.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                ticker = self._ticker_factory(symbol)

                # Preferred: dedicated get_splits() (yfinance >= 0.2.31)
                if hasattr(ticker, "get_splits"):
                    try:
                        splits_df = ticker.get_splits()
                        if splits_df is not None and not splits_df.empty:
                            return self._parse_splits_series(splits_df)
                    except Exception:
                        pass  # fall through to history-based extraction

                # Fallback: full history with actions
                hist = ticker.history(period="max", actions=True, auto_adjust=False)
                if hist is None or hist.empty:
                    return []  # permanent empty — do not retry
                if "Stock Splits" not in hist.columns:
                    return []
                splits_col = hist["Stock Splits"]
                splits_col = splits_col[splits_col != 0].dropna()
                if splits_col.empty:
                    return []
                return self._parse_splits_series(splits_col)

            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    backoff = min(2 ** attempt * 0.5, 8.0)
                    self._sleeper(backoff)
                    continue
                raise RuntimeError(
                    f"yfinance fetch_splits failed for {symbol} after "
                    f"{self._max_retries + 1} attempts: {last_exc}"
                ) from last_exc
        return []  # unreachable, but satisfies type checker

    @staticmethod
    def _parse_splits_series(series: Any) -> list[tuple[dt.date, float]]:
        """Convert a pandas Series (index=date, values=ratio) to a list."""
        out: list[tuple[dt.date, float]] = []
        for idx, val in series.items():
            if hasattr(idx, "date"):
                d = idx.date()
            elif isinstance(idx, dt.date):
                d = idx
            else:
                continue
            try:
                ratio = float(val)
            except (TypeError, ValueError):
                continue
            out.append((d, ratio))
        return out

    @staticmethod
    def _is_valid_ratio(ratio: Any) -> bool:
        """Accept only finite, positive, non-one ratios."""
        try:
            r = float(ratio)
        except (TypeError, ValueError):
            return False
        return math.isfinite(r) and r > 0 and r != 1.0