"""
shadow_runner.py — Phase 6: Shadow Deployment & Calibration.
Runs the full eval pipeline read-only over historical filings,
producing a calibration report with confidence histograms and
agreement-rate statistics.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from api.models.eval_types import ExtractionResult, Decision, Route
from api.services.schema_validator import validate_extraction
from api.services.semantic_validator import validate_semantic
from api.services.confidence_scorer import score_and_route


@dataclass
class FilingResult:
    cik: str
    accession: str
    form_type: str
    decision: Decision
    schema_valid: bool
    semantic_valid: bool
    error: Optional[str] = None


@dataclass
class CalibrationReport:
    total_processed: int = 0
    errors: int = 0
    auto_count: int = 0
    sampled_review_count: int = 0
    escalation_count: int = 0
    confidence_histogram: dict[str, int] = field(default_factory=dict)
    trigger_counts: dict[str, int] = field(default_factory=dict)
    # agreement_rate is populated externally by the calibration service after
    # reviewer verdicts are available (review_queue.compute_agreement_rate).
    # The shadow runner operates on raw ExtractionResult objects before any
    # human review, so it cannot compute this metric itself.
    agreement_rate: Optional[float] = None
    filings: list[FilingResult] = field(default_factory=list)
    recommendations: dict[str, float] = field(default_factory=dict)


def run_shadow_pipeline(
    extractions: list[ExtractionResult],
    ticker: str = "",
) -> CalibrationReport:
    report = CalibrationReport()
    report.total_processed = len(extractions)

    for result in extractions:
        try:
            schema_result = validate_extraction(result)
            semantic_result = validate_semantic(result, ticker)
            decision = score_and_route(result, ticker)

            fr = FilingResult(
                cik=result.cik,
                accession=result.accession,
                form_type=result.form_type,
                decision=decision,
                schema_valid=schema_result.is_valid,
                semantic_valid=semantic_result.is_valid,
            )

            if decision.route == Route.AUTO:
                report.auto_count += 1
            elif decision.route == Route.SAMPLED_REVIEW:
                report.sampled_review_count += 1
            else:
                report.escalation_count += 1

            bucket = _confidence_bucket(decision.confidence)
            report.confidence_histogram[bucket] = report.confidence_histogram.get(bucket, 0) + 1

            for trigger in decision.triggers_fired:
                report.trigger_counts[trigger] = report.trigger_counts.get(trigger, 0) + 1

            report.filings.append(fr)
            logger.info(
                "Shadow: {} {} -> {} (conf={:.2f}, triggers={})",
                result.cik, result.form_type, decision.route.value, decision.confidence,
                decision.triggers_fired,
            )

        except Exception as e:
            logger.error("Shadow error for {} {}: {}", result.cik, result.accession, e)
            report.errors += 1

    report.recommendations = _derive_recommendations(report)
    return report


def _confidence_bucket(score: float) -> str:
    if score >= 0.90:
        return "0.90-1.00"
    elif score >= 0.80:
        return "0.80-0.89"
    elif score >= 0.70:
        return "0.70-0.79"
    elif score >= 0.60:
        return "0.60-0.69"
    elif score >= 0.50:
        return "0.50-0.59"
    elif score >= 0.00:
        return "0.00-0.49"
    return "0.00"


def _derive_recommendations(report: CalibrationReport) -> dict[str, float]:
    total = report.total_processed or 1
    escalation_rate = report.escalation_count / total * 100

    return {
        "escalation_rate_pct": round(escalation_rate, 2),
        "auto_count": report.auto_count,
        "sampled_review_count": report.sampled_review_count,
        "escalation_count": report.escalation_count,
        "total_processed": report.total_processed,
        "errors": report.errors,
    }


def report_to_json(report: CalibrationReport) -> str:
    return json.dumps({
        "total_processed": report.total_processed,
        "errors": report.errors,
        "auto_count": report.auto_count,
        "sampled_review_count": report.sampled_review_count,
        "escalation_count": report.escalation_count,
        "confidence_histogram": report.confidence_histogram,
        "trigger_counts": report.trigger_counts,
        "recommendations": report.recommendations,
    }, indent=2)
