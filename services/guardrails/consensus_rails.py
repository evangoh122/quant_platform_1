"""
consensus_rails.py — Dual-model consensus check (Bias / Model-Risk rail).

The audited (primary) answer is produced upstream and passed IN as `primary_answer`
— this module does not generate it. The rail asks an *independent* secondary model
(MiMo) to answer the SAME question from the SAME retrieved context, then
deterministically compares the material numeric claims of the two answers.

Goal: reduce single-model dependence and surface answer-level divergence. When the
two models disagree on a figure, that is a strong "lower-confidence / send to human
review" signal that feeds the existing eval routing + audit trail.

IMPORTANT (honesty about scope): DeepSeek and MiMo share a similar training
lineage, so their biases are *correlated*. This rail is therefore best read as a
consistency / model-risk control, not a guarantee of demographic fairness or true
model diversity. For genuine diversity, the secondary should be a different-lineage
model (Claude / OpenAI are already wired in api/config.py). See the team's risk
notes before relying on this for the Bias & Fairness story.

The rail is fail-open: any error, timeout, or missing key returns a SKIPPED verdict
(agree=True) so it can never break the chat path.

NOTE: this module only *computes* the consensus verdict. The caller
(`_apply_consensus_rail` in langgraph_engine.py) owns the side effects — route
override (AUTO->SAMPLED_REVIEW), review-queue entry, and persisting consensus_* to
audit_runs — on material disagreement.

RISK-GATING (do not run on every answer): a second LLM call ~doubles base latency,
so the rail is gated by `should_run_consensus()` to HIGH-RISK questions only —
answers already routed to SAMPLED_REVIEW/ESCALATE, hard multi-year questions
(trend / CAGR / YoY / spanning ≥2 fiscal years), and peer/multi-company
comparisons. Single-period single-metric AUTO answers and conversational turns are
NOT cross-checked. See docs/mindforge-risk-alignment.md §3.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

try:
    from openai import OpenAI
    from api.config import Config
except ImportError:  # pragma: no cover
    OpenAI = None
    Config = None


# A financial figure: optional $, digits with separators, optional trailing %.
_NUMERIC = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")

# A 4-digit year in a plausible filing range (used for multi-year detection).
_YEAR = re.compile(r"\b(19|20)\d{2}\b")

# Phrases that signal cross-period / trend reasoning even without explicit years.
_MULTIYEAR_SIGNALS = (
    "trend", "cagr", "year over year", "year-over-year", "yoy", "growth rate",
    "over the past", "over the last", "since 20", "compared to last year",
    "5-year", "five-year", "3-year", "three-year", "annual change", "historical",
    "trajectory", "each year", "every year", "from 20",
)

# Phrases that signal peer / multi-company comparison. NB: kept narrow on purpose
# — bare "against" was removed because it also matches "litigation against",
# "penalties against", etc., which are risk/compliance, not comparisons.
_COMPARISON_SIGNALS = (
    " vs ", " vs.", "versus", "compare", "comparison", "peers", "competitors",
    "relative to", "compared against", "industry average",
)

# Phrases that signal a risk / compliance question — high-consequence topics where
# a wrong figure or misread carries regulatory/legal weight, so they warrant the
# independent second opinion. (Substring match; e.g. "regulat" covers
# regulatory/regulation, "contingenc" covers contingency/contingencies.)
_RISK_COMPLIANCE_SIGNALS = (
    "risk factor", "compliance", "regulat", "litigation", "lawsuit",
    "investigation", "material weakness", "internal control",
    "controls and procedures", "going concern", "covenant", "restatement",
    "non-reliance", "impairment", "contingenc", "sanction", "penalt", "default",
    "fraud", "related party", "disclosure control", "sec inquiry", "subpoena",
)

# Eval routes that are already deemed high-stakes by the eval layer.
_HIGH_STAKES_ROUTES = {"SAMPLED_REVIEW", "ESCALATE"}


def should_run_consensus(query: str, eval_route: Optional[str] = None) -> tuple[bool, str]:
    """Risk gate: decide whether a question warrants the second model.

    The consensus rail adds a synchronous LLM call (~doubles latency), so it must
    only fire on HIGH-RISK questions. Returns `(run, reason)` so the decision is
    auditable. See docs/mindforge-risk-alignment.md §3 for the policy.
    """
    # 1. The eval layer already flagged this as high-stakes.
    if eval_route and eval_route.upper() in _HIGH_STAKES_ROUTES:
        return True, f"eval_route={eval_route.upper()}"

    q = (query or "").lower()

    # 2. Hard, multi-year questions: ≥2 distinct years, or an explicit trend signal.
    distinct_years = {m.group(0) for m in _YEAR.finditer(q)}
    if len(distinct_years) >= 2:
        return True, f"multi-year span ({sorted(distinct_years)})"
    if any(sig in q for sig in _MULTIYEAR_SIGNALS):
        return True, "multi-year / trend signal"

    # 3. Peer / multi-company comparison.
    if any(sig in q for sig in _COMPARISON_SIGNALS):
        return True, "comparison question"

    # 4. Risk / compliance questions — high-consequence regulatory/legal topics.
    if any(sig in q for sig in _RISK_COMPLIANCE_SIGNALS):
        return True, "risk/compliance question"

    # Otherwise: low-risk (single-period, single-metric) — skip the second model.
    return False, "low-risk single-period question"


@dataclass
class ConsensusVerdict:
    agree: bool                                   # False => material numeric disagreement
    skipped: bool = False                         # True => rail could not run (fail-open)
    divergence_score: float = 0.0                 # 0.0 = full agreement, 1.0 = no overlap
    secondary_answer: Optional[str] = None        # MiMo's independent answer (for audit/UI)
    secondary_model: Optional[str] = None
    disagreements: list[str] = field(default_factory=list)  # primary figures not corroborated
    reason: Optional[str] = None


def _normalise_numbers(text: str) -> set[str]:
    """Extract comparable numeric tokens, normalising format ($, commas)."""
    if not text:
        return set()
    out: set[str] = set()
    for m in _NUMERIC.findall(text):
        tok = m.replace("$", "").replace(",", "").rstrip("%").strip(".")
        if tok and tok not in {"", "."}:
            out.add(tok)
    return out


def _divergence(primary: str, secondary: str) -> tuple[float, list[str]]:
    """Fraction of the PRIMARY answer's figures not corroborated by the secondary.

    We only judge the primary's claims (that is the answer the user sees). A figure
    counts as corroborated if it appears in the secondary answer; numbers the
    secondary never mentions are treated as 'unconfirmed', not as disagreements,
    UNLESS the secondary cites a *different* value for an overlapping magnitude —
    that distinction is left to a future LLM judge. v1 is deliberately simple and
    deterministic so the signal is auditable.
    """
    p = _normalise_numbers(primary)
    if not p:
        return 0.0, []
    s = _normalise_numbers(secondary)
    unconfirmed = sorted(p - s)
    score = len(unconfirmed) / len(p)
    return score, unconfirmed


def check_consensus(
    query: str,
    context: str,
    primary_answer: str,
    *,
    divergence_threshold: float = 0.5,
    timeout: Optional[float] = None,
) -> ConsensusVerdict:
    """Run the secondary model and compare against the primary answer.

    Args:
        query:          the user's question.
        context:        the retrieved filing context the primary answer was grounded on.
                        Truncated to ~12k chars (on a paragraph boundary) to keep the
                        secondary call bounded; figures near the end of a very long
                        context may fall outside the window — a known limitation.
        primary_answer: the audited answer from the primary provider (DeepSeek).
        divergence_threshold: fraction of uncorroborated figures above which the
                              verdict is `agree=False`.
        timeout:        secondary-model call timeout (seconds). When None, read from
                        CONSENSUS_TIMEOUT at call time (default 8.0) — read inside
                        the body so the env var is runtime-mutable and a malformed
                        value degrades gracefully instead of crashing at import.
    """
    if timeout is None:
        try:
            timeout = float(os.getenv("CONSENSUS_TIMEOUT", "8.0"))
        except (TypeError, ValueError):
            timeout = 8.0
    # Nothing to compare against → nothing to do.
    if not primary_answer or not primary_answer.strip():
        return ConsensusVerdict(agree=True, skipped=True, reason="empty primary answer")
    if not context or not context.strip():
        return ConsensusVerdict(agree=True, skipped=True, reason="no context to ground secondary")
    if OpenAI is None or Config is None or not Config.MIMO_API_KEY:
        return ConsensusVerdict(agree=True, skipped=True, reason="secondary model not configured")

    mimo_base_url = os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1")
    # CONSENSUS_SECONDARY_MODEL is the forward-looking name (the production swap
    # points it at a different-lineage frontier model); falls back to MIMO_MODEL
    # for the current DeepSeek+MiMo example.
    secondary_model = os.getenv("CONSENSUS_SECONDARY_MODEL") or os.getenv("MIMO_MODEL", "mimo-v2.5-pro")

    # Context can be large; cap it so the secondary call stays bounded. Cut on a
    # paragraph boundary when possible so we don't slice mid-figure/mid-sentence.
    ctx = context[:12000]
    if len(context) > 12000:
        boundary = ctx.rfind("\n\n")
        if boundary > 6000:  # only honour the boundary if it keeps enough context
            ctx = ctx[:boundary]

    prompt = (
        "You are an independent financial analyst. Answer the question using ONLY "
        "the SEC filing context below. State the key figures explicitly. If the "
        "context does not contain the answer, say so. Do not speculate.\n\n"
        f"Question:\n{query}\n\n"
        f"Context:\n{ctx}\n\n"
        "Answer concisely with the specific numbers:"
    )

    try:
        client = OpenAI(api_key=Config.MIMO_API_KEY, base_url=mimo_base_url, timeout=timeout)
        resp = client.chat.completions.create(
            model=secondary_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=600,
            timeout=timeout,  # bound the request explicitly, not just the client
        )
        secondary = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning(f"Consensus rail: secondary model call failed ({e}); skipping.")
        return ConsensusVerdict(agree=True, skipped=True, reason=f"secondary call failed: {e}")

    if not secondary:
        return ConsensusVerdict(agree=True, skipped=True, reason="empty secondary answer")

    score, unconfirmed = _divergence(primary_answer, secondary)
    agree = score <= divergence_threshold

    if not agree:
        logger.info(
            f"Consensus rail: DISAGREEMENT (divergence={score:.2f}); "
            f"uncorroborated primary figures: {unconfirmed}"
        )

    return ConsensusVerdict(
        agree=agree,
        skipped=False,
        divergence_score=round(score, 4),
        secondary_answer=secondary,
        secondary_model=secondary_model,
        disagreements=unconfirmed,
        reason=(
            "Models agree on material figures"
            if agree
            else f"Secondary model did not corroborate {len(unconfirmed)} figure(s)"
        ),
    )
