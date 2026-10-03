"""Deterministic alias resolver — resolves natural-language mentions to canonical entities."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from importlib import resources
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import yaml

from analytics_nl.contracts import (
    AliasResolutionEnvelope,
    AliasResolutionStatus,
    AliasResolutionTrace,
    EntityType,
    IndexEntity,
    SEMANTIC_MODEL_VERSION,
    SectorEntity,
    TickerEntity,
)

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SQL_METACHAR_RE = re.compile(r"[;'\"]|--|/\*|\*/")
_MULTI_SENTENCE_RE = re.compile(r"[.!?]\s+[A-Z]")


class Clock(Protocol):
    """Protocol for injectable clock."""

    def now(self) -> datetime: ...


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(ZoneInfo("America/New_York"))


@dataclass(frozen=True)
class AliasResult:
    status: AliasResolutionStatus
    canonical_entity: TickerEntity | SectorEntity | IndexEntity | None = None
    matched_alias: str | None = None
    source: str | None = None
    reason_code: str | None = None


def _normalize(text: str) -> str:
    """Normalize text: NFKC, strip control chars, collapse whitespace, casefold."""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_CHAR_RE.sub("", text)
    text = " ".join(text.split())
    return text.casefold()


def _reject_hostile(text: str) -> str | None:
    """Return reason code if text contains hostile patterns, else None."""
    if _CONTROL_CHAR_RE.search(text):
        return "control_characters"
    if _SQL_METACHAR_RE.search(text):
        return "sql_metacharacters"
    if _MULTI_SENTENCE_RE.search(text):
        return "multi_sentence_injection"
    return None


class AliasResolver:
    """Deterministic alias resolver with injected clock for relative dates."""

    def __init__(
        self,
        ticker_symbols: set[str],
        alias_data: dict[str, Any],
        clock: Clock | None = None,
    ) -> None:
        self._tickers = ticker_symbols
        self._clock: Clock = clock or _SystemClock()
        self._registry_version = alias_data.get("version", "1.0.0")

        # Build lookup tables
        self._index_aliases: dict[str, tuple[str, str]] = {}
        self._company_aliases: dict[str, tuple[str, EntityType]] = {}
        self._sector_aliases: dict[str, tuple[str, EntityType]] = {}

        for alias, info in alias_data.get("indices", {}).items():
            normalized = _normalize(alias)
            self._index_aliases[normalized] = (info["canonical_id"], info.get("description", ""))

        for alias, info in alias_data.get("companies", {}).items():
            normalized = _normalize(alias)
            self._company_aliases[normalized] = (info["canonical_id"], EntityType(info["entity_type"]))

        for alias, info in alias_data.get("sectors", {}).items():
            normalized = _normalize(alias)
            self._sector_aliases[normalized] = (info["canonical_id"], EntityType(info["entity_type"]))

        # Metric aliases
        self._metric_aliases: dict[str, str] = {}
        for alias, info in alias_data.get("metric_aliases", {}).items():
            normalized = _normalize(alias)
            self._metric_aliases[normalized] = info["canonical_metric"]

    def resolve(self, text: str) -> AliasResult:
        """Resolve a single text mention to a canonical entity."""
        # Reject hostile input
        hostile_reason = _reject_hostile(text)
        if hostile_reason:
            return AliasResult(
                status=AliasResolutionStatus.rejected,
                reason_code=hostile_reason,
            )

        normalized = _normalize(text)

        # Check if it's already a canonical ticker
        if text in self._tickers:
            return AliasResult(
                status=AliasResolutionStatus.success,
                canonical_entity=TickerEntity(canonical_id=text),
                matched_alias=text,
                source="ticker_direct",
            )

        # Check index aliases
        if normalized in self._index_aliases:
            canonical_id, _ = self._index_aliases[normalized]
            return AliasResult(
                status=AliasResolutionStatus.success,
                canonical_entity=IndexEntity(canonical_id=canonical_id),
                matched_alias=normalized,
                source="index_alias",
            )

        # Check company aliases
        if normalized in self._company_aliases:
            canonical_id, entity_type = self._company_aliases[normalized]
            if entity_type == EntityType.ticker:
                return AliasResult(
                    status=AliasResolutionStatus.success,
                    canonical_entity=TickerEntity(canonical_id=canonical_id),
                    matched_alias=normalized,
                    source="company_alias",
                )

        # Check sector aliases
        if normalized in self._sector_aliases:
            canonical_id, entity_type = self._sector_aliases[normalized]
            return AliasResult(
                status=AliasResolutionStatus.success,
                canonical_entity=SectorEntity(canonical_id=canonical_id),
                matched_alias=normalized,
                source="sector_alias",
            )

        # Unknown
        return AliasResult(
            status=AliasResolutionStatus.unknown,
            reason_code="no_match",
        )

    def resolve_metric(self, text: str) -> str | None:
        """Resolve a metric name or alias to its canonical metric value.

        Returns the canonical metric string (e.g. "put_call_ratio") or None
        if no match.  Also accepts direct canonical metric names.
        """
        normalized = _normalize(text)
        # Direct canonical name
        from analytics_nl.contracts import Metric
        for m in Metric:
            if _normalize(m.value) == normalized:
                return m.value
        # Alias lookup
        return self._metric_aliases.get(normalized)


def load_alias_data() -> dict[str, Any]:
    """Load alias data from YAML."""
    ref = resources.files("analytics_nl.data").joinpath("aliases_v1.yaml")
    text = ref.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_ticker_symbols() -> set[str]:
    """Load ticker symbols from config/tickers.yaml and config/universe.yaml."""
    symbols: set[str] = set()

    # Load from config/tickers.yaml
    try:
        ref = resources.files("config").joinpath("tickers.yaml")
        text = ref.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        for group in data.get("groups", {}).values():
            for ticker in group.get("tickers", []):
                if isinstance(ticker, str):
                    symbols.add(ticker)
    except (FileNotFoundError, TypeError):
        pass

    # Load from config/universe.yaml
    try:
        ref = resources.files("config").joinpath("universe.yaml")
        text = ref.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        for sym in data.get("symbols", []):
            if isinstance(sym, str):
                symbols.add(sym)
    except (FileNotFoundError, TypeError):
        pass

    return symbols


def resolve_relative_date(
    relative: str,
    as_of: date | None = None,
    clock: Clock | None = None,
) -> tuple[date, date] | None:
    """Resolve relative date expressions.

    Supports 'last month' and 'YTD'. Uses injected clock or as_of date.
    Returns (start, end) or None if unrecognized.
    """
    normalized = _normalize(relative)
    tz = ZoneInfo("America/New_York")

    if as_of is not None:
        current_date = as_of
    else:
        c = clock or _SystemClock()
        current_date = c.now().date()

    if normalized == "last month":
        # Prior calendar month inclusive
        if current_date.month == 1:
            start = date(current_date.year - 1, 12, 1)
            end = date(current_date.year - 1, 12, 31)
        else:
            from calendar import monthrange
            start = date(current_date.year, current_date.month - 1, 1)
            _, last_day = monthrange(current_date.year, current_date.month - 1)
            end = date(current_date.year, current_date.month - 1, last_day)
        return (start, end)

    if normalized == "ytd":
        # Jan 1 through current date inclusive
        start = date(current_date.year, 1, 1)
        end = current_date
        return (start, end)

    return None


def build_trace(
    original_input: str,
    normalized_input: str,
    resolver_kind: str,
    result: AliasResult,
) -> AliasResolutionTrace:
    """Build a trace record from resolution result."""
    return AliasResolutionTrace(
        original_input=original_input[:200],
        normalized_input=normalized_input[:200],
        registry_version=SEMANTIC_MODEL_VERSION,
        resolver_kind=resolver_kind,
        status=result.status,
        canonical_entity=result.canonical_entity,
        matched_alias=result.matched_alias,
        source=result.source,
        reason_code=result.reason_code,
    )