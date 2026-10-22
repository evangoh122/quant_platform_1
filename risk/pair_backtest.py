"""Open-to-open pair backtester with an explicit one-bar execution lag.

The rules mirror ``strategies/backtest.py`` where that module is usable without
its data-frame functions: a signal produced at close ``t`` fills at open
``t+1``, and the book earns open-to-open returns.  That is two structural
shifts, exactly as in the reference backtester:

* ``w_exec(t) = w(t-1)`` — the book established by the open-``t`` fill
  (``fills[t] = desired[t-1]``);
* ``gross(t) = w_exec(t-1) * ret(t)`` — row ``t``'s open-to-open return
  (``open t-1 -> open t``) is earned by the book *held* over that interval,
  which is the book filled at open ``t-1``, i.e. ``w(t-2)``.

Skipping the second shift would let a weight decided at close ``t-1`` earn the
overnight gap into the open-``t`` fill price: a look-ahead the reference
backtester does not have.  Scalar cost helpers are imported from
``strategies.cost_model``; the vectorized ADV cost expression is the Polars
equivalent and is parity-tested against ``cost_per_trade``.

Costs
-----
* Transaction cost is charged on the notional actually traded
  (``sum |delta w|``) at a configurable flat bps per side, or through the ADV
  participation model when ``cost_mode == "adv"``.
* Borrow is charged only on **short** notional of the book *held* over the
  row's open-to-open interval (``w_a_held`` / ``w_b_held``) -- the same book
  that earns ``gross_return``.  The book established at the open (``w_exec``)
  is not charged until the next row, when it is the held book; charging
  ``w_exec`` would bill borrow for an interval the book did not own.  The
  daily rate is the configured bucket in
  ``strategies.cost_model.CostParams``.  No borrow feed exists in the
  lakehouse, so this remains a stated assumption.
* ``turnover`` is ``sum |delta w|`` and deliberately ignores intraday weight
  drift (documented simplification in ``risk/README.md``).
"""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from risk.config import BacktestParams, PairColumns, load_config
from risk.frames import sorted_by_date
from strategies.cost_model import CostParams, cost_per_trade


@dataclass(frozen=True)
class PairBacktestResult:
    """Daily path plus summary metrics for one weight path."""

    daily: pl.DataFrame
    metrics: dict[str, float]


# ── Cost helpers ─────────────────────────────────────────────────────────────

def cost_bps_per_side(
    order_notional: float,
    adv: float,
    params: CostParams | None = None,
) -> float:
    """Scalar per-side cost in bps (thin wrapper over ``cost_per_trade``)."""
    return cost_per_trade(order_notional, adv, params)


def cost_bps_expr(
    order_notional: pl.Expr,
    adv: pl.Expr,
    params: CostParams | None = None,
) -> pl.Expr:
    """Vectorized Polars equivalent of ``strategies.cost_model.cost_per_trade``.

    Participation is capped at ``adv_participation_cap``; an unknown/zero ADV is
    charged as 100 % participation, matching the scalar helper.
    """
    p = params or CostParams()
    participation = (
        pl.when(adv > 0.0)
        .then(order_notional / adv)
        .otherwise(1.0)
        .clip(upper_bound=p.adv_participation_cap)
    )
    return (
        pl.lit(p.commission_bps)
        + 0.5 * pl.lit(p.spread_bps)
        + pl.lit(p.slippage_bps) * (participation / p.adv_participation_cap)
    )


def borrow_rate_daily(
    bucket: str,
    params: CostParams | None = None,
) -> float:
    """Daily borrow rate (bps) for a ``CostParams`` liquidity bucket."""
    p = params or CostParams()
    if bucket not in p.borrow_bps_daily:
        raise KeyError(f"unknown borrow bucket {bucket!r}")
    return float(p.borrow_bps_daily[bucket])


# ── Price returns ────────────────────────────────────────────────────────────

def _open_returns(open_price: pl.Expr, return_type: str) -> pl.Expr:
    safe = pl.when(open_price > 0.0).then(open_price).otherwise(
        pl.lit(None, dtype=pl.Float64)
    )
    ratio = safe / safe.shift(1)
    if return_type == "simple":
        return ratio - 1.0
    if return_type == "log":
        return ratio.log()
    raise ValueError(f"unknown return_type {return_type!r}")


# ── Metrics ──────────────────────────────────────────────────────────────────

