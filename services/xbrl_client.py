"""
XBRL companyfacts client — fetches tagged facts from SEC EDGAR.
Rate limit: ≤10 req/s (CONSTRAINT-005). User-Agent mandatory.
"""
import os
import time
import threading
import requests
from dataclasses import dataclass
from typing import Optional
from functools import lru_cache
from loguru import logger

from api.config import TICKER_TO_CIK

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "RAG-Workbench research@example.com")
_rate_lock = threading.Lock()
_last_call: float = 0.0
_MIN_INTERVAL = 0.11  # ~9 req/s to stay under 10/s

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
    """GET with rate limiting and User-Agent header."""
    global _last_call
    with _rate_lock:
        elapsed = time.time() - _last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        _last_call = time.time()
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
