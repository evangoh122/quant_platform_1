"""
persona_rails.py — Persona-fit rail (does the answer serve the active reader?).

When a respondent self-selects a professional role (conjoint `role_based`
personalization), the answer is tailored to that persona via `role_guidance`
(see api/routes/conjoint.py). This rail closes the loop: it checks, after the
answer is generated, whether the answer actually satisfies that persona's
hard REQUIREMENTS — not its tone, but the structural musts that define a "good"
answer for them (e.g. a Compliance Officer needs citations + verification status;
a Credit Analyst must not state an unverified number without a caveat).

Design mirrors consensus_rails.py:
  * deterministic and dependency-free (regex/keyword heuristics, no LLM call) so
    the signal is cheap, auditable, and adds no latency to the request path;
  * fail-open — an unknown role, empty answer, or any error returns a SKIPPED
    verdict (fit=True) so it can never break the chat path;
  * advisory only — it NEVER edits the user-facing answer or changes routing. It
    produces a flag that the caller logs and (on a miss) persists to the audit row
    so persona under-service is visible and reviewable.

HONESTY ABOUT SCOPE (v1): the checks are keyword/structure heuristics, not an LLM
judge. They detect the *presence* of the required move (a citation, a caveat, a
verification mention), not its correctness. A determined model could satisfy the
heuristic without genuinely serving the persona, and conversely a good answer
phrased unusually could trip a false "miss". Treat this as a coverage signal that
feeds review, not a guarantee. An LLM-judge upgrade is the natural v2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from loguru import logger


# A *financial figure* — a monetary amount, a percentage, a scaled magnitude, or a
# thousands-separated number. It deliberately does NOT match a bare integer, so
# filing labels ("Item 1A"), form types ("10-K"), section numbers ("1.01"), and
# standalone fiscal years ("2024") are not mistaken for a reported figure — which
# would otherwise trip the credit persona's number-conditional requirements on a
# purely qualitative, correctly-cited answer.
_FINANCIAL_FIGURE = re.compile(
    r"""
    \$\s?\d[\d,]*(?:\.\d+)?                                                  # $1,200 / $3.4
  | \d[\d,]*(?:\.\d+)?\s?%                                                   # 12.5% / 45 %
  | \d[\d,]*(?:\.\d+)?\s?(?:thousand|million|billion|trillion|bn|mn)\b       # 3.4 billion
  | \d{1,3}(?:,\d{3})+(?:\.\d+)?                                             # 1,200 / 26,000
  | (?:\d+\.\d+[kKmMbBtT]|\d{3,}[kKmMbBtT])(?:\b|(?=[\s,;:!?)]|$))           # 3.4B / 2.1M / 500K (not 10K)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Verification statuses that mean the figure(s) were actually checked upstream, so
# the persona's "state verification status / caveat unverified numbers" requirement
# is satisfied structurally by the product (the UI shows the status badge) even if
# the answer prose doesn't repeat it.
_VERIFIED_STATUSES = {"PASS", "VERIFIED"}


def _l(text: str) -> str:
    return (text or "").lower()


def _has_citation(text: str) -> bool:
    """Answer points at a specific filing / section / source."""
    t = _l(text)
    if any(kw in t for kw in (
        "section", "item ", "10-k", "10k", "10-q", "10q", "8-k", "md&a",
        "form ", "filing", "edgar", "accession", "annual report",
        "quarterly report", "according to", "per the", "as disclosed", "as stated in",
    )):
        return True
    # "Item 1A", "Part II", etc.
    return bool(re.search(r"\b(item|part)\s+[0-9ivx]+", t))


def _has_verification_language(text: str) -> bool:
    """Answer explicitly speaks to whether figures were verified."""
    t = _l(text)
    return any(kw in t for kw in (
        "verif", "corroborat", "cross-check", "cross check", "audited",
        "reconcil", "confirmed against", "checked against",
    ))


def _has_caveat(text: str) -> bool:
    """Answer hedges an unverified / uncertain figure."""
    t = _l(text)
    return any(kw in t for kw in (
        "caveat", "unverified", "not verified", "not independently verified",
        "unconfirmed", "not corroborated", "could not verify", "cannot confirm",
        "should be confirmed", "treat with caution", "approximate", "approximately",
        "not available", "no figure", "uncertain", "may not", "could not be confirmed",
    ))


def _has_financial_figure(text: str) -> bool:
    """True only for an actual reported financial figure (see _FINANCIAL_FIGURE).

    Bare integers, fiscal years, form types ("10-K"), and item/section numbers do
    NOT count, so a cited qualitative answer ("Per Item 1A of the 10-K, liquidity
    risk rose in fiscal 2024") is correctly treated as reporting no figure to caveat.
    """
    return bool(_FINANCIAL_FIGURE.search(text or ""))


