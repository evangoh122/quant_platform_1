"""
xbrl_relevance.py — Maps XBRL concepts to financial topic groups and filters
relevant facts by query intent. Returns max 8 facts for contextual display.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

ConceptGroup = str
ConceptName = str

_LATEST_QUERY_TERMS = (
    "latest",
    "most recent",
    "current",
    "newest",
    "last reported",
)
_LATEST_QUERY_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in _LATEST_QUERY_TERMS) + r")\b",
    re.IGNORECASE,
)


def _to_float(value: Any) -> float | None:
    """Safely cast an XBRL value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_value(fact: Dict[str, Any]) -> Any:
    """Return the fact's numeric value, preferring 'value' then 'val'.

    Uses an explicit None check, NOT truthiness — a legitimate 0 (e.g. zero
    long-term debt, zero R&D) must survive and be treated as a real value,
    not fall through to the alternate key or be dropped.
    """
    v = fact.get("value")
    if v is None:
        v = fact.get("val")
    return v


def get_fact_period(fact: Dict[str, Any]) -> str:
    """Return the best available display period for an XBRL fact."""
    for key in ("period_end", "period", "end"):
        value = fact.get(key)
        if value is not None and str(value).strip():
            period = str(value).strip()
            date_match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T\s].*)?$", period)
            return date_match.group(1) if date_match else period

    fiscal_year = fact.get("fiscal_year")
    if fiscal_year is not None and str(fiscal_year).strip():
        fiscal_period = str(fact.get("fiscal_period") or "").strip()
        if fiscal_period.upper() == "FY":
            fiscal_period = ""
        return f"FY{fiscal_year} {fiscal_period}".strip()

    filed = fact.get("filed")
    return str(filed) if filed is not None and str(filed).strip() else ""


def _fact_year(fact: Dict[str, Any]) -> int | None:
    """Return the fiscal year, falling back to a year parsed from the period."""
    fiscal_year = fact.get("fiscal_year")
    if fiscal_year is not None:
        match = re.search(r"\b(19|20)\d{2}\b", str(fiscal_year))
        if match:
            return int(match.group(0))

    match = re.search(r"\b(19|20)\d{2}\b", get_fact_period(fact))
    return int(match.group(0)) if match else None


