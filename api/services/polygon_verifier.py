"""
polygon_verifier.py — Cross-check SEC filing extractions against Polygon.io data.

Used by the SEC Analyzer to independently verify:
  1. Ticker validity and company identity
  2. Financial figures (XBRL revenue / net income vs Polygon financials)
  3. Auditor name recognition (Big 4 / major firm heuristic)

Polygon.io endpoints used:
  - GET /v3/reference/tickers/{ticker}     — company name, SIC, active status
  - GET /vX/reference/financials           — latest annual income statement

Requires POLYGON_API_KEY in .env.
"""
from __future__ import annotations

from typing import Optional
import requests
from loguru import logger
_BASE = "https://api.polygon.io"
_TIMEOUT = 10

# Known major audit firms for name-recognition heuristic
_KNOWN_AUDITORS = {
    "deloitte", "pricewaterhousecoopers", "pwc", "ernst & young", "ey",
    "kpmg", "grant thornton", "bdo", "rsm", "crowe", "mazars",
    "moss adams", "cbiz", "plante moran",
}

# XBRL concept → Polygon income_statement field
_XBRL_TO_POLYGON = {
    "revenues": "revenues",
    "revenue": "revenues",
    "netsales": "revenues",
    "netrevenues": "revenues",
    "netincomeloss": "net_income_loss",
    "netincome": "net_income_loss",
    "operatingincomeloss": "operating_income_loss",
}


# ---------------------------------------------------------------------------
# Polygon API calls
# ---------------------------------------------------------------------------

def _get(url: str, params: dict) -> dict:
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Polygon request failed: {e}") from e


def fetch_company_details(ticker: str, api_key: str) -> dict:
    """Return company name, SIC code, and active status from Polygon ticker details."""
    data = _get(f"{_BASE}/v3/reference/tickers/{ticker}", {"apiKey": api_key})
    result = data.get("results", {})
    return {
        "name": result.get("name", ""),
        "sic_description": result.get("sic_description", ""),
        "active": result.get("active", False),
        "primary_exchange": result.get("primary_exchange", ""),
    }


def fetch_latest_financials(ticker: str, api_key: str) -> dict:
    """Return the latest annual income statement figures from Polygon."""
    data = _get(
        f"{_BASE}/vX/reference/financials",
        {"ticker": ticker, "timeframe": "annual", "limit": 1, "apiKey": api_key},
    )
    results = data.get("results", [])
    if not results:
        return {}
    entry = results[0]
    income = entry.get("financials", {}).get("income_statement", {})
    return {
        "fiscal_year": entry.get("fiscal_year"),
        "period": entry.get("period_of_report_date"),
        "revenues": _safe_val(income.get("revenues")),
        "net_income_loss": _safe_val(income.get("net_income_loss")),
        "operating_income_loss": _safe_val(income.get("operating_income_loss")),
    }


def _safe_val(field: Optional[dict]) -> Optional[float]:
    if field and field.get("value") is not None:
        return float(field["value"])
    return None


# ---------------------------------------------------------------------------
# Cross-checks
# ---------------------------------------------------------------------------

def _check_financials(
    xbrl_facts: list[dict],
    polygon_fin: dict,
    tolerance: float = 0.05,
) -> list[dict]:
    """Compare XBRL fact values against Polygon's annual figures."""
    checks: list[dict] = []
    for fact in xbrl_facts:
        concept_raw = str(fact.get("concept") or fact.get("label") or "").lower()
        concept_key = concept_raw.replace(" ", "").replace("_", "")
        polygon_field = _XBRL_TO_POLYGON.get(concept_key)
        if polygon_field is None:
            continue
        polygon_val = polygon_fin.get(polygon_field)
        if polygon_val is None:
            continue
        try:
            xbrl_val = float(fact.get("value") or fact.get("val") or 0)
        except (TypeError, ValueError):
            continue
        if xbrl_val == 0:
            continue

        delta_pct = abs(xbrl_val - polygon_val) / abs(polygon_val) if polygon_val != 0 else None
        status = (
            "match" if delta_pct is not None and delta_pct <= tolerance
            else "mismatch" if delta_pct is not None
            else "unverifiable"
        )
        checks.append({
            "field": polygon_field,
            "xbrl_value": xbrl_val,
            "polygon_value": polygon_val,
            "delta_pct": round(delta_pct * 100, 2) if delta_pct is not None else None,
            "status": status,
        })
    return checks


def _check_auditors(extracted_auditors: list[str]) -> list[dict]:
    """Flag whether extracted auditor names match known major audit firms."""
    results = []
    for name in extracted_auditors:
        name_lower = name.lower()
        recognized = any(firm in name_lower for firm in _KNOWN_AUDITORS)
        results.append({"name": name, "recognized": recognized})
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_checks(
    ticker: str,
    api_key: str,
    sec_analysis: dict,
    xbrl_facts: Optional[list[dict]] = None,
) -> dict:
    """
    Run all Polygon cross-checks against a sec_analysis dict.

    Args:
        ticker:       Stock ticker symbol.
        api_key:      Polygon.io API key.
        sec_analysis: Output from sec_analyzer.analyze_filing().
        xbrl_facts:   Optional XBRL facts list from the langgraph pipeline
                      for financial figure verification.

    Returns:
        Dict with keys: ticker_valid, company_name, company_active,
        financial_checks, auditor_checks, polygon_period, errors.
    """
    errors: list[str] = []
    company: dict = {}
    polygon_fin: dict = {}

    try:
        company = fetch_company_details(ticker, api_key)
    except Exception as e:
        errors.append(f"company_details: {e}")
        logger.warning(f"Polygon company details failed for {ticker}: {e}")

    try:
        polygon_fin = fetch_latest_financials(ticker, api_key)
    except Exception as e:
        errors.append(f"financials: {e}")
        logger.warning(f"Polygon financials failed for {ticker}: {e}")

    financial_checks = (
        _check_financials(xbrl_facts, polygon_fin) if xbrl_facts and polygon_fin else []
    )

    auditor_checks = _check_auditors(
        sec_analysis.get("named_entities", {}).get("auditors", [])
    )

    return {
        "ticker_valid": bool(company.get("active")),
        "company_name": company.get("name", ""),
        "company_active": company.get("active", False),
        "sic_description": company.get("sic_description", ""),
        "polygon_period": polygon_fin.get("period"),
        "polygon_fiscal_year": polygon_fin.get("fiscal_year"),
        "financial_checks": financial_checks,
        "auditor_checks": auditor_checks,
        "errors": errors,
    }