@dataclass
class PersonaFitVerdict:
    fit: bool                                       # False => answer misses a persona requirement
    skipped: bool = False                           # True => rail could not run (fail-open)
    role: Optional[str] = None                      # role key checked
    score: float = 0.0                              # fraction of requirements MISSED (0.0 = perfect)
    satisfied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reason: Optional[str] = None


# A single checkable requirement: a human label + a predicate over (answer text,
# verification_status). `applies` lets a requirement be conditional (e.g. only when
# the answer actually states a number).
@dataclass(frozen=True)
class _Requirement:
    label: str
    check: Callable[[str, Optional[str]], bool]
    applies: Callable[[str, Optional[str]], bool] = lambda answer, status: True


def _status_is_verified(status: Optional[str]) -> bool:
    return (status or "").strip().upper() in _VERIFIED_STATUSES


# Per-persona hard requirements. Keys MUST match conjoint.ROLES keys. These mirror
# each role's `answer_requirements` prose, expressed as deterministic checks.
_PERSONA_REQUIREMENTS: dict[str, list[_Requirement]] = {
    "compliance_officer": [
        _Requirement(
            "cite source filing / section",
            lambda a, s: _has_citation(a),
        ),
        _Requirement(
            "surface verification status",
            # Either the answer speaks to verification, or the product verified the
            # figures upstream (status badge surfaced independently of the prose).
            lambda a, s: _has_verification_language(a) or _status_is_verified(s),
        ),
    ],
    "equity_research_analyst": [
        _Requirement(
            "cite the filing section",
            lambda a, s: _has_citation(a),
        ),
    ],
    "credit_analyst": [
        _Requirement(
            "source / verification for figures",
            lambda a, s: _has_citation(a) or _has_verification_language(a) or _status_is_verified(s),
            # Only applies when the answer actually reports a financial figure.
            applies=lambda a, s: _has_financial_figure(a),
        ),
        _Requirement(
            "caveat any unverified number",
            # Satisfied if the figures were verified upstream OR the answer hedges.
            lambda a, s: _status_is_verified(s) or _has_caveat(a),
            applies=lambda a, s: _has_financial_figure(a),
        ),
    ],
    # relationship_manager has no hard structural requirement (conciseness is a soft
    # preference handled by tone), so it is intentionally absent — the rail skips it.
}


def check_persona_fit(
    role_key: Optional[str],
    answer: str,
    *,
    verification_status: Optional[str] = None,
    fit_threshold: float = 0.0,
) -> PersonaFitVerdict:
    """Score whether `answer` satisfies the active persona's hard requirements.

    Args:
        role_key:            the conjoint role key the answer was personalized for.
                             None / unknown / a role with no requirements → SKIPPED.
        answer:              the final, user-facing answer text.
        verification_status: the pipeline's verification verdict for this answer
                             (PASS/VERIFIED means figures were checked upstream, which
                             structurally satisfies "state verification status" and
                             "caveat unverified numbers" requirements).
        fit_threshold:       fraction of requirements allowed to miss while still
                             counting as a fit. Default 0.0 → every applicable
                             requirement must be satisfied.

    Never raises: any unexpected error returns a fail-open SKIPPED verdict.
    """
    try:
        key = (role_key or "").strip()
        reqs = _PERSONA_REQUIREMENTS.get(key)
        if not reqs:
            return PersonaFitVerdict(fit=True, skipped=True, role=key or None,
                                     reason="no requirements for role")
        if not answer or not answer.strip():
            return PersonaFitVerdict(fit=True, skipped=True, role=key,
                                     reason="empty answer")

        satisfied: list[str] = []
        missing: list[str] = []
        for req in reqs:
            if not req.applies(answer, verification_status):
                continue  # conditional requirement not in play for this answer
            (satisfied if req.check(answer, verification_status) else missing).append(req.label)

        applicable = len(satisfied) + len(missing)
        if applicable == 0:
            return PersonaFitVerdict(fit=True, skipped=True, role=key,
                                     reason="no applicable requirements")

        score = len(missing) / applicable
        fit = score <= fit_threshold
        return PersonaFitVerdict(
            fit=fit,
            skipped=False,
            role=key,
            score=round(score, 4),
            satisfied=satisfied,
            missing=missing,
            reason=(
                "answer satisfies persona requirements"
                if fit
                else f"answer missed: {', '.join(missing)}"
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive, rail must never break chat
        logger.warning(f"Persona-fit rail errored (non-fatal, skipping): {exc}")
        return PersonaFitVerdict(fit=True, skipped=True, role=role_key,
                                 reason=f"rail error: {exc}")
