"""Risk-aware target weights for a two-leg pair.

One entry point — :func:`size` — exposes four sizers:

``equal_dollar``
    Half the gross on each leg, hedge ratio 1.
``inverse_vol``
    Leg notionals inversely proportional to their estimated volatility.
``covariance_aware``
    Volatility-ratio hedge with a floored spread variance and a vol/gross cap.
``vol_target``
    The covariance-aware book multiplied by the clipped alpha signal.

The hedge ratio is ``h = clip(vol_a / vol_b)`` (equivalently
``sqrt(var_a / var_b)``) clipped to the configured band.  Spread variance is
``var_a + h^2 * var_b - 2 * h * cov`` floored at ``spread_var_floor``, and the
scale is ``min(target_vol / spread_vol, max_gross / (1 + h))``.

Every non-finite input (null, NaN or infinity) produces a zero weight at the
sizing boundary; a NaN never reaches the backtester.
"""
from __future__ import annotations

import math
from typing import Final

import polars as pl

from risk.config import SizingParams, load_config
from risk.estimators import floor_vol

METHODS: Final[tuple[str, ...]] = (
    "equal_dollar",
    "inverse_vol",
    "covariance_aware",
    "vol_target",
)


# ── Hedge / spread math (scalar and expression forms) ───────────────────────

def hedge_ratio(
    vol_a: float | pl.Expr,
    vol_b: float | pl.Expr,
    params: SizingParams | None = None,
) -> float | pl.Expr:
    """``clip(vol_a / vol_b)`` — ``sqrt(var_a / var_b)`` when vols are annualized."""
    p = params or load_config().sizing
    if isinstance(vol_a, pl.Expr) or isinstance(vol_b, pl.Expr):
        expr_a = vol_a if isinstance(vol_a, pl.Expr) else pl.lit(float(vol_a))
        expr_b = vol_b if isinstance(vol_b, pl.Expr) else pl.lit(float(vol_b))
        return (expr_a / expr_b).clip(
            lower_bound=p.hedge_clip_low,
            upper_bound=p.hedge_clip_high,
        )

    a = float(vol_a)
    b = float(vol_b)
    if not math.isfinite(a) or not math.isfinite(b):
        raw = float("nan")
    elif b <= 0.0:
        raw = math.inf if a > 0.0 else 1.0
    else:
        raw = a / b
    if not math.isfinite(raw):
        return p.hedge_clip_high if a > 0.0 else 1.0
    return float(min(max(raw, p.hedge_clip_low), p.hedge_clip_high))


def _floored_variance_expr(raw: pl.Expr, floor: float) -> pl.Expr:
    """Floor an annualized variance expression, including numerical negatives."""
    return (
        pl.when(raw.is_finite() & (raw > floor))
        .then(raw)
        .otherwise(pl.lit(floor))
    )


def spread_variance(
    vol_a: float,
    vol_b: float,
    corr: float,
    params: SizingParams | None = None,
) -> float:
    """Floored annualized variance of the hedged spread (scalar form)."""
    p = params or load_config().sizing
    h = float(hedge_ratio(vol_a, vol_b, p))
    raw = (
        float(vol_a) ** 2
        + h**2 * float(vol_b) ** 2
        - 2.0 * h * float(corr) * float(vol_a) * float(vol_b)
    )
    if not math.isfinite(raw) or raw < p.spread_var_floor:
        return float(p.spread_var_floor)
    return float(raw)


def spread_volatility(
    vol_a: float,
    vol_b: float,
    corr: float,
    params: SizingParams | None = None,
) -> float:
    """Annualized volatility of the hedged spread (scalar form)."""
    return math.sqrt(spread_variance(vol_a, vol_b, corr, params))


# ── Sizing ───────────────────────────────────────────────────────────────────

def _validity(
    method: str,
    signal: pl.Expr,
    vol_a: pl.Expr,
    vol_b: pl.Expr,
    corr: pl.Expr,
) -> pl.Expr:
    finite_signal = signal.is_finite().fill_null(False)
    if method == "equal_dollar":
        return finite_signal
    finite_vols = vol_a.is_finite().fill_null(False) & vol_b.is_finite().fill_null(False)
    if method == "inverse_vol":
        return finite_signal & finite_vols
    finite_corr = corr.is_finite().fill_null(False)
    return finite_signal & finite_vols & finite_corr


