"""
sec_client.py — EDGAR data ingestion using edgartools and Polars.
"""
from functools import lru_cache
from typing import List, Dict, Optional
import polars as pl
from edgar import Company
from loguru import logger
from api.services._edgar_identity import ensure_edgar_identity

@lru_cache(maxsize=32)
def get_latest_10k_facts(ticker: str, concepts: Optional[tuple] = None) -> pl.DataFrame:
    """
    Fetch the latest 10-K XBRL facts for a ticker from the xbrl_facts DuckDB table.
    Columns include concept, value, unit, period metadata, and form type.

    If `concepts` is provided, only facts whose concept contains any of the
    given substrings are returned.  This avoids dragging all 50-200+ facts
    through the pipeline when the user only asked about 2-4 metrics.
    """
    try:
        from api.db.database import db_manager
        conn = db_manager.get_connection()

        if concepts:
            clauses = " OR ".join(["concept LIKE ?" for _ in concepts])
            sql = f"""
                SELECT concept, value, unit, period_end, form_type,
                       fiscal_year, fiscal_period, filed, ticker, cik,
                       accession, period_start, frame
                FROM xbrl_facts
                WHERE ticker = ?
                  AND ({clauses})
                ORDER BY period_end DESC, filed DESC, accession DESC
            """
            params = [ticker] + [f"%{c}%" for c in concepts]
            rows = conn.execute(sql, params).fetchall()
        else:
            rows = conn.execute("""
                SELECT concept, value, unit, period_end, form_type,
                       fiscal_year, fiscal_period, filed, ticker, cik,
                       accession, period_start, frame
                FROM xbrl_facts
                WHERE ticker = ?
                ORDER BY period_end DESC, filed DESC, accession DESC
            """, [ticker]).fetchall()

        if not rows:
            return pl.DataFrame()

        df = pl.DataFrame(
            rows,
            schema=[
                "concept", "value", "unit", "period_end", "form_type",
                "fiscal_year", "fiscal_period", "filed", "ticker", "cik",
                "accession", "period_start", "frame",
            ],
            orient="row",
        )
        return df
    except Exception as e:
        logger.error(f"Error fetching XBRL facts for {ticker}: {e}")
        return pl.DataFrame()

@lru_cache(maxsize=32)
def chunk_filing_sections(ticker: str, accession_number: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Chunk the text sections of a 10-K filing.
    Returns a list of dictionaries with chunk_text and metadata.
    """
    ensure_edgar_identity()
    try:
        company = Company(ticker)
        if accession_number:
            filing = company.get_filings(accession_number=accession_number).latest()
        else:
            filing = company.get_filings(form="10-K").latest()
            
        # Get sections using edgartools
        # edgartools supports getting sections for 10-K
        sections = filing.sections()
        chunks = []
        
        for section_name in sections:
            try:
                text = filing.get_section(section_name)
                # Trivial chunking by paragraph or fixed size for this scaffold
                # In a real app, use a more sophisticated splitter
                section_chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
                for i, chunk in enumerate(section_chunks):
                    chunks.append({
                        "chunk_text": chunk,
                        "metadata": {
                            "section_name": section_name,
                            "accession_number": filing.accession_number,
                            "ticker": ticker,
                            "chunk_index": i
                        }
                    })
            except Exception as se:
                logger.warning(f"Could not extract section {section_name}: {se}")
                
        return chunks
    except Exception as e:
        logger.error(f"Error chunking filing for {ticker}: {e}")
        return []
