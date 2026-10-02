"""
dialog_rails.py — Phase 13: Dialog Rail (Off-Topic Detection).

Detects off-topic queries (non-financial) and gracefully refuses to answer.
Uses keyword-based topic classification (no external ML model required).

Usage:
    from api.services.guardrails.dialog_rails import check_dialog, DialogVerdict
    verdict = check_dialog(user_message)
    if verdict.off_topic:
        return {"answer": verdict.refusal_message}
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class DialogVerdict:
    on_topic: bool
    off_topic: bool = False
    advice: bool = False          # True when the query seeks investment advice (hard-refused)
    topic: Optional[str] = None
    refusal_message: Optional[str] = None


# ── Investment-advice rail (Legal & Regulatory) ──────────────────────────────
# This product summarizes public SEC filings; it is NOT a licensed investment
# adviser. Questions that ask for a recommendation, a personal action, or a price
# prediction are HARD-REFUSED with the disclaimer below — we never answer "should
# I buy/sell" style questions, even though they contain financial keywords.

NOT_ADVICE_DISCLAIMER: str = (
    "This assistant is not a licensed investment adviser and does not provide "
    "investment advice, recommendations, or price predictions. Information is "
    "for general informational purposes only, sourced from public SEC filings."
)

_ADVICE_REFUSAL: str = (
    "I can't help with that — I'm not a licensed investment adviser, so I can't "
    "give investment advice, recommendations, or price predictions. I can only "
    "summarize what public SEC filings disclose — for example, what a company's "
    "latest 10-K says about its revenue, margins, guidance, or risk factors. "
    f"\n\n{NOT_ADVICE_DISCLAIMER}"
)

# High-precision patterns — every one contains an explicit advice/recommendation/
# prediction cue, so factual queries ("what was revenue?", "gross margin?") are
# never caught.
_ADVICE_PATTERNS: list[str] = [
    r"\bshould i (buy|sell|hold|invest|short|trade|purchase|dump|own|add)\b",
    # "you recommend" only — bare "recommend buying" matches filing facts like
    # "does the board recommend buying back shares?", so it's intentionally excluded.
    r"\b(do|would|can|should) (you|u) recommend\b",
    r"\bis (it|now|this|that|the stock)\b.{0,40}\b(a good|a bad)\b.{0,15}\b(buy|investment|time to (buy|sell|invest))\b",
    r"\b(good|bad|great|smart|safe|risky) (investment|buy|stock to (buy|own|pick))\b",
    r"\bworth (buying|investing|owning|the investment)\b",
    r"\bprice target\b",
    r"\bwhat should i do with my (money|portfolio|shares|investment|stocks|savings)\b",
    r"\b(what|which|any) (stock|stocks|shares|companies)\b.{0,20}\b(should i |to )?(buy|invest in|pick)\b",
    # NB: bare "overvalued/undervalued" was removed — it matches filing-analysis
    # questions (e.g. "is goodwill overvalued per the impairment test?").
    r"\b(buy or sell|sell or buy)\b",
    r"\bshould i put my (money|cash|savings)\b",
    r"\bwill (the |this )?(stock|price|share price|it)\b.{0,30}\b(go up|go down|rise|fall|drop|crash|tank|moon|double|skyrocket|rebound|recover)\b",
    r"\b(is it|good time) (a good time )?to (buy|sell|invest)\b",
]

_COMPILED_ADVICE: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in _ADVICE_PATTERNS
]


# ── Financial topic keywords ─────────────────────────────────────────────────
# Queries matching these are considered on-topic for a financial SEC filing assistant.

_FINANCIAL_KEYWORDS: set[str] = {
    # Financial statements
    "revenue", "income", "profit", "loss", "earnings", "margin", "cost",
    "expense", "cash flow", "operating", "net income", "gross profit",
    "ebitda", "free cash flow", "fcf", "capex", "capital expenditure",
    "depreciation", "amortization", "sga", "r&d", "research and development",
    "dividend", "buyback", "share repurchase", "eps", "earnings per share",
    # Balance sheet
    "assets", "liabilities", "equity", "debt", "cash", "inventory",
    "receivable", "payable", "goodwill", "intangible", "current ratio",
    "debt to equity", "leverage", "liquidity", "solvency",
    # SEC filings
    "10-k", "10-q", "8-k", "sec filing", "edgar", "xbrl", "gaap",
    "non-gaap", "restatement", "amendment", "annual report",
    "quarterly report", "form type", "accession", "cik",
    # Company/stock
    "stock", "share", "ticker", "market cap", "valuation", "p/e",
    "price to earnings", "portfolio", "sector", "industry",
    "competitor", "market share",
    # Financial metrics
    "revenue growth", "profit margin", "operating margin", "net margin",
    "return on equity", "roe", "return on assets", "roa",
    "current ratio", "quick ratio", "working capital",
    # Business
    "fiscal year", "fiscal quarter", "segment", "subsidiary",
    "acquisition", "merger", "spinoff", "ipo", "offering",
    # Semiconductor-specific
    "gpu", "data center", "gaming", "ai chip", "semiconductor",
    "wafer", "fab", "foundry", "chip", "asic", "fpga",
    "dram", "nand", "memory", "microcontroller", "analog",
    "test equipment", "packaging", "substrate", "euv lithography",
    # Risk & governance
    "risk", "risks", "risk factor", "management discussion", "md&a",
    "material weakness", "going concern", "contingency", "litigation",
}

# ── Off-topic indicators ─────────────────────────────────────────────────────
# Queries strongly matching these are off-topic.

_OFF_TOPIC_PATTERNS: list[tuple[str, str]] = [
    (r"\b(recipe|cook|bake|ingredient)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(weather|temperature|forecast|rain|snow)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(sports|football|basketball|soccer|baseball|game score)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(movie|tv show|netflix|youtube|music|song|album)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(politics|election|president|senator|congress|democrat|republican)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(joke|riddle|poem|story|tale|novel)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    # NB: bare "test" intentionally excluded — it legitimately appears in filings
    # ("impairment test", "test equipment", "stress test"). Education abuse is still
    # caught by the other terms.
    (r"\b(homework|exam|quiz|assignment|essay)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(travel|hotel|flight|vacation|restaurant|food)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(dating|relationship|love|romance|marriage)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(medical|doctor|symptom|disease|medication|health advice)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
]

_COMPILED_OFF_TOPIC: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), refusal)
    for pattern, refusal in _OFF_TOPIC_PATTERNS
]

# Word-boundary matcher for the financial allowlist. Plain substring matching
# (`kw in msg_lower`) produced false positives on short keys — "eps"→"st**eps**",
# "ipo"→"**ipo**d", "roa"→"ab**roa**d", "fab"→"**fab**ulous", "asic"→"b**asic**" —
# which classified off-topic queries ("what are the steps to bake a cake") as
# on-topic and routed them into the RAG pipeline. \b boundaries close this.
# Longest-first so multi-word phrases ("free cash flow") win over their parts;
# every keyword starts/ends with a word char, so \b…\b is well-defined.
_FINANCIAL_KEYWORD_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(kw) for kw in sorted(_FINANCIAL_KEYWORDS, key=len, reverse=True))
    + r")\b"
)


def check_dialog(message: str) -> DialogVerdict:
    """Check if the user query is on-topic for a financial SEC filing assistant.

    Args:
        message: The raw user input string.

    Returns:
        DialogVerdict with off_topic=True if the query is clearly non-financial.
    """
    if not message or not message.strip():
        return DialogVerdict(on_topic=True)

    # Investment-advice rail runs FIRST: advice questions ("should I buy NVDA?")
    # contain financial keywords, so they would otherwise pass as on-topic. They
    # are hard-refused with the not-a-licensed-adviser disclaimer.
    for compiled in _COMPILED_ADVICE:
        if compiled.search(message):
            return DialogVerdict(
                on_topic=False,
                advice=True,
                topic="investment_advice",
                refusal_message=_ADVICE_REFUSAL,
            )

    # Financial-keyword allowlist runs BEFORE the generic off-topic denylist
    # (Codex r3): otherwise a legitimate accounting question is wrongly refused
    # because a generic education term matches an incidental word — e.g. "test" in
    # "impairment test" / "test equipment". A genuine financial question wins.
    msg_lower = message.lower()
    has_financial_keyword = bool(_FINANCIAL_KEYWORD_RE.search(msg_lower))
    if has_financial_keyword:
        return DialogVerdict(on_topic=True)

    # Check off-topic patterns (only for queries with NO financial keyword)
    for compiled, refusal in _COMPILED_OFF_TOPIC:
        if compiled.search(message):
            return DialogVerdict(
                on_topic=False,
                off_topic=True,
                topic="off_topic",
                refusal_message=refusal,
            )

    # Short queries (commands, greetings) are allowed through
    if len(message.split()) <= 3:
        return DialogVerdict(on_topic=True)

    # Queries without financial keywords and longer than 3 words
    # are potentially off-topic but we allow them through with a soft check
    # (the retrieval/generation pipeline will handle insufficient context)
    return DialogVerdict(on_topic=True)
