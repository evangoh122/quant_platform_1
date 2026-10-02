"""
test_eval_pipeline.py — Unit tests for the Phase 2-7 eval pipeline services.

Covers:
  - schema_validator      (Phase 2)
  - xbrl_cross_validator  (Phase 3)
  - semantic_validator    (Phase 4)
  - confidence_scorer     (Phase 5)
  - shadow_runner         (Phase 6)
  - review_queue DB layer (Phase 8)
"""
from __future__ import annotations

from unittest.mock import patch

import duckdb
import pytest

from api.models.eval_types import (
    Decision, ExtractionResult, ExtractedField, Provenance,
    ReasonCode, Route, ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    cik: str = "0000320193",
    accession: str = "0000320193-23-000106",
    form_type: str = "10-K",
    period: str = "2023-09-30",
    fields: list[ExtractedField] | None = None,
) -> ExtractionResult:
    if fields is None:
        fields = [
            ExtractedField("Revenues",           390_756_000_000.0, Provenance.XBRL, "Revenues"),
            ExtractedField("NetIncomeLoss",        96_995_000_000.0, Provenance.XBRL, "NetIncomeLoss"),
            ExtractedField("Assets",              352_583_000_000.0, Provenance.XBRL, "Assets"),
            ExtractedField("Liabilities",         290_437_000_000.0, Provenance.XBRL, "Liabilities"),
            ExtractedField("StockholdersEquity",   62_146_000_000.0, Provenance.XBRL, "StockholdersEquity"),
            ExtractedField("OperatingIncomeLoss", 114_301_000_000.0, Provenance.XBRL, "OperatingIncomeLoss"),
        ]
    return ExtractionResult(cik=cik, accession=accession, form_type=form_type, period=period, fields=fields)


# ---------------------------------------------------------------------------
# schema_validator
# ---------------------------------------------------------------------------

class TestSchemaValidator:
    def test_valid_10k_passes(self):
        from api.services.schema_validator import validate_extraction
        result = validate_extraction(_make_result())
        assert result.is_valid is True
        assert result.reason_codes == []

    def test_missing_required_field(self):
        from api.services.schema_validator import validate_extraction
        result = _make_result(fields=[
            ExtractedField("Revenues", 100_000_000.0, Provenance.XBRL),
        ])
        vr = validate_extraction(result)
        assert vr.is_valid is False
        assert ReasonCode.MISSING_FIELD in vr.reason_codes

    def test_bad_cik_format(self):
        from api.services.schema_validator import validate_extraction
        result = _make_result(cik="NOT-A-CIK")
        vr = validate_extraction(result)
        assert ReasonCode.BAD_TYPE in vr.reason_codes

    def test_bad_accession_format(self):
        from api.services.schema_validator import validate_extraction
        result = _make_result(accession="bad-accession")
        vr = validate_extraction(result)
        assert ReasonCode.BAD_TYPE in vr.reason_codes

    def test_non_numeric_field_value(self):
        from api.services.schema_validator import validate_extraction
        fields = [
            ExtractedField("Revenues", "not-a-number", Provenance.XBRL),
            ExtractedField("NetIncomeLoss",       96_995_000_000.0, Provenance.XBRL),
            ExtractedField("Assets",             352_583_000_000.0, Provenance.XBRL),
            ExtractedField("Liabilities",        290_437_000_000.0, Provenance.XBRL),
            ExtractedField("StockholdersEquity",  62_146_000_000.0, Provenance.XBRL),
            ExtractedField("OperatingIncomeLoss",114_301_000_000.0, Provenance.XBRL),
        ]
        vr = validate_extraction(_make_result(fields=fields))
        assert ReasonCode.BAD_TYPE in vr.reason_codes

    def test_scale_confusion_detected(self):
        """A monetary XBRL field with value < $10,000 should trigger OUT_OF_RANGE."""
        from api.services.schema_validator import validate_extraction
        fields = [
            ExtractedField("Revenues",            1_234.0, Provenance.XBRL, "Revenues"),  # suspicious
            ExtractedField("NetIncomeLoss",       96_995_000_000.0, Provenance.XBRL),
            ExtractedField("Assets",             352_583_000_000.0, Provenance.XBRL),
            ExtractedField("Liabilities",        290_437_000_000.0, Provenance.XBRL),
            ExtractedField("StockholdersEquity",  62_146_000_000.0, Provenance.XBRL),
            ExtractedField("OperatingIncomeLoss",114_301_000_000.0, Provenance.XBRL),
        ]
        vr = validate_extraction(_make_result(fields=fields))
        assert ReasonCode.OUT_OF_RANGE in vr.reason_codes
        assert "scale_warnings" in vr.details

    def test_scale_check_ignores_non_monetary_fields(self):
        """EPS or share-count fields should not trigger the scale check."""
        from api.services.schema_validator import validate_extraction
        fields = [
            ExtractedField("EarningsPerShareBasic", 6.13, Provenance.XBRL),
            ExtractedField("Revenues",           390_756_000_000.0, Provenance.XBRL),
            ExtractedField("NetIncomeLoss",       96_995_000_000.0, Provenance.XBRL),
            ExtractedField("Assets",             352_583_000_000.0, Provenance.XBRL),
            ExtractedField("Liabilities",        290_437_000_000.0, Provenance.XBRL),
            ExtractedField("StockholdersEquity",  62_146_000_000.0, Provenance.XBRL),
            ExtractedField("OperatingIncomeLoss",114_301_000_000.0, Provenance.XBRL),
        ]
        vr = validate_extraction(_make_result(fields=fields))
        assert vr.is_valid is True

    def test_8k_has_no_required_fields(self):
        from api.services.schema_validator import validate_extraction
        result = _make_result(form_type="8-K", fields=[])
        vr = validate_extraction(result)
        # 8-K has no required fields so missing fields should not fire
        assert ReasonCode.MISSING_FIELD not in vr.reason_codes


