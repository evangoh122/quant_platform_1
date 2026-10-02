"""Shared financial metric routing logic.

Consolidates the metric dispatch that was previously duplicated across:
- langgraph_engine.py:math_node
- langgraph_engine.py:_execute_tool
- peer_comparison.py:compute_metric

Usage:
    from api.services.metric_router import route_metric, MetricResult

    result = route_metric("gross_margin", extractor, latest, prior)
    if result:
        print(result.value, result.display())
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from loguru import logger


@dataclass
class MetricResult:
    """Standardized result from a metric computation."""
    value: float
    unit: str = "USD"
    display_text: str = ""
    calc: Any = None  # The underlying CalcResult for audit trails

    def display(self) -> str:
        return self.display_text or f"{self.value:,.2f}"


def _safe_get(extractor, concept: str, period: str = "") -> Optional[float]:
    """Get a value from a FactExtractor, returning None on any failure."""
    try:
        return extractor.get(concept, period=period)
    except Exception:
        return None


def route_metric(
    metric: str,
    extractor: Any,
    latest: str,
    prior: Optional[str] = None,
) -> Optional[MetricResult]:
    """Route a metric name to its computation and return a standardized result.

    Args:
        metric: The metric identifier (e.g. "gross_margin", "operating_margin")
        extractor: A FactExtractor instance with XBRL facts loaded
        latest: The latest period string
        prior: The prior period string (for growth metrics)

    Returns:
        MetricResult if computation succeeded, None otherwise
    """
    from api.services.financial_calc import (
        gross_margin, gross_margin_growth, operating_margin, net_margin,
        free_cash_flow, current_ratio, debt_to_equity, rd_intensity,
        yoy_growth, net_debt,
    )

    try:
        # Gross margin growth (must check before gross margin — substring match)
        if metric == "gross_margin_growth" and prior:
            rc = _safe_get(extractor, "revenues", latest)
            cc = _safe_get(extractor, "costofrevenue", latest)
            rp = _safe_get(extractor, "revenues", prior)
            cp = _safe_get(extractor, "costofrevenue", prior)
            if all(v is not None for v in (rc, cc, rp, cp)):
                r = gross_margin_growth(rc, cc, rp, cp, current_period=latest, prior_period=prior)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Gross margin
        elif metric == "gross_margin":
            rev = _safe_get(extractor, "revenues", latest)
            gp = _safe_get(extractor, "grossprofit", latest)
            cogs = _safe_get(extractor, "costofrevenue", latest)
            # Revenue ≡ GrossProfit + COGS — recover by identity for filers
            # that tag GP/COGS but not a top-line Revenues concept (e.g. TXN).
            if rev is None and gp is not None and cogs is not None:
                rev = gp + cogs
            if rev is not None and gp is not None:
                r = gross_margin(rev, cogs, period=latest, gross_profit=gp)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)
            if rev is not None and cogs is not None:
                r = gross_margin(rev, cogs, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Operating margin
        elif metric == "operating_margin":
            rev = _safe_get(extractor, "revenues", latest)
            oi = _safe_get(extractor, "operatingincomeloss", latest)
            if rev is not None and oi is not None:
                r = operating_margin(rev, oi, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Net margin
        elif metric == "net_margin":
            rev = _safe_get(extractor, "revenues", latest)
            ni = _safe_get(extractor, "netincomeloss", latest)
            if rev is not None and ni is not None:
                r = net_margin(rev, ni, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Free cash flow
        elif metric == "free_cash_flow":
            ocf = _safe_get(extractor, "netcashoperating", latest)
            capex = _safe_get(extractor, "capitalexpenditures", latest)
            if ocf is not None and capex is not None:
                r = free_cash_flow(ocf, capex, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Current ratio
        elif metric == "current_ratio":
            ca = _safe_get(extractor, "currentassets", latest)
            cl = _safe_get(extractor, "currentliabilities", latest)
            if ca is not None and cl is not None:
                r = current_ratio(ca, cl, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Debt to equity
        elif metric == "debt_to_equity":
            debt = _safe_get(extractor, "longtermdebt", latest)
            eq = _safe_get(extractor, "stockholdersequity", latest)
            if debt is not None and eq is not None:
                r = debt_to_equity(debt, eq, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Net debt
        elif metric == "net_debt":
            debt = _safe_get(extractor, "longtermdebt", latest)
            cash = _safe_get(extractor, "cashandequivalents", latest)
            if debt is not None and cash is not None:
                r = net_debt(debt, cash, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # R&D intensity
        elif metric == "rd_intensity":
            rev = _safe_get(extractor, "revenues", latest)
            rd = _safe_get(extractor, "researchanddevelopment", latest)
            if rev is not None and rd is not None:
                r = rd_intensity(rev, rd, period=latest)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Revenue YoY growth
        elif metric == "revenue_yoy_growth" and prior:
            curr_val = _safe_get(extractor, "revenues", latest)
            prev_val = _safe_get(extractor, "revenues", prior)
            if curr_val is not None and prev_val is not None:
                r = yoy_growth(curr_val, prev_val, metric_name="Revenue",
                               current_period=latest, prior_period=prior)
                return MetricResult(value=r.value, unit=r.unit, display_text=r.display(), calc=r)

        # Raw values (revenue, net income)
        elif metric in ("revenue", "net_income"):
            concept = "revenues" if metric == "revenue" else "netincomeloss"
            val = _safe_get(extractor, concept, latest)
            if val is not None:
                label = "Revenue" if metric == "revenue" else "Net Income"
                return MetricResult(value=val, unit="USD", display_text=f"{label}: ${val:,.0f}")

    except Exception as e:
        logger.warning(f"route_metric({metric}) failed: {e}")

    return None


def query_to_metric(query: str) -> str:
    """Map a natural-language query to a metric identifier.

    Returns the metric string, or "unknown" if no match.
    """
    q = query.lower()
    # Order matters: more specific matches first
    if any(k in q for k in ("gross margin growth", "gross margin change", "gross margin yoy")):
        return "gross_margin_growth"
    if any(k in q for k in ("gross margin", "gross profit margin")):
        return "gross_margin"
    if any(k in q for k in ("operating margin", "operating income margin")):
        return "operating_margin"
    if any(k in q for k in ("net margin", "profit margin", "net income margin")):
        return "net_margin"
    if any(k in q for k in ("free cash flow", "fcf")):
        return "free_cash_flow"
    if any(k in q for k in ("current ratio", "liquidity ratio")):
        return "current_ratio"
    if any(k in q for k in ("debt to equity", "debt-to-equity", "d/e ratio")):
        return "debt_to_equity"
    if any(k in q for k in ("net debt", "net cash position")):
        return "net_debt"
    if any(k in q for k in ("r&d", "research and development", "rd intensity")):
        return "rd_intensity"
    if any(k in q for k in ("revenue growth", "revenue yoy", "sales growth")):
        return "revenue_yoy_growth"
    if any(k in q for k in ("revenue", "net sales", "total revenue")):
        return "revenue"
    if any(k in q for k in ("net income", "net earnings")):
        return "net_income"
    return "unknown"
