# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # 02 — Ingest SEC EDGAR Data (for RAG)
# MAGIC
# MAGIC **Writes to:** `bootcamp_students.evangoh_capstone.bronze_sec_filings`
# MAGIC
# MAGIC **Sources:** SEC EDGAR free REST API (`data.sec.gov`) — no API key required.  
# MAGIC Rate limit: ≤10 req/s. This notebook enforces 0.12s delay between requests.
# MAGIC
# MAGIC **What gets ingested:**
# MAGIC 1. Filing metadata (10-K, 10-Q, 8-K) per ticker via `/submissions/CIK{cik}.json`
# MAGIC 2. XBRL financial facts (revenue, EPS, assets, etc.) via `/api/xbrl/companyfacts/`
# MAGIC 3. Raw filing document text (Item 1, 1A, 7, 7A) via direct EDGAR document fetch + HTML strip + chunking
# MAGIC
# MAGIC **RAG pipeline:** The `chunk_text` column feeds into `silver_sec_sections` → `gold_sec_features` (sentiment, risk change, filing similarity) and into the agent's `search_sec_filings()` tool.
# MAGIC
# MAGIC **PIT rule:** Always use `accepted_ts` (EDGAR acceptance timestamp) for point-in-time joins, NEVER `filing_date`.
# MAGIC
# MAGIC **Run order:**
# MAGIC 1. Config + install
# MAGIC 2. Stage 1: Filing metadata (fast, ≈0.5 req/ticker/form)
# MAGIC 3. Stage 2: XBRL financial facts
# MAGIC 4. Stage 3: Full-text extraction + chunking (slow, 1 doc/sec rate limit)
# MAGIC 5. Verification

# COMMAND ----------

# DBTITLE 1,Install packages + config
# %pip install -q requests beautifulsoup4>=4.12.0 lxml>=4.9.0 loguru>=0.7.0
# dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Config + SEC client helpers
import os, sys, time, re, json
from datetime import datetime, timezone
from typing import Optional, List, Dict
from pyspark.sql import SparkSession
import requests
from bs4 import BeautifulSoup

spark = SparkSession.builder.getOrCreate()

CATALOG = "bootcamp_students"
SCHEMA  = "evangoh_capstone"
TABLE   = f"{CATALOG}.{SCHEMA}.bronze_sec_filings"

# ── Universe (same 20 symbols as 01_ingest_market_data) ────────────────────
# Only equities (no ETFs) have SEC filings
UNIVERSE_STK = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "MRVL", "MU",
    "AMAT", "LRCX", "KLAC", "TSM",  "ASML",
    "ADI", "TXN", "LRCX", "AMAT", "QCOM", "INTC",
    "MRVL", "KLAC", "CDNS", "SNPS", "MPWR", "TER",
    "NXPI", "STM", "ARM", "ALAB", "MCHP", "ON", "SWKS",
]
FORM_TYPES = ["10-K", "10-Q", "8-K"]

# ── EDGAR REST client ───────────────────────────────────────────────
EDGAR_EMAIL = os.getenv("EDGAR_EMAIL", "evangoh@gmail.com")
HEADERS = {
    "User-Agent": f"Capstone-Quant-Platform {EDGAR_EMAIL}",
    "Accept": "application/json",
}
DATA_BASE_URL = "https://data.sec.gov"       # submissions + XBRL JSON APIs
WWW_BASE_URL  = "https://www.sec.gov"        # ticker file + filing archives
DELAY    = 0.12  # 8 req/s, under the 10/s SEC limit