def performance_metrics(
    daily: pl.DataFrame,
    params: BacktestParams | None = None,
) -> dict[str, float]:
    """Summary statistics for a daily path (all columns are per-NAV fractions).

    ``sharpe``, ``realized_vol_gross`` and ``realized_vol_net`` all use
    ``params.sharpe_ddof`` as their standard-deviation ``ddof``.  The path is
    sorted stably by its ``pl.Date`` column and duplicate dates are rejected,
    because cumulative returns and max drawdown read row order: a shuffled
    daily frame must produce the same statistics as the chronological one.
    """
    p = params or load_config().backtest
    n = daily.height
    empty = {
        "n_days": float(n),
        "sharpe": float("nan"),
        "ann_return": float("nan"),
        "realized_vol_net": float("nan"),
        "realized_vol_gross": float("nan"),
        "max_drawdown": float("nan"),
        "gross_exposure_avg": float("nan"),
        "net_exposure_avg": float("nan"),
        "turnover_avg": float("nan"),
        "turnover_cost_total": float("nan"),
        "borrow_cost_total": float("nan"),
        "cost_total": float("nan"),
        "net_pnl_total": float("nan"),
    }
    if n == 0:
        return empty

    daily = sorted_by_date(daily)
    net = daily["net_return"]
    gross = daily["gross_return"]
    mean = float(net.mean())
    std = float(net.std(ddof=p.sharpe_ddof)) if n > p.sharpe_ddof else 0.0
    scale = float(p.annualization) ** 0.5
    sharpe = mean / std * scale if std > p.epsilon else float("nan")

    equity_expr = (1.0 + pl.col("net_return")).cum_prod()
    drawdown_frame = daily.select(equity_expr.alias("_equity")).select(
        (
            pl.col("_equity")
            / pl.max_horizontal(pl.col("_equity").cum_max(), pl.lit(1.0))
            - 1.0
        )
        .min()
        .alias("_mdd")
    )
    drawdown = float(drawdown_frame["_mdd"][0])
    final_equity = float(daily.select(equity_expr.alias("_equity"))["_equity"][-1])
    if final_equity > 0.0:
        ann_return = final_equity ** (float(p.annualization) / n) - 1.0
    else:
        ann_return = float("nan")

    # Realized-vol ddof is the configured metric ddof -- the same knob that sets
    # the Sharpe ddof, so both metrics share one convention.
    vol_ddof = p.sharpe_ddof
    has_vol = n > vol_ddof
    gross_vol = float(gross.std(ddof=vol_ddof)) * scale if has_vol else 0.0
    net_vol = float(net.std(ddof=vol_ddof)) * scale if has_vol else 0.0
    return {
        "n_days": float(n),
        "sharpe": float(sharpe),
        "ann_return": float(ann_return),
        "realized_vol_net": float(net_vol),
        "realized_vol_gross": float(gross_vol),
        "max_drawdown": float(drawdown),
        "gross_exposure_avg": float(daily["gross_exposure"].mean()),
        "net_exposure_avg": float(daily["net_exposure"].mean()),
        "turnover_avg": float(daily["traded_notional"].mean()),
        "turnover_cost_total": float(daily["turnover_cost"].sum()),
        "borrow_cost_total": float(daily["borrow_cost"].sum()),
        "cost_total": float(
            (daily["turnover_cost"] + daily["borrow_cost"]).sum()
        ),
        "net_pnl_total": float(net.sum()),
    }


# ── Backtest ─────────────────────────────────────────────────────────────────

