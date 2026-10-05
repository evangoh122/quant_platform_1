"""api/routes/sec.py — GET /api/sec/coverage.

Returns the list of tickers that have SEC filing chunks in
``gold_sec_coverage`` (n_chunks > 0), sorted by ticker.  Honest states:
table missing → 200 with empty list + status "unavailable" (never a 500).
"""
from __future__ import annotations

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

_log = logging.getLogger(__name__)

_TABLE = "gold_sec_coverage"


class SecCoverageItem(BaseModel):
    ticker: str
    cik: str = ""
    n_filings: int = 0
    n_chunks: int = 0
    first_filed: Optional[str] = None
    last_filed: Optional[str] = None


class SecCoverageResponse(BaseModel):
    data: List[SecCoverageItem] = Field(default_factory=list)
    count: int = 0
    status: Literal["ok", "unavailable"] = "ok"


def _read_coverage_rows() -> List[dict]:
    """Read coverage rows via delta_adapter warehouse path (no user input in SQL)."""
    from db.delta_adapter import _fqn, _warehouse_query

    query = (
        f"SELECT ticker, cik, n_filings, n_chunks, first_filed, last_filed "
        f"FROM {_fqn(_TABLE)} "
        f"WHERE n_chunks > 0 "
        f"ORDER BY ticker"
    )
    return _warehouse_query(query, limit=10000)


@router.get("/coverage", response_model=SecCoverageResponse)
def sec_coverage() -> SecCoverageResponse:
    try:
        rows = _read_coverage_rows()
    except ImportError:
        _log.warning("sec/coverage: pyspark/Delta not available")
        return SecCoverageResponse(data=[], count=0, status="unavailable")
    except Exception as exc:
        _log.warning("sec/coverage: read failed (%s)", type(exc).__name__)
        return SecCoverageResponse(data=[], count=0, status="unavailable")

    items = [
        SecCoverageItem(
            ticker=str(r.get("ticker", "")),
            cik=str(r.get("cik", "")),
            n_filings=int(r.get("n_filings") or 0),
            n_chunks=int(r.get("n_chunks") or 0),
            first_filed=_coerce_str(r.get("first_filed")),
            last_filed=_coerce_str(r.get("last_filed")),
        )
        for r in rows
    ]
    return SecCoverageResponse(data=items, count=len(items), status="ok")


def _coerce_str(value: object) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)