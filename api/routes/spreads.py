"""api/routes/spreads.py — GET /api/spreads.

Five relative-value / macro charts for the "Market Spreads" screen, built from
data the lakehouse already holds (no new ingestion):

1. USO split-adjusted close                 — ``silver_ohlcv_day_adjusted``
2. US 10Y and 2Y Treasury yields + 10s2s    — ``bronze_fed_series`` (DGS10/DGS2)
3. RSP/SPY, 4. MAGS/SOXX, 5. MAGS/SMH       — rebased relative performance

All alignment, rebasing and the 10s2s spread are computed in
:mod:`api.spreads` with Polars; the frontend only draws what this returns.

The window is bounded to the last N trading days (weekday approximation — NYSE
holidays are not excluded), default 252, max 1000, same bounds style as
``api/routes/market.py``.  Reads go through the ``agent.tools_retrieval``
contracts, never string-built SQL.  Each source is read through
``api.deps.read_delta`` so a failure degrades only the affected charts
(freshness ``unavailable``) instead of failing the whole response.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from loguru import logger

from api.deps import AppUser, get_current_user, read_delta
from api.schemas import (
    Freshness,
    MarketSpreadsResponse,
    SpreadChart,
    SpreadSeries,
    SpreadTile,
)
from api.spreads import INDEX_LABEL, price_series, rebased_relative_index, yield_curve
from api.trading_days import start_for_trading_days

router = APIRouter()

_DEFAULT_DAYS = 252
_MAX_DAYS = 1000
_MAX_ROWS = 5000
#: ``bronze_fed_series`` stores one row per *vintage* of each observation, so its
#: read is much larger than a silver read: ~2000 rows for the two market-rate
#: series over a 1000-trading-day window today, but a re-vintaged table would
#: multiply that.  A separate, larger cap keeps the whole window bounded without
#: silently cutting the oldest observations of the window.
_FED_MAX_ROWS = 20_000
_FED_TRUNCATED_DETAIL = "rows truncated at cap; window may be incomplete"

_SILVER = "silver_ohlcv_day_adjusted"
_FED = "bronze_fed_series"
_FED_SERIES = ("DGS10", "DGS2")
_WEEKDAY_DETAIL = "weekday approximation (calendar_limited)"

_EQUITY_SYMBOLS = ("USO", "RSP", "SPY", "MAGS", "SOXX", "SMH")

_USO_TITLE = "USO — split-adjusted close"
_USO_SUBTITLE = (
    "current-scale split-adjusted close "
    "(silver_ohlcv_day_adjusted.adj_close); a price level, not a rebased index"
)
_YIELD_TITLE = "US 10Y and 2Y Treasury yields"
_YIELD_SUBTITLE = (
    "constant-maturity yields (%), latest vintage per observation; "
    "tile = 10s2s spread (DGS10 − DGS2) on dates present in both"
)

#: (chart_id, title, leg A, leg B) — the index is A / B rebased to 100.
_PAIRS = (
    ("rsp_spy", "RSP / SPY relative performance", "RSP", "SPY"),
    ("mags_soxx", "MAGS / SOXX relative performance", "MAGS", "SOXX"),
    ("mags_smh", "MAGS / SMH relative performance", "MAGS", "SMH"),
)

_STATE_PRIORITY = {"unavailable": 3, "empty": 2, "stale": 1, "fresh": 0}


def _join_detail(*parts: str) -> str:
    """Join non-empty detail strings with '; ', avoiding leading separators."""
    return "; ".join(p for p in parts if p)


def _combined_state(*states: str) -> str:
    """Worst of the leg states: unavailable > empty > stale > fresh."""
    return max(states or ("empty",), key=lambda s: _STATE_PRIORITY.get(s, 0))


def _unavailable_chart(
    *,
    chart_id: str,
    title: str,
    subtitle: str,
    kind: Literal["price", "index", "yield"],
    unit: str,
    source: str,
    detail: str,
    tile: SpreadTile | None = None,
) -> SpreadChart:
    """One chart whose computation failed unexpectedly: empty, not a 500.

    Only the fixed public ``detail`` text is returned; the exception itself goes
    to the server log and never into the response.
    """
    return SpreadChart(
        chart_id=chart_id,
        title=title,
        subtitle=subtitle,
        kind=kind,
        unit=unit,
        source=source,
        freshness=Freshness(
            state="unavailable",
            table=source,
            detail=_join_detail(detail, _WEEKDAY_DETAIL),
        ),
        empty=True,
        series=[],
        tile=tile,
        caption="",
    )


def _series_from(
    key: str,
    label: str,
    points: Sequence[list],
    *,
    latest_value: float | None,
    latest_date: str | None,
    window_pct_change: float | None,
) -> SpreadSeries:
    return SpreadSeries(
        key=key,
        label=label,
        points=[(str(p[0]), float(p[1])) for p in points],
        latest_value=latest_value,
        latest_date=latest_date,
        window_pct_change=window_pct_change,
    )


def _outperformance_caption(
    result: dict,
    symbol_a: str,
    symbol_b: str,
) -> str:
    """Plain-evidence caption: who outperformed whom over the window."""
    pct = result.get("window_pct_change")
    if pct is None:
        return ""
    winner, loser = (symbol_a, symbol_b) if pct >= 0 else (symbol_b, symbol_a)
    return (
        f"{winner} outperformed {loser} by {abs(pct):.2f}% over the window "
        f"(price return, splits adjusted, dividends not)."
    )


@router.get("", response_model=MarketSpreadsResponse)
def market_spreads(
    _user: Annotated[AppUser, Depends(get_current_user)],
    days: int = Query(default=_DEFAULT_DAYS, ge=1, le=_MAX_DAYS),
) -> MarketSpreadsResponse:
    # Bounded date window: last N trading days (weekday approximation)
    end_dt = datetime.now(timezone.utc)
    window_end = end_dt.date()
    window_start = start_for_trading_days(window_end, days)
    start_text = window_start.isoformat()
    end_text = window_end.isoformat()

    def _read_symbol(symbol: str) -> tuple[list[dict], str, str]:
        from agent.tools_retrieval import get_market_features

        def _read() -> list[dict]:
            return get_market_features(symbol, start_text, end_text, limit=_MAX_ROWS)

        return read_delta(_read)

    from api.diagnostics import stage

    equity: dict[str, tuple[list[dict], str, str]] = {}
    for symbol in _EQUITY_SYMBOLS:
        with stage("delta_read", table=_SILVER, symbol=symbol):
            equity[symbol] = _read_symbol(symbol)

    def _read_fed() -> list[dict]:
        from agent.tools_retrieval import get_fed_series

        return get_fed_series(list(_FED_SERIES), start_text, end_text, limit=_FED_MAX_ROWS)

    with stage("delta_read", table=_FED):
        fed_rows, fed_state, fed_detail = read_delta(_read_fed)

    # A read that comes back at exactly the cap was very likely cut off by it:
    # the adapter orders ``observation_date DESC`` before applying the limit, so
    # truncation drops the OLDEST observations of the window.  Say so in the
    # chart's freshness detail instead of claiming a complete window.
    fed_truncated = len(fed_rows) >= _FED_MAX_ROWS

    charts: list[SpreadChart] = []

    # ── 1. USO split-adjusted close ──────────────────────────────────────────
    uso_rows, uso_state, uso_detail = equity["USO"]
    try:
        uso = price_series(uso_rows, window_start=window_start)
        uso_caption = ""
        if not uso["empty"]:
            uso_caption = (
                f"Split-adjusted close {uso['latest_value']:.2f} USD on "
                f"{uso['as_of']}."
            )
            if uso["window_pct_change"] is not None:
                uso_caption += f" Window change {uso['window_pct_change']:+.2f}%."
        uso_chart = SpreadChart(
            chart_id="uso_price",
            title=_USO_TITLE,
            subtitle=_USO_SUBTITLE,
            kind="price",
            unit="USD",
            source=_SILVER,
            freshness=Freshness(
                state=uso_state,
                table=_SILVER,
                detail=_join_detail(uso_detail, _WEEKDAY_DETAIL),
            ),
            empty=uso["empty"],
            series=[
                _series_from(
                    "USO",
                    "USO",
                    uso["points"],
                    latest_value=uso["latest_value"],
                    latest_date=uso["latest_date"],
                    window_pct_change=uso["window_pct_change"],
                )
            ],
            first_common_date=uso["first_common_date"],
            dropped_dates=uso["dropped_dates"],
            as_of=uso["as_of"],
            caption=uso_caption,
        )
    except Exception:  # noqa: BLE001 - one bad chart must not fail the response
        logger.exception("market spreads: {} computation failed", "uso_price")
        uso_chart = _unavailable_chart(
            chart_id="uso_price",
            title=_USO_TITLE,
            subtitle=_USO_SUBTITLE,
            kind="price",
            unit="USD",
            source=_SILVER,
            detail="chart computation unavailable",
        )
    charts.append(uso_chart)

    # ── 2. US 10Y / 2Y yields + 10s2s spread ─────────────────────────────────
    try:
        curve = yield_curve(fed_rows, window_start=window_start)
        yield_series = [
            _series_from(
                "DGS10",
                "10Y Treasury yield (DGS10)",
                curve["points"]["DGS10"],
                latest_value=(
                    curve["points"]["DGS10"][-1][1]
                    if curve["points"]["DGS10"]
                    else None
                ),
                latest_date=curve["as_of"],
                window_pct_change=None,
            ),
            _series_from(
                "DGS2",
                "2Y Treasury yield (DGS2)",
                curve["points"]["DGS2"],
                latest_value=(
                    curve["points"]["DGS2"][-1][1]
                    if curve["points"]["DGS2"]
                    else None
                ),
                latest_date=curve["as_of"],
                window_pct_change=None,
            ),
        ]
        yield_caption = ""
        if not curve["empty"]:
            yield_caption = (
                f"10s2s = DGS10 − DGS2 on {len(curve['spread_points'])} common "
                f"dates; latest {curve['spread_value']:+.2f} pp on "
                f"{curve['spread_as_of']}. FRED values are plotted at "
                f"observation_date; the constant-maturity rate is published the "
                f"next business day."
            )
        yields_chart = SpreadChart(
            chart_id="treasury_yields",
            title=_YIELD_TITLE,
            subtitle=_YIELD_SUBTITLE,
            kind="yield",
            unit="%",
            source=_FED,
            freshness=Freshness(
                state=fed_state,
                table=_FED,
                detail=_join_detail(
                    fed_detail,
                    _FED_TRUNCATED_DETAIL if fed_truncated else "",
                    "latest vintage per (series_id, observation_date)",
                    _WEEKDAY_DETAIL,
                ),
            ),
            empty=curve["empty"],
            series=yield_series,
            first_common_date=curve["first_common_date"],
            dropped_dates=curve["dropped_dates"],
            as_of=curve["as_of"],
            tile=SpreadTile(
                label="10s2s",
                value=curve["spread_value"],
                as_of=curve["spread_as_of"],
                # A yield spread is in percentage points, not percent.
                unit="pp",
                points=[
                    (str(p[0]), float(p[1]))
                    for p in curve["spread_points"]
                ],
            ),
            caption=yield_caption,
        )
    except Exception:  # noqa: BLE001 - one bad chart must not fail the response
        logger.exception("market spreads: {} computation failed", "treasury_yields")
        yields_chart = _unavailable_chart(
            chart_id="treasury_yields",
            title=_YIELD_TITLE,
            subtitle=_YIELD_SUBTITLE,
            kind="yield",
            unit="%",
            source=_FED,
            detail="chart computation unavailable",
            tile=SpreadTile(label="10s2s", unit="pp"),
        )
    charts.append(yields_chart)

    # ── 3-5. Rebased relative performance ────────────────────────────────────
    for chart_id, title, symbol_a, symbol_b in _PAIRS:
        rows_a, state_a, detail_a = equity[symbol_a]
        rows_b, state_b, detail_b = equity[symbol_b]
        leg_detail = _join_detail(
            f"{symbol_a}: {detail_a}",
            f"{symbol_b}: {detail_b}",
            _WEEKDAY_DETAIL,
        )
        try:
            rel = rebased_relative_index(
                rows_a,
                rows_b,
                symbol_a=symbol_a,
                symbol_b=symbol_b,
                window_start=window_start,
            )
            pair_chart = SpreadChart(
                chart_id=chart_id,
                title=title,
                subtitle=INDEX_LABEL,
                kind="index",
                unit="index",
                source=_SILVER,
                freshness=Freshness(
                    state=_combined_state(state_a, state_b),
                    table=_SILVER,
                    detail=leg_detail,
                ),
                empty=rel["empty"],
                series=[
                    _series_from(
                        f"{symbol_a}/{symbol_b}",
                        f"{symbol_a} / {symbol_b} (rebased 100)",
                        rel["points"],
                        latest_value=rel["latest_value"],
                        latest_date=rel["latest_date"],
                        window_pct_change=rel["window_pct_change"],
                    )
                ],
                first_common_date=rel["first_common_date"],
                dropped_dates=rel["dropped_dates"],
                as_of=rel["as_of"],
                caption=_outperformance_caption(rel, symbol_a, symbol_b),
            )
        except Exception:  # noqa: BLE001 - one bad chart must not fail the response
            logger.exception("market spreads: {} computation failed", chart_id)
            pair_chart = _unavailable_chart(
                chart_id=chart_id,
                title=title,
                subtitle=INDEX_LABEL,
                kind="index",
                unit="index",
                source=_SILVER,
                detail=_join_detail(leg_detail, "chart computation unavailable"),
            )
        charts.append(pair_chart)

    return MarketSpreadsResponse(
        days=days,
        window_start=start_text,
        window_end=end_text,
        charts=charts,
    )
