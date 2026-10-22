"""Polars-based volatility estimators for the pair risk layer.

Conventions
-----------
* Every function takes and returns Polars expressions or frames.  There is no
  index: a ``date`` column carries time order.  The expression helpers are bare
  ``pl.Expr`` builders and assume the caller already ordered rows by date; the
  frame-level entry point (:func:`estimate_pair`) sorts stably by date itself
  and rejects duplicate dates.
* Returns are computed from **adjusted** price columns.  Adjusted *levels* are
  never used as features; only ratios of adjusted levels are.
* ``ewm_var``/``ewm_std`` are pinned to ``bias=False`` (the sample / ``ddof=1``
  convention) and ``rolling_std`` to ``ddof=1``.  The population variance is
  used internally only to convert a population correlation into a sample
  covariance consistently with ``ewm_var(bias=False)``.
* Every rolling/EWMA expression is strictly backward looking.  The current bar
  is included (it is known at the close); no future bar is ever read.
* Nulls are preserved.  Turning a missing estimate into a zero weight is the
  job of ``risk.sizing`` at the sizing boundary, not of the estimator.
"""
from __future__ import annotations

import math

import polars as pl

from risk.config import (
    EstimatorParams,
    PairColumns,
    load_config,
)
from risk.frames import sorted_by_date

# ── Returns ───────────────────────────────────────────────────────────────────

def _positive(price: pl.Expr) -> pl.Expr:
    """Mask non-positive prices to null before taking ratios/logs."""
    return pl.when(price > 0.0).then(price).otherwise(pl.lit(None, dtype=pl.Float64))


def price_returns(price: pl.Expr, params: EstimatorParams) -> pl.Expr:
    """Bar-over-bar return from a price expression (log by default)."""
    safe = _positive(price)
    previous = safe.shift(1)
    ratio = safe / previous
    if params.return_type == "log":
        return ratio.log()
    if params.return_type == "simple":
        return ratio - 1.0
    raise ValueError(f"unknown return_type {params.return_type!r}")


def overnight_returns(open_price: pl.Expr, close_price: pl.Expr) -> pl.Expr:
    """Close(t-1) to open(t) log gap."""
    previous_close = _positive(close_price).shift(1)
    return (_positive(open_price) / previous_close).log()


def intraday_returns(open_price: pl.Expr, close_price: pl.Expr) -> pl.Expr:
    """Open(t) to close(t) log return."""
    return (_positive(close_price) / _positive(open_price)).log()


# ── EWMA ──────────────────────────────────────────────────────────────────────

def _ewm_kwargs(params: EstimatorParams) -> dict:
    return {
        "span": params.ewma_span,
        "adjust": params.ewma_adjust,
        "min_samples": params.ewma_min_samples,
    }


def ewma_mean(returns: pl.Expr, params: EstimatorParams) -> pl.Expr:
    return returns.ewm_mean(**_ewm_kwargs(params))


def ewma_var(returns: pl.Expr, params: EstimatorParams) -> pl.Expr:
    """Sample EWMA variance (``bias=False`` == ddof 1)."""
    series = returns
    return series.ewm_var(bias=False, **_ewm_kwargs(params))


def ewma_vol(returns: pl.Expr, params: EstimatorParams) -> pl.Expr:
    """Annualized EWMA volatility."""
    return (ewma_var(returns, params) * float(params.annualization)).sqrt()


def _correlation(returns_a: pl.Expr, returns_b: pl.Expr, params: EstimatorParams) -> pl.Expr:
    """Backward-looking EWMA correlation, zero when variance is degenerate."""
    kwargs = _ewm_kwargs(params)
    mean_a = returns_a.ewm_mean(**kwargs)
    mean_b = returns_b.ewm_mean(**kwargs)
    mean_ab = (returns_a * returns_b).ewm_mean(**kwargs)
    covariance_pop = mean_ab - mean_a * mean_b
    var_pop_a = returns_a.ewm_var(bias=True, **kwargs)
    var_pop_b = returns_b.ewm_var(bias=True, **kwargs)
    sd_pop = (var_pop_a * var_pop_b).sqrt()
    return (
        pl.when(sd_pop.is_null())
        .then(pl.lit(None, dtype=pl.Float64))
        .when(sd_pop > params.epsilon)
        .then((covariance_pop / sd_pop).clip(lower_bound=-1.0, upper_bound=1.0))
        .otherwise(0.0)
    )


def ewma_corr(returns_a: pl.Expr, returns_b: pl.Expr, params: EstimatorParams) -> pl.Expr:
    """Annualization-free EWMA correlation in ``[-1, 1]``."""
    return _correlation(returns_a, returns_b, params)


def ewma_cov(returns_a: pl.Expr, returns_b: pl.Expr, params: EstimatorParams) -> pl.Expr:
    """Annualized sample EWMA covariance.

    The sample standard deviations come from ``ewm_var(bias=False)``; the
    correlation comes from the population means.  Multiplying the (unitless)
    correlation by the sample standard deviations makes ``ewma_cov`` exactly
    consistent with ``ewma_vol`` and keeps the correlation invariant.
    """
    sd_sample_a = returns_a.ewm_var(bias=False, **_ewm_kwargs(params)).sqrt()
    sd_sample_b = returns_b.ewm_var(bias=False, **_ewm_kwargs(params)).sqrt()
    return (
        _correlation(returns_a, returns_b, params)
        * sd_sample_a
        * sd_sample_b
        * float(params.annualization)
    )


