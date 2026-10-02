"""
xbrl_cross_validator.py — Phase 3: XBRL Cross-Validation.
Compares extracted field values against SEC XBRL facts, producing
field-level confidence scores and XBRL_MISMATCH reason codes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from api.models.eval_types import (
    ExtractionResult, Provenance, ReasonCode, ValidationResult,
)
from api.services.xbrl_client import get_fact

PROVENANCE_BASE_SCORE: dict[Provenance, float] = {
    Provenance.XBRL: 0.98,
    Provenance.STRUCTURED_TABLE: 0.85,
    Provenance.NARRATIVE_LLM: 0.55,
}

@dataclass
class FieldConfidence:
    name: str
    confidence: float
    matched_xbrl: bool = False
    xbrl_value: Optional[float] = None
    claimed_value: Optional[float] = None
    reason_code: Optional[ReasonCode] = None

@dataclass
class CrossValidationResult:
    field_confidences: list[FieldConfidence] = field(default_factory=list)
    validation: ValidationResult = field(default_factory=lambda: ValidationResult(is_valid=True))
    record_confidence: float = 0.0

    def min_confidence(self) -> float:
        if not self.field_confidences:
            return 0.0
        return min(f.confidence for f in self.field_confidences)


def cross_validate(
    result: ExtractionResult,
    ticker: str = "",
) -> CrossValidationResult:
    field_confidences: list[FieldConfidence] = []
    reason_codes: list[ReasonCode] = []
    details: dict = {}

    for field in result.fields:
        fc = FieldConfidence(
            name=field.name,
            confidence=PROVENANCE_BASE_SCORE.get(field.provenance, 0.5),
        )

        if not isinstance(field.value, (int, float)):
            field_confidences.append(fc)
            continue

        if not field.concept:
            field_confidences.append(fc)
            continue

        period = result.period or ""
        xbrl_fact = get_fact(
            cik=result.cik,
            concept=field.concept,
            period_end=period,
            ticker=ticker,
        )

        if xbrl_fact is None:
            field_confidences.append(fc)
            continue

        fc.xbrl_value = xbrl_fact.value
        fc.claimed_value = float(field.value)

        delta = abs(fc.claimed_value - xbrl_fact.value) / max(abs(xbrl_fact.value), 1.0)

        if delta <= 0.01:
            fc.confidence = 1.0
            fc.matched_xbrl = True
        else:
            fc.confidence = 0.0
            fc.matched_xbrl = False
            fc.reason_code = ReasonCode.XBRL_MISMATCH
            reason_codes.append(ReasonCode.XBRL_MISMATCH)
            details[field.name] = {
                "xbrl": xbrl_fact.value,
                "extracted": fc.claimed_value,
                "delta_pct": f"{delta:.2%}",
            }

        field_confidences.append(fc)

    is_valid = len(reason_codes) == 0
    validation = ValidationResult(
        is_valid=is_valid,
        reason_codes=reason_codes,
        details=details,
    )

    record_confidence = 0.0
    if field_confidences:
        record_confidence = min(f.confidence for f in field_confidences)

    return CrossValidationResult(
        field_confidences=field_confidences,
        validation=validation,
        record_confidence=record_confidence,
    )


def lookup_xbrl_fact_exists(cik: str, concept: str, period: str) -> bool:
    """Check if an XBRL fact exists for a given concept — used by triggers."""
    fact = get_fact(cik, concept, period)
    return fact is not None