# ---------------------------------------------------------------------------
# semantic_validator
# ---------------------------------------------------------------------------

class TestSemanticValidator:
    def test_balanced_balance_sheet_passes(self):
        from api.services.semantic_validator import validate_semantic
        # Assets = Liabilities + Equity exactly
        fields = [
            ExtractedField("Assets",             352_583_000_000.0, Provenance.XBRL),
            ExtractedField("Liabilities",        290_437_000_000.0, Provenance.XBRL),
            ExtractedField("StockholdersEquity",  62_146_000_000.0, Provenance.XBRL),
        ]
        vr = validate_semantic(_make_result(fields=fields))
        assert ReasonCode.IDENTITY_VIOLATION not in vr.reason_codes

    def test_unbalanced_balance_sheet_fails(self):
        from api.services.semantic_validator import validate_semantic
        fields = [
            ExtractedField("Assets",             400_000_000_000.0, Provenance.XBRL),
            ExtractedField("Liabilities",        290_437_000_000.0, Provenance.XBRL),
            ExtractedField("StockholdersEquity",  62_146_000_000.0, Provenance.XBRL),
        ]
        vr = validate_semantic(_make_result(fields=fields))
        assert ReasonCode.IDENTITY_VIOLATION in vr.reason_codes
        assert "balance_sheet" in vr.details

    def test_referential_bad_cik(self):
        from api.services.semantic_validator import validate_semantic
        result = _make_result(cik="NOT-DIGITS")
        vr = validate_semantic(result)
        assert ReasonCode.REFERENTIAL in vr.reason_codes

    def test_referential_bad_period(self):
        from api.services.semantic_validator import validate_semantic
        result = _make_result(period="not-a-date")
        vr = validate_semantic(result)
        assert ReasonCode.REFERENTIAL in vr.reason_codes

    def test_referential_valid_period_passes(self):
        from api.services.semantic_validator import validate_semantic
        result = _make_result(period="2023-09-30")
        # Should not raise REFERENTIAL for valid period
        vr = validate_semantic(result)
        assert ReasonCode.REFERENTIAL not in vr.reason_codes


# ---------------------------------------------------------------------------
# confidence_scorer — trigger registration
# ---------------------------------------------------------------------------