def filter_facts_for_query(query: str, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For explicit latest queries, keep facts from the newest available year."""
    if not facts:
        return []
    if not _LATEST_QUERY_PATTERN.search(query):
        return facts

    facts_with_years = [(fact, _fact_year(fact)) for fact in facts]
    years = [year for _, year in facts_with_years if year is not None]
    if not years:
        return facts
    latest_year = max(years)
    return [fact for fact, year in facts_with_years if year == latest_year]

CONCEPT_GROUP_MAP: Dict[ConceptName, ConceptGroup] = {
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "SalesRevenueNet": "revenue",
    "SalesRevenueGoodsNet": "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "revenue",
    "NetIncomeLoss": "profitability",
    "GrossProfit": "profitability",
    "OperatingIncomeLoss": "profitability",
    "EarningsPerShareBasic": "profitability",
    "EarningsPerShareDiluted": "profitability",
    "CostOfGoodsAndServicesSold": "profitability",
    "CostOfRevenue": "profitability",
    "ResearchAndDevelopmentExpense": "profitability",
    "SellingGeneralAndAdministrativeExpense": "profitability",
    "OperatingExpenses": "profitability",
    "InterestExpense": "profitability",
    "IncomeTaxExpenseBenefit": "profitability",
    "Assets": "leverage",
    "Liabilities": "leverage",
    "StockholdersEquity": "leverage",
    "LongTermDebt": "leverage",
    "LongTermDebtCurrent": "leverage",
    "LiabilitiesCurrent": "leverage",
    "AssetsCurrent": "leverage",
    "DebtInstrumentCarryingAmount": "leverage",
    "CashAndCashEquivalentsAtCarryingValue": "liquidity",
    "OperatingCashFlow": "liquidity",
    "NetCashProvidedByUsedInOperatingActivities": "liquidity",
    "NetCashProvidedByUsedInInvestingActivities": "liquidity",
    "NetCashProvidedByUsedInFinancingActivities": "liquidity",
    "PaymentsToAcquirePropertyPlantAndEquipment": "liquidity",
    "FreeCashFlow": "liquidity",
    "CommonStockSharesOutstanding": "valuation",
    "CommonStockSharesIssued": "valuation",
    "TreasuryStockSharesAcquired": "valuation",
    "MarketCapitalization": "valuation",
    "InterestIncomeExpenseNet": "banking",
    "ProvisionForLoanLeaseAndOtherLosses": "banking",
    "InvestmentIncomeNet": "banking",
    "LoansAndLeasesReceivableNetReportedAmount": "banking",
    "Deposits": "banking",
    "TradingAccountAssets": "banking",
}

QUERY_KEYWORD_TO_GROUP: Dict[str, ConceptGroup] = {
    "revenue": "revenue",
    "sales": "revenue",
    "top line": "revenue",
    "income": "profitability",
    "gross profit": "profitability",
    "gross margin": "profitability",
    "net income": "profitability",
    "profit": "profitability",
    "earnings": "profitability",
    "eps": "profitability",
    "operating income": "profitability",
    "operating margin": "profitability",
    "r&d": "profitability",
    "research": "profitability",
    "expense": "profitability",
    "cost": "profitability",
    "margin": "profitability",
    "debt": "leverage",
    "leverage": "leverage",
    "liability": "leverage",
    "equity": "leverage",
    "balance sheet": "leverage",
    "asset": "leverage",
    "cash": "liquidity",
    "liquidity": "liquidity",
    "free cash": "liquidity",
    "cash flow": "liquidity",
    "capex": "liquidity",
    "capital expenditure": "liquidity",
    "operating cash": "liquidity",
    "share": "valuation",
    "outstanding": "valuation",
    "market cap": "valuation",
    "loan": "banking",
    "deposit": "banking",
    "interest income": "banking",
    "net interest": "banking",
    "provision": "banking",
}

_DISPLAY_NAMES: Dict[str, str] = {
    "Revenues": "Revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
    "SalesRevenueNet": "Revenue",
    "SalesRevenueGoodsNet": "Revenue",
    "NetIncomeLoss": "Net Income",
    "GrossProfit": "Gross Profit",
    "OperatingIncomeLoss": "Operating Income",
    "EarningsPerShareBasic": "EPS (Basic)",
    "EarningsPerShareDiluted": "EPS (Diluted)",
    "CostOfGoodsAndServicesSold": "COGS",
    "CostOfRevenue": "Cost of Revenue",
    "ResearchAndDevelopmentExpense": "R&D Expense",
    "OperatingExpenses": "Operating Expenses",
    "InterestExpense": "Interest Expense",
    "Assets": "Total Assets",
    "Liabilities": "Total Liabilities",
    "StockholdersEquity": "Shareholders' Equity",
    "LongTermDebt": "Long-Term Debt",
    "CashAndCashEquivalentsAtCarryingValue": "Cash & Equivalents",
    "NetCashProvidedByUsedInOperatingActivities": "Operating Cash Flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "CapEx",
    "CommonStockSharesOutstanding": "Shares Outstanding",
}


_REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]

# Specific metric intents → the exact XBRL concepts that explain them, in
# display order. A margin is numerator/denominator, so we surface both
# components (e.g. gross margin = gross profit / revenue) rather than a wall
# of loosely-related profitability facts.
_INTENT_PRIORITY_CONCEPTS: List[Tuple[str, List[str]]] = [
    ("gross margin",     ["Revenues", "GrossProfit"]),
    ("gross profit",     ["Revenues", "GrossProfit"]),
    ("operating margin", ["Revenues", "OperatingIncomeLoss"]),
    ("operating income", ["Revenues", "OperatingIncomeLoss"]),
    ("net margin",       ["Revenues", "NetIncomeLoss"]),
    ("profit margin",    ["Revenues", "NetIncomeLoss"]),
    ("net income",       ["Revenues", "NetIncomeLoss"]),
]


def _priority_concepts_for_query(query: str) -> List[str]:
    """Return the ordered concepts that directly explain a specific metric
    intent (e.g. a margin's numerator + denominator), or [] if none match.

    Revenue concepts are expanded to all known aliases so the lookup matches
    whichever revenue tag a given filer uses.
    """
    q = query.lower()
    for phrase, concepts in _INTENT_PRIORITY_CONCEPTS:
        if phrase in q:
            expanded: List[str] = []
            for c in concepts:
                expanded.extend(_REVENUE_CONCEPTS if c == "Revenues" else [c])
            return expanded
    return []


def _dedupe_latest_per_concept(facts: List[Dict]) -> List[Dict]:
    """Collapse facts to one-per-concept, keeping the most recent period.

    Showing the same concept across several years reads as noise when the user
    just wants the headline figures; the trend lives in the comparison view.
    """
    best: Dict[str, Tuple[int, Dict]] = {}
    order: List[str] = []
    for f in facts:
        concept = f.get("concept", "") or f.get("label", "")
        year = _fact_year(f) or -1
        if concept not in best:
            order.append(concept)
            best[concept] = (year, f)
        elif year > best[concept][0]:
            best[concept] = (year, f)
    return [best[c][1] for c in order]


def _classify_query(query: str) -> ConceptGroup:
    """Map a natural-language query to a concept group via keyword matching.
    Accumulates all matched groups and picks the most-represented one."""
    q = query.lower()
    groups: list[ConceptGroup] = []
    for keyword, group in sorted(QUERY_KEYWORD_TO_GROUP.items(),
                                 key=lambda x: -len(x[0])):
        if re.search(r"\b" + re.escape(keyword) + r"\b", q, re.IGNORECASE):
            groups.append(group)
    if not groups:
        return "profitability"
    return Counter(groups).most_common(1)[0][0]


def _rank_facts(facts: List[Dict], primary_group: ConceptGroup, top_n: int = 3,
                priority_concepts: Optional[List[str]] = None) -> List[Dict]:
    """
    Rank and filter XBRL facts to a maximum of top_n records.

    When ``priority_concepts`` is given (a specific metric intent like gross
    margin), those exact concepts are surfaced first in the given order so the
    user sees the metric's components (e.g. revenue + gross profit) rather than
    a broad group dump. Otherwise facts matching the primary concept group get
    priority, followed by complementary groups.
    """
    if not facts:
        return []

    priority_rank = {c: i for i, c in enumerate(priority_concepts or [])}

    ranked: List[Tuple[int, Dict]] = []
    secondary_order = {
        "revenue":       ["revenue", "profitability", "liquidity", "leverage"],
        "profitability": ["profitability", "revenue", "liquidity", "leverage"],
        "liquidity":     ["liquidity", "profitability", "leverage", "revenue"],
        "leverage":      ["leverage", "liquidity", "profitability", "revenue"],
        "valuation":     ["valuation", "profitability", "revenue", "liquidity"],
        "banking":       ["banking", "profitability", "liquidity", "leverage"],
    }
    group_priority = secondary_order.get(primary_group,
                                         [primary_group, "profitability", "revenue", "liquidity"])
    group_rank = {g: i for i, g in enumerate(group_priority)}

    for f in facts:
        concept = f.get("concept", "") or f.get("label", "")
        if priority_rank:
            # Explicit metric intent: keep only the components, ordered as given.
            if concept not in priority_rank:
                continue
            rank = priority_rank[concept]
        else:
            group = CONCEPT_GROUP_MAP.get(concept, "other")
            rank = group_rank.get(group, 99)
        value = _pick_value(f)
        has_value = value is not None and str(value).strip() != ""
        if not has_value:
            rank += 50
        ranked.append((rank, f))

    ranked.sort(key=lambda x: (x[0], -(abs(_to_float(_pick_value(x[1])) or 0))))
    ordered = [f for _, f in ranked]
    # For an explicit metric intent (e.g. gross margin), collapse to one fact
    # per concept (latest period) so the display shows the distinct components
    # — revenue + gross profit — not the same concept repeated across years.
    if priority_rank:
        ordered = _dedupe_latest_per_concept(ordered)
    return ordered[:top_n]


def get_relevant_facts(query: str, all_facts: List[Dict[str, Any]],
                       max_facts: int = 3,
                       filter_by_period: bool = True) -> Dict[str, Any]:
    """
    Return a structured summary of the most relevant XBRL facts for a query.

    Returns:
        {
            "relevant": List[Dict],   # Top matches (≤max_facts)
            "total": int,             # Total facts in the DB
            "group": str,             # Detected concept group
            "badge_text": str,        # e.g. "XBRL verified • 8 facts"
        }
    """
    if not all_facts:
        return {
            "relevant": [],
            "total": 0,
            "group": "none",
            "badge_text": "",
        }

    group = _classify_query(query)
    priority_concepts = _priority_concepts_for_query(query)
    candidate_facts = (
        filter_facts_for_query(query, all_facts)
        if filter_by_period else all_facts
    )
    relevant = _rank_facts(candidate_facts, group, max_facts,
                           priority_concepts=priority_concepts)

    badge_text = f"XBRL verified • {len(all_facts)} facts"
    if len(relevant) < len(all_facts):
        badge_text = f"XBRL verified • {len(relevant)} of {len(all_facts)} shown"

    return {
        "relevant": relevant,
        "total": len(all_facts),
        "group": group,
        "badge_text": badge_text,
    }


def format_fact_for_display(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a fact dict for frontend consumption, preserving provenance.

    The SEC company-concept endpoint is the raw JSON dataset from which the
    value was selected.  The accession URL identifies the exact filing that
    reported it.  Together with period/unit/form metadata this makes the
    displayed number independently traceable instead of merely "SEC sourced".
    """
    concept = fact.get("concept", "") or fact.get("label", "")
    value = _pick_value(fact)
    unit = fact.get("unit", "")
    period = get_fact_period(fact)
    label = fact.get("label", "") or _DISPLAY_NAMES.get(concept, concept)
    num = _to_float(value)

    ticker = str(fact.get("ticker") or "")
    cik = re.sub(r"\D", "", str(fact.get("cik") or "")).zfill(10) if fact.get("cik") else ""
    taxonomy = str(fact.get("taxonomy") or "us-gaap")
    accession = str(fact.get("accession") or fact.get("accn") or "")
    filed = str(fact.get("filed") or fact.get("filed_date") or "")
    form_type = str(fact.get("form_type") or fact.get("form") or "")
    period_start = str(fact.get("period_start") or fact.get("start") or "")
    frame = str(fact.get("frame") or "")

    raw_fact_url = ""
    if cik and concept:
        raw_fact_url = (
            f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/"
            f"{quote(taxonomy, safe='')}/{quote(str(concept), safe='')}.json"
        )

    raw_frame_url = ""
    if frame and concept and unit:
        raw_frame_url = (
            f"https://data.sec.gov/api/xbrl/frames/{quote(taxonomy, safe='')}/"
            f"{quote(str(concept), safe='')}/{quote(str(unit), safe='')}/"
            f"{quote(frame, safe='')}.json"
        )

    filing_url = ""
    clean_accession = re.sub(r"\D", "", accession)
    if len(clean_accession) >= 18:
        filing_cik = (cik.lstrip("0") if cik else clean_accession[:10].lstrip("0"))
        dashed = (
            f"{clean_accession[:10]}-{clean_accession[10:12]}-"
            f"{clean_accession[12:]}"
        )
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{filing_cik}/"
            f"{clean_accession}/{dashed}-index.htm"
        )

    return {
        "concept": concept,
        "label": label,
        "value": num,
        "unit": unit,
        "period": period,
        "is_verified": num is not None,
        "ticker": ticker,
        "cik": cik,
        "taxonomy": taxonomy,
        "accession": accession,
        "form_type": form_type,
        "filed": filed,
        "period_start": period_start,
        "period_end": str(fact.get("period_end") or fact.get("end") or period),
        "frame": frame,
        "raw_fact_url": raw_fact_url,
        "raw_frame_url": raw_frame_url,
        "filing_url": filing_url,
    }