# ── Rolling realized volatility ──────────────────────────────────────────────

def rolling_vol(
    returns: pl.Expr,
    window: int,
    params: EstimatorParams,
) -> pl.Expr:
    """Annualized rolling standard deviation with ``ddof=1``."""
    return returns.rolling_std(
        window_size=window,
        min_samples=params.rolling_min_samples,
        ddof=1,
    ) * math.sqrt(params.annualization)


def overnight_vol(
    open_price: pl.Expr,
    close_price: pl.Expr,
    params: EstimatorParams,
) -> pl.Expr:
    """Annualized rolling volatility of close-to-open gaps."""
    return rolling_vol(
        overnight_returns(open_price, close_price),
        params.overnight_window,
        params,
    )


def intraday_vol(
    open_price: pl.Expr,
    close_price: pl.Expr,
    params: EstimatorParams,
) -> pl.Expr:
    """Annualized rolling volatility of open-to-close moves."""
    return rolling_vol(
        intraday_returns(open_price, close_price),
        params.intraday_window,
        params,
    )


# ── Volatility percentile / floors ──────────────────────────────────────────

def vol_percentile(
    vol: pl.Expr,
    window: int,
    min_history: int,
) -> pl.Expr:
    """Fraction of the trailing window at or below the current vol.

    The window ends at the current row, so the result is past-only.  Fewer than
    ``min_history`` usable observations yields null (the caller maps that to
    ``unknown``); it never fabricates a number from a short history.
    """

    def _percentile(values: pl.Series) -> float | None:
        raw = values.to_list()
        if not raw or raw[-1] is None:
            return None
        current = float(raw[-1])
        if not math.isfinite(current):
            return None
        finite = [float(v) for v in raw if v is not None and math.isfinite(float(v))]
        if len(finite) < min_history:
            return None
        return sum(1 for value in finite if value <= current) / len(finite)

    return vol.rolling_map(_percentile, window_size=window, min_samples=min_history)


def floor_vol(vol: pl.Expr, floor: float) -> pl.Expr:
    """Apply a volatility floor; nulls and non-finite values stay null."""
    return (
        pl.when(vol.is_null())
        .then(pl.lit(None, dtype=pl.Float64))
        .when(vol.is_finite() & (vol < floor))
        .then(pl.lit(floor))
        .when(vol.is_finite())
        .then(vol)
        .otherwise(pl.lit(None, dtype=pl.Float64))
    )


# ── Frame-level helpers ─────────────────────────────────────────────────────

def estimate_pair(
    panel: pl.DataFrame,
    params: EstimatorParams | None = None,
    columns: PairColumns | None = None,
) -> pl.DataFrame:
    """Estimate pair volatilities, correlation and regime inputs.

    ``panel`` is a long frame with ``date`` (``pl.Date``) and the four adjusted
    price columns named by ``columns``.  The frame is sorted stably by date
    before any expression is built and duplicate dates are rejected, so a
    shuffled frame produces exactly the same estimates as the chronological
    one.  The returned frame keeps ``date`` and adds returns, EWMA
    vols/correlation/covariance, rolling vols for every configured window,
    overnight/intraday vols and the past-only vol percentile of leg A.
    """
    cfg = load_config()
    p = params or cfg.estimators
    cols = columns or cfg.columns

    frame = sorted_by_date(panel, cols.date)
    ret_a = price_returns(pl.col(cols.close_a), p)
    ret_b = price_returns(pl.col(cols.close_b), p)

    expressions = [
        ret_a.alias("r_a"),
        ret_b.alias("r_b"),
        ewma_vol(ret_a, p).alias("vol_a"),
        ewma_vol(ret_b, p).alias("vol_b"),
        ewma_corr(ret_a, ret_b, p).alias("corr"),
        ewma_cov(ret_a, ret_b, p).alias("cov"),
        overnight_vol(pl.col(cols.open_a), pl.col(cols.close_a), p).alias(
            "overnight_vol_a"
        ),
        intraday_vol(pl.col(cols.open_a), pl.col(cols.close_a), p).alias(
            "intraday_vol_a"
        ),
        overnight_vol(pl.col(cols.open_b), pl.col(cols.close_b), p).alias(
            "overnight_vol_b"
        ),
        intraday_vol(pl.col(cols.open_b), pl.col(cols.close_b), p).alias(
            "intraday_vol_b"
        ),
    ]
    for window in p.rolling_windows:
        expressions.append(rolling_vol(ret_a, window, p).alias(f"rvol_{window}_a"))
        expressions.append(rolling_vol(ret_b, window, p).alias(f"rvol_{window}_b"))

    frame = frame.with_columns(expressions)
    frame = frame.with_columns(
        vol_percentile(
            pl.col("vol_a"),
            p.percentile_window,
            p.percentile_min_history,
        ).alias("vol_pct_a")
    )
    return frame
