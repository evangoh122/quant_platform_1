"""
edgar_adapter.py — EdgarTools wrapper that produces ExtractionResult.

This is the ONLY place in the codebase that imports edgartools. All
downstream components receive ExtractionResult; they never touch raw
EdgarTools objects. (CONSTRAINT-009: no custom EDGAR/XBRL parser.)

Provenance assignment rules (CONSTRAINT-002):
  - XBRL financials (filing.financials.*)     → Provenance.XBRL
  - HTML structured tables (filing.obj())     → Provenance.STRUCTURED_TABLE
  - LLM-extracted narrative                   → Provenance.NARRATIVE_LLM (Phase 3+)
"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from api.models.eval_types import (
    ExtractionResult,
    ExtractedField,
    Provenance,
)
from api.services._edgar_identity import ensure_edgar_identity


class EdgarAdapterError(Exception):
    """Raised when edgartools cannot fetch or parse a filing."""


def _set_edgar_identity() -> None:
    user_agent = os.getenv("EDGAR_USER_AGENT")
    if not user_agent:
        raise EdgarAdapterError(
            "EDGAR_USER_AGENT environment variable is not set. "
            "Set it to 'Your Name your@email.com' before calling fetch_filing()."
        )
    ensure_edgar_identity()


def _xbrl_dataframe_to_fields(df: pd.DataFrame, concept_col: str = "concept") -> list[ExtractedField]:
    """Convert a single EdgarTools financials DataFrame into XBRL-tagged ExtractedFields.

    EdgarTools financials DataFrames (balance_sheet, income_statement,
    cash_flow_statement) contain at minimum a concept column and a value
    column. Column names differ slightly by EdgarTools version; this function
    handles the two most common layouts.

    Returns an empty list if the DataFrame is None or empty.
    """
    if df is None or df.empty:
        return []

    fields: list[ExtractedField] = []

    # EdgarTools >= 2.x typically has columns: concept, label, value, units, decimals
    # Older versions may use 'name' instead of 'concept'.
    if concept_col not in df.columns:
        concept_col = "name" if "name" in df.columns else df.columns[0]

    value_col = "value" if "value" in df.columns else df.columns[-1]

    for _, row in df.iterrows():
        raw_concept = str(row.get(concept_col, ""))
        raw_value   = row.get(value_col)

        fields.append(
            ExtractedField(
                name=raw_concept,
                value=raw_value,
                provenance=Provenance.XBRL,
                concept=raw_concept or None,
            )
        )

    return fields


def _html_tables_to_fields(filing) -> list[ExtractedField]:  # type: ignore[type-arg]
    """Extract structured tables from the filing's primary HTML document.

    Uses EdgarTools' filing.obj() to retrieve the parsed filing object,
    then walks its data tables. Returns STRUCTURED_TABLE-tagged fields.

    Returns an empty list if no HTML tables are found or if obj() fails.
    """
    fields: list[ExtractedField] = []
    try:
        doc = filing.obj()
        if doc is None:
            return fields

        # EdgarTools TenK/TenQ objects expose .income_statement, .balance_sheet etc.
        # as properties that may return DataFrames or None.
        # For form types without a structured obj(), we skip gracefully.
        for attr in ("income_statement", "balance_sheet", "cash_flow_statement"):
            tbl: Optional[pd.DataFrame] = getattr(doc, attr, None)
            if tbl is None or not isinstance(tbl, pd.DataFrame) or tbl.empty:
                continue

            label_col = tbl.columns[0]
            value_col = tbl.columns[-1]

            for _, row in tbl.iterrows():
                label = str(row.get(label_col, ""))
                value = row.get(value_col)
                fields.append(
                    ExtractedField(
                        name=label,
                        value=value,
                        provenance=Provenance.STRUCTURED_TABLE,
                    )
                )
    except Exception:  # noqa: BLE001 — structured table extraction is best-effort
        logger.debug("Structured table extraction skipped (no tables found or parse error)")

    return fields


def fetch_filing(cik: str, accession: str) -> ExtractionResult:
    """Fetch a SEC filing via EdgarTools and return a typed ExtractionResult.

    Args:
        cik: SEC Central Index Key, e.g. "0001045810" (Nvidia).
        accession: SEC accession number, e.g. "0000320193-23-000064".

    Returns:
        ExtractionResult with all extracted fields provenance-tagged.

    Raises:
        EdgarAdapterError: If the filing cannot be fetched or parsed.
    """
    _set_edgar_identity()

    try:
        from edgar import Company  # noqa: PLC0415 — deferred import
    except ImportError as exc:
        raise EdgarAdapterError(
            "edgartools is not installed. Run: pip install 'edgartools>=2.26.0'"
        ) from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )
    def _fetch() -> object:
        return Company(cik).get_filings(accession_number=accession)[0]

    try:
        filing = _fetch()
    except Exception as exc:
        raise EdgarAdapterError(
            f"EdgarTools failed to fetch filing (CIK={cik}, accession={accession}): {exc}"
        ) from exc

    if filing is None:
        raise EdgarAdapterError(
            f"No filing found for CIK={cik}, accession={accession}."
        )

    # --- Extract XBRL fields ---
    xbrl_fields: list[ExtractedField] = []
    try:
        financials = filing.financials
        if financials is not None:
            for df in (
                financials.balance_sheet,
                financials.income_statement,
                financials.cash_flow_statement,
            ):
                xbrl_fields.extend(_xbrl_dataframe_to_fields(df))
    except Exception:  # noqa: BLE001 — XBRL block may not exist for all form types
        logger.debug("XBRL extraction skipped (no structured facts for this filing)")

    # --- Extract structured HTML table fields ---
    table_fields = _html_tables_to_fields(filing)

    all_fields = xbrl_fields + table_fields

    # Determine period — EdgarTools exposes period_of_report on most form types
    period_val = getattr(filing, "period_of_report", None)
    period: Optional[str] = str(period_val) if period_val else None

    return ExtractionResult(
        cik=cik,
        accession=accession,
        form_type=getattr(filing, "form_type", "UNKNOWN"),
        period=period,
        fields=all_fields,
    )