class TestConfidenceScorer:
    def test_all_triggers_registered(self):
        """Spec §4.3 requires 9 triggers (8 original + out_of_range)."""
        from api.services.confidence_scorer import ALL_TRIGGERS
        names = [name for name, _ in ALL_TRIGGERS]
        assert "out_of_range" in names, "out_of_range trigger must be in ALL_TRIGGERS"
        assert "balance_sheet_imbalance" in names
        assert "amended_filing" in names
        assert "xbrl_mismatch" in names
        assert "unrecognized_concept" in names

    def test_amended_filing_trigger(self):
        from api.services.confidence_scorer import evaluate_triggers_only
        result = _make_result(accession="0000320193/A-23-000106")
        triggers = evaluate_triggers_only(result)
        assert "amended_filing" in triggers

    def test_going_concern_trigger(self):
        from api.services.confidence_scorer import evaluate_triggers_only
        fields = [ExtractedField("Note1", "going concern substantial doubt", Provenance.NARRATIVE_LLM)]
        result = _make_result(fields=fields)
        triggers = evaluate_triggers_only(result)
        assert "going_concern" in triggers

    def test_high_confidence_routes_auto(self):
        from api.services.confidence_scorer import score_and_route
        # Patch cross_validate to return high confidence with no mismatches
        with patch("api.services.confidence_scorer.cross_validate") as mock_cv, \
             patch("api.services.confidence_scorer.validate_semantic") as mock_vs:
            from api.services.xbrl_cross_validator import CrossValidationResult, FieldConfidence
            fc = FieldConfidence(name="Revenues", confidence=0.98, matched_xbrl=True)
            mock_cv.return_value = CrossValidationResult(
                field_confidences=[fc],
                validation=ValidationResult(is_valid=True),
                record_confidence=0.98,
            )
            mock_vs.return_value = ValidationResult(is_valid=True)
            decision = score_and_route(_make_result())
        assert decision.route == Route.AUTO
        assert decision.confidence >= 0.85

    def test_low_confidence_routes_escalate(self):
        from api.services.confidence_scorer import score_and_route
        with patch("api.services.confidence_scorer.cross_validate") as mock_cv, \
             patch("api.services.confidence_scorer.validate_semantic") as mock_vs:
            from api.services.xbrl_cross_validator import CrossValidationResult, FieldConfidence
            fc = FieldConfidence(name="Revenues", confidence=0.0, matched_xbrl=False,
                                 reason_code=ReasonCode.XBRL_MISMATCH)
            mock_cv.return_value = CrossValidationResult(
                field_confidences=[fc],
                validation=ValidationResult(is_valid=False, reason_codes=[ReasonCode.XBRL_MISMATCH]),
                record_confidence=0.0,
            )
            mock_vs.return_value = ValidationResult(is_valid=True)
            decision = score_and_route(_make_result())
        assert decision.route == Route.ESCALATE

    def test_route_enum_values_are_uppercase(self):
        """BUG-1 regression: Route enum values must be uppercase to match DB CHECK."""
        assert Route.AUTO.value == "AUTO"
        assert Route.SAMPLED_REVIEW.value == "SAMPLED_REVIEW"
        assert Route.ESCALATE.value == "ESCALATE"


# ---------------------------------------------------------------------------
# shadow_runner
# ---------------------------------------------------------------------------

class TestShadowRunner:
    def test_run_shadow_pipeline_empty(self):
        from api.services.shadow_runner import run_shadow_pipeline
        report = run_shadow_pipeline([])
        assert report.total_processed == 0
        assert report.errors == 0

    def test_run_shadow_pipeline_counts(self):
        from api.services.shadow_runner import run_shadow_pipeline
        with patch("api.services.shadow_runner.score_and_route") as mock_sr, \
             patch("api.services.shadow_runner.validate_extraction") as mock_ve, \
             patch("api.services.shadow_runner.validate_semantic") as mock_vs:
            mock_ve.return_value = ValidationResult(is_valid=True)
            mock_vs.return_value = ValidationResult(is_valid=True)
            mock_sr.return_value = Decision(
                route=Route.AUTO,
                confidence=0.95,
                validation=ValidationResult(is_valid=True),
                triggers_fired=[],
            )
            report = run_shadow_pipeline([_make_result(), _make_result()])
        assert report.total_processed == 2
        assert report.auto_count == 2
        assert report.errors == 0

    def test_agreement_rate_is_none_by_default(self):
        """BUG-4 regression: agreement_rate should be None (not 0.0) until populated externally."""
        from api.services.shadow_runner import CalibrationReport
        report = CalibrationReport()
        assert report.agreement_rate is None

    def test_confidence_histogram_bucketing(self):
        from api.services.shadow_runner import _confidence_bucket
        assert _confidence_bucket(0.95) == "0.90-1.00"
        assert _confidence_bucket(0.85) == "0.80-0.89"
        assert _confidence_bucket(0.55) == "0.50-0.59"
        assert _confidence_bucket(0.30) == "0.00-0.49"


