"""sec_kg/model.py — canonical vocabulary, schemas, and identity helpers.

This module is the single source of truth for node types, edge types,
provenance structs, and deterministic ID generation.  It imports without
PySpark, Databricks, OpenAI, LangChain, or network configuration.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple, Union

# ── Node types ───────────────────────────────────────────────────────────────

class NodeType(str, Enum):
    COMPANY = "Company"
    FILING = "Filing"
    SECTION = "Section"
    CHUNK = "Chunk"
    XBRL_FACT = "XbrlFact"
    METRIC = "Metric"
    PERIOD = "Period"
    RISK_FACTOR = "RiskFactor"
    EVENT = "Event"
    SEGMENT = "Segment"
    PRODUCT = "Product"
    CUSTOMER = "Customer"


NODE_TYPES: FrozenSet[str] = frozenset(nt.value for nt in NodeType)

# ── Edge types ───────────────────────────────────────────────────────────────

class EdgeType(str, Enum):
    FILED = "FILED"
    HAS_SECTION = "HAS_SECTION"
    HAS_CHUNK = "HAS_CHUNK"
    REPORTED_FACT = "REPORTED_FACT"
    INSTANCE_OF = "INSTANCE_OF"
    FOR_PERIOD = "FOR_PERIOD"
    SOURCED_FROM = "SOURCED_FROM"
    DISCLOSED_RISK = "DISCLOSED_RISK"
    REPORTED_EVENT = "REPORTED_EVENT"
    HAS_SEGMENT = "HAS_SEGMENT"
    HAS_PRODUCT = "HAS_PRODUCT"
    HAS_CUSTOMER = "HAS_CUSTOMER"
    SUPERSEDES = "SUPERSEDES"


EDGE_TYPES: FrozenSet[str] = frozenset(et.value for et in EdgeType)

# ── Normalisation helpers ────────────────────────────────────────────────────

def normalize_unicode(text: str) -> str:
    """NFKC normalise, strip, collapse whitespace."""
    import unicodedata
    text = unicodedata.normalize("NFKC", text)
    text = text.strip()
    # collapse internal whitespace
    parts = text.split()
    return " ".join(parts)


def normalize_ticker(ticker: str) -> str:
    return normalize_unicode(ticker).upper()


def normalize_cik(cik: str) -> str:
    """Zero-pad CIK to 10 digits."""
    cik = normalize_unicode(cik).lstrip("0")
    return cik.zfill(10)


def normalize_accession(accession: str) -> str:
    return normalize_unicode(accession).upper()


def normalize_unit(unit: str) -> str:
    return normalize_unicode(unit).upper()


def normalize_type_discriminator(disc: str) -> str:
    return normalize_unicode(disc).lower()


def iso_date(date_str: str) -> str:
    """Normalise a date string to ISO format (YYYY-MM-DD)."""
    s = normalize_unicode(date_str)
    if not s:
        return ""
    # already ISO
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    raise ValueError(f"Invalid date format: {date_str!r}")


def epoch_to_utc(epoch: Union[int, float]) -> datetime:
    """Convert epoch seconds to timezone-aware UTC datetime."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Reject naive datetimes; return timezone-aware UTC."""
    if dt.tzinfo is None:
        raise ValueError(
            f"Naive datetime {dt!r} is not allowed; use timezone-aware UTC"
        )
    return dt.astimezone(timezone.utc)


def validate_value(value: Any) -> None:
    """Reject non-finite numeric values."""
    if isinstance(value, float):
        import math
        if not math.isfinite(value):
            raise ValueError(f"Non-finite value: {value}")


# ── Canonical ID generation ─────────────────────────────────────────────────

def _canonical_tuple(*parts: str) -> str:
    """Build a versioned, length-delimited canonical tuple string."""
    segments = [str(len(p)) + ":" + p for p in parts]
    return "|".join(segments)


