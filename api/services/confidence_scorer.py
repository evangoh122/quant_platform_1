"""
confidence_scorer.py — Phase 5: Confidence Scoring, Routing & Always-Escalate Triggers.
Derives record-level confidence from provenance + XBRL cross-check,
evaluates 8 deterministic always-escalate triggers, and routes to
AUTO / SAMPLED_REVIEW / ESCALATE.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from api.models.eval_types import (
    ExtractionResult, ValidationResult,
    Decision, Route, ReasonCode, Provenance,
)
from api.services.xbrl_cross_validator import (
    cross_validate, CrossValidationResult, PROVENANCE_BASE_SCORE,
)
from api.services.semantic_validator import validate_semantic

TriggerFn = Callable[[ExtractionResult, "ScorerContext"], bool]

@dataclass
class ScorerContext:
    ticker: str = ""
    xbrl_result: CrossValidationResult = field(default_factory=CrossValidationResult)
    is_downstream: bool = False  # True when extraction feeds a user-facing figure or downstream action


def _trigger_balance_sheet_imbalance(result: ExtractionResult, ctx: ScorerContext) -> bool:
    validation = validate_semantic(result, ctx.ticker)
    return ReasonCode.IDENTITY_VIOLATION in validation.reason_codes


def _trigger_amended_filing(result: ExtractionResult, ctx: ScorerContext) -> bool:
    return "/A" in (result.accession or "")


def _trigger_bankruptcy_8k(result: ExtractionResult, ctx: ScorerContext) -> bool:
    if result.form_type != "8-K":
        return False
    for f in result.fields:
        if "1.03" in (f.name or "") and "bankruptcy" in str(f.value or "").lower():
            return True
    return False


def _trigger_non_reliance_8k(result: ExtractionResult, ctx: ScorerContext) -> bool:
    if result.form_type != "8-K":
        return False
    for f in result.fields:
        if "4.02" in (f.name or "") or "non-reliance" in str(f.value or "").lower():
            return True
    return False


def _trigger_auditor_change_8k(result: ExtractionResult, ctx: ScorerContext) -> bool:
    if result.form_type != "8-K":
        return False
    for f in result.fields:
        if "4.01" in (f.name or "") or "auditor" in str(f.value or "").lower():
            return True
    return False


def _trigger_going_concern(result: ExtractionResult, ctx: ScorerContext) -> bool:
    for f in result.fields:
        val = str(f.value or "").lower()
        if "going concern" in val or "substantial doubt" in val:
            return True
    return False


def _trigger_xbrl_mismatch(result: ExtractionResult, ctx: ScorerContext) -> bool:
    return ReasonCode.XBRL_MISMATCH in ctx.xbrl_result.validation.reason_codes


def _trigger_unrecognized_concept(result: ExtractionResult, ctx: ScorerContext) -> bool:
    return ReasonCode.UNKNOWN_CONCEPT in ctx.xbrl_result.validation.reason_codes


def _trigger_out_of_range(result: ExtractionResult, ctx: ScorerContext) -> bool:
    validation = validate_semantic(result, ctx.ticker)
    return ReasonCode.OUT_OF_RANGE in validation.reason_codes


def _trigger_downstream_action(result: ExtractionResult, ctx: ScorerContext) -> bool:
    """Trigger 8: extraction feeds a user-facing financial figure or downstream action."""
    return ctx.is_downstream


# Spec §4.3 lists 8 deterministic always-escalate triggers (CONSTRAINT-004).
# _trigger_out_of_range was implemented but accidentally omitted from this list.
ALL_TRIGGERS: list[tuple[str, TriggerFn]] = [
    ("balance_sheet_imbalance", _trigger_balance_sheet_imbalance),
    ("amended_filing", _trigger_amended_filing),
    ("bankruptcy_8k", _trigger_bankruptcy_8k),
    ("non_reliance_8k", _trigger_non_reliance_8k),
    ("auditor_change_8k", _trigger_auditor_change_8k),
    ("going_concern", _trigger_going_concern),
    ("xbrl_mismatch", _trigger_xbrl_mismatch),
    ("unrecognized_concept", _trigger_unrecognized_concept),
    ("out_of_range", _trigger_out_of_range),          # REQ-CR-04 / spec §4.3
    ("downstream_action", _trigger_downstream_action), # REQ-CR-06: feeds user-facing figure
]


def _get_cut_points() -> dict[str, float]:
    return {
        "high": float(os.getenv("ROUTING_THRESHOLD_HIGH", "0.85")),
        "medium": float(os.getenv("ROUTING_THRESHOLD_MEDIUM", "0.55")),
    }


def score_and_route(
    result: ExtractionResult,
    ticker: str = "",
    is_downstream: bool = False,
) -> Decision:
    xbrl_result = cross_validate(result, ticker)
    semantic_validation = validate_semantic(result, ticker)

    all_reason_codes = list(set(
        list(ValidationResult(is_valid=True).reason_codes)
        + xbrl_result.validation.reason_codes
        + semantic_validation.reason_codes
    ))
    details = {
        **xbrl_result.validation.details,
        **semantic_validation.details,
    }
    base_valid = xbrl_result.validation.is_valid and semantic_validation.is_valid

    ctx = ScorerContext(ticker=ticker, xbrl_result=xbrl_result, is_downstream=is_downstream)
    triggers_fired = [name for name, fn in ALL_TRIGGERS if fn(result, ctx)]

    record_confidence = xbrl_result.record_confidence
    if not xbrl_result.field_confidences:
        record_confidence = PROVENANCE_BASE_SCORE.get(Provenance.NARRATIVE_LLM, 0.55)

    # L4: 10-K/A has 0.0 confidence
    if _trigger_amended_filing(result, ctx) and (not result.fields or record_confidence == 0):
        if ReasonCode.NO_DATA not in all_reason_codes:
            all_reason_codes.append(ReasonCode.NO_DATA)

    cut = _get_cut_points()

    if triggers_fired:
        route = Route.ESCALATE
    elif record_confidence >= cut["high"]:
        route = Route.AUTO
    elif record_confidence >= cut["medium"]:
        route = Route.SAMPLED_REVIEW
    else:
        route = Route.ESCALATE

    validation = ValidationResult(
        is_valid=base_valid and route != Route.ESCALATE,
        reason_codes=all_reason_codes,
        details=details,
    )

    return Decision(
        route=route,
        confidence=record_confidence,
        validation=validation,
        triggers_fired=triggers_fired,
    )


def evaluate_triggers_only(
    result: ExtractionResult,
    ticker: str = "",
    is_downstream: bool = False,
) -> list[str]:
    """Return list of trigger names that fire — for use by shadow runner."""
    ctx = ScorerContext(ticker=ticker, xbrl_result=cross_validate(result, ticker), is_downstream=is_downstream)
    return [name for name, fn in ALL_TRIGGERS if fn(result, ctx)]
