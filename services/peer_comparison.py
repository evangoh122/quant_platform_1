"""
peer_comparison.py — Multi-company comparison for the Auditable Filing-QA engine.

The core LangGraph DAG answers about a single company. This module handles the
two cases it can't:

  1. PEER intent  — "How does NVIDIA's revenue growth compare to its competitors?"
                    The peer set is derived from the knowledge graph's
                    COMPETES_WITH edges (mapped to covered tickers), with a
                    curated sector fallback.
  2. EXPLICIT set — "Compare NVDA, INTC and TXN gross margins." Any 2+ covered
                    companies named in the query, competitors or not.

For each company it pulls the latest 10-K XBRL facts and computes the requested
metric with the same `financial_calc` functions the single-company numeric path
uses, then renders a comparison table. Numbers stay filing-derived and auditable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# Covered companies → the names/aliases that appear in queries and filings.
_TICKER_TO_NAMES: Dict[str, List[str]] = {
    "NVDA": ["nvidia"],
    "AMD":  ["amd", "advanced micro devices"],
    "INTC": ["intel"],
    "QCOM": ["qualcomm"],
    "AVGO": ["broadcom"],
    "TXN":  ["texas instruments"],
    "MU":   ["micron"],
    "AMAT": ["applied materials"],
    "LRCX": ["lam research"],
    "KLAC": ["kla", "kla-tencor", "kla corporation"],
    "MRVL": ["marvell"],
    "MCHP": ["microchip"],
    "ADI":  ["analog devices"],
    "SPCX": ["spacex", "space exploration"],
    "RKLB": ["rocket lab", "rocket labs", "rocketlab", "rocket lab usa", "rklb"],
    "ON":   ["on semi", "on semiconductor", "onsemi", "on"],
    "STM":  ["stmicroelectronics", "stmicro", "stm"],
    "TSM":  ["tsmc", "taiwan semiconductor", "tsm"],
    "PLAB": ["photronics", "plab"],
    # Remaining covered companies (distinctive aliases only — bare English words
    # like "form"/"onto" are left to the >=3-char symbol matcher to avoid
    # false positives such as "fill out the form").
    "ACLS": ["axcelis"],
    "AEHR": ["aehr test systems", "aehr"],
    "AMKR": ["amkor"],
    "COHU": ["cohu"],
    "ENTG": ["entegris"],
    "FORM": ["formfactor"],
    "ICHR": ["ichor holdings", "ichor"],
    "KLIC": ["kulicke and soffa", "kulicke & soffa", "kulicke"],
    "MPWR": ["monolithic power systems", "monolithic power"],
    "NXPI": ["nxp semiconductors", "nxp"],
    "ONTO": ["onto innovation"],
    "QRVO": ["qorvo"],
    "SWKS": ["skyworks solutions", "skyworks"],
    "TER":  ["teradyne"],
    "VECO": ["veeco instruments", "veeco"],
}

# Curated sector peers — used when the graph has no covered-ticker competitor,
# and merged with graph-derived peers otherwise. Keeps comparisons relevant
# (chip designers vs chip designers, equipment vs equipment).
_PEER_GROUPS: Dict[str, List[str]] = {
    "NVDA": ["AMD", "INTC", "QCOM", "AVGO"],
    "AMD":  ["NVDA", "INTC", "QCOM", "AVGO"],
    "INTC": ["NVDA", "AMD", "QCOM", "AVGO"],
    "QCOM": ["AVGO", "NVDA", "MRVL", "TXN"],
    "AVGO": ["QCOM", "NVDA", "MRVL", "TXN"],
    "MRVL": ["AVGO", "QCOM", "NVDA", "TXN"],
    "TXN":  ["ADI", "MCHP", "AVGO", "QCOM"],
    "ADI":  ["TXN", "MCHP", "MRVL"],
    "MCHP": ["ADI", "TXN", "MRVL"],
    "MU":   ["NVDA", "AVGO", "INTC"],
    "AMAT": ["LRCX", "KLAC"],
    "LRCX": ["AMAT", "KLAC"],
    "KLAC": ["AMAT", "LRCX"],
    "SPCX": [],
}

_MAX_PEERS = 4  # subject + up to 4 peers keeps the table readable

# Words that signal "compare me to my competitors / the field".
_PEER_SIGNALS = (
    "competitor", "competitors", "competition", "peer", "peers", "rival",
    "rivals", "industry", "other companies", "others in the", "vs the industry",
    "versus the industry", "compared to other", "against competitors",
    "against its peers", "relative to peers", "relative to competitors",
    "how does it stack up", "stack up against",
)

# Query phrasing → (financial_calc metric key, display label, value formatter).
# Order matters: first match wins, so put more specific phrases first.
_METRIC_RULES: List[Tuple[Tuple[str, ...], str, str]] = [
    (("gross margin", "gross profit margin"),            "gross_margin",      "Gross Margin"),
    (("operating margin",),                              "operating_margin",  "Operating Margin"),
    (("net margin", "profit margin"),                    "net_margin",        "Net Margin"),
    (("r&d", "research and development", "rd intensity"),"rd_intensity",      "R&D Intensity"),
    (("free cash flow", "fcf"),                          "free_cash_flow",    "Free Cash Flow"),
    (("debt to equity", "debt-to-equity", "leverage"),   "debt_to_equity",    "Debt / Equity"),
    (("current ratio", "liquidity"),                     "current_ratio",     "Current Ratio"),
    (("revenue growth", "revenue growth rate", "sales growth",
      "growth rate", "top-line growth", "grow"),         "revenue_yoy_growth","Revenue YoY Growth"),
    (("net income", "earnings", "profit"),               "net_income",        "Net Income"),
    (("revenue", "sales", "top line"),                   "revenue",           "Revenue"),
]

_PERCENT_METRICS = {
    "gross_margin", "operating_margin", "net_margin", "rd_intensity",
    "revenue_yoy_growth",
}
_USD_METRICS = {"revenue", "net_income", "free_cash_flow"}


def covered_tickers() -> List[str]:
    """The tickers we actually have SEC data for."""
    try:
        from api.config import TICKER_TO_CIK
        return list(TICKER_TO_CIK.keys())
    except Exception:
        return list(_TICKER_TO_NAMES.keys())


def _name_to_ticker(text: str) -> Optional[str]:
    """Map a free-text company name (from a filing or query) to a covered ticker."""
    t = (text or "").lower()
    for ticker, names in _TICKER_TO_NAMES.items():
        if any(n in t for n in names):
            return ticker
    return None


def _tickers_named_in_query(query: str) -> List[str]:
    """Return covered tickers explicitly named in the query, in first-seen order.

    Matches both company names ("Intel") and ticker symbols length >= 3
    ("INTC") on a word boundary, mirroring the single-ticker resolver.
    """
    q = (query or "")
    found: List[str] = []
    covered = set(covered_tickers())

    # Company names
    ql = q.lower()
    name_hits: List[Tuple[int, str]] = []
    for ticker, names in _TICKER_TO_NAMES.items():
        if ticker not in covered:
            continue
        for n in names:
            if n == "on":
                # Special-case "on" to be uppercase-only to avoid false-positive match on the English word "on"
                m = re.search(r"\bON\b", q)
                if m:
                    name_hits.append((m.start(), ticker))
                    break
                else:
                    continue
            # Use word boundary to prevent matching substrings of other words (e.g. 'on' in 'micron')
            m = re.search(r"\b" + re.escape(n) + r"\b", ql)
            if m:
                name_hits.append((m.start(), ticker))
                break
    # Explicit symbols (>=3 chars, word boundary)
    for ticker in covered:
        if len(ticker) >= 3:
            m = re.search(r"\b" + re.escape(ticker) + r"\b", q, re.IGNORECASE)
            if m:
                name_hits.append((m.start(), ticker))

    for _, ticker in sorted(name_hits, key=lambda x: x[0]):
        if ticker not in found:
            found.append(ticker)
    return found


def detect_comparison(query: str, subject_ticker: str) -> Optional[Dict[str, Any]]:
    """Decide whether a query needs a multi-company comparison.

    Returns None when it's an ordinary single-company question. Otherwise a dict:
        {"mode": "peer"|"explicit", "subject": ticker, "explicit": [tickers]}
    """
    if not query:
        return None
    q = query.lower()
    named = _tickers_named_in_query(query)
    has_peer_signal = any(s in q for s in _PEER_SIGNALS)

    # Explicit: 2+ covered companies named → compare exactly those.
    if len(named) >= 2:
        return {"mode": "explicit", "subject": named[0], "explicit": named}

    # Peer: a single subject + an explicit "competitors / industry" ask.
    subject = named[0] if named else (subject_ticker or "")
    if has_peer_signal and subject:
        return {"mode": "peer", "subject": subject, "explicit": [subject]}

    return None


def _graph_competitors(subject: str, conn) -> Tuple[List[str], List[str]]:
    """Read COMPETES_WITH edges for a subject from the knowledge graph.

    Returns (covered_peer_tickers, named_competitor_strings). The first is the
    subset that maps to companies we cover (so we can compute metrics); the
    second is the raw filing-derived competitor names, for citation.
    """
    covered_peers: List[str] = []
    named: List[str] = []
    try:
        # Outgoing: subject competes with X
        rows = conn.execute(
            "SELECT object FROM graph_triples "
            "WHERE ticker = ? AND predicate = 'COMPETES_WITH'",
            [subject],
        ).fetchall()
        for (obj,) in rows:
            if not obj:
                continue
            named.append(str(obj))
            mapped = _name_to_ticker(str(obj))
            if mapped and mapped != subject:
                covered_peers.append(mapped)
        # Incoming: another covered company names the subject as a competitor
        # Use exact match or word-boundary match to avoid false positives on short tickers
        rows2 = conn.execute(
            "SELECT DISTINCT ticker FROM graph_triples "
            "WHERE predicate = 'COMPETES_WITH' AND ticker <> ? "
            "AND (lower(object) = ? OR lower(object) LIKE ? OR lower(object) LIKE ? OR lower(object) LIKE ?)",
            [subject, subject.lower(), f"{subject.lower()},%", f"%, {subject.lower()}%", f"%, {subject.lower()}"],
        ).fetchall()
        for (tk,) in rows2:
            if tk and tk != subject:
                covered_peers.append(tk)
    except Exception as e:
        logger.warning(f"graph competitor lookup failed for {subject}: {e}")

    # Dedupe preserving order
    seen: set = set()
    covered_peers = [p for p in covered_peers if not (p in seen or seen.add(p))]
    return covered_peers, named


def resolve_peers(subject: str) -> Dict[str, Any]:
    """Resolve a subject's peer set: graph competitors first, sector fallback,
    capped at _MAX_PEERS. Returns tickers to compare + cited competitor names."""
    covered = set(covered_tickers())
    graph_peers: List[str] = []
    named_competitors: List[str] = []
    try:
        from api.db.database import db_manager
        conn = db_manager.get_connection()
        graph_peers, named_competitors = _graph_competitors(subject, conn)
    except Exception as e:
        logger.warning(f"resolve_peers: graph unavailable ({e})")

    peers: List[str] = [p for p in graph_peers if p in covered]
    # Merge curated sector peers (fills out the set, keeps it relevant).
    for p in _PEER_GROUPS.get(subject, []):
        if p in covered and p not in peers and p != subject:
            peers.append(p)
    peers = peers[:_MAX_PEERS]

    return {
        "peers": peers,
        "named_competitors": named_competitors,
        "from_graph": [p for p in graph_peers if p in covered],
    }


def _metric_for_query(query: str) -> Tuple[str, str]:
    """Map a query to (metric_key, label). Defaults to revenue."""
    q = (query or "").lower()
    for phrases, key, label in _METRIC_RULES:
        if any(p in q for p in phrases):
            return key, label
    return "revenue", "Revenue"


def _format_value(metric: str, value: Optional[float]) -> str:
    """Human-format a computed value for the comparison table."""
    if value is None:
        return "n/a"
    if metric in _PERCENT_METRICS:
        return f"{value:.1f}%"
    if metric in _USD_METRICS:
        absv = abs(value)
        if absv >= 1e9:
            return f"${value / 1e9:.2f}B"
        if absv >= 1e6:
            return f"${value / 1e6:.1f}M"
        return f"${value:,.0f}"
    return f"{value:.2f}"  # ratios (current_ratio, debt_to_equity)


# ── Multi-year comparison support ─────────────────────────────────────────────
_MAX_TREND_YEARS = 8  # keep the table/chart readable; mirrors chart_tool._MAX_YEARS

# Comparison metrics with a clean annual series we can tabulate year-by-year
# (reusing the deterministic, filing-derived chart builder). Other metrics
# (ratios, growth, FCF, R&D intensity) keep the single-period snapshot.
_MULTIYEAR_CHARTABLE = {
    "revenue", "net_income", "gross_margin", "operating_margin", "net_margin",
}

# Phrases that signal the user wants a multi-year history, not a snapshot.
_MULTIYEAR_SIGNALS = (
    "over the years", "over time", "trend", "history", "historical", "each year",
    "year by year", "year-by-year", "annually", "past few years", "last few years",
    "over the past", "over the last",
)

_WRITTEN_NUMS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _parse_year_horizon(query: str) -> Optional[int]:
    """Parse an explicit N-year window from the query (e.g. "5 years", "5-year",
    "last three years"). Returns N clamped to 2.._MAX_TREND_YEARS, or None."""
    q = (query or "").lower()
    n: Optional[int] = None
    m = re.search(r"(\d+)\s*[-\s]?\s*(?:year|yr|fiscal year)", q)
    if m:
        n = int(m.group(1))
    else:
        for word, val in _WRITTEN_NUMS.items():
            if re.search(rf"\b{word}\b[\s-]+(?:year|yr|fiscal)", q):
                n = val
                break
    if n is None:
        return None
    return max(2, min(n, _MAX_TREND_YEARS))


def _wants_multiyear(query: str) -> bool:
    """True when the query asks for a multi-year history — an explicit N-year
    horizon, or a trend/history signal word."""
    if _parse_year_horizon(query) is not None:
        return True
    q = (query or "").lower()
    return any(s in q for s in _MULTIYEAR_SIGNALS)


def _annual_series_for_metric(ticker: str, metric: str) -> Dict[str, float]:
    """{fiscal_year: value} for a chartable metric, via the deterministic chart
    builder (so the numbers stay filing-derived XBRL). Empty if unavailable."""
    try:
        from api.services.chart_tool import build_chart_spec
        spec = build_chart_spec(ticker, metric, "line")
        pts = (spec or {}).get("annual") or (spec or {}).get("data") or []
        return {
            str(p["period"]): float(p["value"])
            for p in pts if p.get("value") is not None
        }
    except Exception as exc:
        logger.warning(f"_annual_series_for_metric({ticker}, {metric}) failed: {exc}")
        return {}


def _multiyear_comparison(
    query: str, decision: Dict[str, Any], metric: str, label: str,
    tickers: List[str], named_competitors: List[str], from_graph: List[str],
    horizon: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Year-by-year comparison table + multi-series trend chart for a chartable
    metric. Returns None when fewer than 2 companies have a usable annual series,
    so the caller falls back to the single-period snapshot."""
    subject = decision["subject"]
    series: Dict[str, Dict[str, float]] = {}
    for tk in tickers:
        s = _annual_series_for_metric(tk, metric)
        if s:
            series[tk] = s
    have = [tk for tk in tickers if tk in series]
    if len(have) < 2:
        return None

    # Year window: the union of available fiscal years, most-recent `horizon`
    # (default 5). Companies with differing fiscal calendars show "—" for a year
    # they didn't file.
    all_years = sorted({y for s in series.values() for y in s})
    window = horizon or 5
    years = all_years[-window:]
    is_pct = metric in _PERCENT_METRICS

    # ── Table: one row per fiscal year, one column per company ──
    span = f"{years[0]}–{years[-1]}" if years else ""
    lines: List[str] = [f"**{label} — {' vs. '.join(have)} ({span})**\n"]
    lines.append("| Fiscal Year | " + " | ".join(have) + " |")
    lines.append("|---|" + "|".join("---" for _ in have) + "|")
    for y in years:
        cells = [
            _format_value(metric, series[tk].get(y)) if series[tk].get(y) is not None else "—"
            for tk in have
        ]
        lines.append(f"| {y} | " + " | ".join(cells) + " |")

    # Peer-mode provenance notes (same as the snapshot path).
    if decision["mode"] == "peer":
        if from_graph:
            lines.append(
                f"\n*Peers include competitors named in {subject}'s own filing "
                f"(via the knowledge graph): {', '.join(from_graph)}.*"
            )
        extra = [n for n in named_competitors if not _name_to_ticker(n)]
        if extra:
            lines.append(
                f"\n*{subject}'s filing also names competitors outside our coverage "
                f"(no SEC data to compute): {'; '.join(extra[:5])}.*"
            )
    lines.append(
        "\n*Figures computed from each company's annual 10-K XBRL facts. Fiscal "
        "years may differ across companies; \"—\" = no comparable annual figure filed.*"
    )

    # ── 3-layer fields (rendered separately by the UI) ──
    # "What it means": per-company change over the window (and CAGR for levels).
    reads: List[str] = []
    for tk in have:
        pts = [(y, series[tk][y]) for y in years if y in series[tk]]
        if len(pts) < 2 or not pts[0][1]:
            continue
        (first_y, first_v), (last_y, last_v) = pts[0], pts[-1]
        if is_pct:
            reads.append(
                f"**{tk}** moved from {_format_value(metric, first_v)} ({first_y}) "
                f"to {_format_value(metric, last_v)} ({last_y})"
            )
        else:
            growth = (last_v - first_v) / abs(first_v) * 100
            n_span = int(last_y) - int(first_y)
            cagr = ((last_v / first_v) ** (1 / n_span) - 1) * 100 if n_span > 0 and first_v > 0 else None
            cagr_txt = f", a {cagr:.0f}% CAGR" if cagr is not None else ""
            reads.append(f"**{tk}** grew {growth:+.0f}% ({first_y}→{last_y}){cagr_txt}")
    what_it_means = ("Over " + span + ": " + "; ".join(reads) + ".") if reads else ""

    how_to_interpret = (
        "Read the trajectory, not just the latest value — a higher CAGR means faster "
        "compounding growth, while a flat or falling line signals stalling momentum. "
        "Fiscal years can differ across companies, so align the periods before drawing "
        "conclusions, and treat \"—\" as 'not filed for that year', not zero."
    )
    others = [t for t in have if t != subject]
    follow_ups = [
        f"How did {subject} and {others[0]}'s gross margins compare over the same period?"
        if others else f"How did {subject}'s gross margin trend over this period?",
        f"What drove {subject}'s {label.lower()} trajectory?",
        f"Compare {' vs '.join(have)} net income over {len(years)} years",
    ]

    unit = "%" if is_pct else ("USD" if metric in _USD_METRICS else "")
    trend_series = [
        {"name": tk, "data": [{"period": y, "value": series[tk][y]} for y in years if y in series[tk]]}
        for tk in have
    ]
    chart = {
        "type": "line",
        "title": f"{label} — {subject} vs. peers ({span})",
        "metric": metric, "label": label, "unit": unit, "ticker": subject,
        "data": [], "series": trend_series,
    }
    answer = "\n".join(lines)
    reasoning = (
        f"Multi-year peer comparison: {label} across {', '.join(have)} "
        f"over {span} (mode={decision['mode']})."
    )
    return _shaped_response(
        answer, reasoning, chart=chart,
        what_it_means=what_it_means, how_to_interpret=how_to_interpret,
        follow_ups=follow_ups, retrieved_docs=_filing_sources(have),
    )