def _sha256_hex(data: str) -> str:
    """SHA-256 hex digest of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def make_node_id(*parts: str) -> str:
    """Deterministic lowercase SHA-256 node ID from a versioned canonical tuple."""
    tpl = _canonical_tuple(*parts)
    return _sha256_hex(tpl)


def make_edge_id(src_id: str, edge_type: str, dst_id: str,
                 accession: str, source_chunk_id: str,
                 accepted_ts: datetime) -> str:
    """Deterministic edge ID including evidence/version information."""
    ts_iso = ensure_utc(accepted_ts).isoformat()
    tpl = _canonical_tuple("v1", "edge", src_id, edge_type, dst_id,
                           accession, source_chunk_id, ts_iso)
    return _sha256_hex(tpl)


# ── Identity helpers for each entity type ────────────────────────────────────

def company_id(cik: str) -> str:
    return make_node_id("v1", "company", normalize_cik(cik))


def filing_id(cik: str, accession: str) -> str:
    return make_node_id("v1", "filing", normalize_cik(cik),
                        normalize_accession(accession))


def section_id(accession: str, filing_section: str) -> str:
    return make_node_id("v1", "section", normalize_accession(accession),
                        normalize_unicode(filing_section).lower())


def chunk_id_from_parts(chunk_id_or_accession: str) -> str:
    return make_node_id("v1", "chunk", normalize_unicode(chunk_id_or_accession))


def metric_id(canonical_concept: str) -> str:
    return make_node_id("v1", "metric",
                        normalize_unicode(canonical_concept).lower())


def period_id(period_start: str, period_end: str) -> str:
    return make_node_id("v1", "period",
                        iso_date(period_start) if period_start else "",
                        iso_date(period_end))


def xbrl_fact_id(cik: str, accession: str, metric_concept: str,
                 period_start: str, period_end: str, unit: str,
                 canonical_value: str, source_chunk_id: str) -> str:
    return make_node_id(
        "v1", "xbrl_fact",
        normalize_cik(cik),
        normalize_accession(accession),
        normalize_unicode(metric_concept).lower(),
        iso_date(period_start) if period_start else "",
        iso_date(period_end),
        normalize_unit(unit) if unit else "",
        normalize_unicode(canonical_value),
        normalize_unicode(source_chunk_id),
    )


def risk_factor_id(cik: str, accession: str, source_chunk_id: str,
                   normalized_key: str, normalized_value: str) -> str:
    return make_node_id(
        "v1", "risk_factor",
        normalize_cik(cik),
        normalize_accession(accession),
        normalize_unicode(source_chunk_id),
        normalize_unicode(normalized_key).lower(),
        normalize_unicode(normalized_value),
    )


def event_id(cik: str, accession: str, source_chunk_id: str,
             normalized_key: str, normalized_value: str) -> str:
    return make_node_id(
        "v1", "event",
        normalize_cik(cik),
        normalize_accession(accession),
        normalize_unicode(source_chunk_id),
        normalize_unicode(normalized_key).lower(),
        normalize_unicode(normalized_value),
    )


def optional_entity_id(entity_type: str, cik: str, label: str) -> str:
    """Segment/Product/Customer ID."""
    return make_node_id(
        "v1",
        normalize_type_discriminator(entity_type),
        normalize_cik(cik),
        normalize_unicode(label).lower(),
    )


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Provenance:
    accession_number: str
    source_chunk_id: str
    accepted_ts: datetime

    def __post_init__(self):
        if not self.accession_number:
            raise ValueError("Provenance.accession_number must not be blank")
        if not self.source_chunk_id:
            raise ValueError("Provenance.source_chunk_id must not be blank")
        # ensure UTC
        object.__setattr__(self, "accepted_ts", ensure_utc(self.accepted_ts))

    def to_dict(self) -> dict:
        return {
            "accession_number": self.accession_number,
            "source_chunk_id": self.source_chunk_id,
            "accepted_ts": self.accepted_ts.isoformat(),
        }

    def to_struct(self) -> dict:
        """Spark STRUCT-compatible dict."""
        return {
            "accession_number": self.accession_number,
            "source_chunk_id": self.source_chunk_id,
            "accepted_ts": self.accepted_ts,
        }


@dataclass(frozen=True)
class KgNode:
    node_id: str
    node_type: str
    label: str
    properties_json: str
    provenance: Tuple[Provenance, ...]
    build_version: str

    def __post_init__(self):
        if self.node_type not in NODE_TYPES:
            raise ValueError(f"Invalid node_type: {self.node_type!r}")
        if not self.node_id:
            raise ValueError("node_id must not be blank")

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "properties_json": self.properties_json,
            "provenance": [p.to_dict() for p in self.provenance],
            "build_version": self.build_version,
        }


@dataclass(frozen=True)
class KgEdge:
    edge_id: str
    src_id: str
    edge_type: str
    dst_id: str
    valid_from: datetime
    accession_number: str
    source_chunk_id: str
    accepted_ts: datetime
    confidence: Optional[float]
    properties_json: str
    build_version: str

    def __post_init__(self):
        if self.edge_type not in EDGE_TYPES:
            raise ValueError(f"Invalid edge_type: {self.edge_type!r}")
        vf = ensure_utc(self.valid_from)
        at = ensure_utc(self.accepted_ts)
        if vf != at:
            raise ValueError(
                f"valid_from ({vf}) must equal accepted_ts ({at})"
            )
        if not self.accession_number:
            raise ValueError("accession_number must not be blank")
        if not self.source_chunk_id:
            raise ValueError("source_chunk_id must not be blank")

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "src_id": self.src_id,
            "edge_type": self.edge_type,
            "dst_id": self.dst_id,
            "valid_from": self.valid_from.isoformat(),
            "accession_number": self.accession_number,
            "source_chunk_id": self.source_chunk_id,
            "accepted_ts": self.accepted_ts.isoformat(),
            "confidence": self.confidence,
            "properties_json": self.properties_json,
            "build_version": self.build_version,
        }


# ── Deterministic JSON serialisation ────────────────────────────────────────

def deterministic_json(obj: Any) -> str:
    """Compact, sorted-keys JSON for property storage."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=_json_default)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Period grammar ───────────────────────────────────────────────────────────

def parse_period(period_str: str) -> Tuple[str, str]:
    """Parse period string into (period_start, period_end).

    Accepts:
      - 'YYYY-MM-DD' → end date only, start = ''
      - 'YYYY-MM-DD/YYYY-MM-DD' → start/end pair
    """
    s = normalize_unicode(period_str)
    if "/" in s:
        parts = s.split("/", 1)
        start = iso_date(parts[0]) if parts[0] else ""
        end = iso_date(parts[1])
        return (start, end)
    # Single date = end date
    end = iso_date(s)
    return ("", end)


# ── Decimal parsing ─────────────────────────────────────────────────────────

def parse_decimal(value: str) -> Optional[Decimal]:
    """Parse a value as Decimal; return None if not numeric."""
    if not value or not value.strip():
        return None
    try:
        d = Decimal(value.strip())
        if not d.is_finite():
            return None
        return d
    except (InvalidOperation, ValueError):
        return None


# ── Build version ───────────────────────────────────────────────────────────

BUILD_VERSION = "1.0.0"