"""input_validator.py — Canonicalize and validate user/history text.

Implements Unicode normalization, control character rejection, and hard caps
on character/token/turn counts. All user-facing text passes through this
before reaching any LLM or tool.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InputLimits:
    """Configurable hard caps for input validation."""
    max_chars: int = 4000
    max_tokens_est: int = 3000  # rough estimate: ~1.3 chars/token
    max_history_turns: int = 20
    max_history_chars: int = 20000
    max_bidi_depth: int = 0  # zero tolerance for bidi overrides


# Characters explicitly forbidden in user input
_FORBIDDEN_CHARS_RE = re.compile(
    r"[\x00"           # NUL
    r"\u202a-\u202e"   # LRE/RLE/LRO/RLO/PDF bidi overrides
    r"\u2066-\u2069"   # LRI/RLI/FSI/PDI bidi isolates
    r"\u200b-\u200f"   # zero-width space/non-joining/RLM/LRM
    r"\u2028\u2029"    # line/paragraph separator
    r"\u00ad"          # soft hyphen
    r"\u034f"          # combining grapheme joiner
    r"\u061c"          # Arabic letter mark
    r"\ufff9-\ufffb"   # interlinear annotations
    r"\U000e0001"      # language tag
    r"\U000e0020-\U000e007f"  # tag characters
    r"]"
)

# Additional dangerous control characters (except common whitespace)
_CONTROL_RE = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Bidi override characters (explicit check)
_BIDI_OVERRIDES = set(
    "\u202a\u202b\u202c\u202d\u202e"  # LRE/RLE/PDF/LRO/RLO
    "\u2066\u2067\u2068\u2069"         # LRI/RLI/FSI/PDI
)

# Regex for detecting excessive repeated characters (spam/overflow)
_REPEAT_RE = re.compile(r"(.)\1{50,}")

# ── Injection detection patterns (defense in depth) ─────────────────────────

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # System prompt override attempts
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
     "Attempted system prompt override"),
    (r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
     "Attempted system prompt override"),
    (r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
     "Attempted system prompt override"),
    (r"you\s+are\s+now\s+(a|an)\s+",
     "Attempted role hijacking"),
    (r"new\s+instructions?\s*:",
     "Attempted instruction injection"),
    (r"system\s*:\s*",
     "Attempted system message injection"),
    (r"\[system\]",
     "Attempted system message injection"),
    (r"<\s*system\s*>",
     "Attempted system message injection"),

    # DAN-style jailbreaks
    (r"do\s+anything\s+now",
     "DAN-style jailbreak attempt"),
    (r"jailbreak",
     "Jailbreak attempt (explicit mention)"),
    (r"bypass\s+(all\s+)?(safety|content|security)\s+(filters?|restrictions?|rules?|safeguards?)",
     "Safety bypass attempt"),
    (r"for\s+a\s+security\s+audit.*bypass",
     "Safety bypass attempt"),

    # Prompt leaking
    (r"(reveal|show|print|output|repeat)\s+\w*\s*(your|the)\s+(system|initial|original)\s+(prompt|instructions?)",
     "Prompt leaking attempt"),
    (r"what\s+(are|is)\s+your\s+(system|initial|original)\s+(prompt|instructions?)",
     "Prompt leaking attempt"),
    (r"repeat\s+(everything|all)\s+(above|before)",
     "Prompt leaking attempt"),
    (r"(show|reveal|tell|give)\s+\w*\s*(me|us)\s+\w*\s*(your|the)\s+(system|initial|original|full)\s+(prompt|instructions?)",
     "Prompt leaking attempt"),

    # Encoding/obfuscation attacks
    (r"(base64|rot13|hex)\s+(encode|decode)",
     "Encoding-based evasion attempt"),
]

_COMPILED_INJECTION: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in _INJECTION_PATTERNS
]

_JAILBREAK_KEYWORDS: set[str] = {
    "DAN", "jailbreak", "prompt injection",
    "ignore previous", "ignore instructions",
    "you are now", "act as if",
}


@dataclass
class ValidationResult:
    """Result of input validation."""
    valid: bool
    canonical_text: Optional[str] = None
    reason: Optional[str] = None
    char_count: int = 0
    token_estimate: int = 0


def canonicalize_text(text: str) -> str:
    """Normalize Unicode and strip dangerous characters.

    Steps:
    1. NFKC normalization (compatibility decomposition + canonical composition)
    2. Remove forbidden characters (bidi overrides, zero-width, tags)
    3. Remove control characters except \\n, \\r, \\t
    4. Collapse excessive whitespace
    5. Strip leading/trailing whitespace
    """
    if not text:
        return ""

    # Step 1: NFKC normalization
    text = unicodedata.normalize("NFKC", text)

    # Step 2: Remove forbidden characters
    text = _FORBIDDEN_CHARS_RE.sub("", text)

    # Step 3: Remove dangerous control chars (keep \n \r \t)
    text = _CONTROL_RE.sub("", text)

    # Step 4: Collapse excessive whitespace
    text = re.sub(r"[ \t]{3,}", "  ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # Step 5: Strip
    text = text.strip()

    return text


def validate_input(
    text: str,
    limits: InputLimits | None = None,
    field_name: str = "input",
) -> ValidationResult:
    """Validate user input against security constraints.

    Returns ValidationResult with valid=True only if the text passes all checks.
    The canonical_text field contains the cleaned text when valid.
    """
    if limits is None:
        limits = InputLimits()

    if text is None:
        return ValidationResult(valid=False, reason=f"{field_name}: null input")

    # Canonicalize first
    canonical = canonicalize_text(text)

    if not canonical:
        return ValidationResult(valid=False, reason=f"{field_name}: empty after canonicalization")

    # Character limit
    if len(canonical) > limits.max_chars:
        return ValidationResult(
            valid=False,
            reason=f"{field_name}: exceeds {limits.max_chars} character limit ({len(canonical)} chars)",
        )

    # Token estimate (rough: ~4 chars per token for English)
    token_est = max(1, len(canonical) // 4)
    if token_est > limits.max_tokens_est:
        return ValidationResult(
            valid=False,
            reason=f"{field_name}: estimated tokens ({token_est}) exceed limit ({limits.max_tokens_est})",
        )

    # Check for bidi override characters (zero tolerance)
    found_bidi = [c for c in canonical if c in _BIDI_OVERRIDES]
    if found_bidi and limits.max_bidi_depth == 0:
        return ValidationResult(
            valid=False,
            reason=f"{field_name}: contains bidi override characters",
        )

    # Check for excessive repetition (spam/overflow attack)
    if _REPEAT_RE.search(canonical):
        return ValidationResult(
            valid=False,
            reason=f"{field_name}: excessive character repetition detected",
        )

    # Check injection patterns (defense in depth)
    for compiled, reason in _COMPILED_INJECTION:
        if compiled.search(canonical):
            return ValidationResult(
                valid=False,
                reason=reason,
            )

    # Check jailbreak keywords (case-insensitive)
    canonical_lower = canonical.lower()
    for keyword in _JAILBREAK_KEYWORDS:
        if keyword.lower() in canonical_lower:
            return ValidationResult(
                valid=False,
                reason=f"Jailbreak keyword detected: {keyword}",
            )

    return ValidationResult(
        valid=True,
        canonical_text=canonical,
        char_count=len(canonical),
        token_estimate=token_est,
    )


def validate_history(
    history: list[dict[str, str]] | None,
    limits: InputLimits | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    """Validate and filter conversation history.

    History is treated as untrusted data (not instructions), so injection
    detection is skipped — only structural validation (role, length, chars)
    is applied. The envelope encoder wraps history as untrusted data.

    Returns (valid_turns, reasons) where valid_turns contains only
    sanitized turns and reasons lists any validation failures.
    """
    if limits is None:
        limits = InputLimits()

    if not history:
        return [], []

    valid_turns: list[dict[str, str]] = []
    reasons: list[str] = []
    total_chars = 0

    # Take only the last N turns
    recent = history[-limits.max_history_turns:]

    for i, turn in enumerate(recent):
        role = turn.get("role", "")
        content = turn.get("content", "")

        if role not in ("user", "assistant"):
            reasons.append(f"history[{i}]: invalid role '{role}'")
            continue

        if not isinstance(content, str):
            reasons.append(f"history[{i}]: non-string content")
            continue

        # Canonicalize but skip injection detection — history is data
        canonical = canonicalize_text(content)
        if not canonical:
            reasons.append(f"history[{i}]: empty after canonicalization")
            continue

        if len(canonical) > limits.max_chars:
            reasons.append(f"history[{i}]: exceeds {limits.max_chars} char limit")
            continue

        total_chars += len(canonical)
        if total_chars > limits.max_history_chars:
            reasons.append(f"history[{i}]: cumulative char limit exceeded")
            break

        valid_turns.append({
            "role": role,
            "content": canonical[:2000],  # cap per-turn
        })

    return valid_turns, reasons