def compute_metric(ticker: str, metric: str) -> Dict[str, Any]:
    """Compute one metric for one ticker from its latest 10-K XBRL facts.

    Returns {"value": float|None, "period": str, "ok": bool}.
    """
    from api.services.financial_calc import FactExtractor
    from api.services.metric_router import route_metric
    from api.services.sec_client import get_latest_10k_facts

    import polars as pl

    out = {"value": None, "period": "", "ok": False}
    try:
        df = get_latest_10k_facts(ticker)
        if df is None or df.is_empty():
            return out
        ex = FactExtractor(df)
        periods = ex.periods()
        latest = periods[-1] if periods else ""
        prior = periods[-2] if len(periods) >= 2 else None
        out["period"] = latest

        # Use the shared metric router
        result = route_metric(metric, ex, latest, prior)
        if result:
            out.update(value=float(result.value), ok=True)
    except Exception as e:
        logger.warning(f"compute_metric({ticker}, {metric}) failed: {e}")
    return out


def _filing_sources(tickers: List[str]) -> List[Dict[str, Any]]:
    """Per-company filing references, shaped like the engine's `retrieved_docs` so
    the chat route renders them in the Sources / audit panel. The comparison's
    numbers are computed from each company's latest 10-K XBRL facts, so we cite
    that filing (EDGAR 10-K list, by CIK when known)."""
    try:
        from api.config import TICKER_TO_CIK
    except Exception:
        TICKER_TO_CIK = {}
    docs: List[Dict[str, Any]] = []
    for tk in tickers:
        cik = (TICKER_TO_CIK or {}).get(tk)
        url = (
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K"
            if cik else
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={tk}&type=10-K"
        )
        docs.append({
            "chunk_text": (
                f"{tk}: figures computed from the company's latest 10-K XBRL "
                f"financial data (SEC EDGAR)."
            ),
            "metadata": {
                "ticker": tk,
                "section_id": "XBRL financial data",
                "edgar_url": url,
            },
        })
    return docs


