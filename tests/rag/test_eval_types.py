"""
tests/test_eval_types.py

Round-trip serialisation and provenance enforcement tests for eval_types.py.
Run with: python -m pytest tests/test_eval_types.py -v
"""
import dataclasses
import pytest

from api.models.eval_types import (
    Decision,
    ExtractedField,
    ExtractionResult,
    Provenance,
    ReasonCode,
    Route,
    ValidationResult,
)


def test_provenance_values():
    assert Provenance.XBRL.value == "xbrl"
    assert Provenance.STRUCTURED_TABLE.value == "table"
    assert Provenance.NARRATIVE_LLM.value == "narrative"


def test_provenance_is_str_enum():
    assert isinstance(Provenance.XBRL, str)


def test_reason_code_values():
    assert ReasonCode.OK.value == "ok"
    assert ReasonCode.XBRL_MISMATCH.value == "xbrl_mismatch"
    assert ReasonCode.IDENTITY_VIOLATION.value == "identity_violation"


def test_reason_codes_are_str_enum():
    assert isinstance(ReasonCode.XBRL_MISMATCH, str)


def test_route_values():
    # Route enum values are uppercase to match the DB CHECK constraint in
    # review_decisions (route IN ('SAMPLED_REVIEW', 'ESCALATE')).
    # See BUG-1 fix in fix/audit-corrections.
    assert Route.AUTO.value == "AUTO"
    assert Route.SAMPLED_REVIEW.value == "SAMPLED_REVIEW"
    assert Route.ESCALATE.value == "ESCALATE"


def test_route_is_str_enum():
    assert isinstance(Route.ESCALATE, str)


def test_requires_provenance():
    """ExtractedField must not be constructable without a provenance tag."""
    with pytest.raises(TypeError):
        # Missing provenance positional arg
        ExtractedField(name="Revenue", value=1_000_000)  # type: ignore[call-arg]


def test_optional_defaults():
    f = ExtractedField(name="Revenue", value=1_000_000, provenance=Provenance.XBRL)
    assert f.concept is None
    assert f.source_span is None


def test_concept_and_span_set():
    f = ExtractedField(
        name="Revenue",
        value=1_000_000,
        provenance=Provenance.XBRL,
        concept="us-gaap/Revenues",
        source_span="span[2]",
    )
    assert f.concept == "us-gaap/Revenues"
    assert f.source_span == "span[2]"


@pytest.fixture
def sample_extraction_result():
    return ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000064",
        form_type="10-K",
        period="2023-09-30",
        fields=[
            ExtractedField(
                name="Revenue",
                value=383_285_000_000,
                provenance=Provenance.XBRL,
                concept="us-gaap/Revenues",
            ),
            ExtractedField(
                name="NetIncomeLoss",
                value=96_995_000_000,
                provenance=Provenance.STRUCTURED_TABLE,
            ),
        ],
    )


def test_round_trip_scalars(sample_extraction_result):
    original = sample_extraction_result
    as_dict = dataclasses.asdict(original)

    # Reconstruct — fields list must be rebuilt manually because
    # dataclasses.asdict converts nested dataclasses to dicts too.
    fields = [
        ExtractedField(
            name=f["name"],
            value=f["value"],
            provenance=Provenance(f["provenance"]),
            concept=f.get("concept"),
            source_span=f.get("source_span"),
        )
        for f in as_dict["fields"]
    ]
    reconstructed = ExtractionResult(
        cik=as_dict["cik"],
        accession=as_dict["accession"],
        form_type=as_dict["form_type"],
        period=as_dict["period"],
        fields=fields,
    )

    assert reconstructed.cik == original.cik
    assert reconstructed.accession == original.accession
    assert reconstructed.form_type == original.form_type
    assert reconstructed.period == original.period
    assert len(reconstructed.fields) == len(original.fields)
    assert reconstructed.fields[0].provenance == original.fields[0].provenance


def test_all_fields_tagged(sample_extraction_result):
    result = sample_extraction_result
    for f in result.fields:
        assert isinstance(f.provenance, Provenance), f"Field '{f.name}' is missing a valid Provenance tag"


def test_validation_result_defaults():
    vr = ValidationResult(is_valid=True)
    assert vr.reason_codes == []
    assert vr.details == {}


def test_validation_result_mutable_defaults_are_independent():
    """Each instance must have its own list/dict, not a shared reference."""
    a = ValidationResult(is_valid=True)
    b = ValidationResult(is_valid=False)
    a.reason_codes.append(ReasonCode.MISSING_FIELD)
    assert b.reason_codes == []


def test_decision_triggers_fired_defaults_empty():
    d = Decision(
        route=Route.AUTO,
        confidence=0.99,
        validation=ValidationResult(is_valid=True),
    )
    assert d.triggers_fired == []


def test_decision_mutable_defaults_are_independent():
    a = Decision(route=Route.AUTO, confidence=0.9, validation=ValidationResult(is_valid=True))
    b = Decision(route=Route.AUTO, confidence=0.8, validation=ValidationResult(is_valid=True))
    a.triggers_fired.append("balance_sheet_identity_failure")
    assert b.triggers_fired == []
