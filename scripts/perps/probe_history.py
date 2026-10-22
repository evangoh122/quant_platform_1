#!/usr/bin/env python3
"""Probe the earliest available perpetual-futures history.

The probe is **not** part of the test suite and never runs on import.  It is
dry-run by default: it prints the requests it would make and touches no
network.  ``--live`` is required to send requests.

Hyperliquid (company and commodity perps, HIP-3)
------------------------------------------------
``POST https://api.hyperliquid.xyz/info`` with::

    {"type": "candleSnapshot",
     "req": {"coin": "xyz:NVDA", "interval": "1h",
             "startTime": <ms>, "endTime": <ms>}}
    {"type": "fundingHistory",
     "coin": "xyz:NVDA", "startTime": <ms>, "endTime": <ms>}

Each stream is paged forward by ``startTime``.  Empty windows are skipped in
``--coarse-days`` steps; the first non-empty window yields the earliest
timestamp.  The response is bounded by ``endTime`` so a page cannot silently
include later data.

Minute bars are the exception: the public API serves only roughly the last
~3.5 days of ``1m`` candles.  Treat ``1m`` as a forward-capture stream (a daily
job) and use ``15m`` / ``1h`` for historical measurement; Binance Vision
archives carry full ``1m`` history for the controls.

Binance USD-M controls
----------------------
``data.binance.vision`` monthly archives are listed for ``klines`` (1h),
``fundingRate`` and ``metrics``; the first available month is then refined to
the first available daily archive.  Downloads are not performed by this probe.

The archive host serves an HTML site, so the probe lists the bucket through the
S3 endpoint (``s3-ap-northeast-1.amazonaws.com/data.binance.vision``) with
``delimiter=/&prefix=``.  The response is an S3 ``ListBucketResult`` XML
document: it uses the S3 namespace, lists ``Contents`` keys (and
``CommonPrefixes`` for directories) and is paged with ``IsTruncated`` /
``NextMarker``.  The probe follows every page before choosing the first month.

Every per-instrument record in the JSON and Markdown report carries
``data_source`` (``hyperliquid`` for the HIP-3 perps, ``binance_um`` for the
Binance USD-M controls).  The code comes from the validated universe row and is
checked against ``config/data_sources.py``, so a report can never label a row
with an unknown or contradictory provider.  Every record also carries
``instrument_type`` from the validated universe row
(``config.perp_universe.INSTRUMENT_TYPE``, i.e. ``perpetual_future``): the
probed instrument is a derivative, never the equity/ETF/spot it tracks.

Open interest
-------------
Hyperliquid's public info API exposes **current** open interest only (via
``metaAndAssetCtxs`` / ``clearinghouseState``).  Historical OI is not available
there; see ``OPEN_INTEREST_NOTE`` for the backfill options presented to the
owner.

Usage::

    python scripts/perps/probe_history.py                  # dry-run plan
    python scripts/perps/probe_history.py --live           # network probe
    python scripts/perps/probe_history.py --live --start 2025-06-01 \
        --out-json docs/data/perps_history_probe.json \
        --out-md docs/data/perps_history_probe.md
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
from xml.etree import ElementTree

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config.data_sources import validate_data_source  # noqa: E402
from config.perp_universe import (  # noqa: E402
    PerpControl,
    PerpUniverse,
    load_perp_universe,
)

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
BINANCE_VISION_URL = "https://data.binance.vision"
#: S3 endpoint behind the archive host; this is the one that serves XML listings
#: (the CDN hostname serves the HTML download site).
BINANCE_VISION_LISTING_URL = (
    "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
)
DEFAULT_OUT_JSON = _REPO_ROOT / "docs" / "data" / "perps_history_probe.json"
DEFAULT_OUT_MD = _REPO_ROOT / "docs" / "data" / "perps_history_probe.md"
DEFAULT_START = "2025-01-01"
DEFAULT_COARSE_DAYS = 60
DEFAULT_MAX_STEPS = 60
DEFAULT_RATE_LIMIT_RPS = 2.0
DEFAULT_RETRIES = 4
DEFAULT_TIMEOUT = 30.0
MAX_RATE_LIMIT_RPS = 2.0
DEFAULT_MAX_LISTING_PAGES = 100

OPEN_INTEREST_NOTE = (
    "Hyperliquid's public info API serves current open interest only "
    "(metaAndAssetCtxs.openInterest, and clearinghouseState for a user); it does "
    "not serve historical OI. Options for the owner: (a) forward snapshots - poll "
    "metaAndAssetCtxs on a schedule into bronze_perp_oi_snapshots (starts when the "
    "poller is deployed; no back-history); (b) backfill from Hyperliquid's published "
    "node-data archive on S3 if the owner enables requester-pays access (verify "
    "licence, retention and egress cost first); (c) use a candle-derived proxy, "
    "which is not OI and must be labelled as such. This probe does not attempt an "
    "OI history fetch."
)

_STREAMS = ("candle_1h", "candle_1d", "funding")
_BINANCE_STREAMS = ("klines_1h", "funding_rate", "metrics")


class ProbeError(RuntimeError):
    """Raised for malformed payloads or exhausted network retries."""


@dataclass(frozen=True)
class ProbeTarget:
    ticker: str
    venue: str
    symbol: str
    kind: str  # "equity_perp" | "commodity_perp" | "control"
    data_source: str

    def __post_init__(self) -> None:
        try:
            validate_data_source(self.data_source)
        except ValueError as exc:
            raise ProbeError(f"{self.ticker}: {exc}") from exc


@dataclass(frozen=True)
class PlannedRequest:
    method: str
    url: str
    body: Optional[Mapping[str, Any]]
    purpose: str
    follow_up: bool = False

    def display(self) -> str:
        suffix = ""
        if self.body is not None:
            suffix = " " + json.dumps(self.body, sort_keys=True)
        note = " [follow-up]" if self.follow_up else ""
        return f"{self.method} {self.url}{suffix}  # {self.purpose}{note}"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def build_targets(universe: PerpUniverse) -> List[ProbeTarget]:
    targets = [
        ProbeTarget(
            ticker=company.ticker,
            venue=company.venue,
            symbol=company.symbol,
            kind="equity_perp",
            data_source=company.data_source,
        )
        for company in universe.companies
    ]
    targets.extend(
        ProbeTarget(
            ticker=commodity.commodity,
            venue=commodity.venue,
            symbol=commodity.symbol,
            kind="commodity_perp",
            data_source=commodity.data_source,
        )
        for commodity in universe.commodities
    )
    targets.extend(
        ProbeTarget(
            ticker=control.symbol,
            venue=control.venue,
            symbol=control.symbol,
            kind="control",
            data_source=control.data_source,
        )
        for control in universe.controls
    )
    return targets


def _start_ms(start: str | date | datetime) -> int:
    if isinstance(start, datetime):
        moment = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    elif isinstance(start, date):
        moment = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    else:
        raw = start.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ProbeError(f"--start must be an ISO date, got {start!r}") from exc
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.astimezone(timezone.utc).timestamp() * 1000)


def hyperliquid_body(
    target: ProbeTarget, stream: str, start_ms: int, end_ms: int
) -> Dict[str, Any]:
    if stream == "funding":
        return {
            "type": "fundingHistory",
            "coin": target.symbol,
            "startTime": start_ms,
            "endTime": end_ms,
        }
    interval = "1h" if stream == "candle_1h" else "1d"
    return {
        "type": "candleSnapshot",
        "req": {
            "coin": target.symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
        },
    }


def _binance_monthly_prefix(symbol: str, stream: str) -> str:
    if stream == "klines_1h":
        return f"data/futures/um/monthly/klines/{symbol}/1h/"
    if stream == "funding_rate":
        return f"data/futures/um/monthly/fundingRate/{symbol}/"
    if stream == "metrics":
        return f"data/futures/um/monthly/metrics/{symbol}/"
    raise ProbeError(f"unknown Binance stream {stream!r}")


def _binance_daily_prefix(monthly_key: str) -> str:
    """Turn a monthly key into the daily prefix for the same stream."""

    return re.sub(r"\d{4}-\d{2}\.zip$", "", monthly_key).replace(
        "/monthly/", "/daily/"
    )


def binance_listing_url(prefix: str, marker: Optional[str] = None) -> str:
    """Return an S3 ``ListBucketResult`` URL for *prefix* (one delimiter level)."""

    url = (
        f"{BINANCE_VISION_LISTING_URL}?delimiter=/&prefix="
        f"{urlparse.quote(prefix, safe='/')}"
    )
    if marker:
        url += f"&marker={urlparse.quote(marker, safe='/')}"
    return url


def plan_requests(
    universe: PerpUniverse,
    *,
    start: str | date | datetime = DEFAULT_START,
) -> List[PlannedRequest]:
    """Return the complete dry-run plan (no network)."""
    start_ms = _start_ms(start)
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    plan: List[PlannedRequest] = []
    for target in build_targets(universe):
        if target.kind in ("equity_perp", "commodity_perp"):
            for stream in _STREAMS:
                plan.append(
                    PlannedRequest(
                        method="POST",
                        url=HYPERLIQUID_INFO_URL,
                        body=hyperliquid_body(target, stream, start_ms, end_ms),
                        purpose=(
                            f"{target.symbol} {stream} first page "
                            "(paged by startTime until non-empty)"
                        ),
                    )
                )
        else:
            symbol = target.symbol
            for stream in _BINANCE_STREAMS:
                prefix = _binance_monthly_prefix(symbol, stream)
                plan.append(
                    PlannedRequest(
                        method="GET",
                        url=binance_listing_url(prefix),
                        body=None,
                        purpose=f"{symbol} {stream} monthly archive listing",
                    )
                )
            for stream in _BINANCE_STREAMS:
                prefix = _binance_monthly_prefix(symbol, stream)
                plan.append(
                    PlannedRequest(
                        method="GET",
                        url=binance_listing_url(prefix + "{first-month}-"),
                        body=None,
                        purpose=(
                            f"{symbol} {stream} daily listing for the first month"
                        ),
                        follow_up=True,
                    )
                )
    return plan


# ---------------------------------------------------------------------------
# Payload parsing (pure; exercised by the tests)
# ---------------------------------------------------------------------------

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProbeError(f"{field} must be an integer, got {value!r}") from exc


def _as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProbeError(f"{field} must be numeric, got {value!r}") from exc


def parse_candles(payload: Any) -> List[Dict[str, Any]]:
    """Normalise a ``candleSnapshot`` response page."""
    _require(isinstance(payload, list), "candleSnapshot payload must be a list")
    candles: List[Dict[str, Any]] = []
    for index, raw in enumerate(payload):
        _require(isinstance(raw, Mapping), f"candle[{index}] must be an object")
        for key in ("t", "T", "s", "i", "o", "h", "l", "c", "v"):
            _require(key in raw, f"candle[{index}] missing {key!r}")
        candles.append(
            {
                "start_ms": _as_int(raw["t"], f"candle[{index}].t"),
                "end_ms": _as_int(raw["T"], f"candle[{index}].T"),
                "symbol": str(raw["s"]),
                "interval": str(raw["i"]),
                "open": _as_float(raw["o"], f"candle[{index}].o"),
                "high": _as_float(raw["h"], f"candle[{index}].h"),
                "low": _as_float(raw["l"], f"candle[{index}].l"),
                "close": _as_float(raw["c"], f"candle[{index}].c"),
                "volume": _as_float(raw["v"], f"candle[{index}].v"),
                "trades": _as_int(raw.get("n", 0), f"candle[{index}].n"),
            }
        )
    return candles


def parse_funding(payload: Any) -> List[Dict[str, Any]]:
    """Normalise a ``fundingHistory`` response page."""
    _require(isinstance(payload, list), "fundingHistory payload must be a list")
    records: List[Dict[str, Any]] = []
    for index, raw in enumerate(payload):
        _require(isinstance(raw, Mapping), f"funding[{index}] must be an object")
        for key in ("coin", "fundingRate", "time"):
            _require(key in raw, f"funding[{index}] missing {key!r}")
        records.append(
            {
                "coin": str(raw["coin"]),
                "time_ms": _as_int(raw["time"], f"funding[{index}].time"),
                "funding_rate": _as_float(
                    raw["fundingRate"], f"funding[{index}].fundingRate"
                ),
                "premium": (
                    _as_float(raw["premium"], f"funding[{index}].premium")
                    if raw.get("premium") is not None
                    else None
                ),
            }
        )
    return records


def earliest_timestamp(
    records: Sequence[Mapping[str, Any]], key: str
) -> Optional[int]:
    """Return the smallest ``key`` across *records* (``None`` when empty)."""
    if not records:
        return None
    values: List[int] = []
    for index, record in enumerate(records):
        _require(key in record, f"record[{index}] missing {key!r}")
        values.append(_as_int(record[key], f"record[{index}].{key}"))
    return min(values)


def _iso_utc(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


_ZIP_KEY_RE = re.compile(r"(?:<Key>|href=[\"'])(?P<key>[^<\"']+?\.zip)")


@dataclass(frozen=True)
class BinanceListingPage:
    """One page of an S3 ``ListBucketResult`` listing."""

    keys: Tuple[str, ...]
    common_prefixes: Tuple[str, ...]
    truncated: bool
    next_marker: Optional[str]


def _local_name(tag: str) -> str:
    """Return an XML tag without its ``{namespace}`` prefix."""

    return tag.rsplit("}", 1)[-1]


def parse_binance_listing_page(text: str) -> BinanceListingPage:
    """Parse one namespaced S3 ``ListBucketResult`` page.

    Element names are compared by local name so the S3 default namespace
    (``http://s3.amazonaws.com/doc/2006-03-01/``) cannot hide ``Contents`` or
    ``CommonPrefixes``.  Pagination state is returned to the caller.
    """

    _require(isinstance(text, str) and text.strip(), "listing payload must be text")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ProbeError(f"listing is not valid XML: {exc}") from exc
    _require(
        _local_name(root.tag) == "ListBucketResult",
        f"unexpected listing document <{_local_name(root.tag)}>",
    )

    keys: List[str] = []
    common_prefixes: List[str] = []
    truncated = False
    next_marker: Optional[str] = None
    for element in root:
        name = _local_name(element.tag)
        if name == "Contents":
            for child in element:
                if _local_name(child.tag) == "Key" and child.text:
                    keys.append(child.text.strip())
        elif name == "CommonPrefixes":
            for child in element:
                if _local_name(child.tag) == "Prefix" and child.text:
                    common_prefixes.append(child.text.strip())
        elif name == "IsTruncated" and element.text:
            truncated = element.text.strip().lower() == "true"
        elif name == "NextMarker" and element.text:
            next_marker = element.text.strip()
    return BinanceListingPage(
        keys=tuple(keys),
        common_prefixes=tuple(common_prefixes),
        truncated=truncated,
        next_marker=next_marker,
    )


def _normalise_listing_key(raw: str) -> str:
    """Turn a listing ``Key`` or HTML href into a bucket-relative key."""

    raw = raw.split("?")[0].strip()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
        raw = raw.split("/", 1)[1] if "/" in raw else raw
    marker = raw.find("data/")
    if marker > 0:
        raw = raw[marker:]
    return urlparse.unquote(raw.lstrip("/"))


def _is_xml_listing(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("<?xml") or stripped.startswith("<ListBucketResult")


def parse_binance_listing(text: str, prefix: str = "") -> List[str]:
    """Extract sorted ``.zip`` archive keys from an S3 XML or HTML listing.

    XML pages are parsed with :func:`parse_binance_listing_page` (namespace
    aware); the HTML fallback covers the archive site's download pages.
    """

    _require(isinstance(text, str), "listing payload must be text")
    if _is_xml_listing(text):
        raw_keys: Sequence[str] = parse_binance_listing_page(text).keys
    else:
        raw_keys = [match.group("key") for match in _ZIP_KEY_RE.finditer(text)]
    keys = set()
    for raw in raw_keys:
        key = _normalise_listing_key(raw)
        if not key.endswith(".zip"):
            continue
        if prefix and not key.startswith(prefix):
            continue
        keys.add(key)
    return sorted(keys)


def fetch_binance_listing(client: Any, prefix: str, *, _depth: int = 0) -> List[str]:
    """Fetch every page of the S3 listing for *prefix* and return ``.zip`` keys.

    Follows ``IsTruncated``/``NextMarker`` until the last page.  A truncated
    page without ``NextMarker`` is an error (fail closed, never silently drop
    archives).  When a parent prefix returns only ``CommonPrefixes`` the
    function descends one level so a listing cannot come back empty merely
    because the caller passed a directory instead of a dataset prefix.
    """

    keys = set()
    marker: Optional[str] = None
    common_prefixes: List[str] = []
    for _ in range(DEFAULT_MAX_LISTING_PAGES):
        text = client.get_text(binance_listing_url(prefix, marker))
        if not _is_xml_listing(text):
            keys.update(parse_binance_listing(text, prefix))
            break
        page = parse_binance_listing_page(text)
        keys.update(parse_binance_listing(text, prefix))
        common_prefixes.extend(page.common_prefixes)
        if not page.truncated:
            break
        _require(
            bool(page.next_marker),
            f"{prefix}: truncated listing without NextMarker",
        )
        _require(
            page.next_marker != marker,
            f"{prefix}: pagination did not advance past {marker!r}",
        )
        marker = page.next_marker
    else:
        raise ProbeError(
            f"{prefix}: listing did not finish within "
            f"{DEFAULT_MAX_LISTING_PAGES} pages"
        )

    if not keys and common_prefixes and _depth < 1:
        for child in sorted(set(common_prefixes)):
            if not child.startswith(prefix):
                continue
            keys.update(fetch_binance_listing(client, child, _depth=_depth + 1))
    return sorted(keys)


def _month_of(key: str) -> Optional[str]:
    match = re.search(r"(\d{4}-\d{2})\.zip$", key)
    return match.group(1) if match else None


def _day_of(key: str) -> Optional[str]:
    match = re.search(r"(\d{4}-\d{2}-\d{2})\.zip$", key)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Network client
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple minimum-interval limiter (default 2 requests/second)."""

    def __init__(self, max_rps: float = DEFAULT_RATE_LIMIT_RPS) -> None:
        if max_rps <= 0:
            raise ProbeError("--rate-limit must be > 0")
        if max_rps > MAX_RATE_LIMIT_RPS:
            raise ProbeError(
                f"--rate-limit must be <= {MAX_RATE_LIMIT_RPS} requests/second "
                "(polite-use cap)"
            )
        self.min_interval = 1.0 / max_rps
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delay = self.min_interval - (now - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


class HttpClient:
    """Minimal stdlib HTTP client with rate limiting and retry/backoff.

    Retries use exponential backoff **plus jitter** so parallel probes do not
    retry a rate limit in lockstep; ``rng`` is injectable for tests.
    """

    def __init__(
        self,
        *,
        max_rps: float = DEFAULT_RATE_LIMIT_RPS,
        retries: int = DEFAULT_RETRIES,
        backoff_seconds: float = 1.0,
        jitter_fraction: float = 0.5,
        timeout: float = DEFAULT_TIMEOUT,
        limiter: Optional[RateLimiter] = None,
        rng: Optional[random.Random] = None,
        urlopen: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.jitter_fraction = min(max(0.0, jitter_fraction), 1.0)
        self.timeout = timeout
        self.limiter = limiter or RateLimiter(max_rps)
        self._rng = rng or random.Random()
        self._urlopen = urlopen or urlrequest.urlopen

    def post_json(self, url: str, body: Mapping[str, Any]) -> Any:
        raw = self._request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"{url}: invalid JSON response: {exc}") from exc

    def get_text(self, url: str) -> str:
        return self._request(url)

    def _request(
        self,
        url: str,
        *,
        data: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> str:
        request_headers = {
            "User-Agent": "quant-platform-perps-probe/1.0",
            **(headers or {}),
        }
        last_error: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            self.limiter.wait()
            request = urlrequest.Request(
                url,
                data=data,
                headers=dict(request_headers),
                method="POST" if data is not None else "GET",
            )
            try:
                with self._urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8")
            except urlerror.HTTPError as exc:
                last_error = exc
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt >= self.retries:
                    raise ProbeError(
                        f"{url}: HTTP {exc.code} {exc.reason}"
                    ) from exc
                delay = self._delay(attempt)
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
                time.sleep(delay)
            except (urlerror.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise ProbeError(f"{url}: {type(exc).__name__}: {exc}") from exc
                time.sleep(self._delay(attempt))
        raise ProbeError(f"{url}: exhausted retries ({last_error})")

    def _delay(self, attempt: int) -> float:
        """Exponential backoff with upward-only jitter (never shortens a wait)."""
        base = self.backoff_seconds * (2 ** attempt)
        return base * (1.0 + self._rng.random() * self.jitter_fraction)


# ---------------------------------------------------------------------------
# Live probing
# ---------------------------------------------------------------------------

def find_first_hyperliquid(
    client: Any,
    target: ProbeTarget,
    stream: str,
    *,
    start_ms: int,
    now_ms: int,
    coarse_days: int = DEFAULT_COARSE_DAYS,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> Dict[str, Any]:
    """Page forward until the first non-empty window; return its earliest ts."""
    parser = parse_candles if stream.startswith("candle_") else parse_funding
    key = "start_ms" if stream.startswith("candle_") else "time_ms"
    step_ms = max(1, coarse_days) * 24 * 60 * 60 * 1000
    cursor = start_ms
    requests = 0
    for _ in range(max_steps):
        if cursor > now_ms:
            break
        end = min(cursor + step_ms - 1, now_ms)
        body = hyperliquid_body(target, stream, cursor, end)
        payload = client.post_json(HYPERLIQUID_INFO_URL, body)
        requests += 1
        records = parser(payload)
        first = earliest_timestamp(records, key)
        if first is not None:
            return {
                "first_ms": first,
                "first_iso": _iso_utc(first),
                "requests": requests,
                "window_start_ms": cursor,
                "window_end_ms": end,
                "records_in_first_page": len(records),
                "truncated": False,
            }
        if end >= now_ms:
            break
        cursor = end + 1
    return {
        "first_ms": None,
        "first_iso": None,
        "requests": requests,
        "window_start_ms": start_ms,
        "window_end_ms": now_ms,
        "records_in_first_page": 0,
        "truncated": True,
    }


def probe_binance(client: Any, control: PerpControl) -> Dict[str, Any]:
    """Find the first monthly and daily archive for each control stream."""
    out: Dict[str, Any] = {}
    symbol = control.symbol
    for stream in _BINANCE_STREAMS:
        prefix = _binance_monthly_prefix(symbol, stream)
        monthly_keys = fetch_binance_listing(client, prefix)
        if not monthly_keys:
            out[stream] = {"error": "no monthly archives", "prefix": prefix}
            continue
        first_key = monthly_keys[0]
        month = _month_of(first_key)
        daily_prefix = _binance_daily_prefix(first_key)
        daily_keys = fetch_binance_listing(client, daily_prefix)
        first_day = _day_of(daily_keys[0]) if daily_keys else None
        out[stream] = {
            "first_month": month,
            "first_monthly_key": first_key,
            "monthly_archives": len(monthly_keys),
            "first_day": first_day,
            "first_daily_key": daily_keys[0] if daily_keys else None,
            "daily_archives_in_first_month": len(daily_keys),
        }
    return out


def probe_live(
    universe: PerpUniverse,
    *,
    start: str,
    coarse_days: int,
    max_steps: int,
    client: Any,
    rate_limit_rps: float = DEFAULT_RATE_LIMIT_RPS,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    start_ms = _start_ms(start)
    result: Dict[str, Any] = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": "live",
        "probe": {
            "start": _iso_utc(start_ms),
            "coarse_days": coarse_days,
            "max_steps": max_steps,
            "rate_limit_rps": rate_limit_rps,
        },
        "hyperliquid": {
            "endpoint": HYPERLIQUID_INFO_URL,
            "instruments": [],
            "commodities": [],
        },
        "binance_usdm": {"endpoint": BINANCE_VISION_URL, "instruments": []},
        "notes": {"open_interest": OPEN_INTEREST_NOTE},
    }
    for company in universe.companies:
        target = ProbeTarget(
            ticker=company.ticker,
            venue=company.venue,
            symbol=company.symbol,
            kind="equity_perp",
            data_source=company.data_source,
        )
        entry: Dict[str, Any] = {
            "ticker": company.ticker,
            "venue": company.venue,
            "instrument_type": company.instrument_type,
            "data_source": company.data_source,
            "dex": company.dex,
            "symbol": company.symbol,
            "tier": company.tier,
            "streams": {},
        }
        for stream in _STREAMS:
            try:
                entry["streams"][stream] = find_first_hyperliquid(
                    client,
                    target,
                    stream,
                    start_ms=start_ms,
                    now_ms=now_ms,
                    coarse_days=coarse_days,
                    max_steps=max_steps,
                )
            except ProbeError as exc:
                entry["streams"][stream] = {"error": str(exc)}
        result["hyperliquid"]["instruments"].append(entry)

    for commodity in universe.commodities:
        target = ProbeTarget(
            ticker=commodity.commodity,
            venue=commodity.venue,
            symbol=commodity.symbol,
            kind="commodity_perp",
            data_source=commodity.data_source,
        )
        entry = {
            "commodity": commodity.commodity,
            "venue": commodity.venue,
            "instrument_type": commodity.instrument_type,
            "data_source": commodity.data_source,
            "dex": commodity.dex,
            "symbol": commodity.symbol,
            "tier": commodity.tier,
            "etfs": list(commodity.etfs),
            "etf_kind": commodity.etf_kind,
            "streams": {},
        }
        for stream in _STREAMS:
            try:
                entry["streams"][stream] = find_first_hyperliquid(
                    client,
                    target,
                    stream,
                    start_ms=start_ms,
                    now_ms=now_ms,
                    coarse_days=coarse_days,
                    max_steps=max_steps,
                )
            except ProbeError as exc:
                entry["streams"][stream] = {"error": str(exc)}
        result["hyperliquid"]["commodities"].append(entry)

    for control in universe.controls:
        entry = {
            "ticker": control.symbol,
            "venue": control.venue,
            "instrument_type": control.instrument_type,
            "data_source": control.data_source,
            "symbol": control.symbol,
            "streams": {},
        }
        try:
            entry["streams"] = probe_binance(client, control)
        except ProbeError as exc:
            entry["streams"] = {"error": str(exc)}
        result["binance_usdm"]["instruments"].append(entry)
    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(value: Optional[str]) -> str:
    return value if value else "n/a"


def render_markdown(result: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Perp history probe")
    lines.append("")
    lines.append(f"- Generated: {result.get('generated_at', 'unknown')}")
    lines.append(f"- Mode: {result.get('mode', 'unknown')}")
    probe = result.get("probe", {})
    lines.append(
        f"- Hyperliquid start floor: {probe.get('start')} "
        f"(coarse window {probe.get('coarse_days')} days, "
        f"max {probe.get('max_steps')} steps)"
    )
    lines.append(
        "- `n/a` means the probe did not find data within the configured floor/"
        "step budget; it does not prove the instrument has no history."
    )
    lines.append("")
    lines.append("## Hyperliquid HIP-3 equity perpetuals")
    lines.append("")
    lines.append(
        "| Ticker | Symbol | Tier | Data source | Instrument type | First 1h candle | First 1d candle | First funding |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for entry in result.get("hyperliquid", {}).get("instruments", []):
        streams = entry.get("streams", {})
        def field(stream: str, key: str = "first_iso") -> str:
            value = (streams.get(stream) or {}).get(key)
            return _fmt(value)
        lines.append(
            f"| {entry.get('ticker')} | `{entry.get('symbol')}` | "
            f"{entry.get('tier')} | {_fmt(entry.get('data_source'))} | "
            f"{_fmt(entry.get('instrument_type'))} | "
            f"{field('candle_1h')} | "
            f"{field('candle_1d')} | {field('funding')} |"
        )
    lines.append("")
    lines.append("## Hyperliquid HIP-3 commodity perpetuals")
    lines.append("")
    lines.append(
        "| Commodity | Symbol | Tier | Data source | Instrument type | ETF wrapper | First 1h candle | First 1d candle | First funding |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for entry in result.get("hyperliquid", {}).get("commodities", []):
        streams = entry.get("streams", {})
        def field(stream: str, key: str = "first_iso") -> str:
            value = (streams.get(stream) or {}).get(key)
            return _fmt(value)
        wrapper = ", ".join(entry.get("etfs") or []) or "n/a"
        lines.append(
            f"| {entry.get('commodity')} | `{entry.get('symbol')}` | "
            f"{entry.get('tier')} | {_fmt(entry.get('data_source'))} | "
            f"{_fmt(entry.get('instrument_type'))} | "
            f"{wrapper} ({entry.get('etf_kind')}) | "
            f"{field('candle_1h')} | {field('candle_1d')} | {field('funding')} |"
        )
    lines.append("")
    lines.append("## Binance USD-M controls")
    lines.append("")
    lines.append(
        "| Symbol | Data source | Instrument type | Klines 1h first day | Funding first day | Metrics first day |"
    )
    lines.append("|---|---|---|---|---|---|")
    for entry in result.get("binance_usdm", {}).get("instruments", []):
        streams = entry.get("streams", {})
        def day(stream: str) -> str:
            value = (streams.get(stream) or {}).get("first_day")
            return _fmt(value)
        lines.append(
            f"| {entry.get('symbol')} | {_fmt(entry.get('data_source'))} | "
            f"{_fmt(entry.get('instrument_type'))} | "
            f"{day('klines_1h')} | "
            f"{day('funding_rate')} | {day('metrics')} |"
        )
    lines.append("")
    lines.append("## Open interest")
    lines.append("")
    lines.append(OPEN_INTEREST_NOTE)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_plan(plan: Sequence[PlannedRequest], universe: PerpUniverse) -> None:
    print("mode: dry-run (no network; pass --live to probe)")
    print(
        f"targets: {universe.company_count} equity perps + "
        f"{universe.commodity_count} commodity perps + "
        f"{universe.control_count} Binance controls"
    )
    print(
        f"planned requests: {len(plan)} "
        "(Hyperliquid requests are the first page of a startTime-paged stream)"
    )
    print("")
    for index, request in enumerate(plan, start=1):
        print(f"{index:3d}. {request.display()}")
    print("")
    print("open interest: current-only in the public Hyperliquid info API")
    print(OPEN_INTEREST_NOTE)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--live",
        action="store_true",
        help="actually send requests (default is a dry-run plan)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned requests and exit (default)",
    )
    parser.add_argument("--start", default=DEFAULT_START, help="Hyperliquid probe floor")
    parser.add_argument(
        "--coarse-days",
        type=int,
        default=DEFAULT_COARSE_DAYS,
        help="size of each startTime window while searching for the first record",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help="maximum windows per stream before declaring the floor exhausted",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT_RPS,
        help=f"requests/second (<= {MAX_RATE_LIMIT_RPS})",
    )
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    args = parser.parse_args(argv)

    if args.live and args.dry_run:
        parser.error("--live and --dry-run are mutually exclusive")

    universe = load_perp_universe()
    if not args.live:
        try:
            plan = plan_requests(universe, start=args.start)
        except ProbeError as exc:
            parser.error(str(exc))
        _print_plan(plan, universe)
        return 0

    if args.coarse_days <= 0:
        parser.error("--coarse-days must be > 0")
    if args.max_steps <= 0:
        parser.error("--max-steps must be > 0")
    try:
        limiter = RateLimiter(args.rate_limit)
    except ProbeError as exc:
        parser.error(str(exc))

    client = HttpClient(
        max_rps=args.rate_limit,
        retries=args.retries,
        timeout=args.timeout,
        limiter=limiter,
    )
    try:
        result = probe_live(
            universe,
            start=args.start,
            coarse_days=args.coarse_days,
            max_steps=args.max_steps,
            client=client,
            rate_limit_rps=args.rate_limit,
        )
    except ProbeError as exc:
        print(f"probe failed: {exc}", file=sys.stderr)
        return 2
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(result), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
