"""
XBRL companyfacts client — fetches tagged facts from SEC EDGAR.
Rate limit: ≤10 req/s (CONSTRAINT-005). User-Agent mandatory.
Uses the process-wide limiter from pipelines.sec_rag_ingest.
"""
import os
import requests
from dataclasses import dataclass
from typing import Optional
from functools import lru_cache
from loguru import logger

from api.config import TICKER_TO_CIK
from pipelines.sec_rag_ingest import get_global_limiter

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_USER_AGENT = None  # Lazy-initialized on first use


def _get_user_agent() -> str:
    global _USER_AGENT
    if _USER_AGENT is None:
        raw = os.getenv("EDGAR_USER_AGENT", "")
        if not raw or "example" in raw.lower():
            raise ValueError(
                "EDGAR_USER_AGENT must be set to a descriptive application/contact string. "
                "Set it from environment or Databricks secret."
            )
        _USER_AGENT = raw
    return _USER_AGENT

@dataclass
class XBRLFact:
    concept: str
    label: str
    value: float
    unit: str
    period: str        # ISO date string e.g. "2023-09-30"
    ticker: str
    accession: str

def _rate_limited_get(url: str) -> dict:
    """GET with rate limiting and User-Agent header.

    Uses the process-wide limiter shared with sec_rag_ingest.
    """
    limiter = get_global_limiter()
    limiter.acquire()
    resp = requests.get(url, headers={"User-Agent": _get_user_agent()}, timeout=15)
    resp.raise_for_status()
    return resp.json()

@lru_cache(maxsize=64)
def fetch_company_facts(cik_or_ticker: str) -> dict:
    """Fetch all companyfacts for a CIK (or ticker). Cached per process."""
    if not cik_or_ticker.isdigit():
        cik = TICKER_TO_CIK.get(cik_or_ticker.upper(), "")
        if not cik:
            logger.warning("Invalid CIK/nonmapped ticker: {}", cik_or_ticker)
            return {}
    else:
        cik = cik_or_ticker
    cik_padded = cik.zfill(10)
    url = COMPANYFACTS_URL.format(cik=cik_padded)
    logger.info("Fetching companyfacts for CIK {}", cik_padded)
    try:
        return _rate_limited_get(url)
    except Exception as e:
        logger.warning("companyfacts fetch failed for CIK {}: {}", cik, e)
        return {}

def get_fact(
    cik: str,
    concept: str,            # e.g. "Revenues" or "us-gaap/Revenues"
    period_end: str,         # e.g. "2023-09-30"
    ticker: str = "",
    form: str = "10-K",
) -> Optional[XBRLFact]:
    """
    Look up a single XBRL fact for a company/concept/period.
    concept may omit the taxonomy prefix; we try us-gaap first.
    """
    concept_key = concept.replace("us-gaap/", "").replace("dei/", "")
    facts = fetch_company_facts(cik)

    for taxonomy in ("us-gaap", "dei", "invest"):
        taxonomy_facts = facts.get("facts", {}).get(taxonomy, {})
        if concept_key not in taxonomy_facts:
            continue
        entry = taxonomy_facts[concept_key]
        label = entry.get("label", concept_key)

        for unit_key, unit_facts in entry.get("units", {}).items():
            for f in unit_facts:
                if (f.get("end") == period_end
                        and f.get("form") == form
                        and f.get("val") is not None):
                    return XBRLFact(
                        concept=f"{taxonomy}/{concept_key}",
                        label=label,
                        value=float(f["val"]),
                        unit=unit_key,
                        period=period_end,
                        ticker=ticker,
                        accession=f.get("accn", ""),
                    )
    return None