def _shaped_response(
    answer: str, reasoning: str, chart: Optional[Dict[str, Any]] = None,
    *, what_it_means: str = "", how_to_interpret: str = "",
    follow_ups: Optional[List[str]] = None,
    retrieved_docs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return a result dict shaped like the LangGraph engine's output so the
    chat route can consume it uniformly. Optional fields let the comparison path
    carry the same Sources + 3-layer educational fields a single-company answer
    does (otherwise the UI shows no graph context, no sources, no 'what it means')."""
    done = {k: "skipped" for k in (
        "input", "retrieval", "classifier", "extraction", "eval", "math",
        "verification", "output")}
    done["input"] = "success"
    done["output"] = "success"
    if retrieved_docs:
        done["retrieval"] = "success"
    return {
        "final_answer": answer,
        "xbrl_facts": [], "relevant_xbrl": [],
        "retrieved_docs": retrieved_docs or [],
        "polygon_data": [], "math_result": None, "math_steps": [],
        "verification_status": "SKIPPED",
        "verification_reasoning": reasoning,
        "chart": chart,
        "what_it_means": what_it_means,
        "how_to_interpret": how_to_interpret,
        "follow_ups": follow_ups or [],
        "status": done,
    }


def run_peer_comparison(query: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    """Build a multi-company comparison answer for a detected comparison query."""
    subject = decision["subject"]
    metric, label = _metric_for_query(query)

    if decision["mode"] == "explicit":
        tickers = decision["explicit"]
        named_competitors: List[str] = []
        from_graph: List[str] = []
    else:
        resolved = resolve_peers(subject)
        named_competitors = resolved["named_competitors"]
        from_graph = resolved["from_graph"]
        tickers = [subject] + [p for p in resolved["peers"] if p != subject]

    if len(tickers) < 2:
        return _shaped_response(
            f"I can compare **{subject}** against peers, but I don't have other "
            f"covered companies in its segment to compare with. I currently cover "
            f"major semiconductor names (NVDA, AMD, INTC, QCOM, AVGO, MU, TXN, "
            f"AMAT, LRCX, MRVL, MCHP, ADI) plus SpaceX.",
            reasoning="Peer comparison requested but no covered peers resolved.",
        )

    # Multi-year request ("...over 5 years", "...trend"): build a year-by-year
    # table + trend chart instead of a single-period snapshot, when the metric has
    # a chartable annual series. Falls through to the snapshot otherwise.
    if _wants_multiyear(query) and metric in _MULTIYEAR_CHARTABLE:
        multi = _multiyear_comparison(
            query, decision, metric, label, tickers,
            named_competitors, from_graph, _parse_year_horizon(query),
        )
        if multi is not None:
            return multi

    # Compute the metric per company.
    rows: List[Tuple[str, str, Optional[float], str]] = []
    for tk in tickers:
        res = compute_metric(tk, metric)
        rows.append((tk, _format_value(metric, res["value"]), res["value"], res["period"]))

    # Rank: percentages/USD/ratios all read better high→low except leverage.
    ascending = metric in ("debt_to_equity",)
    ranked = sorted(
        rows,
        key=lambda x: (x[2] is None, (x[2] if x[2] is not None else 0) * (1 if ascending else -1)),
    )

    # ── Build the answer (Answer / table / read), matching the 3-layer style ──
    lines: List[str] = []
    lines.append(f"**{label} — {subject} vs. peers**\n")
    lines.append(f"| Company | {label} | Period |")
    lines.append("|---|---|---|")
    for tk, disp, _val, period in ranked:
        mark = " *(subject)*" if tk == subject else ""
        lines.append(f"| {tk}{mark} | {disp} | {period or '—'} |")

    # One-line read: where the subject lands (rendered as the UI's "what it means").
    have = [r for r in ranked if r[2] is not None]
    what_it_means = ""
    if len(have) >= 2 and any(r[0] == subject and r[2] is not None for r in have):
        subj_rank = [i for i, r in enumerate(have) if r[0] == subject][0] + 1
        leader = have[0]
        lead_txt = "lowest" if ascending else "highest"
        what_it_means = (
            f"Among the {len(have)} companies with reported data, {subject} ranks "
            f"#{subj_rank} on {label.lower()}. {leader[0]} has the {lead_txt} at "
            f"{leader[1]}."
        )

    if decision["mode"] == "peer":
        if from_graph:
            lines.append(
                f"\n*Peers include competitors named in {subject}'s own filing "
                f"(via the knowledge graph): {', '.join(from_graph)}.*"
            )
        extra = [n for n in named_competitors if not _name_to_ticker(n)]
        if extra:
            shown = "; ".join(extra[:5])
            lines.append(
                f"\n*{subject}'s filing also names competitors outside our coverage "
                f"(no SEC data to compute): {shown}.*"
            )

    lines.append(
        "\n*Figures computed from each company's latest 10-K XBRL facts. "
        "Margins/growth are point-in-time; fiscal years may differ across companies.*"
    )

    answer = "\n".join(lines)
    reasoning = (
        f"Peer comparison: {label} across {', '.join(t for t, *_ in rows)} "
        f"(mode={decision['mode']})."
    )

    unit = "%" if metric in _PERCENT_METRICS else ("USD" if metric in _USD_METRICS else "")

    # Prefer a multi-year TREND line — one line per company over time — when the
    # metric has a chartable annual history (reuses the single-company chart
    # builder per ticker). Fall back to a single-period BAR snapshot for metrics
    # with no annual series (rd_intensity, free_cash_flow, ratios, growth).
    chart = None
    trend_series: List[Dict[str, Any]] = []
    try:
        from api.services.chart_tool import build_chart_spec
        for tk in [t for t, *_ in ranked]:
            spec = build_chart_spec(tk, metric, "line")
            pts = (spec or {}).get("data") or []
            if len(pts) >= 2:
                trend_series.append({"name": tk, "data": pts})
    except Exception as exc:  # never let charting break the answer
        logger.warning(f"Peer comparison trend build failed: {exc}")

    if len(trend_series) >= 2:
        chart = {
            "type": "line",
            "title": f"{label} — {subject} vs. peers (trend)",
            "metric": metric, "label": label, "unit": unit,
            "ticker": subject,
            "data": [],            # multi-series chart; per-company points in `series`
            "series": trend_series,
        }
    else:
        snapshot = [
            {"period": tk, "value": float(val)}
            for tk, _disp, val, _period in ranked
            if val is not None
        ]
        if len(snapshot) >= 2:
            chart = {
                "type": "bar",
                "title": f"{label} — {subject} vs. peers",
                "metric": metric, "label": label, "unit": unit,
                "ticker": subject,
                "data": snapshot,
            }

    tickers_with_data = [t for t, _disp, val, _period in ranked if val is not None]
    how_to_interpret = (
        "These are point-in-time figures from each company's latest 10-K — useful for "
        "ranking, but a single period hides the trajectory. Fiscal years may differ "
        "across companies, so a like-for-like read needs aligned periods. Ask for the "
        "same metric \"over N years\" to see the trend."
    )
    others = [t for t in tickers_with_data if t != subject]
    follow_ups = [
        f"Compare {subject} and {others[0]} {label.lower()} over 5 years"
        if others else f"How has {subject}'s {label.lower()} trended over 5 years?",
        f"How do {subject} and its peers compare on gross margin?",
        f"What drove the gap in {label.lower()} between these companies?",
    ]
    return _shaped_response(
        answer, reasoning, chart=chart,
        what_it_means=what_it_means, how_to_interpret=how_to_interpret,
        follow_ups=follow_ups,
        retrieved_docs=_filing_sources(tickers_with_data or tickers),
    )