def _get(url: str, retries: int = 3) -> Optional[dict]:
    """GET JSON from EDGAR with retries and polite rate limiting."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:  # rate limited
                wait = 2 ** (attempt + 1)
                print(f"  [RATE] 429 on {url} — sleeping {wait}s")
                time.sleep(wait)
            elif 500 <= r.status_code < 600:
                wait = 2 ** attempt
                print(f"  [WARN] {r.status_code} for {url} — retrying in {wait}s")
                time.sleep(wait)
            else:
                print(f"  [WARN] {r.status_code} for {url}")
                return None
        except Exception as e:
            print(f"  [ERROR] attempt {attempt+1}: {e}")
            time.sleep(1)
    return None

def _get_raw(url: str, retries: int = 3) -> Optional[str]:
    """GET raw text (HTML/XML) from EDGAR."""
    h = dict(HEADERS)
    h["Accept"] = "text/html,application/xhtml+xml,text/plain,*/*"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=h, timeout=30)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 429:
                time.sleep(2 ** (attempt + 1))
        except Exception as e:
            print(f"  [ERROR] {e}")
            time.sleep(1)
    return None

def build_cik_map(tickers: List[str]) -> Dict[str, str]:
    """Build ticker -> zero-padded 10-digit CIK map from EDGAR company_tickers.json."""
    data = _get(f"{WWW_BASE_URL}/files/company_tickers.json")
    if not data:
        return {}
    result = {}
    for v in data.values():
        sym = str(v.get("ticker", "")).upper()
        cik = str(v.get("cik_str", "")).zfill(10)
        if sym in [t.upper() for t in tickers]:
            result[sym] = cik
    missing = [t for t in tickers if t.upper() not in result]
    if missing:
        print(f"[WARN] CIK not found for: {missing}")
    print(f"[CIK] Mapped {len(result)}/{len(tickers)} tickers")
    return result

def _now():
    return datetime.now(timezone.utc)

print(f"Config ready: {len(UNIVERSE_STK)} equities, forms={FORM_TYPES}")

# COMMAND ----------

# DBTITLE 1,Stage 1: Filing metadata (10-K, 10-Q, 8-K)
from typing import Dict, List
from datetime import datetime
import json
import time

from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    TimestampType,
)

# -------------------------------------------------------------------
# Explicit schema
# -------------------------------------------------------------------
# Required because Stage 1 intentionally writes NULL values for
# chunk_text and chunk_char_count. Spark Connect cannot infer the type
# of a column when every value is None.
# -------------------------------------------------------------------

SEC_FILINGS_SCHEMA = StructType([
    StructField("ticker", StringType(), True),
    StructField("cik", StringType(), True),
    StructField("company_name", StringType(), True),
    StructField("form_type", StringType(), True),
    StructField("filing_date", StringType(), True),
    StructField("accepted_ts", TimestampType(), True),
    StructField("accession_number", StringType(), True),
    StructField("primary_doc", StringType(), True),
    StructField("filing_url", StringType(), True),
    StructField("chunk_id", IntegerType(), True),
    StructField("filing_section", StringType(), True),
    StructField("chunk_text", StringType(), True),
    StructField("chunk_char_count", IntegerType(), True),
    StructField("source", StringType(), True),
    StructField("ingest_ts", TimestampType(), True),
    StructField("raw_payload", StringType(), True),
])


def ingest_filing_metadata(
    ticker_cik_map: Dict[str, str],
    form_types: List[str]
) -> int:
    """
    Fetch recent filing metadata for each ticker from EDGAR submissions API.

    Writes one row per filing to bronze_sec_filings.
    No filing text is written yet.

    Important timestamps:
      filing_date:
          Date shown on the filing.

      accepted_ts:
          Actual EDGAR acceptance timestamp.
          Use this for point-in-time-safe joins.

    Stage 1 metadata rows intentionally have:
      chunk_id = 0
      filing_section = "metadata"
      chunk_text = None
      chunk_char_count = None
    """

    form_set = set(form_types)
    all_rows = []

    # Keep ingest timestamp naive UTC for Spark TimestampType
    ingest_ts = _now()

    # If _now() returns timezone-aware datetime, strip timezone
    if isinstance(ingest_ts, datetime) and ingest_ts.tzinfo is not None:
        ingest_ts = ingest_ts.replace(tzinfo=None)

    for ticker, cik in ticker_cik_map.items():

        # SEC submissions API lives on data.sec.gov
        url = f"{DATA_BASE_URL}/submissions/CIK{cik}.json"

        data = _get(url)

        if data is None:
            print(f"  [WARN] {ticker}: no submissions data")
            continue

        company_name = data.get("name", "")

        recent = (
            data
            .get("filings", {})
            .get("recent", {})
        )

        forms = recent.get("form", [])
        filed_dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        accept_dts = recent.get("acceptanceDateTime", [])

        rows_written = 0

        for form, filed, accn, doc, accept_dt in zip(
            forms,
            filed_dates,
            accessions,
            primary_docs,
            accept_dts,
        ):

            # Only ingest requested SEC form types
            if form not in form_set:
                continue

            # -------------------------------------------------------
            # Parse PIT-safe EDGAR acceptance timestamp
            # -------------------------------------------------------
            accepted_ts = None

            if accept_dt:
                try:
                    accepted_ts = datetime.fromisoformat(
                        accept_dt.replace("Z", "+00:00")
                    )

                    # Spark TimestampType is safest with naive datetime
                    if accepted_ts.tzinfo is not None:
                        accepted_ts = accepted_ts.replace(tzinfo=None)

                except Exception as e:
                    print(
                        f"  [WARN] {ticker} {accn}: "
                        f"could not parse acceptance timestamp "
                        f"{accept_dt}: {e}"
                    )
                    accepted_ts = None

            # -------------------------------------------------------
            # Build SEC filing document URL
            # -------------------------------------------------------
            accn_clean = accn.replace("-", "")

            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accn_clean}/{doc}"
            )

            # -------------------------------------------------------
            # Build Bronze metadata row
            # -------------------------------------------------------
            row = {
                "ticker": ticker,
                "cik": cik,
                "company_name": company_name,
                "form_type": form,
                "filing_date": filed,
                "accepted_ts": accepted_ts,
                "accession_number": accn,
                "primary_doc": doc,
                "filing_url": filing_url,

                # Metadata-only row
                "chunk_id": 0,
                "filing_section": "metadata",
                "chunk_text": None,
                "chunk_char_count": None,

                "source": "sec_edgar",
                "ingest_ts": ingest_ts,

                "raw_payload": json.dumps({
                    "form": form,
                    "filed": filed,
                    "cik": cik,
                    "accession_number": accn,
                    "primary_document": doc,
                    "acceptance_datetime": accept_dt,
                }),
            }

            all_rows.append(row)
            rows_written += 1

        print(
            f"  {ticker} "
            f"(CIK {cik}): "
            f"{rows_written} filings"
        )

        time.sleep(DELAY)

    # ----------------------------------------------------------------
    # Nothing returned from SEC
    # ----------------------------------------------------------------
    if not all_rows:
        print("[WARN] No filing metadata to write.")
        return 0

    # ----------------------------------------------------------------
    # IMPORTANT:
    # Explicitly pass the schema.
    #
    # Do NOT use:
    #   spark.createDataFrame(all_rows)
    #
    # because chunk_text and chunk_char_count are NULL for every Stage 1
    # row and Spark Connect therefore cannot infer their types.
    # ----------------------------------------------------------------
    sdf = spark.createDataFrame(
        all_rows,
        schema=SEC_FILINGS_SCHEMA,
    )

    # Optional debug
    print("\n=== Stage 1 Spark schema ===")
    sdf.printSchema()

    # ----------------------------------------------------------------
    # Write to Delta / Unity Catalog
    # ----------------------------------------------------------------
    (
        sdf.write
        .format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(TABLE)
    )

    print(
        f"[DONE] Stage 1: "
        f"{len(all_rows)} filing metadata rows written"
    )

    return len(all_rows)


# ===================================================================
# RUN STAGE 1
# ===================================================================

print("=== Building CIK map ===")

cik_map = build_cik_map(UNIVERSE_STK)

print("\n=== Stage 1: Filing metadata ===")

total_1 = ingest_filing_metadata(
    cik_map,
    FORM_TYPES,
)

print(
    f"\n[DONE] Stage 1 complete: "
    f"{total_1} metadata rows"
)

# COMMAND ----------

# DBTITLE 1,Stage 2: XBRL financial facts
# ================================================================
# Stage 2: XBRL financial facts
# ================================================================

from datetime import datetime
import json
import time


# Financial concepts we want from SEC Company Facts API.
# Format:
#   (taxonomy, SEC concept name, our friendly label)

XBRL_CONCEPTS = [
    ("us-gaap", "Revenues",                                         "revenue"),
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "revenue"),
    ("us-gaap", "NetIncomeLoss",                                    "net_income"),
    ("us-gaap", "OperatingIncomeLoss",                              "operating_income"),
    ("us-gaap", "Assets",                                           "total_assets"),
    ("us-gaap", "Liabilities",                                      "total_liabilities"),
    ("us-gaap", "StockholdersEquity",                               "stockholders_equity"),
    ("us-gaap", "CashAndCashEquivalentsAtCarryingValue",            "cash"),
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivities",       "operating_cash_flow"),
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment",       "capex"),
    ("us-gaap", "EarningsPerShareDiluted",                          "eps_diluted"),
    ("us-gaap", "EarningsPerShareBasic",                            "eps_basic"),
    ("us-gaap", "CommonStockSharesOutstanding",                     "shares_outstanding"),
    ("dei",     "EntityCommonStockSharesOutstanding",               "shares_outstanding"),
    ("us-gaap", "GrossProfit",                                      "gross_profit"),
    ("us-gaap", "ResearchAndDevelopmentExpense",                    "r_and_d"),
    ("us-gaap", "OperatingExpenses",                                "operating_expenses"),
    ("us-gaap", "LongTermDebt",                                     "long_term_debt"),
]


def ingest_xbrl_facts(
    ticker_cik_map: Dict[str, str]
) -> int:
    """
    Fetch SEC XBRL Company Facts for each ticker.

    Each XBRL fact becomes a row in the same Bronze SEC table.

    Important:
    Stage 2 contains NULL values for fields such as:
        primary_doc
        filing_url

    Therefore we MUST use SEC_FILINGS_SCHEMA rather than allowing
    Spark Connect to infer the DataFrame schema.
    """

    all_rows = []

    ingest_ts = _now()

    # Normalize timezone-aware timestamp for Spark TimestampType
    if isinstance(ingest_ts, datetime) and ingest_ts.tzinfo is not None:
        ingest_ts = ingest_ts.replace(tzinfo=None)

    FLUSH_SIZE = 5000
    total = 0

    # ------------------------------------------------------------
    # Write buffered rows using EXPLICIT schema
    # ------------------------------------------------------------
    def flush(rows):

        if not rows:
            return 0

        # CRITICAL:
        # Do not use spark.createDataFrame(rows) without schema.
        sdf = spark.createDataFrame(
            rows,
            schema=SEC_FILINGS_SCHEMA,
        )

        (
            sdf.write
            .format("delta")
            .mode("append")
            .option("mergeSchema", "true")
            .saveAsTable(TABLE)
        )

        return len(rows)

    # ------------------------------------------------------------
    # Process each ticker
    # ------------------------------------------------------------
    for ticker, cik in ticker_cik_map.items():

        url = (
            f"{DATA_BASE_URL}/api/xbrl/companyfacts/"
            f"CIK{cik}.json"
        )

        data = _get(url)

        if data is None:
            print(f"  [WARN] {ticker}: no XBRL Company Facts data")
            continue

        company_name = data.get("entityName", ticker)

        facts_root = data.get("facts", {})

        rows_written = 0

        # --------------------------------------------------------
        # Iterate through requested financial concepts
        # --------------------------------------------------------
        for taxonomy, concept, label in XBRL_CONCEPTS:

            taxonomy_root = facts_root.get(
                taxonomy,
                {}
            )

            concept_root = taxonomy_root.get(
                concept,
                {}
            )

            units_root = concept_root.get(
                "units",
                {}
            )

            if not units_root:
                continue

            # ----------------------------------------------------
            # Facts can have units such as:
            #
            # USD
            # USD/shares
            # shares
            # pure
            #
            # Iterate across whatever SEC returns.
            # ----------------------------------------------------
            for unit, entries in units_root.items():

                for entry in entries:

                    form = entry.get("form", "")

                    # Only use financial statement filings
                    if form not in ("10-K", "10-Q"):
                        continue

                    # ------------------------------------------------
                    # SEC Company Facts gives "filed", but generally
                    # does NOT expose the exact EDGAR acceptance
                    # timestamp here.
                    #
                    # Treat filed date as a conservative PIT proxy.
                    # ------------------------------------------------
                    filed_str = entry.get("filed")

                    accepted_ts = None

                    if filed_str:
                        try:
                            accepted_ts = datetime.strptime(
                                filed_str,
                                "%Y-%m-%d"
                            )

                        except Exception as e:
                            print(
                                f"  [WARN] {ticker}: "
                                f"failed to parse filed date "
                                f"{filed_str}: {e}"
                            )

                            accepted_ts = None

                    # ------------------------------------------------
                    # Build compact payload used later by retrieval /
                    # transformation layers.
                    # ------------------------------------------------
                    fact_payload = {
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "label": label,
                        "unit": unit,
                        "value": entry.get("val"),
                        "period_start": entry.get("start"),
                        "period_end": entry.get("end"),
                        "filed": entry.get("filed"),
                        "form_type": form,
                        "fiscal_year": entry.get("fy"),
                        "fiscal_period": entry.get("fp"),
                        "accession": entry.get("accn"),
                        "frame": entry.get("frame"),
                    }

                    fact_json = json.dumps(
                        fact_payload,
                        default=str
                    )

                    raw_json = json.dumps(
                        entry,
                        default=str
                    )

                    # ------------------------------------------------
                    # Bronze table row
                    # ------------------------------------------------
                    row = {
                        "ticker": ticker,
                        "cik": cik,
                        "company_name": company_name,

                        "form_type": form,

                        # Filing date should be the date SEC says
                        # the document was filed.
                        "filing_date": entry.get("filed"),

                        # Filed date used as proxy here.
                        "accepted_ts": accepted_ts,

                        "accession_number": entry.get("accn"),

                        # XBRL fact does not directly correspond to
                        # one HTML primary document in this API.
                        "primary_doc": None,
                        "filing_url": None,

                        "chunk_id": 0,

                        "filing_section": (
                            f"xbrl_fact_{label}"
                        ),

                        "chunk_text": fact_json,

                        "chunk_char_count": len(
                            fact_json
                        ),

                        "source": "sec_edgar_xbrl",

                        "ingest_ts": ingest_ts,

                        "raw_payload": raw_json,
                    }

                    all_rows.append(row)

                    rows_written += 1

                    # ------------------------------------------------
                    # Flush periodically to avoid very large Python
                    # lists / Spark Connect payloads.
                    # ------------------------------------------------
                    if len(all_rows) >= FLUSH_SIZE:

                        written = flush(all_rows)

                        total += written

                        all_rows.clear()

        # --------------------------------------------------------
        # Flush remaining rows for this ticker
        # --------------------------------------------------------
        if all_rows:

            written = flush(all_rows)

            total += written

            all_rows.clear()

        print(
            f"  {ticker}: "
            f"{rows_written} XBRL fact entries"
        )

        time.sleep(DELAY)

    print(
        f"[DONE] Stage 2: "
        f"{total} XBRL fact rows written"
    )

    return total


# ================================================================
# RUN STAGE 2
# ================================================================

print("=== Stage 2: XBRL financial facts ===")

total_2 = ingest_xbrl_facts(
    cik_map
)

print(
    f"\n[DONE] Stage 2 complete: "
    f"{total_2} rows"
)

# COMMAND ----------

# DBTITLE 1,Stage 3: Full-text extraction + chunking (RAG source)
# ================================================================
# Stage 3: Full-text extraction + chunking for RAG
# ================================================================

import re
import time
import warnings

from typing import Dict, List, Optional
from datetime import datetime

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning


# ----------------------------------------------------------------
# SEC filings are sometimes XHTML / inline-XBRL.
# BeautifulSoup may warn that the document looks XML-like.
#
# For our purpose (extracting readable filing text), parsing as HTML
# is intentional, so suppress this non-fatal warning.
# ----------------------------------------------------------------
warnings.filterwarnings(
    "ignore",
    category=XMLParsedAsHTMLWarning
)


# ----------------------------------------------------------------
# Section patterns
# ----------------------------------------------------------------
# Maps SEC filing Item labels to semantic section names.
#
# These are primarily useful for 10-K filings.
# If no sections are detected, we fall back to chunking the full
# cleaned document.
# ----------------------------------------------------------------

SECTION_PATTERNS = [
    (
        r"(?i)item\s*1[^0-9a].*?(?=item\s*[2-9]|$)",
        "item1_business"
    ),
    (
        r"(?i)item\s*1a[^0-9a].*?(?=item\s*[2-9]|$)",
        "item1a_risk_factors"
    ),
    (
        r"(?i)item\s*7[^a0-9].*?(?=item\s*[89]|$)",
        "item7_mda"
    ),
    (
        r"(?i)item\s*7a[^0-9].*?(?=item\s*8|$)",
        "item7a_quant_risk"
    ),
    (
        r"(?i)item\s*8[^0-9a].*?(?=item\s*9|$)",
        "item8_financial_statements"
    ),
]


# ----------------------------------------------------------------
# Chunking configuration
# ----------------------------------------------------------------

DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200


def _strip_html(html_text: str) -> str:
    """
    Convert SEC filing HTML / XHTML into clean plain text.

    Removes:
      - scripts
      - styles
      - tables
      - excessive whitespace
      - common EDGAR navigation text
    """

    if not html_text:
        return ""

    soup = BeautifulSoup(
        html_text,
        "lxml"
    )

    # Remove non-narrative elements
    for tag in soup([
        "script",
        "style",
        "table",
        "noscript"
    ]):
        tag.decompose()

    text = soup.get_text(
        separator=" "
    )

    # Collapse whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    # Remove common navigation artifacts
    text = re.sub(
        r"Table of Contents",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text


def _chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """
    Split filing text into overlapping character-based chunks.

    Example:
        chunk_size = 1500
        overlap = 200

    Produces approximately 300-400 token chunks depending on text.
    """

    if not text:
        return []

    if len(text) < 50:
        return []

    # Prevent bad configuration / infinite loops
    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be > 0"
        )

    if overlap < 0:
        raise ValueError(
            "overlap must be >= 0"
        )

    if overlap >= chunk_size:
        raise ValueError(
            "overlap must be smaller than chunk_size"
        )

    chunks = []

    start = 0

    while start < len(text):

        end = min(
            start + chunk_size,
            len(text)
        )

        chunk = text[
            start:end
        ].strip()

        if chunk:
            chunks.append(
                chunk
            )

        # Finished
        if end >= len(text):
            break

        start += (
            chunk_size - overlap
        )

    return chunks


def _fetch_filing_text(
    ticker: str,
    cik: str,
    accn: str,
    doc: str,
) -> Optional[str]:
    """
    Fetch the primary SEC filing document.

    Primary attempt:
        SEC Archives primaryDocument

    Fallback:
        SEC filing index JSON
    """

    accn_clean = accn.replace(
        "-",
        ""
    )

    # ------------------------------------------------------------
    # Primary document URL
    # ------------------------------------------------------------

    url = (
        f"{WWW_BASE_URL}/Archives/edgar/data/"
        f"{int(cik)}/"
        f"{accn_clean}/"
        f"{doc}"
    )

    raw = _get_raw(
        url
    )

    if raw is not None:
        return raw

    # ------------------------------------------------------------
    # Fallback to filing index
    # ------------------------------------------------------------

    idx_url = (
        f"{WWW_BASE_URL}/Archives/edgar/data/"
        f"{int(cik)}/"
        f"{accn_clean}/"
        f"{accn}-index.json"
    )

    idx_data = _get(
        idx_url
    )

    if not idx_data:
        return None

    # SEC index JSON may expose files under directory.item
    candidate_files = (
        idx_data
        .get("directory", {})
        .get("item", [])
    )

    # Compatibility with alternate structure
    if not candidate_files:
        candidate_files = idx_data.get(
            "files",
            []
        )

    for f in candidate_files:

        file_name = (
            f.get("name")
            or ""
        )

        if not file_name:
            continue

        lower_name = file_name.lower()

        # Ignore obvious support files
        if lower_name.endswith(
            (
                ".xml",
                ".xsd",
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".css",
                ".js",
                ".txt",
            )
        ):
            continue

        if lower_name.endswith(
            (
                ".htm",
                ".html",
            )
        ):

            fallback_url = (
                f"{WWW_BASE_URL}/Archives/edgar/data/"
                f"{int(cik)}/"
                f"{accn_clean}/"
                f"{file_name}"
            )

            raw = _get_raw(
                fallback_url
            )

            if raw is not None:
                return raw

    return None


def ingest_filing_text(
    ticker_cik_map: Dict[str, str],
    max_filings_per_ticker: int = 8,
    form_types: Optional[List[str]] = None,
) -> int:
    """
    Fetch recent SEC filing documents, extract narrative sections,
    chunk them, and write them into bronze_sec_filings.

    These rows become the main unstructured-document source for RAG.

    Point-in-time timestamp:
        accepted_ts = EDGAR acceptanceDateTime

    Important:
        We use SEC_FILINGS_SCHEMA explicitly because some Stage 3
        fields such as raw_payload are NULL for every chunk.
    """

    if form_types is None:
        form_types = [
            "10-K",
            "10-Q",
        ]

    form_set = set(
        form_types
    )

    total = 0

    ingest_ts = _now()

    # ------------------------------------------------------------
    # Spark TimestampType works more consistently with naive
    # datetime objects in this Databricks/Spark Connect workflow.
    # ------------------------------------------------------------

    if (
        isinstance(
            ingest_ts,
            datetime
        )
        and ingest_ts.tzinfo is not None
    ):
        ingest_ts = (
            ingest_ts
            .replace(
                tzinfo=None
            )
        )

    FLUSH_SIZE = 2000

    all_rows = []

    # ------------------------------------------------------------
    # Flush buffered rows
    # ------------------------------------------------------------

    def flush(rows):

        if not rows:
            return 0

        # ========================================================
        # CRITICAL FIX
        #
        # DO NOT use:
        #
        # spark.createDataFrame(rows)
        #
        # raw_payload is None for every Stage 3 row, so Spark
        # Connect cannot infer its type.
        # ========================================================

        sdf = spark.createDataFrame(
            rows,
            schema=SEC_FILINGS_SCHEMA,
        )

        (
            sdf.write
            .format("delta")
            .mode("append")
            .option(
                "mergeSchema",
                "true"
            )
            .saveAsTable(
                TABLE
            )
        )

        return len(
            rows
        )

    # ============================================================
    # Process tickers
    # ============================================================

    for ticker, cik in ticker_cik_map.items():

        submissions_url = (
            f"{DATA_BASE_URL}/submissions/"
            f"CIK{cik}.json"
        )

        data = _get(
            submissions_url
        )

        if data is None:
            print(
                f"  [WARN] {ticker}: "
                f"unable to retrieve submissions"
            )
            continue

        company_name = data.get(
            "name",
            ticker
        )

        recent = (
            data
            .get(
                "filings",
                {}
            )
            .get(
                "recent",
                {}
            )
        )

        forms = recent.get(
            "form",
            []
        )

        filed_dts = recent.get(
            "filingDate",
            []
        )

        accessions = recent.get(
            "accessionNumber",
            []
        )

        primary_ds = recent.get(
            "primaryDocument",
            []
        )

        accept_dts = recent.get(
            "acceptanceDateTime",
            []
        )

        # --------------------------------------------------------
        # Most recent qualifying filings
        # --------------------------------------------------------

        qualifying = [
            (
                form,
                filed,
                accn,
                doc,
                acpt,
            )

            for (
                form,
                filed,
                accn,
                doc,
                acpt,
            )

            in zip(
                forms,
                filed_dts,
                accessions,
                primary_ds,
                accept_dts,
            )

            if form in form_set
        ][
            :max_filings_per_ticker
        ]

        ticker_chunks = 0

        # ========================================================
        # Process each filing
        # ========================================================

        for (
            form,
            filed,
            accn,
            doc,
            accept_dt,
        ) in qualifying:

            # ----------------------------------------------------
            # PIT-safe SEC acceptance timestamp
            # ----------------------------------------------------

            accepted_ts = None

            if accept_dt:

                try:

                    accepted_ts = (
                        datetime
                        .fromisoformat(
                            accept_dt.replace(
                                "Z",
                                "+00:00"
                            )
                        )
                    )

                    if accepted_ts.tzinfo is not None:

                        accepted_ts = (
                            accepted_ts
                            .replace(
                                tzinfo=None
                            )
                        )

                except Exception as e:

                    print(
                        f"    [WARN] "
                        f"{ticker} {form} {accn}: "
                        f"could not parse acceptance timestamp "
                        f"{accept_dt}: {e}"
                    )

                    accepted_ts = None

            # ----------------------------------------------------
            # Fetch filing
            # ----------------------------------------------------

            raw_html = _fetch_filing_text(
                ticker,
                cik,
                accn,
                doc,
            )

            if not raw_html:

                print(
                    f"    [WARN] "
                    f"{ticker} {form} {accn}: "
                    f"failed to fetch document"
                )

                time.sleep(
                    DELAY
                )

                continue

            # ----------------------------------------------------
            # HTML -> plain text
            # ----------------------------------------------------

            plain_text = _strip_html(
                raw_html
            )

            if not plain_text:

                print(
                    f"    [WARN] "
                    f"{ticker} {form} {accn}: "
                    f"no usable text extracted"
                )

                continue

            # ----------------------------------------------------
            # Extract sections
            # ----------------------------------------------------

            sections_found = []

            for (
                pattern,
                section_name,
            ) in SECTION_PATTERNS:

                match = re.search(
                    pattern,
                    plain_text,
                    re.DOTALL,
                )

                if match:

                    section_text = (
                        match
                        .group(0)
                        .strip()
                    )

                    # Prevent pathological giant sections
                    section_text = (
                        section_text[
                            :50000
                        ]
                    )

                    if len(
                        section_text
                    ) >= 50:

                        sections_found.append(
                            (
                                section_name,
                                section_text,
                            )
                        )

            # ----------------------------------------------------
            # Fallback when Item detection fails
            # ----------------------------------------------------

            if not sections_found:

                sections_found = [
                    (
                        "full_document",
                        plain_text[
                            :100000
                        ],
                    )
                ]

            # ====================================================
            # Chunk sections
            # ====================================================

            for (
                section_name,
                section_text,
            ) in sections_found:

                chunks = _chunk_text(
                    section_text
                )

                for (
                    chunk_idx,
                    chunk,
                ) in enumerate(
                    chunks
                ):

                    filing_url = (
                        f"{WWW_BASE_URL}/Archives/edgar/data/"
                        f"{int(cik)}/"
                        f"{accn.replace('-', '')}/"
                        f"{doc}"
                    )

                    all_rows.append(
                        {
                            "ticker": ticker,

                            "cik": cik,

                            "company_name": company_name,

                            "form_type": form,

                            "filing_date": filed,

                            "accepted_ts": accepted_ts,

                            "accession_number": accn,

                            "primary_doc": doc,

                            "filing_url": filing_url,

                            "chunk_id": (
                                chunk_idx + 1
                            ),

                            "filing_section": (
                                section_name
                            ),

                            "chunk_text": (
                                chunk
                            ),

                            "chunk_char_count": (
                                len(chunk)
                            ),

                            "source": (
                                "sec_edgar"
                            ),

                            "ingest_ts": (
                                ingest_ts
                            ),

                            # Explicit schema tells Spark this is
                            # nullable STRING.
                            "raw_payload": None,
                        }
                    )

                    ticker_chunks += 1

                    # ------------------------------------------------
                    # Flush immediately once buffer reaches threshold
                    # ------------------------------------------------

                    if len(all_rows) >= FLUSH_SIZE:

                        written = flush(
                            all_rows
                        )

                        total += written

                        all_rows.clear()

            # Respect SEC access rate
            time.sleep(
                max(
                    DELAY,
                    0.5
                )
            )

        print(
            f"  {ticker}: "
            f"{len(qualifying)} filings, "
            f"{ticker_chunks} chunks"
        )

    # ============================================================
    # Final flush
    # ============================================================

    if all_rows:

        written = flush(
            all_rows
        )

        total += written

        all_rows.clear()

    print(
        f"[DONE] Stage 3: "
        f"{total} text chunks written"
    )

    return total


# ================================================================
# RUN STAGE 3
# ================================================================

print(
    "=== Stage 3: Full-text extraction + chunking ==="
)

print(
    "  (Fetching SEC filing HTML and creating RAG source chunks)"
)

total_3 = ingest_filing_text(
    cik_map,
    max_filings_per_ticker=8,
)

print(
    f"\n[DONE] Stage 3 complete: "
    f"{total_3} chunks"
)

# COMMAND ----------

# Databricks notebook source
# ================================================================
# SEC EDGAR INGESTION — SMH UNIVERSE
# ================================================================
#
# Stages:
#   1. Filing metadata
#   2. XBRL financial facts
#   3. Filing text extraction + RAG chunking
#
# Features:
#   - Expanded SMH semiconductor universe
#   - Domestic + foreign SEC filer support
#   - Explicit Spark schema
#   - Point-in-time accepted_ts
#   - Idempotent Delta MERGE
#   - Safe to rerun without duplicating records
#
# Output:
#   bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
#
# ================================================================


# ================================================================
# 0. INSTALL — run once if required
# ================================================================

# %pip install -q requests beautifulsoup4 lxml delta-spark
# dbutils.library.restartPython()


# ================================================================
# 1. IMPORTS
# ================================================================

import os
import re
import json
import time
import hashlib
import warnings

from datetime import datetime, timezone
from typing import Optional, List, Dict

import requests

from bs4 import (
    BeautifulSoup,
    XMLParsedAsHTMLWarning,
)

from pyspark.sql import SparkSession

from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    TimestampType,
)

from delta.tables import DeltaTable


spark = SparkSession.builder.getOrCreate()


# ================================================================
# 2. CONFIG
# ================================================================

CATALOG = "bootcamp_students"
SCHEMA = "evangoh_capstone"

# ------------------------------------------------
# IMPORTANT
#
# Use V2 because your existing bronze_sec_filings
# table has an older incompatible schema.
# ------------------------------------------------

TABLE = (
    f"{CATALOG}.{SCHEMA}."
    f"bronze_sec_filings_v2"
)


# ================================================================
# 3. SMH UNIVERSE
# ================================================================

UNIVERSE_STK = [
    "NVDA",
    "TSM",
    "AVGO",
    "MU",
    "AMD",
    "ASML",
    "ADI",
    "TXN",
    "LRCX",
    "AMAT",
    "QCOM",
    "INTC",
    "MRVL",
    "KLAC",
    "CDNS",
    "SNPS",
    "MPWR",
    "TER",
    "NXPI",
    "STM",
    "ARM",
    "ALAB",
    "MCHP",
    "ON",
    "SWKS",
]


# ------------------------------------------------
# Metadata forms
#
# Domestic:
#   10-K / 10-Q / 8-K
#
# Foreign private issuers:
#   20-F / 6-K
# ------------------------------------------------

FORM_TYPES = [
    "10-K",
    "10-Q",
    "8-K",
    "20-F",
    "6-K",
]


# ------------------------------------------------
# Forms we actually want to chunk for RAG
#
# Avoid chunking every 8-K and 6-K for now.
# ------------------------------------------------

RAG_FORM_TYPES = [
    "10-K",
    "10-Q",
    "20-F",
]


# ================================================================
# 4. SEC CONFIG
# ================================================================

EDGAR_EMAIL = os.getenv(
    "EDGAR_EMAIL",
    "your_email@example.com",
)

HEADERS = {
    "User-Agent": (
        f"Capstone-Quant-Platform "
        f"{EDGAR_EMAIL}"
    ),
    "Accept": "application/json",
}

# JSON APIs
DATA_BASE_URL = "https://data.sec.gov"

# Ticker file + filing archives
WWW_BASE_URL = "https://www.sec.gov"

# ~8 requests/sec maximum here
DELAY = 0.12


# ================================================================
# 5. EXPLICIT BRONZE SCHEMA
# ================================================================

SEC_FILINGS_SCHEMA = StructType([

    # Deterministic primary-style key
    StructField(
        "record_key",
        StringType(),
        False,
    ),

    StructField(
        "ticker",
        StringType(),
        True,
    ),

    StructField(
        "cik",
        StringType(),
        True,
    ),

    StructField(
        "company_name",
        StringType(),
        True,
    ),

    StructField(
        "form_type",
        StringType(),
        True,
    ),

    StructField(
        "filing_date",
        StringType(),
        True,
    ),

    StructField(
        "accepted_ts",
        TimestampType(),
        True,
    ),

    StructField(
        "accession_number",
        StringType(),
        True,
    ),

    StructField(
        "primary_doc",
        StringType(),
        True,
    ),

    StructField(
        "filing_url",
        StringType(),
        True,
    ),

    StructField(
        "chunk_id",
        IntegerType(),
        True,
    ),

    StructField(
        "filing_section",
        StringType(),
        True,
    ),

    StructField(
        "chunk_text",
        StringType(),
        True,
    ),

    StructField(
        "chunk_char_count",
        IntegerType(),
        True,
    ),

    StructField(
        "source",
        StringType(),
        True,
    ),

    StructField(
        "ingest_ts",
        TimestampType(),
        True,
    ),

    StructField(
        "raw_payload",
        StringType(),
        True,
    ),
])


# ================================================================
# 6. GENERAL HELPERS
# ================================================================

def _now():
    """
    Naive UTC datetime for Spark TimestampType.
    """

    return datetime.utcnow()


def _record_key(*parts) -> str:
    """
    Create deterministic SHA-256 identifier.

    Same logical SEC record always generates
    exactly the same record_key.
    """

    text = "||".join(
        "" if p is None else str(p)
        for p in parts
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def _parse_sec_timestamp(
    value: Optional[str],
) -> Optional[datetime]:

    if not value:
        return None

    try:

        ts = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        # Store UTC-naive for Spark
        if ts.tzinfo is not None:

            ts = (
                ts
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )

        return ts

    except Exception:

        return None


def _rows_to_df(rows):

    if not rows:
        return None

    return spark.createDataFrame(
        rows,
        schema=SEC_FILINGS_SCHEMA,
    )


# ================================================================
# 7. SEC HTTP CLIENT
# ================================================================

def _get(
    url: str,
    retries: int = 3,
) -> Optional[dict]:
    """
    GET JSON from SEC EDGAR.
    """

    for attempt in range(retries):

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=30,
            )

            time.sleep(DELAY)

            if r.status_code == 200:

                return r.json()

            if r.status_code == 429:

                wait = 2 ** (
                    attempt + 1
                )

                print(
                    f"  [RATE] 429 — "
                    f"sleeping {wait}s"
                )

                time.sleep(wait)

                continue

            if 500 <= r.status_code < 600:

                wait = 2 ** attempt

                print(
                    f"  [WARN] "
                    f"{r.status_code} "
                    f"retrying in {wait}s"
                )

                time.sleep(wait)

                continue

            print(
                f"  [WARN] "
                f"{r.status_code} "
                f"for {url}"
            )

            return None

        except Exception as e:

            print(
                f"  [ERROR] "
                f"attempt {attempt + 1}: "
                f"{e}"
            )

            time.sleep(
                2 ** attempt
            )

    return None


def _get_raw(
    url: str,
    retries: int = 3,
) -> Optional[str]:
    """
    Fetch raw HTML / XHTML / text.
    """

    headers = dict(HEADERS)

    headers["Accept"] = (
        "text/html,"
        "application/xhtml+xml,"
        "text/plain,*/*"
    )

    for attempt in range(retries):

        try:

            r = requests.get(
                url,
                headers=headers,
                timeout=45,
            )

            time.sleep(DELAY)

            if r.status_code == 200:

                return r.text

            if r.status_code == 429:

                wait = 2 ** (
                    attempt + 1
                )

                time.sleep(wait)

                continue

            if 500 <= r.status_code < 600:

                time.sleep(
                    2 ** attempt
                )

                continue

            return None

        except Exception as e:

            print(
                f"  [ERROR] raw fetch: "
                f"{e}"
            )

            time.sleep(
                2 ** attempt
            )

    return None


# ================================================================
# 8. CIK LOOKUP
# ================================================================

def build_cik_map(
    tickers: List[str],
) -> Dict[str, str]:
    """
    ticker -> zero-padded 10-digit CIK
    """

    data = _get(
        f"{WWW_BASE_URL}/files/"
        f"company_tickers.json"
    )

    if not data:

        raise RuntimeError(
            "Unable to retrieve SEC ticker map."
        )

    wanted = {
        t.upper()
        for t in tickers
    }

    result = {}

    for row in data.values():

        ticker = str(
            row.get(
                "ticker",
                "",
            )
        ).upper()

        if ticker not in wanted:
            continue

        cik = str(
            row.get(
                "cik_str",
                "",
            )
        ).zfill(10)

        result[ticker] = cik

    missing = [
        ticker
        for ticker in tickers
        if ticker.upper() not in result
    ]

    print(
        f"[CIK] "
        f"Mapped {len(result)}/"
        f"{len(tickers)} tickers"
    )

    if missing:

        print(
            f"[WARN] CIK not found: "
            f"{missing}"
        )

    return result


# ================================================================
# 9. IDEMPOTENT DELTA WRITER
# ================================================================

def merge_sec_rows(sdf) -> int:
    """
    Insert only records whose record_key
    does not already exist.

    Safe to rerun.
    """

    if sdf is None:
        return 0

    # Remove duplicates inside current batch
    sdf = sdf.dropDuplicates([
        "record_key"
    ])

    # ------------------------------------------------
    # First ever write
    # ------------------------------------------------

    if not spark.catalog.tableExists(TABLE):

        inserted = sdf.count()

        (
            sdf.write
            .format("delta")
            .mode("overwrite")
            .saveAsTable(TABLE)
        )

        print(
            f"    [MERGE] "
            f"Created table: "
            f"{inserted:,} rows"
        )

        return inserted

    # ------------------------------------------------
    # Existing keys
    # ------------------------------------------------

    existing = (
        spark.table(TABLE)
        .select("record_key")
        .dropDuplicates()
    )

    new_rows = (
        sdf
        .join(
            existing,
            on="record_key",
            how="left_anti",
        )
    )

    inserted = new_rows.count()

    if inserted == 0:

        print(
            "    [MERGE] "
            "0 new rows"
        )

        return 0

    # ------------------------------------------------
    # Delta MERGE
    # ------------------------------------------------

    target = DeltaTable.forName(
        spark,
        TABLE,
    )

    (
        target.alias("t")
        .merge(
            new_rows.alias("s"),
            "t.record_key = s.record_key",
        )
        .whenNotMatchedInsertAll()
        .execute()
    )

    print(
        f"    [MERGE] "
        f"{inserted:,} new rows"
    )

    return inserted


# ================================================================
# STAGE 1
# Filing metadata
# ================================================================

def ingest_filing_metadata(
    ticker_cik_map: Dict[str, str],
    form_types: List[str],
) -> int:

    form_set = set(
        form_types
    )

    all_rows = []

    ingest_ts = _now()

    for ticker, cik in ticker_cik_map.items():

        data = _get(
            f"{DATA_BASE_URL}/"
            f"submissions/"
            f"CIK{cik}.json"
        )

        if not data:

            print(
                f"  [WARN] {ticker}: "
                f"no submissions"
            )

            continue

        company_name = data.get(
            "name",
            ticker,
        )

        recent = (
            data
            .get("filings", {})
            .get("recent", {})
        )

        forms = recent.get(
            "form",
            [],
        )

        filing_dates = recent.get(
            "filingDate",
            [],
        )

        accessions = recent.get(
            "accessionNumber",
            [],
        )

        documents = recent.get(
            "primaryDocument",
            [],
        )

        accepted = recent.get(
            "acceptanceDateTime",
            [],
        )

        found = 0

        for (
            form,
            filed,
            accn,
            doc,
            accepted_raw,
        ) in zip(
            forms,
            filing_dates,
            accessions,
            documents,
            accepted,
        ):

            if form not in form_set:
                continue

            accepted_ts = (
                _parse_sec_timestamp(
                    accepted_raw
                )
            )

            accession_clean = (
                accn.replace(
                    "-",
                    "",
                )
            )

            filing_url = (
                f"{WWW_BASE_URL}/"
                f"Archives/edgar/data/"
                f"{int(cik)}/"
                f"{accession_clean}/"
                f"{doc}"
            )

            key = _record_key(
                "metadata",
                ticker,
                accn,
            )

            all_rows.append({

                "record_key":
                    key,

                "ticker":
                    ticker,

                "cik":
                    cik,

                "company_name":
                    company_name,

                "form_type":
                    form,

                "filing_date":
                    filed,

                "accepted_ts":
                    accepted_ts,

                "accession_number":
                    accn,

                "primary_doc":
                    doc,

                "filing_url":
                    filing_url,

                "chunk_id":
                    0,

                "filing_section":
                    "metadata",

                "chunk_text":
                    None,

                "chunk_char_count":
                    None,

                "source":
                    "sec_edgar",

                "ingest_ts":
                    ingest_ts,

                "raw_payload":
                    json.dumps({
                        "form":
                            form,
                        "filed":
                            filed,
                        "cik":
                            cik,
                        "accession_number":
                            accn,
                        "acceptance_datetime":
                            accepted_raw,
                    }),
            })

            found += 1

        print(
            f"  {ticker:<6} "
            f"{found:,} metadata filings"
        )

    if not all_rows:

        print(
            "[WARN] Stage 1 returned "
            "no records."
        )

        return 0

    sdf = _rows_to_df(
        all_rows
    )

    inserted = merge_sec_rows(
        sdf
    )

    print(
        f"[DONE] Stage 1: "
        f"{inserted:,} NEW rows"
    )

    return inserted


# ================================================================
# STAGE 2
# XBRL COMPANY FACTS
# ================================================================

XBRL_CONCEPTS = [

    (
        "us-gaap",
        "Revenues",
        "revenue",
    ),

    (
        "us-gaap",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "revenue",
    ),

    (
        "us-gaap",
        "NetIncomeLoss",
        "net_income",
    ),

    (
        "us-gaap",
        "OperatingIncomeLoss",
        "operating_income",
    ),

    (
        "us-gaap",
        "Assets",
        "total_assets",
    ),

    (
        "us-gaap",
        "Liabilities",
        "total_liabilities",
    ),

    (
        "us-gaap",
        "StockholdersEquity",
        "stockholders_equity",
    ),

    (
        "us-gaap",
        "CashAndCashEquivalentsAtCarryingValue",
        "cash",
    ),

    (
        "us-gaap",
        "NetCashProvidedByUsedInOperatingActivities",
        "operating_cash_flow",
    ),

    (
        "us-gaap",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "capex",
    ),

    (
        "us-gaap",
        "EarningsPerShareDiluted",
        "eps_diluted",
    ),

    (
        "us-gaap",
        "EarningsPerShareBasic",
        "eps_basic",
    ),

    (
        "us-gaap",
        "GrossProfit",
        "gross_profit",
    ),

    (
        "us-gaap",
        "ResearchAndDevelopmentExpense",
        "r_and_d",
    ),

    (
        "us-gaap",
        "OperatingExpenses",
        "operating_expenses",
    ),

    (
        "us-gaap",
        "LongTermDebt",
        "long_term_debt",
    ),

    (
        "dei",
        "EntityCommonStockSharesOutstanding",
        "shares_outstanding",
    ),
]


def ingest_xbrl_facts(
    ticker_cik_map: Dict[str, str],
) -> int:

    total_inserted = 0

    ingest_ts = _now()

    FLUSH_SIZE = 5000

    rows = []

    def flush():

        nonlocal rows
        nonlocal total_inserted

        if not rows:
            return

        sdf = _rows_to_df(
            rows
        )

        total_inserted += (
            merge_sec_rows(sdf)
        )

        rows = []

    for ticker, cik in ticker_cik_map.items():

        data = _get(
            f"{DATA_BASE_URL}/"
            f"api/xbrl/companyfacts/"
            f"CIK{cik}.json"
        )

        if not data:

            print(
                f"  {ticker:<6} "
                f"no XBRL data"
            )

            continue

        company_name = data.get(
            "entityName",
            ticker,
        )

        facts_root = data.get(
            "facts",
            {},
        )

        ticker_rows = 0

        for (
            taxonomy,
            concept,
            label,
        ) in XBRL_CONCEPTS:

            units = (
                facts_root
                .get(taxonomy, {})
                .get(concept, {})
                .get("units", {})
            )

            for unit, entries in units.items():

                for entry in entries:

                    form = entry.get(
                        "form",
                        "",
                    )

                    if form not in [
                        "10-K",
                        "10-Q",
                        "20-F",
                    ]:
                        continue

                    accession = entry.get(
                        "accn"
                    )

                    if not accession:
                        continue

                    filed = entry.get(
                        "filed"
                    )

                    accepted_ts = None

                    if filed:

                        try:

                            accepted_ts = (
                                datetime.strptime(
                                    filed,
                                    "%Y-%m-%d",
                                )
                            )

                        except Exception:
                            pass

                    start = entry.get(
                        "start"
                    )

                    end = entry.get(
                        "end"
                    )

                    fiscal_year = entry.get(
                        "fy"
                    )

                    fiscal_period = entry.get(
                        "fp"
                    )

                    frame = entry.get(
                        "frame"
                    )

                    # --------------------------------------------
                    # Deterministic XBRL identity
                    #
                    # Prevents different periods / facts from
                    # colliding even under the same accession.
                    # --------------------------------------------

                    key = _record_key(
                        "xbrl",
                        ticker,
                        accession,
                        taxonomy,
                        concept,
                        unit,
                        start,
                        end,
                        fiscal_year,
                        fiscal_period,
                        frame,
                    )

                    # Spark IntegerType-safe deterministic ID
                    chunk_id = int(
                        key[:8],
                        16,
                    ) % 2147483647

                    fact_payload = {

                        "taxonomy":
                            taxonomy,

                        "concept":
                            concept,

                        "label":
                            label,

                        "unit":
                            unit,

                        "value":
                            entry.get("val"),

                        "period_start":
                            start,

                        "period_end":
                            end,

                        "filed":
                            filed,

                        "form_type":
                            form,

                        "fiscal_year":
                            fiscal_year,

                        "fiscal_period":
                            fiscal_period,

                        "accession":
                            accession,

                        "frame":
                            frame,
                    }

                    fact_json = json.dumps(
                        fact_payload,
                        default=str,
                    )

                    rows.append({

                        "record_key":
                            key,

                        "ticker":
                            ticker,

                        "cik":
                            cik,

                        "company_name":
                            company_name,

                        "form_type":
                            form,

                        "filing_date":
                            filed,

                        # filed date used as PIT proxy
                        # for Company Facts rows
                        "accepted_ts":
                            accepted_ts,

                        "accession_number":
                            accession,

                        "primary_doc":
                            None,

                        "filing_url":
                            None,

                        "chunk_id":
                            chunk_id,

                        "filing_section":
                            f"xbrl_fact_{label}",

                        "chunk_text":
                            fact_json,

                        "chunk_char_count":
                            len(fact_json),

                        "source":
                            "sec_edgar_xbrl",

                        "ingest_ts":
                            ingest_ts,

                        "raw_payload":
                            json.dumps(
                                entry,
                                default=str,
                            ),
                    })

                    ticker_rows += 1

                    if len(rows) >= FLUSH_SIZE:
                        flush()

        flush()

        print(
            f"  {ticker:<6} "
            f"{ticker_rows:,} XBRL facts"
        )

    flush()

    print(
        f"[DONE] Stage 2: "
        f"{total_inserted:,} "
        f"NEW XBRL rows"
    )

    return total_inserted


# ================================================================
# STAGE 3
# FILING TEXT + RAG CHUNKS
# ================================================================

warnings.filterwarnings(
    "ignore",
    category=XMLParsedAsHTMLWarning,
)


DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200


# ------------------------------------------------
# 10-K / 10-Q oriented sections
#
# 20-F will fall back to full-document chunking
# when these patterns do not match.
# ------------------------------------------------

SECTION_PATTERNS = [

    (
        r"(?i)item\s*1[^0-9a].*?"
        r"(?=item\s*[2-9]|$)",
        "item1_business",
    ),

    (
        r"(?i)item\s*1a[^0-9a].*?"
        r"(?=item\s*[2-9]|$)",
        "item1a_risk_factors",
    ),

    (
        r"(?i)item\s*7[^a0-9].*?"
        r"(?=item\s*[89]|$)",
        "item7_mda",
    ),

    (
        r"(?i)item\s*7a[^0-9].*?"
        r"(?=item\s*8|$)",
        "item7a_quant_risk",
    ),

    (
        r"(?i)item\s*8[^0-9a].*?"
        r"(?=item\s*9|$)",
        "item8_financial_statements",
    ),
]


def _strip_html(
    html_text: str,
) -> str:

    if not html_text:
        return ""

    soup = BeautifulSoup(
        html_text,
        "lxml",
    )

    for tag in soup([
        "script",
        "style",
        "noscript",
        "table",
    ]):

        tag.decompose()

    text = soup.get_text(
        separator=" "
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    text = re.sub(
        r"Table of Contents",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text


def _chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:

    if not text:
        return []

    if len(text) < 50:
        return []

    if overlap >= chunk_size:

        raise ValueError(
            "overlap must be smaller "
            "than chunk_size"
        )

    chunks = []

    start = 0

    while start < len(text):

        end = min(
            start + chunk_size,
            len(text),
        )

        chunk = (
            text[start:end]
            .strip()
        )

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start += (
            chunk_size
            - overlap
        )

    return chunks


def _fetch_filing_text(
    ticker: str,
    cik: str,
    accn: str,
    doc: str,
) -> Optional[str]:

    accession_clean = (
        accn.replace(
            "-",
            "",
        )
    )

    url = (
        f"{WWW_BASE_URL}/"
        f"Archives/edgar/data/"
        f"{int(cik)}/"
        f"{accession_clean}/"
        f"{doc}"
    )

    raw = _get_raw(
        url
    )

    if raw:
        return raw

    # --------------------------------------------
    # Fallback: SEC filing index JSON
    # --------------------------------------------

    index_url = (
        f"{WWW_BASE_URL}/"
        f"Archives/edgar/data/"
        f"{int(cik)}/"
        f"{accession_clean}/"
        f"index.json"
    )

    index_data = _get(
        index_url
    )

    if not index_data:
        return None

    files = (
        index_data
        .get("directory", {})
        .get("item", [])
    )

    for file_info in files:

        name = (
            file_info
            .get("name", "")
        )

        lower = name.lower()

        if not lower.endswith(
            (
                ".htm",
                ".html",
            )
        ):
            continue

        fallback_url = (
            f"{WWW_BASE_URL}/"
            f"Archives/edgar/data/"
            f"{int(cik)}/"
            f"{accession_clean}/"
            f"{name}"
        )

        candidate = _get_raw(
            fallback_url
        )

        if candidate:
            return candidate

    return None


def ingest_filing_text(
    ticker_cik_map: Dict[str, str],
    max_filings_per_ticker: int = 8,
    form_types: Optional[List[str]] = None,
) -> int:

    if form_types is None:

        form_types = (
            RAG_FORM_TYPES
        )

    form_set = set(
        form_types
    )

    total_inserted = 0

    ingest_ts = _now()

    FLUSH_SIZE = 2000

    rows = []

    def flush():

        nonlocal rows
        nonlocal total_inserted

        if not rows:
            return

        sdf = _rows_to_df(
            rows
        )

        total_inserted += (
            merge_sec_rows(sdf)
        )

        rows = []

    # ============================================================
    # Companies
    # ============================================================

    for ticker, cik in ticker_cik_map.items():

        submissions = _get(
            f"{DATA_BASE_URL}/"
            f"submissions/"
            f"CIK{cik}.json"
        )

        if not submissions:

            print(
                f"  [WARN] "
                f"{ticker}: "
                f"no submissions"
            )

            continue

        company_name = (
            submissions.get(
                "name",
                ticker,
            )
        )

        recent = (
            submissions
            .get("filings", {})
            .get("recent", {})
        )

        forms = recent.get(
            "form",
            [],
        )

        filed_dates = recent.get(
            "filingDate",
            [],
        )

        accessions = recent.get(
            "accessionNumber",
            [],
        )

        documents = recent.get(
            "primaryDocument",
            [],
        )

        accepted_dates = recent.get(
            "acceptanceDateTime",
            [],
        )

        qualifying = [

            (
                form,
                filed,
                accession,
                document,
                accepted,
            )

            for (
                form,
                filed,
                accession,
                document,
                accepted,
            )

            in zip(
                forms,
                filed_dates,
                accessions,
                documents,
                accepted_dates,
            )

            if form in form_set

        ][:max_filings_per_ticker]

        ticker_chunks = 0

        # ========================================================
        # Filings
        # ========================================================

        for (
            form,
            filed,
            accession,
            document,
            accepted_raw,
        ) in qualifying:

            accepted_ts = (
                _parse_sec_timestamp(
                    accepted_raw
                )
            )

            raw_html = (
                _fetch_filing_text(
                    ticker,
                    cik,
                    accession,
                    document,
                )
            )

            if not raw_html:

                print(
                    f"    [WARN] "
                    f"{ticker} "
                    f"{form} "
                    f"{accession}: "
                    f"fetch failed"
                )

                continue

            plain_text = (
                _strip_html(
                    raw_html
                )
            )

            if not plain_text:
                continue

            sections_found = []

            # --------------------------------------------
            # Section extraction
            # --------------------------------------------

            for (
                pattern,
                section_name,
            ) in SECTION_PATTERNS:

                match = re.search(
                    pattern,
                    plain_text,
                    flags=re.DOTALL,
                )

                if not match:
                    continue

                section_text = (
                    match
                    .group(0)
                    .strip()
                )

                # 50k character cap
                section_text = (
                    section_text[:50000]
                )

                if len(section_text) >= 50:

                    sections_found.append(
                        (
                            section_name,
                            section_text,
                        )
                    )

            # --------------------------------------------
            # Fallback
            #
            # Especially useful for foreign 20-F filings.
            # --------------------------------------------

            if not sections_found:

                sections_found = [
                    (
                        "full_document",
                        plain_text[:100000],
                    )
                ]

            accession_clean = (
                accession.replace(
                    "-",
                    "",
                )
            )

            filing_url = (
                f"{WWW_BASE_URL}/"
                f"Archives/edgar/data/"
                f"{int(cik)}/"
                f"{accession_clean}/"
                f"{document}"
            )

            # ============================================
            # Sections -> chunks
            # ============================================

            for (
                section_name,
                section_text,
            ) in sections_found:

                chunks = _chunk_text(
                    section_text
                )

                for (
                    chunk_idx,
                    chunk,
                ) in enumerate(
                    chunks,
                    start=1,
                ):

                    key = _record_key(
                        "rag_chunk",
                        ticker,
                        accession,
                        section_name,
                        chunk_idx,
                    )

                    rows.append({

                        "record_key":
                            key,

                        "ticker":
                            ticker,

                        "cik":
                            cik,

                        "company_name":
                            company_name,

                        "form_type":
                            form,

                        "filing_date":
                            filed,

                        "accepted_ts":
                            accepted_ts,

                        "accession_number":
                            accession,

                        "primary_doc":
                            document,

                        "filing_url":
                            filing_url,

                        "chunk_id":
                            chunk_idx,

                        "filing_section":
                            section_name,

                        "chunk_text":
                            chunk,

                        "chunk_char_count":
                            len(chunk),

                        "source":
                            "sec_edgar",

                        "ingest_ts":
                            ingest_ts,

                        "raw_payload":
                            None,
                    })

                    ticker_chunks += 1

                    if len(rows) >= FLUSH_SIZE:
                        flush()

            # Extra politeness for full-document retrieval
            time.sleep(0.5)

        flush()

        print(
            f"  {ticker:<6} "
            f"{len(qualifying)} filings, "
            f"{ticker_chunks:,} chunks"
        )

    flush()

    print(
        f"[DONE] Stage 3: "
        f"{total_inserted:,} "
        f"NEW text chunks"
    )

    return total_inserted


# ================================================================
# 10. RUN PIPELINE
# ================================================================

print(
    "=" * 70
)

print(
    "SEC EDGAR SMH INGESTION"
)

print(
    "=" * 70
)


# ------------------------------------------------
# Build CIK map
# ------------------------------------------------

print(
    "\n=== Building CIK map ==="
)

cik_map = build_cik_map(
    UNIVERSE_STK
)


# ------------------------------------------------
# Stage 1
# ------------------------------------------------

print(
    "\n=== Stage 1: Filing metadata ==="
)

total_1 = ingest_filing_metadata(
    cik_map,
    FORM_TYPES,
)


# ------------------------------------------------
# Stage 2
# ------------------------------------------------

print(
    "\n=== Stage 2: XBRL financial facts ==="
)

total_2 = ingest_xbrl_facts(
    cik_map
)


# ------------------------------------------------
# Stage 3
# ------------------------------------------------

print(
    "\n=== Stage 3: Filing text + RAG chunks ==="
)

total_3 = ingest_filing_text(
    cik_map,
    max_filings_per_ticker=8,
    form_types=RAG_FORM_TYPES,
)


# ================================================================
# 11. SUMMARY
# ================================================================

print(
    "\n"
    + "=" * 70
)

print(
    "INGESTION COMPLETE"
)

print(
    "=" * 70
)

print(
    f"Stage 1 new metadata: "
    f"{total_1:,}"
)

print(
    f"Stage 2 new XBRL:     "
    f"{total_2:,}"
)

print(
    f"Stage 3 new chunks:   "
    f"{total_3:,}"
)

print(
    f"\nTarget table:\n{TABLE}"
)


# ================================================================
# 12. VERIFY
# ================================================================

print(
    "\n=== Verification ==="
)

display(
    spark.sql(
        f"""
        SELECT
            ticker,
            source,
            form_type,
            filing_section,
            COUNT(*) AS rows,
            COUNT(
                DISTINCT accession_number
            ) AS filings,
            MIN(accepted_ts) AS earliest,
            MAX(accepted_ts) AS latest
        FROM {TABLE}
        GROUP BY
            ticker,
            source,
            form_type,
            filing_section
        ORDER BY
            ticker,
            source,
            form_type,
            filing_section
        """
    )
)


# ================================================================
# 13. DUPLICATE CHECK
# ================================================================

print(
    "\n=== Duplicate check ==="
)

duplicate_df = spark.sql(
    f"""
    SELECT
        record_key,
        COUNT(*) AS n
    FROM {TABLE}
    GROUP BY record_key
    HAVING COUNT(*) > 1
    """
)

duplicate_count = (
    duplicate_df.count()
)

if duplicate_count == 0:

    print(
        "[PASS] No duplicate "
        "record_key values."
    )

else:

    print(
        f"[FAIL] Found "
        f"{duplicate_count:,} "
        f"duplicate record keys."
    )

    display(
        duplicate_df
    )

# COMMAND ----------

# DBTITLE 1,Verification: Row counts + sample chunks
# MAGIC %sql
# MAGIC -- Summary of all ingested SEC data
# MAGIC SELECT
# MAGIC   -- form_type,
# MAGIC   -- filing_section,
# MAGIC   -- COUNT(*)                       AS rows,
# MAGIC   -- COUNT(DISTINCT ticker)         AS tickers,
# MAGIC   -- COUNT(DISTINCT accession_number) AS filings,
# MAGIC   -- ROUND(AVG(chunk_char_count), 0) AS avg_chunk_chars,
# MAGIC   -- MIN(accepted_ts)               AS earliest_filing,
# MAGIC   -- MAX(accepted_ts)               AS latest_filing
# MAGIC   *
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_sec_filings
# MAGIC -- GROUP BY form_type, filing_section
# MAGIC -- ORDER BY rows DESC
# MAGIC LIMIT 100

# COMMAND ----------

# DBTITLE 1,Sample: 5 random text chunks for RAG quality check
# MAGIC %sql
# MAGIC -- Sample filing text chunks to verify quality
# MAGIC SELECT
# MAGIC   ticker,
# MAGIC   form_type,
# MAGIC   filing_section,
# MAGIC   accepted_ts,
# MAGIC   chunk_id,
# MAGIC   chunk_char_count,
# MAGIC   LEFT(chunk_text, 500)  AS chunk_preview
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_sec_filings
# MAGIC WHERE filing_section IN ('item1a_risk_factors', 'item7_mda')
# MAGIC   AND chunk_text IS NOT NULL
# MAGIC   AND chunk_char_count > 200
# MAGIC ORDER BY RAND()
# MAGIC LIMIT 5

# COMMAND ----------

# DBTITLE 1,Total row counts summary
# MAGIC %sql
# MAGIC -- Final row count summary across both ingestion notebooks
# MAGIC SELECT 'bronze_ohlcv (stock bars)'         AS table_name, FORMAT_NUMBER(COUNT(*), 0) AS row_count
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_ohlcv
# MAGIC UNION ALL
# MAGIC SELECT 'bronze_options_quotes (Volume ≥5M target)', FORMAT_NUMBER(COUNT(*), 0)
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_options_quotes
# MAGIC UNION ALL
# MAGIC SELECT 'bronze_options_trades',               FORMAT_NUMBER(COUNT(*), 0)
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_options_trades
# MAGIC UNION ALL
# MAGIC SELECT 'bronze_sec_filings (Variety source)', FORMAT_NUMBER(COUNT(*), 0)
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_sec_filings
# MAGIC UNION ALL
# MAGIC SELECT 'bronze_cot',                          FORMAT_NUMBER(COUNT(*), 0)
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_cot