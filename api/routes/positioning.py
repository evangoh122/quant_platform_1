"""api/routes/positioning.py — GET /api/positioning/cot.

CFTC Commitments of Traders data from gold_cot_features and
silver_cot_positions.  Bounded by weeks (4..520, default 156),
filtered by mapped_asset (one of 6 asset classes).  Uses
information_available_ts / release_ts as the as-of timestamp.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import AppUser, get_current_user, read_delta
from api.schemas import (
    CotContractRow,
    CotWeeklyRow,
    Envelope,
    Freshness,
    PositioningResponse,
    iso,
)

router = APIRouter()

_VALID_ASSET_CLASSES = frozenset({
    "equity_index",
    "rate",
    "fx",
    "other",
    "crypto",
    "commodity",
})

_DEFAULT_WEEKS = 156
_MIN_WEEKS = 4
_MAX_WEEKS = 520


@router.get("/cot", response_model=PositioningResponse)
def positioning_cot(
    asset_class: str = Query(..., min_length=1, max_length=30),
    weeks: int = Query(default=_DEFAULT_WEEKS, ge=_MIN_WEEKS, le=_MAX_WEEKS),
    _user: AppUser = Depends(get_current_user),
) -> PositioningResponse:
    asset_class = asset_class.strip().lower()
    if asset_class not in _VALID_ASSET_CLASSES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid asset_class; expected one of {sorted(_VALID_ASSET_CLASSES)}",
        )

    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _read_weekly() -> list[dict]:
        from db.delta_adapter import read_sql

        cutoff = (now_utc - timedelta(weeks=weeks)).strftime("%Y-%m-%dT%H:%M:%SZ")
        sql = """
            SELECT
                mapped_asset,
                report_date,
                information_available_ts,
                lev_money_net,
                lev_money_net_chg_1w,
                lev_money_pctile_52w,
                lev_money_zscore_52w,
                asset_mgr_net,
                asset_mgr_pctile_52w,
                crowding_score,
                regime_label
            FROM gold_cot_features
            WHERE mapped_asset = :asset_class
              AND information_available_ts >= :cutoff
            ORDER BY information_available_ts
        """
        return read_sql(sql, {"asset_class": asset_class, "cutoff": cutoff})

    def _read_contracts() -> list[dict]:
        from db.delta_adapter import read_sql

        sql = """
            SELECT
                contract_name,
                open_interest,
                dealer_net,
                asset_mgr_net,
                lev_money_net,
                dealer_pct_oi,
                asset_mgr_pct_oi,
                lev_money_pct_oi
            FROM silver_cot_positions
            WHERE mapped_asset = :asset_class
              AND release_ts <= :now
            ORDER BY report_date DESC
            LIMIT 200
        """
        return read_sql(sql, {"asset_class": asset_class, "now": now_str})

    from api.diagnostics import stage

    with stage("delta_read", table="gold_cot_features", asset_class=asset_class):
        weekly_rows, weekly_state, weekly_detail = read_delta(_read_weekly)

    with stage("delta_read", table="silver_cot_positions", asset_class=asset_class):
        contract_rows, contract_state, contract_detail = read_delta(_read_contracts)

    weekly = Envelope(
        data=[
            CotWeeklyRow(
                mapped_asset=str(r.get("mapped_asset", asset_class)),
                report_date=iso(r.get("report_date")) or "",
                information_available_ts=iso(r.get("information_available_ts")) or "",
                lev_money_net=r.get("lev_money_net"),
                lev_money_net_chg_1w=r.get("lev_money_net_chg_1w"),
                lev_money_pctile_52w=r.get("lev_money_pctile_52w"),
                lev_money_zscore_52w=r.get("lev_money_zscore_52w"),
                asset_mgr_net=r.get("asset_mgr_net"),
                asset_mgr_pctile_52w=r.get("asset_mgr_pctile_52w"),
                crowding_score=r.get("crowding_score"),
                regime_label=r.get("regime_label"),
            )
            for r in weekly_rows
        ],
        count=len(weekly_rows),
        empty=not weekly_rows,
        source="gold_cot_features",
        freshness=Freshness(
            state=weekly_state, table="gold_cot_features", detail=weekly_detail
        ),
    )

    contracts = Envelope(
        data=[
            CotContractRow(
                contract_name=str(r.get("contract_name", "")),
                open_interest=r.get("open_interest"),
                dealer_net=r.get("dealer_net"),
                asset_mgr_net=r.get("asset_mgr_net"),
                lev_money_net=r.get("lev_money_net"),
                dealer_pct_oi=r.get("dealer_pct_oi"),
                asset_mgr_pct_oi=r.get("asset_mgr_pct_oi"),
                lev_money_pct_oi=r.get("lev_money_pct_oi"),
            )
            for r in contract_rows
        ],
        count=len(contract_rows),
        empty=not contract_rows,
        source="silver_cot_positions",
        freshness=Freshness(
            state=contract_state,
            table="silver_cot_positions",
            detail=contract_detail,
        ),
    )

    return PositioningResponse(
        asset_class=asset_class, weekly=weekly, contracts=contracts
    )