def backtest_vol_pair(
    prices: pl.DataFrame,
    weights: pl.DataFrame,
    params: BacktestParams | None = None,
    cost_params: CostParams | None = None,
    columns: PairColumns | None = None,
    adv: pl.DataFrame | None = None,
) -> PairBacktestResult:
    """Backtest a two-leg target-weight path on adjusted open prices.

    Args:
        prices: long frame with ``date`` (``pl.Date``) and adjusted ``open_a``,
            ``open_b`` (plus any close columns; only opens drive P&L).
        weights: long frame ``date, w_a, w_b`` decided at the close of
            ``date``.  A weight fills at the next open and only earns from the
            following open-to-open interval (two structural shifts).
        params: backtest parameters (cost bps, borrow bucket, annualization).
        cost_params: ``CostParams`` providing the borrow schedule.
        columns: pair column names.
        adv: optional ``date, adv_a, adv_b`` frame for ``cost_mode == "adv"``.

    ``prices``, ``weights`` and ``adv`` are sorted stably by date and duplicate
    dates are rejected, so the fill lag and the resulting P&L path do not
    depend on the caller's row order.
    """
    cfg = load_config()
    p = params or cfg.backtest
    cols = columns or cfg.columns
    cp = cost_params or CostParams()

    if cols.date not in prices.columns or prices.schema[cols.date] != pl.Date:
        raise TypeError(f"{cols.date!r} must exist and be pl.Date")
    if cols.date not in weights.columns or weights.schema[cols.date] != pl.Date:
        raise TypeError(f"{cols.date!r} must exist and be pl.Date")

    px = sorted_by_date(prices, cols.date).select(
        pl.col(cols.date),
        _open_returns(pl.col(cols.open_a), p.return_type).alias("ret_a"),
        _open_returns(pl.col(cols.open_b), p.return_type).alias("ret_b"),
    )
    book = sorted_by_date(weights, cols.date).select(
        pl.col(cols.date),
        pl.col("w_a").cast(pl.Float64),
        pl.col("w_b").cast(pl.Float64),
    )
    frame = px.join(book, on=cols.date, how="left").sort(cols.date)

    # Signal at close t -> fill at open t+1: w_exec(t) = w(t-1) is the book
    # established at the open of row t.  Row t's return spans open t-1 -> open
    # t, so it belongs to w_exec(t-1) = w(t-2), the book actually held over
    # that interval.  Using w_exec(t) here would earn the gap into the fill
    # price with a weight decided before the fill (a one-bar look-ahead).
    frame = frame.with_columns(
        pl.col("w_a").shift(1).alias("w_a_exec"),
        pl.col("w_b").shift(1).alias("w_b_exec"),
    )
    frame = frame.with_columns(
        pl.col("w_a_exec").fill_null(0.0),
        pl.col("w_b_exec").fill_null(0.0),
    )
    frame = frame.with_columns(
        pl.col("w_a_exec").shift(1).fill_null(0.0).alias("w_a_held"),
        pl.col("w_b_exec").shift(1).fill_null(0.0).alias("w_b_held"),
    )
    frame = frame.with_columns(
        (
            pl.col("w_a_held") * pl.col("ret_a")
            + pl.col("w_b_held") * pl.col("ret_b")
        ).alias("gross_return"),
        (
            pl.col("w_a_exec") - pl.col("w_a_exec").shift(1).fill_null(0.0)
        ).abs().alias("dw_a"),
        (
            pl.col("w_b_exec") - pl.col("w_b_exec").shift(1).fill_null(0.0)
        ).abs().alias("dw_b"),
    )
    frame = frame.with_columns(
        (pl.col("dw_a") + pl.col("dw_b")).alias("traded_notional"),
        (pl.col("w_a_exec").abs() + pl.col("w_b_exec").abs()).alias(
            "gross_exposure"
        ),
        (pl.col("w_a_exec") + pl.col("w_b_exec")).alias("net_exposure"),
    )

    if p.cost_mode == "adv":
        if adv is None:
            raise ValueError("cost_mode='adv' requires an adv frame")
        adv_frame = sorted_by_date(adv, cols.date).select(
            pl.col(cols.date),
            pl.col("adv_a").cast(pl.Float64),
            pl.col("adv_b").cast(pl.Float64),
        )
        frame = frame.join(adv_frame, on=cols.date, how="left")
        frame = frame.with_columns(
            (
                pl.col("dw_a")
                * cost_bps_expr(
                    pl.col("dw_a") * pl.lit(p.book_capital),
                    pl.col("adv_a").fill_null(0.0),
                    cp,
                )
                / 10_000.0
                + pl.col("dw_b")
                * cost_bps_expr(
                    pl.col("dw_b") * pl.lit(p.book_capital),
                    pl.col("adv_b").fill_null(0.0),
                    cp,
                )
                / 10_000.0
            ).alias("turnover_cost")
        )
    elif p.cost_mode == "flat":
        frame = frame.with_columns(
            (
                pl.col("traded_notional")
                * pl.lit(p.cost_bps_per_side)
                / 10_000.0
            ).alias("turnover_cost")
        )
    else:
        raise ValueError(f"unknown cost_mode {p.cost_mode!r}")

    borrow_bps = borrow_rate_daily(p.borrow_bucket, cp)
    frame = frame.with_columns(
        (
            pl.when(pl.col("w_a_held") < 0.0)
            .then(-pl.col("w_a_held"))
            .otherwise(0.0)
            + pl.when(pl.col("w_b_held") < 0.0)
            .then(-pl.col("w_b_held"))
            .otherwise(0.0)
        )
        .mul(pl.lit(borrow_bps / 10_000.0))
        .alias("borrow_cost")
    )
    frame = frame.with_columns(
        (
            pl.col("gross_return")
            - pl.col("turnover_cost")
            - pl.col("borrow_cost")
        ).alias("net_return")
    )

    # The first row has no open-to-open return; drop it after the lag is applied
    # so the first usable row still carries the signal from the prior close.
    frame = frame.filter(
        pl.col("ret_a").is_not_null() & pl.col("ret_b").is_not_null()
    )
    daily = frame.select(
        pl.col(cols.date),
        pl.col("ret_a"),
        pl.col("ret_b"),
        pl.col("w_a_exec"),
        pl.col("w_b_exec"),
        pl.col("w_a_held"),
        pl.col("w_b_held"),
        pl.col("gross_return"),
        pl.col("net_return"),
        pl.col("traded_notional"),
        pl.col("turnover_cost"),
        pl.col("borrow_cost"),
        pl.col("gross_exposure"),
        pl.col("net_exposure"),
    )
    return PairBacktestResult(daily=daily, metrics=performance_metrics(daily, p))
