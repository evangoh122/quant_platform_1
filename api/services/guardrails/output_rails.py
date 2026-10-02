"""
output_rails.py — Phase 15: Output Rail (Hallucination Detection & PII Masking).

Performs final checks on LLM output:
  1. Hallucination detection — checks if the answer is grounded in retrieved context
  2. PII masking — detects and masks sensitive data (SSN, credit cards, emails, phone numbers)
  3. System prompt leak detection — blocks responses that contain system prompt fragments

Usage:
    from api.services.guardrails.output_rails import check_output, OutputVerdict
    verdict = check_output(answer, context, query)
    if verdict.masked_answer:
        return verdict.masked_answer
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OutputVerdict:
    safe: bool
    reason: Optional[str] = None
    masked_answer: Optional[str] = None
    pii_found: list[str] = field(default_factory=list)
    hallucination_score: float = 0.0  # 0.0 = grounded, 1.0 = likely hallucinated


# ── PII patterns ─────────────────────────────────────────────────────────────

_PII_PATTERNS: list[tuple[str, str, str]] = [
    # SSN (US Social Security Number)
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN", "***-**-****"),
    (r"\b\d{9}\b", "SSN (raw)", "***-**-****"),
    # Credit card numbers
    (r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))\d{12,15}\b",
     "Credit card", "****-****-****-****"),
    # Email addresses
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
     "Email", "[EMAIL REDACTED]"),
    # Phone numbers (US format)
    (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
     "Phone", "[PHONE REDACTED]"),
    # API keys (common patterns)
    (r"\b(?:sk-[a-zA-Z0-9]{20,}|api[_-]?key[_-]?[a-zA-Z0-9]{20,})\b",
     "API key", "[API KEY REDACTED]"),
]

_COMPILED_PII: list[tuple[re.Pattern, str, str]] = [
    (re.compile(pattern), pii_type, replacement)
    for pattern, pii_type, replacement in _PII_PATTERNS
]


# ── System prompt leak detection ─────────────────────────────────────────────

_SYSTEM_PROMPT_FRAGMENTS: list[str] = [
    "you are a financial data analyst assistant",
    "you have access to a duckdb financial database",
    "respond with ONLY a valid DuckDB SQL query",
    "never make up data",
    "system prompt",
    "system instructions",
    "your instructions are",
]


# ── Hallucination heuristic ──────────────────────────────────────────────────
# Check if key entities from the context appear in the answer.

def _extract_entities(text: str) -> set[str]:
    """Extract meaningful entities (numbers, proper nouns) from text."""
    # Numbers (financial figures)
    numbers = set(re.findall(r"\$?\d[\d,.]+%?", text))
    # Capitalized words (company names, etc.)
    caps = set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text))
    return numbers | caps


def _hallucination_score(answer: str, context: str) -> float:
    """Score how grounded the answer is in the context.

    Returns 0.0 if fully grounded, 1.0 if likely hallucinated.
    """
    if not context or not answer:
        return 0.0

    answer_entities = _extract_entities(answer)
    context_entities = _extract_entities(context)

    if not answer_entities:
        return 0.0

    # What fraction of answer entities appear in context?
    grounded = answer_entities & context_entities
    if not answer_entities:
        return 0.0

    ratio = len(grounded) / len(answer_entities)
    return max(0.0, 1.0 - ratio)


# ── Main check function ──────────────────────────────────────────────────────

def check_output(
    answer: str,
    context: str = "",
    query: str = "",
) -> OutputVerdict:
    """Check LLM output for safety issues.

    Args:
        answer: The LLM's response text.
        context: The retrieved context used to generate the answer.
        query: The original user query.

    Returns:
        OutputVerdict with safe=True if the output passes all checks.
    """
    if not answer:
        return OutputVerdict(safe=True)

    # 1. Check for system prompt leaks
    answer_lower = answer.lower()
    for fragment in _SYSTEM_PROMPT_FRAGMENTS:
        if fragment in answer_lower:
            return OutputVerdict(
                safe=False,
                reason="Response contains system prompt fragments",
            )

    # 2. Check for PII
    masked = answer
    pii_found = []
    for compiled, pii_type, replacement in _COMPILED_PII:
        matches = compiled.findall(masked)
        if matches:
            pii_found.extend([f"{pii_type}: {m}" for m in matches])
            masked = compiled.sub(replacement, masked)

    # 3. Hallucination check
    h_score = _hallucination_score(answer, context) if context else 0.0

    # If high hallucination score and answer contains specific numbers
    if h_score > 0.7:
        # Check if the answer makes specific numerical claims not in context
        answer_numbers = set(re.findall(r"\$?\d[\d,.]+%?", answer))
        context_numbers = set(re.findall(r"\$?\d[\d,.]+%?", context))
        unsupported = answer_numbers - context_numbers
        if unsupported:
            return OutputVerdict(
                safe=False,
                reason=f"Potential hallucination: answer contains figures not in context: {unsupported}",
                hallucination_score=h_score,
                pii_found=pii_found,
                masked_answer=masked if pii_found else None,
            )

    if pii_found:
        return OutputVerdict(
            safe=True,
            reason=f"PII detected and masked: {', '.join(pii_found)}",
            masked_answer=masked,
            pii_found=pii_found,
            hallucination_score=h_score,
        )

    return OutputVerdict(
        safe=True,
        hallucination_score=h_score,
    )
