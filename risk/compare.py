"""Run one signal through every sizer with identical execution rules.

The comparison exists to answer a plumbing question: *does volatility-aware
sizing change net risk-adjusted performance relative to fixed sizing?*  Every
variant sees the same prices, the same signal, the same one-bar fill lag and the
same cost/carry rules; only ``risk.sizing`` differs.
"""
from __future__ import annotations

from dataclasses import replace

import polars as pl

from risk.config import (
    BacktestParams,
    PairColumns,
    RiskConfig,
    SignalParams,
    SizingParams,
    load_config,
)
from risk.estimators import estimate_pair
from risk.frames import sorted_by_date
from risk.pair_backtest import backtest_vol_pair, performance_metrics
from risk.sizing import METHODS, size


def build_signal(
    panel: pl.DataFrame,
    params: SignalParams | None = None,
    columns: PairColumns | None = None,
) -> pl.DataFrame:
    """Deterministic reference signal from leg A's adjusted close.

    ``momentum`` is ``sign(close_t / close_{t-lookback} - 1)``; ``reversal`` is
    its negative; ``momentum_z`` is ``tanh(ratio / rolling_std(ratio))`` in
    ``[-1, 1]`` so the alpha magnitude varies; ``constant`` is always long the
    spread.  This is an experiment input, not a claimed alpha.  The panel is
    sorted stably by date first and duplicate dates are rejected, because the
    lookback and rolling scale read row order.
    """
    cfg = load_config()
    p = params or cfg.signals
    cols = columns or cfg.columns
    frame = sorted_by_date(panel, cols.date)
    lookback = int(p.lookback)
    ratio = pl.col(cols.close_a) / pl.col(cols.close_a).shift(lookback) - 1.0
    if p.mode == "momentum":
        raw = ratio.sign()
    elif p.mode == "reversal":
        raw = (-ratio).sign()
    elif p.mode == "momentum_z":
        scale = ratio.rolling_std(window_size=lookback, min_samples=lookback)
        raw = (ratio / scale).tanh()
    elif p.mode == "constant":
        raw = pl.lit(1.0, dtype=pl.Float64)
    else:
        raise ValueError(f"unknown signal mode {p.mode!r}")
    return frame.select(
        pl.col(cols.date),
        pl.when(raw.is_finite())
        .then(raw)
        .otherwise(0.0)
        .alias("signal"),
    )


def _oos_tail(daily: pl.DataFrame, fraction: float) -> pl.DataFrame:
    n_rows = daily.height
    if n_rows == 0:
        return daily
    start = int(n_rows * (1.0 - fraction))
    start = max(0, min(start, n_rows - 1))
    return daily.slice(start, n_rows - start)


def compare_sizers(
    panel: pl.DataFrame,
    config: RiskConfig | None = None,
    signals: pl.DataFrame | None = None,
    methods: tuple[str, ...] | None = None,
    cost_levels: tuple[float, ...] | None = None,
) -> pl.DataFrame:
    """Compare sizers at several per-side cost levels; metrics are OOS only.

    The panel (and a precomputed ``signals`` frame, when given) is sorted
    stably by date and duplicate dates are rejected before any estimator,
    signal or backtest runs.
    """
    cfg = config or load_config()
    compare = cfg.compare
    selected = tuple(methods) if methods is not None else compare.methods
    unknown = set(selected).difference(METHODS)
    if unknown:
        raise ValueError(f"unknown sizing methods: {sorted(unknown)}")
    costs = tuple(cost_levels) if cost_levels is not None else cfg.costs.bps_per_side

    panel = sorted_by_date(panel, cfg.columns.date)
    if signals is not None:
        signals = sorted_by_date(signals, cfg.columns.date)

    estimates = estimate_pair(panel, cfg.estimators, cfg.columns)
    signal_frame = signals if signals is not None else build_signal(
        panel, cfg.signals, cfg.columns
    )

    rows: list[dict[str, float | str]] = []
    for method in selected:
        sizing: SizingParams = replace(cfg.sizing, method=method)
        weights = size(signal_frame, estimates, sizing)
        for bps in costs:
            backtest: BacktestParams = replace(
                cfg.backtest, cost_bps_per_side=float(bps)
            )
            result = backtest_vol_pair(
                panel,
                weights,
                backtest,
                columns=cfg.columns,
            )
            oos = _oos_tail(result.daily, compare.oos_fraction)
            metrics = performance_metrics(oos, backtest)
            rows.append(
                {
                    "variant": method,
                    "cost_bps": float(bps),
                    "target_vol": float(cfg.sizing.target_vol),
                    "oos_sharpe": metrics["sharpe"],
                    "ann_return": metrics["ann_return"],
                    "realized_vol_net": metrics["realized_vol_net"],
                    "realized_vol_gross": metrics["realized_vol_gross"],
                    "vol_gap": abs(
                        metrics["realized_vol_gross"] - cfg.sizing.target_vol
                    ),
                    "max_drawdown": metrics["max_drawdown"],
                    "gross_exposure_avg": metrics["gross_exposure_avg"],
                    "net_exposure_avg": metrics["net_exposure_avg"],
                    "turnover_avg": metrics["turnover_avg"],
                    "borrow_cost_total": metrics["borrow_cost_total"],
                    "cost_total": metrics["cost_total"],
                    "net_pnl_total": metrics["net_pnl_total"],
                    "n_days": metrics["n_days"],
                }
            )
    return pl.DataFrame(rows)