def _safe_weight(expr: pl.Expr, valid: pl.Expr) -> pl.Expr:
    return (
        pl.when(valid & expr.is_finite().fill_null(False))
        .then(expr)
        .otherwise(0.0)
        .fill_nan(0.0)
        .fill_null(0.0)
    )


def size(
    signal_or_pair: pl.DataFrame | None,
    estimates: pl.DataFrame,
    params: SizingParams | None = None,
) -> pl.DataFrame:
    """Return target NAV-fraction weights ``date, w_a, w_b`` for one sizer.

    Args:
        signal_or_pair: long frame ``[date, signal]``.  ``signal`` is the
            direction/magnitude of the long-A/short-B spread.  ``None`` means
            the configured default signal (constant, direction only).
        estimates: long frame ``[date, vol_a, vol_b, corr]`` of annualized
            volatilities and correlation.  Missing estimates yield zero weight.
        params: sizing parameters; ``params.method`` selects the sizer.
    """
    p = params or load_config().sizing
    if p.method not in METHODS:
        raise ValueError(f"unknown sizing method {p.method!r}; expected one of {METHODS}")

    required = {"date", "vol_a", "vol_b", "corr"}
    missing = required.difference(estimates.columns)
    if missing:
        raise KeyError(f"estimates missing columns: {sorted(missing)}")

    est = estimates.select(
        pl.col("date"),
        pl.col("vol_a").cast(pl.Float64),
        pl.col("vol_b").cast(pl.Float64),
        pl.col("corr").cast(pl.Float64),
    )
    if signal_or_pair is None:
        signal_frame = est.select(
            pl.col("date"),
            pl.lit(p.default_signal, dtype=pl.Float64).alias("signal"),
        )
    else:
        if "signal" not in signal_or_pair.columns:
            raise KeyError("signal_or_pair must contain a 'signal' column")
        signal_frame = signal_or_pair.select(
            pl.col("date"),
            pl.col("signal").cast(pl.Float64),
        )

    frame = est.join(signal_frame, on="date", how="left").sort("date")
    frame = frame.with_columns(
        floor_vol(pl.col("vol_a"), p.vol_floor).alias("_vol_a"),
        floor_vol(pl.col("vol_b"), p.vol_floor).alias("_vol_b"),
    )

    signal = pl.col("signal")
    vol_a = pl.col("_vol_a")
    vol_b = pl.col("_vol_b")
    corr = pl.col("corr").clip(lower_bound=-1.0, upper_bound=1.0)
    h = hedge_ratio(vol_a, vol_b, p)
    covariance = corr * vol_a * vol_b
    spread_var = _floored_variance_expr(
        vol_a * vol_a + h * h * vol_b * vol_b - 2.0 * h * covariance,
        p.spread_var_floor,
    )
    spread_vol = spread_var.sqrt()
    scale = pl.min_horizontal(
        pl.lit(p.target_vol) / spread_vol,
        pl.lit(p.max_gross) / (1.0 + h),
    )
    direction = signal.sign()
    alpha = signal.clip(lower_bound=-p.signal_cap, upper_bound=p.signal_cap)
    valid = _validity(p.method, signal, vol_a, vol_b, corr)

    if p.method == "equal_dollar":
        gross = min(p.equal_dollar_gross, p.max_gross)
        weight_a = direction * (gross / 2.0)
        weight_b = direction * (-gross / 2.0)
    elif p.method == "inverse_vol":
        gross = min(p.inverse_vol_gross, p.max_gross)
        raw_a = 1.0 / vol_a
        raw_b = 1.0 / vol_b
        denominator = raw_a + raw_b
        weight_a = direction * gross * raw_a / denominator
        weight_b = direction * (-gross) * raw_b / denominator
    elif p.method == "covariance_aware":
        weight_a = direction * scale
        weight_b = (-direction) * h * scale
    else:  # vol_target
        weight_a = alpha * scale
        weight_b = (-alpha) * h * scale

    return frame.select(
        pl.col("date"),
        _safe_weight(weight_a, valid).alias("w_a"),
        _safe_weight(weight_b, valid).alias("w_b"),
    )
