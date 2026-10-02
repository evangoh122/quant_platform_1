"""
Numeric verification — compares RAG-claimed values against XBRL facts.
"""
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class VerificationResult:
    status: str   # "verified" | "mismatch" | "unverifiable" | "not_checked"
    claimed_value: Optional[float] = None
    xbrl_value: Optional[float] = None
    note: Optional[str] = None

_NUMBER_RE = re.compile(r"\$?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand|B|M|K)?", re.IGNORECASE)
_SCALE = {"billion": 1e9, "B": 1e9, "million": 1e6, "M": 1e6, "thousand": 1e3, "K": 1e3}

def extract_first_number(text: str) -> Optional[float]:
    """Extract the first dollar-value mention from text."""
    m = _NUMBER_RE.search(text)
    if not m:
        return None
    raw = float(m.group(1).replace(",", ""))
    scale = _SCALE.get(m.group(2) or "", 1.0)
    return raw * scale

def verify_answer(
    answer: str,
    cik: str,
    concept: str,
    period_end: str,
    ticker: str = "",
    tolerance: float = 0.01,   # 1% tolerance for rounding
) -> VerificationResult:
    """
    Extract a number from the answer text and compare against the XBRL fact.
    Returns a VerificationResult with status and both values.
    """
    from api.services.xbrl_client import get_fact

    claimed = extract_first_number(answer)
    if claimed is None:
        return VerificationResult(status="not_checked", note="No numeric value found in answer")

    fact = get_fact(cik, concept, period_end, ticker=ticker)
    if fact is None:
        return VerificationResult(
            status="unverifiable",
            claimed_value=claimed,
            note=f"No XBRL fact found for {concept} at {period_end}",
        )

    delta = abs(claimed - fact.value) / max(abs(fact.value), 1.0)
    if delta <= tolerance:
        return VerificationResult(
            status="verified",
            claimed_value=claimed,
            xbrl_value=fact.value,
        )
    return VerificationResult(
        status="mismatch",
        claimed_value=claimed,
        xbrl_value=fact.value,
        note=f"Delta {delta:.1%} exceeds tolerance {tolerance:.1%}",
    )
