"""
semantic_validator.py — Phase 4: Layer-2 Validation.
Catches accounting identity violations, referential inconsistencies,
and statistically implausible values.
"""
from __future__ import annotations

from typing import Optional

from api.models.eval_types import (
    ExtractionResult, ValidationResult, ReasonCode,
)
from api.services.xbrl_client import get_fact

_TOLERANCE = 0.05  # 5% tolerance for accounting identity checks
_HISTORICAL_SD_MULTIPLIER = 3.0  # N standard deviations for OUT_OF_RANGE


def validate_semantic(result: ExtractionResult, ticker: str = "") -> ValidationResult:
    reason_codes: list[ReasonCode] = []
    details: dict = {}

    _check_identity(result, reason_codes, details)
    _check_referential(result, reason_codes, details)
    _check_plausibility(result, ticker, reason_codes, details)

    is_valid = len(reason_codes) == 0
    return ValidationResult(is_valid=is_valid, reason_codes=reason_codes, details=details)


def _field_value(result: ExtractionResult, name: str) -> Optional[float]:
    for f in result.fields:
        if f.name == name and isinstance(f.value, (int, float)):
            return float(f.value)
    return None


def _check_identity(result: ExtractionResult, reason_codes: list[ReasonCode], details: dict) -> None:
    assets = _field_value(result, "Assets")
    liabs = _field_value(result, "Liabilities")
    equity = _field_value(result, "StockholdersEquity")

    if assets is not None and liabs is not None and equity is not None:
        implied = liabs + equity
        delta = abs(assets - implied) / max(abs(assets), 1.0)
        if delta > _TOLERANCE:
            reason_codes.append(ReasonCode.IDENTITY_VIOLATION)
            details["balance_sheet"] = {
                "assets": assets,
                "liabilities_plus_equity": implied,
                "delta_pct": f"{delta:.2%}",
            }

    revenue = _field_value(result, "Revenues")
    cogs = _field_value(result, "CostOfRevenue")
    if revenue is not None and cogs is not None:
        gross = revenue - cogs
        gp_field = _field_value(result, "GrossProfit")
        if gp_field is not None:
            delta = abs(gross - gp_field) / max(abs(gp_field), 1.0)
            if delta > _TOLERANCE:
                reason_codes.append(ReasonCode.IDENTITY_VIOLATION)
                details["gross_profit"] = {
                    "revenues": revenue,
                    "cost_of_revenue": cogs,
                    "expected": gross,
                    "reported": gp_field,
                    "delta_pct": f"{delta:.2%}",
                }


def _check_referential(result: ExtractionResult, reason_codes: list[ReasonCode], details: dict) -> None:
    """Check referential consistency of the extraction record (REQ-SEM-02).

    Validates:
    1. CIK is a non-empty digit string (format guard).
    2. Period date is a valid ISO-8601 date string (YYYY-MM-DD).
    3. Accession number CIK prefix matches the record CIK where possible
       (accession format: XXXXXXXXXX-YY-ZZZZZZ where X is the submitter CIK).
    """
    import re as _re
    _ISO_DATE_RE = _re.compile(r'^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$')
    _ACCESSION_RE = _re.compile(r'^(\d{10})-(\d{2})-(\d{6})$')

    # 1. CIK must be non-empty digits
    if not result.cik or not result.cik.strip().isdigit():
        reason_codes.append(ReasonCode.REFERENTIAL)
        details["cik_format"] = f"CIK must be a digit string, got '{result.cik}'"

    # 2. Period date format
    if result.period and not _ISO_DATE_RE.match(result.period):
        reason_codes.append(ReasonCode.REFERENTIAL)
        details["period_format"] = (
            f"Period must be YYYY-MM-DD, got '{result.period}'"
        )

    # 3. Accession CIK prefix consistency
    m = _ACCESSION_RE.match(result.accession or "")
    if m:
        accession_cik = m.group(1).lstrip("0")
        record_cik    = result.cik.lstrip("0")
        if accession_cik and record_cik and accession_cik != record_cik:
            # Some filings are submitted by a parent entity, so this is a
            # WARNING-level signal rather than a hard error — we flag it but
            # do not add a REFERENTIAL code to avoid false positives.
            details.setdefault("referential_warnings", []).append(
                f"Accession CIK prefix ({accession_cik}) differs from record CIK ({record_cik})"
            )


def _check_plausibility(
    result: ExtractionResult,
    ticker: str,
    reason_codes: list[ReasonCode],
    details: dict,
) -> None:
    if not ticker or not result.period:
        return

    concepts_to_check = ["Revenues", "NetIncomeLoss", "OperatingIncomeLoss"]
    for concept in concepts_to_check:
        val = _field_value(result, concept)
        if val is None:
            continue

        xbrl_fact = get_fact(
            cik=result.cik, concept=concept,
            period_end=result.period, ticker=ticker,
        )
        if xbrl_fact is None:
            continue

        delta = abs(val - xbrl_fact.value) / max(abs(xbrl_fact.value), 1.0)
        if delta > _HISTORICAL_SD_MULTIPLIER * 0.20:
            reason_codes.append(ReasonCode.OUT_OF_RANGE)
            details.setdefault("out_of_range", {})[concept] = {
                "extracted": val,
                "xbrl": xbrl_fact.value,
                "delta_pct": f"{delta:.2%}",
            }


def is_balance_sheet_balanced(
    assets: float,
    liabilities: float,
    equity: float,
    tolerance: float = _TOLERANCE,
) -> bool:
    implied = liabilities + equity
    delta = abs(assets - implied) / max(abs(assets), 1.0)
    return delta <= tolerance