# ---------------------------------------------------------------------------
# review_queue DB layer
# ---------------------------------------------------------------------------

class TestReviewQueueDB:
    @pytest.fixture
    def conn(self):
        """In-memory DuckDB connection with review tables initialised."""
        from api.db.review_queue import init_review_tables
        c = duckdb.connect(":memory:")
        init_review_tables(c)
        yield c
        c.close()

    def test_insert_and_list_decision(self, conn):
        from api.db.review_queue import insert_decision, list_decisions
        did = insert_decision(conn, {
            "cik": "0000320193",
            "accession": "0000320193-23-000106",
            "form_type": "10-K",
            "route": "SAMPLED_REVIEW",
            "confidence": 0.72,
            "triggers_fired": [],
        })
        assert isinstance(did, str)
        rows = list_decisions(conn)
        assert len(rows) == 1
        assert rows[0]["id"] == did

    def test_list_decisions_filter_by_status(self, conn):
        from api.db.review_queue import insert_decision, list_decisions
        insert_decision(conn, {
            "cik": "0000320193", "accession": "0000320193-23-000106",
            "form_type": "10-K", "route": "SAMPLED_REVIEW",
            "confidence": 0.72, "triggers_fired": [],
        })
        pending = list_decisions(conn, status="pending")
        reviewed = list_decisions(conn, status="reviewed")
        assert len(pending) == 1
        assert len(reviewed) == 0

    def test_insert_verdict_marks_reviewed(self, conn):
        from api.db.review_queue import insert_decision, insert_verdict, get_decision
        did = insert_decision(conn, {
            "cik": "0000320193", "accession": "0000320193-23-000106",
            "form_type": "10-K", "route": "ESCALATE",
            "confidence": 0.30, "triggers_fired": ["xbrl_mismatch"],
        })
        insert_verdict(conn, decision_id=did, reviewer_agrees=True, notes="Looks correct")
        decision = get_decision(conn, did)
        assert decision["status"] == "reviewed"

    def test_compute_agreement_rate_no_verdicts(self, conn):
        from api.db.review_queue import compute_agreement_rate
        rate = compute_agreement_rate(conn)
        assert rate == 0.0

    def test_compute_agreement_rate_with_verdicts(self, conn):
        from api.db.review_queue import insert_decision, insert_verdict, compute_agreement_rate
        for i in range(4):
            did = insert_decision(conn, {
                "cik": "0000320193", "accession": f"0000320193-23-{i:06d}",
                "form_type": "10-K", "route": "SAMPLED_REVIEW",
                "confidence": 0.75, "triggers_fired": [],
            })
            insert_verdict(conn, decision_id=did, reviewer_agrees=(i < 3))  # 3 agree, 1 disagree
        rate = compute_agreement_rate(conn, window=10)
        assert abs(rate - 0.75) < 0.01

    def test_count_unrecognized_concepts_lowercase_match(self, conn):
        """BUG-2 regression: trigger name stored as lowercase must be matched correctly."""
        from api.db.review_queue import insert_decision, count_unrecognized_concepts
        insert_decision(conn, {
            "cik": "0000320193", "accession": "0000320193-23-000001",
            "form_type": "10-K", "route": "ESCALATE",
            "confidence": 0.40,
            "triggers_fired": ["unrecognized_concept"],  # lowercase — as stored by scorer
        })
        count = count_unrecognized_concepts(conn, window_hours=24 * 365)
        assert count == 1, (
            "count_unrecognized_concepts must match lowercase 'unrecognized_concept' "
            "as stored by confidence_scorer.ALL_TRIGGERS"
        )

    def test_get_calibration_data_empty(self, conn):
        from api.db.review_queue import get_calibration_data
        data = get_calibration_data(conn)
        assert data == []

    def test_get_calibration_data_returns_joined_rows(self, conn):
        from api.db.review_queue import (
            insert_decision, insert_verdict, get_calibration_data,
        )
        did = insert_decision(conn, {
            "cik": "0000320193", "accession": "0000320193-23-000001",
            "form_type": "10-K", "route": "SAMPLED_REVIEW",
            "confidence": 0.80, "triggers_fired": [],
        })
        insert_verdict(conn, decision_id=did, reviewer_agrees=True)
        data = get_calibration_data(conn)
        assert len(data) == 1
        assert abs(data[0]["confidence"] - 0.80) < 0.001
        assert data[0]["reviewer_agrees"] is True
