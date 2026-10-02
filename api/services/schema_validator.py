"""
schema_validator.py — Layer-1 validation (Phase 2).
Checks field presence, types, and unit sanity per form type.
"""
from __future__ import annotations

import re

from api.models.eval_types import (
    ExtractionResult, ExtractedField, ValidationResult, ReasonCode, Provenance,
)

ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
CIK_RE = re.compile(r"^\d{1,10}$")

REQUIRED_FIELDS_BY_FORM: dict[str, list[str]] = {
    "10-K": [
        "Revenues", "NetIncomeLoss", "Assets", "Liabilities",
        "StockholdersEquity", "OperatingIncomeLoss",
    ],
    "10-Q": [
        "Revenues", "NetIncomeLoss", "Assets", "Liabilities",
        "StockholdersEquity",
    ],
    "8-K": [],
}

# XBRL reports monetary values in full dollars (not thousands).
# A value below this floor for a revenue/asset field is suspicious —
# it likely means the extractor read a "thousands" table and forgot to
# multiply by 1 000.  $10 000 is chosen as a conservative floor: even
# the smallest public filers report revenues well above this.
_SCALE_FLOOR_USD = 10_000.0

# Fields that carry monetary values and should be checked for scale confusion.
_MONETARY_FIELD_NAMES: frozenset[str] = frozenset({
    "Revenues", "NetIncomeLoss", "Assets", "Liabilities",
    "StockholdersEquity", "OperatingIncomeLoss",
    "GrossProfit", "CashAndCashEquivalentsAtCarryingValue",
    "LongTermDebt", "RetainedEarningsAccumulatedDeficit",
})


def validate_extraction(result: ExtractionResult) -> ValidationResult:
    reason_codes: list[ReasonCode] = []
    details: dict = {}

    if not CIK_RE.fullmatch(result.cik):
        reason_codes.append(ReasonCode.BAD_TYPE)
        details["cik"] = f"Expected 1-10 digits, got '{result.cik}'"

    if not ACCESSION_RE.match(result.accession):
        reason_codes.append(ReasonCode.BAD_TYPE)
        details["accession"] = f"Expected nnnnnnnnnn-nn-nnnnnn format, got '{result.accession}'"

    field_map = {f.name: f for f in result.fields if f.name}

    required = REQUIRED_FIELDS_BY_FORM.get(result.form_type, [])
    for field_name in required:
        if field_name not in field_map:
            reason_codes.append(ReasonCode.MISSING_FIELD)
            details.setdefault("missing_fields", []).append(field_name)
        else:
            fld = field_map[field_name]
            if not isinstance(fld.value, (int, float)):
                reason_codes.append(ReasonCode.BAD_TYPE)
                details.setdefault("bad_types", {})[field_name] = (
                    f"Expected numeric, got {type(fld.value).__name__}"
                )

    for fld in result.fields:
        if fld.provenance == Provenance.XBRL and isinstance(fld.value, (int, float)):
            if _is_suspicious_scale(fld):
                reason_codes.append(ReasonCode.OUT_OF_RANGE)
                details.setdefault("scale_warnings", {})[fld.name] = (
                    f"Value {fld.value:,.2f} is suspiciously small for a monetary XBRL field "
                    f"(< ${_SCALE_FLOOR_USD:,.0f}) — possible thousands/units confusion"
                )

    is_valid = len(reason_codes) == 0
    return ValidationResult(is_valid=is_valid, reason_codes=reason_codes, details=details)


def _is_suspicious_scale(fld: ExtractedField) -> bool:
    """Return True when an XBRL monetary field value looks like it was reported
    in thousands instead of full dollars.

    XBRL SEC filings always report monetary values in full USD.  A value below
    _SCALE_FLOOR_USD for a known monetary concept is almost certainly a
    thousands-scale error (e.g. the extractor read "$1,234" from a table that
    was labelled "in thousands" and stored 1234 instead of 1_234_000).

    Non-monetary fields (EPS, share counts, ratios) are excluded by checking
    against _MONETARY_FIELD_NAMES.
    """
    if not isinstance(fld.value, (int, float)):
        return False
    if fld.name not in _MONETARY_FIELD_NAMES:
        return False
    return abs(fld.value) < _SCALE_FLOOR_USD and fld.value != 0.0
