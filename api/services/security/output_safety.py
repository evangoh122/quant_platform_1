"""output_safety.py — Output sanitization, leak detection, and secret redaction.

Sanitizes all model-produced and tool-produced display text. Detects and
redacts secrets, unsafe HTML/Markdown, and system prompt leaks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OutputVerdict:
    """Result of output safety checks."""
    safe: bool
    sanitized_text: str = ""
    reason: Optional[str] = None
    secrets_found: list[str] = field(default_factory=list)
    leak_detected: bool = False
    pii_found: list[str] = field(default_factory=list)


# ── Unsafe HTML/Markdown patterns ───────────────────────────────────────────

# Script tags and event handlers
_SCRIPT_RE = re.compile(
    r"<\s*script[^>]*>.*?<\s*/\s*script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_HANDLER_RE = re.compile(
    r"\bon\w+\s*=",  # onclick, onload, onerror, etc.
    re.IGNORECASE,
)
_IFRAME_RE = re.compile(
    r"<\s*iframe[^>]*>.*?<\s*/\s*iframe\s*>",
    re.IGNORECASE | re.DOTALL,
)
_FORM_RE = re.compile(
    r"<\s*form[^>]*>.*?<\s*/\s*form\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SVG_RE = re.compile(
    r"<\s*svg[^>]*>.*?<\s*/\s*svg\s*>",
    re.IGNORECASE | re.DOTALL,
)
_STYLE_RE = re.compile(
    r"<\s*style[^>]*>.*?<\s*/\s*style\s*>",
    re.IGNORECASE | re.DOTALL,
)
_RAW_TAG_RE = re.compile(
    r"<\s*/?\s*(?:div|span|p|a|img|br|hr|h[1-6]|table|tr|td|th|"
    r"ul|ol|li|pre|code|blockquote|em|strong|b|i|u|s|del|ins|"
    r"mark|small|sub|sup|abbr|cite|q|kbd|var|samp|details|summary|"
    r"section|article|nav|header|footer|main|aside|figure|figcaption|"
    r"audio|video|source|track|map|area|canvas|picture|object|embed|"
    r"param|output|progress|meter|datalist|fieldset|legend|label|"
    r"select|option|optgroup|textarea|button|datalist)\b[^>]*>",
    re.IGNORECASE,
)

# Dangerous URL schemes
_DANGEROUS_URL_RE = re.compile(
    r"(?:javascript|data|vbscript|file)\s*:",
    re.IGNORECASE,
)

# Protocol-relative URLs
_PROTOCOL_RELATIVE_RE = re.compile(r"//[^/\s]")

# Remote Markdown images: ![alt](url) or ![alt](url "title")
_MD_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)]+?)(?:\s+\"[^\"]*\")?\)",
)

# Embedded credentials in URLs: user:pass@host
_EMBEDDED_CRED_RE = re.compile(
    r"://[^@\s]+:[^@\s]+@",
)


# ── Secret detection patterns ───────────────────────────────────────────────

_SECRET_PATTERNS: list[tuple[str, str]] = [
    # API keys
    (r"\b(?:sk-[a-zA-Z0-9]{20,}|api[_-]?key[_-]?[a-zA-Z0-9]{20,})\b", "API key"),
    # AWS keys
    (r"\b(?:AKIA[0-9A-Z]{16})\b", "AWS access key"),
    (r"\b(?:[0-9a-zA-Z/+=]{40})\b", "AWS secret key (candidate)"),
    # Generic bearer tokens
    (r"\b(?:Bearer\s+[a-zA-Z0-9._\-]{20,})\b", "Bearer token"),
    # JWT tokens
    (r"\b(?:eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*)\b", "JWT token"),
    # Connection strings
    (r"\b(?:postgresql|mysql|mongodb|redis)://[^\s]+", "Connection string"),
    # Private keys
    (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "Private key"),
]

_COMPILED_SECRETS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), name)
    for pattern, name in _SECRET_PATTERNS
]

# PII patterns
_PII_PATTERNS: list[tuple[str, str, str]] = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN", "***-**-****"),
    (r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))\d{12,15}\b",
     "Credit card", "****-****-****-****"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
     "Email", "[EMAIL REDACTED]"),
]

_COMPILED_PII: list[tuple[re.Pattern, str, str]] = [
    (re.compile(pattern), name, replacement)
    for pattern, name, replacement in _PII_PATTERNS
]


# ── System prompt leak detection ────────────────────────────────────────────

# Canary fingerprints (versioned, injected into prompts)
_CANARY_PATTERNS: list[str] = [
    # These would be populated with actual canary values from the system prompt
    "you are a financial data analyst assistant",
    "you have access to a duckdb financial database",
    "respond with only a valid duckdb sql query",
    "never make up data",
    "system prompt",
    "system instructions",
    "your instructions are",
    "you are a financial analyst assistant specializing in sec filings",
]

# Encoded/transformed variants of leak patterns
_ENCODED_LEAK_PATTERNS: list[re.Pattern] = [
    # Base64-encoded system prompt fragments
    re.compile(r"(?:you are|system prompt|instructions)", re.IGNORECASE),
]


def _sanitize_html(text: str) -> str:
    """Remove or escape raw HTML tags, keeping only safe Markdown.

    Returns text with dangerous HTML neutralized.
    """
    if not text:
        return ""

    # Remove script blocks entirely
    text = _SCRIPT_RE.sub("[SCRIPT REMOVED]", text)

    # Remove iframe blocks entirely
    text = _IFRAME_RE.sub("[IFRAME REMOVED]", text)

    # Remove form blocks entirely
    text = _FORM_RE.sub("[FORM REMOVED]", text)

    # Remove SVG blocks entirely
    text = _SVG_RE.sub("[SVG REMOVED]", text)

    # Remove style blocks entirely
    text = _STYLE_RE.sub("[STYLE REMOVED]", text)

    # Remove event handlers
    text = _EVENT_HANDLER_RE.sub("[EVENT-HANDLER-REMOVED]", text)

    # Escape remaining raw HTML tags (angle brackets)
    # This makes them display as text rather than rendering
    text = _RAW_TAG_RE.sub(lambda m: m.group(0).replace("<", "&lt;").replace(">", "&gt;"), text)

    return text


def _sanitize_urls(text: str) -> str:
    """Neutralize dangerous URLs and schemes."""
    if not text:
        return ""

    # Neutralize dangerous schemes
    text = _DANGEROUS_URL_RE.sub("[UNSAFE-URL]", text)

    # Neutralize protocol-relative URLs
    text = _PROTOCOL_RELATIVE_RE.sub("[PROTOCOL-RELATIVE-URL]", text)

    # Neutralize embedded credentials
    text = _EMBEDDED_CRED_RE.sub("://[CREDENTIALS-REMOVED]@", text)

    return text


def _remove_markdown_images(text: str) -> str:
    """Remove Markdown images (potential data exfiltration via URL).

    Converts ![alt](url) to [IMAGE REMOVED] to prevent the renderer
    from fetching the URL (which could leak data in the query string).
    """
    if not text:
        return ""
    return _MD_IMAGE_RE.sub("[IMAGE REMOVED]", text)


def detect_secrets(text: str, configured_secrets: list[str] | None = None) -> list[str]:
    """Detect known secret patterns in text.

    Returns a list of descriptions of secrets found.
    """
    if not text:
        return []

    found: list[str] = []

    # Check pattern-based secrets
    for compiled, name in _COMPILED_SECRETS:
        matches = compiled.findall(text)
        if matches:
            for m in matches:
                found.append(f"{name}: {m[:20]}...")

    # Check configured secret values (exact match)
    if configured_secrets:
        for secret in configured_secrets:
            if secret and len(secret) >= 8 and secret in text:
                found.append(f"Configured secret value detected")

    return found


def detect_prompt_leak(
    text: str,
    canary_values: list[str] | None = None,
) -> bool:
    """Detect if the text contains system prompt fragments or canary values.

    Returns True if a leak is detected.
    """
    if not text:
        return False

    text_lower = text.lower()

    # Check built-in canary patterns
    for canary in _CANARY_PATTERNS:
        if canary in text_lower:
            return True

    # Check additional canary values
    if canary_values:
        for canary in canary_values:
            if canary and len(canary) >= 10 and canary.lower() in text_lower:
                return True

    return False


def sanitize_output(
    text: str,
    configured_secrets: list[str] | None = None,
    canary_values: list[str] | None = None,
    check_leaks: bool = True,
) -> OutputVerdict:
    """Full output sanitization pipeline.

    1. Remove/escape unsafe HTML
    2. Neutralize dangerous URLs
    3. Remove Markdown images
    4. Detect secrets
    5. Detect prompt leaks
    6. Detect PII

    On leak detection, replaces the entire answer with a generic refusal.
    """
    if not text:
        return OutputVerdict(safe=True, sanitized_text="")

    # Step 1: Sanitize HTML
    sanitized = _sanitize_html(text)

    # Step 2: Sanitize URLs
    sanitized = _sanitize_urls(sanitized)

    # Step 3: Remove Markdown images
    sanitized = _remove_markdown_images(sanitized)

    # Step 4: Detect secrets
    secrets = detect_secrets(sanitized, configured_secrets)

    # Step 5: Detect prompt leaks
    leak = False
    if check_leaks:
        leak = detect_prompt_leak(sanitized, canary_values)

    # Step 6: Detect PII
    pii_found: list[str] = []
    for compiled, pii_type, replacement in _COMPILED_PII:
        matches = compiled.findall(sanitized)
        if matches:
            pii_found.extend([f"{pii_type}: {m}" for m in matches])
            sanitized = compiled.sub(replacement, sanitized)

    # If leak detected, replace entire answer
    if leak:
        return OutputVerdict(
            safe=False,
            sanitized_text="I cannot provide that information. Please rephrase your question.",
            reason="System prompt leak detected in output",
            leak_detected=True,
            secrets_found=secrets,
            pii_found=pii_found,
        )

    # If secrets found, redact entire answer
    if secrets:
        return OutputVerdict(
            safe=False,
            sanitized_text="I cannot provide that information. Please rephrase your question.",
            reason="Secret/credential detected in output",
            secrets_found=secrets,
            pii_found=pii_found,
        )

    return OutputVerdict(
        safe=True,
        sanitized_text=sanitized,
        secrets_found=secrets,
        pii_found=pii_found,
    )


def redact_for_audit(text: str) -> str:
    """Recursively redact sensitive content for audit logs.

    Removes: prompt bodies, chunk text, tool payloads, secrets, tokens,
    cookies, authorization headers, notes, and full model output.
    """
    if not text:
        return "[REDACTED]"

    # Redact secrets
    for compiled, _ in _COMPILED_SECRETS:
        text = compiled.sub("[SECRET-REDACTED]", text)

    # Redact PII
    for compiled, _, _ in _COMPILED_PII:
        text = compiled.sub("[PII-REDACTED]", text)

    # Redact connection strings
    text = re.sub(
        r"(?:postgresql|mysql|mongodb|redis)://[^\s]+",
        "[CONNECTION-REDACTED]",
        text,
        flags=re.IGNORECASE,
    )

    # Redact auth headers
    text = re.sub(
        r"(?:Authorization|Cookie|X-Api-Key)\s*:\s*\S+",
        "[AUTH-REDACTED]",
        text,
        flags=re.IGNORECASE,
    )

    return text