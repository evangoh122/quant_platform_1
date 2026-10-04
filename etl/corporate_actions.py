"""etl/corporate_actions.py — corporate-action ingestion.

Defines an immutable normalized split record and a source protocol so that
providers (Massive, …) can be swapped without changing downstream
normalization or Bronze writing logic.

Import-safe: no Spark, dbutils, or network calls at module level.  All I/O
happens inside adapter methods that accept injectable dependencies.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import time as _time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Sequence
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse


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
# Massive adapter
# ---------------------------------------------------------------------------

_MASSIVE_BASE_URL = "https://api.massive.com/v3/reference/splits"

# Pattern to detect apiKey= in URLs for redaction.
_APIKEY_RE = re.compile(r"(apiKey=)[^&\s]+")


def _redact_api_key(url: str) -> str:
    """Redact apiKey value in a URL for safe logging."""
    return _APIKEY_RE.sub(r"\g<1>***REDACTED***", url)


class MassiveCorporateActionsSource:
    """Massive REST API-backed split source.

    Constructor accepts injectable dependencies so tests can inject fakes::

        MassiveCorporateActionsSource(
            api_key="test-key",
            session=fake_session,
            clock=lambda: dt.datetime(2025, 1, 1, 12, 0, 0),
            sleeper=lambda secs: None,
        )

    Production defaults use ``requests.Session``, wall clock, and
    ``time.sleep``.  The API key is read from the ``MASSIVE_API_KEY``
    env var if not explicitly provided.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        session: Any = None,
        clock: Optional[Callable[[], dt.datetime]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        delay_seconds: float = 1.0,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("MASSIVE_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Massive API key required: pass api_key or set MASSIVE_API_KEY env var"
            )
        if session is not None:
            self._session = session
        else:
            import requests
            self._session = requests.Session()
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
        self._sleeper = sleeper or _time.sleep
        self._delay = max(delay_seconds, 0.5)
        self._max_retries = max(0, max_retries)
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_splits(self, symbol: str) -> list[CorporateActionSplit]:
        """Fetch and normalize all splits for *symbol* from Massive API.

        Follows ``next_url`` pagination.  Filters results to exact
        ``ticker == symbol`` (defensive).  Skips invalid ratios.
        """
        raw = self._fetch_all_pages(symbol)
        fetched_ts = self._clock()
        out: list[CorporateActionSplit] = []
        for row in raw:
            if not self._is_valid_ratio(row.get("split_ratio")):
                continue
            ex_date = row.get("ex_date")
            if not isinstance(ex_date, dt.date):
                continue
            try:
                avail = information_available_ts_for(ex_date)
            except Exception:
                continue
            out.append(CorporateActionSplit(
                symbol=symbol.upper().strip(),
                ex_date=ex_date,
                split_ratio=float(row["split_ratio"]),
                source="massive",
                fetched_ts=fetched_ts,
                information_available_ts=avail,
            ))
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_all_pages(self, symbol: str) -> list[dict]:
        """Fetch all pages of splits for *symbol*, returning normalized rows."""
        url = f"{_MASSIVE_BASE_URL}?{urlencode({'ticker': symbol, 'limit': 1000, 'apiKey': self._api_key})}"
        all_rows: list[dict] = []

        while url:
            data = self._request_with_retry(url)
            results = data.get("results", [])
            for item in results:
                # Defensive: filter to exact ticker
                if item.get("ticker", "").upper().strip() != symbol.upper().strip():
                    continue
                normalized = self._normalize_item(item)
                if normalized is not None:
                    all_rows.append(normalized)
            # Pagination: next_url does NOT include apiKey; append it
            next_url = data.get("next_url")
            if next_url:
                url = self._append_api_key(next_url)
            else:
                url = None

        return all_rows

    def _request_with_retry(self, url: str) -> dict:
        """Execute GET with retry on 429/5xx.  Raise on 401/403."""
        redacted_url = _redact_api_key(url)
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._session.get(url, timeout=self._timeout)
                if resp.status_code == 401 or resp.status_code == 403:
                    raise PermissionError(
                        f"Massive API auth error (HTTP {resp.status_code}). "
                        "Check your API key."
                    )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = RuntimeError(
                        f"Massive API HTTP {resp.status_code}"
                    )
                    if attempt < self._max_retries:
                        backoff = min(2 ** attempt * 1.0, 30.0)
                        self._sleeper(backoff)
                        continue
                    raise last_exc
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Massive API HTTP {resp.status_code} from {redacted_url}"
                    )
                return resp.json()
            except (PermissionError, RuntimeError):
                raise
            except Exception:
                if attempt < self._max_retries:
                    backoff = min(2 ** attempt * 1.0, 30.0)
                    self._sleeper(backoff)
                    continue
                raise RuntimeError(
                    f"Massive API request failed after "
                    f"{self._max_retries + 1} attempts: "
                    f"HTTP error from {redacted_url}"
                ) from None
        return {}  # unreachable

    def _append_api_key(self, url: str) -> str:
        """Append apiKey to next_url (Massive omits it from next_url)."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params["apiKey"] = [self._api_key]
        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    @staticmethod
    def _normalize_item(item: dict) -> Optional[dict]:
        """Normalize a Massive API result row.

        Returns dict with ``ex_date`` (date) and ``split_ratio`` (float),
        or None if the row is invalid.
        """
        exec_date_str = item.get("execution_date")
        split_from = item.get("split_from")
        split_to = item.get("split_to")

        if not exec_date_str or split_from is None or split_to is None:
            return None

        try:
            ex_date = dt.date.fromisoformat(str(exec_date_str))
        except (ValueError, TypeError):
            return None

        try:
            sf = float(split_from)
            st = float(split_to)
        except (TypeError, ValueError):
            return None

        if sf <= 0 or not math.isfinite(sf):
            return None

        split_ratio = st / sf
        if not math.isfinite(split_ratio) or split_ratio <= 0 or split_ratio == 1.0:
            return None

        return {"ex_date": ex_date, "split_ratio": split_ratio}

    @staticmethod
    def _is_valid_ratio(ratio: Any) -> bool:
        """Accept only finite, positive, non-one ratios."""
        try:
            r = float(ratio)
        except (TypeError, ValueError):
            return False
        return math.isfinite(r) and r > 0 and r != 1.0