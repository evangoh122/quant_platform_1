"""
eval_types.py — canonical type contract for the SEC Filing Eval & HITL pipeline.

All pipeline components (reader, validators, scorer, router, dashboard) accept and
emit these types. No ad-hoc dicts or parallel schemas are permitted (REQ-DS-02).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Provenance(str, Enum):
    """Source tier for an extracted field — drives the base confidence score."""
    XBRL = "xbrl"
    STRUCTURED_TABLE = "table"
    NARRATIVE_LLM = "narrative"


class ReasonCode(str, Enum):
    """Machine-readable reason codes emitted by validators."""
    OK = "ok"
    MISSING_FIELD = "missing_field"
    BAD_TYPE = "bad_type"
    OUT_OF_RANGE = "out_of_range"
    IDENTITY_VIOLATION = "identity_violation"
    XBRL_MISMATCH = "xbrl_mismatch"
    UNKNOWN_CONCEPT = "unknown_concept"
    REFERENTIAL = "referential"
    NOVEL_FORM = "novel_form"
    NO_DATA = "no_data"


class Route(str, Enum):
    """Routing tier assigned by the confidence scorer.

    Values are uppercase to match the DB CHECK constraint in review_decisions
    (route IN ('SAMPLED_REVIEW', 'ESCALATE')) and the Pydantic Literal in
    ReviewDecisionIn/Out.  Do not lowercase these without updating the DB schema.
    """
    AUTO = "AUTO"
    SAMPLED_REVIEW = "SAMPLED_REVIEW"
    ESCALATE = "ESCALATE"


# ---------------------------------------------------------------------------
# Field-level container
# ---------------------------------------------------------------------------

@dataclass
class ExtractedField:
    """A single extracted datum with its provenance tag.

    Every field MUST carry a provenance tag — XBRL, STRUCTURED_TABLE, or
    NARRATIVE_LLM. This tag determines the base confidence score (REQ-DS-04).
    """
    name: str
    value: Any
    provenance: Provenance
    concept: Optional[str] = None       # us-gaap concept tag, if applicable
    source_span: Optional[str] = None   # char-offset or XPath hint for traceability


# ---------------------------------------------------------------------------
# Record-level containers
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """The canonical output of the reader/adapter layer for a single filing."""
    cik: str
    accession: str
    form_type: str
    period: Optional[str]
    fields: list[ExtractedField]


@dataclass
class ValidationResult:
    """Output of a validation pass (layer-1 schema or layer-2 semantic)."""
    is_valid: bool
    reason_codes: list[ReasonCode] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class PolygonData:
    """Consolidated Polygon.io metadata and market data for a ticker."""
    ticker: str
    name: str
    description: Optional[str] = None
    last_price: Optional[float] = None
    price_date: Optional[str] = None
    volume: Optional[int] = None


@dataclass
class Decision:
    """Final routing decision produced by the confidence scorer."""
    route: Route
    confidence: float
    validation: ValidationResult
    triggers_fired: list[str] = field(default_factory=list)
