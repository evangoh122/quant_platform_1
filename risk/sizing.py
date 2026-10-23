"""Risk-aware target weights for a two-leg pair.

One entry point — :func:`size` — exposes four sizers:

``equal_dollar``
    Half the gross on each leg, hedge ratio 1.
``inverse_vol``
    Leg notionals inversely proportional to their estimated volatility.
``covariance_aware``
    Volatility-ratio hedge with a floored spread variance and a vol/gross cap.
``vol_target``
    The covariance-aware book multiplied by the clipped alpha signal, with the
    scale divided by ``max(1, |alpha|)`` so gross exposure stays at or below
    ``max_gross`` for any configured ``signal_cap``.

The hedge ratio is ``h = clip(vol_a / vol_b)`` (equivalently
``sqrt(var_a / var_b)``) clipped to the configured band.  Spread variance is
``var_a + h^2 * var_b - 2 * h * cov`` floored at ``spread_var_floor``, and the
scale is ``min(target_vol / spread_vol, max_gross / (1 + h))``.

Estimate contract
-----------------
Every sizer -- including ``equal_dollar``, whose formula uses none of the
estimates -- requires a finite signal *and* a complete, finite raw estimate set
(``vol_a``, ``vol_b``, ``corr``).  A null, NaN or infinite value in any of them
yields exactly ``0.0`` on both legs: a missing or unusable risk estimate never
produces a position.  The check runs on the **raw** estimates, before the
correlation is clipped into ``[-1, 1]``, so an infinite correlation cannot be
laundered into ``+1`` and turned into a maximum-size book.  A NaN never reaches
the backtester as a weight.
"""
from __future__ import annotations

import math
from typing import Final

import polars as pl

from risk.config import SizingParams, load_config
from risk.estimators import floor_vol
from risk.frames import sorted_by_date

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
    signal: pl.Expr,
    vol_a: pl.Expr,
    vol_b: pl.Expr,
    corr: pl.Expr,
) -> pl.Expr:
    """True only when the signal and the whole raw estimate set are finite.

    Method-independent on purpose: every sizer needs a trustworthy estimate
    set, even when its own formula ignores one of the fields (``equal_dollar``
    ignores all three).  Callers pass raw columns, never clipped ones, so a
    non-finite value is rejected instead of being clipped into range.
    """
    finite = signal.is_finite().fill_null(False)
    for expr in (vol_a, vol_b, corr):
        finite = finite & expr.is_finite().fill_null(False)
    return finite


def _safe_weight(expr: pl.Expr, valid: pl.Expr) -> pl.Expr:
    return (
        pl.when(valid & expr.is_finite().fill_null(False))
        .then(expr)
        .otherwise(0.0)
        .fill_nan(0.0)
        .fill_null(0.0)
    )


def _date_column_hint(frame: pl.DataFrame, missing: set[str]) -> str:
    """Explain a missing ``date`` column, naming a custom date column if present."""
    if "date" not in missing:
        return ""
    candidates = [
        name for name, dtype in frame.schema.items() if dtype == pl.Date
    ]
    if not candidates:
        return ""
    found = ", ".join(repr(name) for name in candidates)
    return (
        f"; frames passed to size() require a 'date' column by contract, found "
        f"date column {found} - rename it to 'date' before sizing"
    )


def size(
    signal_or_pair: pl.DataFrame | None,
    estimates: pl.DataFrame,
    params: SizingParams | None = None,
) -> pl.DataFrame:
    """Return target NAV-fraction weights ``date, w_a, w_b`` for one sizer.

    The date column name is fixed by this public contract (``date``), not read
    from the config; a frame whose date column has another name is rejected
    with an error naming that column, so callers rename at this boundary (as
    :func:`risk.compare.compare_sizers` does).

    Args:
        signal_or_pair: long frame ``[date, signal]``.  ``signal`` is the
            direction/magnitude of the long-A/short-B spread.  ``None`` means
            the configured default signal (constant, direction only).
        estimates: long frame ``[date, vol_a, vol_b, corr]`` of annualized
            volatilities and correlation.  A null, NaN or infinite value in any
            of the three yields zero weight for every method (see the module
            docstring's estimate contract).  The frame is sorted stably by
            date and duplicate dates are rejected before any arithmetic.
        params: sizing parameters; ``params.method`` selects the sizer.
    """
    p = params or load_config().sizing
    if p.method not in METHODS:
        raise ValueError(f"unknown sizing method {p.method!r}; expected one of {METHODS}")

    required = {"date", "vol_a", "vol_b", "corr"}
    missing = required.difference(estimates.columns)
    if missing:
        raise KeyError(
            f"estimates missing columns: {sorted(missing)}"
            + _date_column_hint(estimates, missing)
        )

    est = sorted_by_date(
        estimates.select(
            pl.col("date"),
            pl.col("vol_a").cast(pl.Float64),
            pl.col("vol_b").cast(pl.Float64),
            pl.col("corr").cast(pl.Float64),
        ),
        "date",
    )
    if signal_or_pair is None:
        signal_frame = est.select(
            pl.col("date"),
            pl.lit(p.default_signal, dtype=pl.Float64).alias("signal"),
        )
    else:
        missing_signal = {"date", "signal"}.difference(signal_or_pair.columns)
        if missing_signal:
            raise KeyError(
                f"signal_or_pair missing columns: {sorted(missing_signal)}"
                + _date_column_hint(signal_or_pair, missing_signal)
            )
        signal_frame = sorted_by_date(
            signal_or_pair.select(
                pl.col("date"),
                pl.col("signal").cast(pl.Float64),
            ),
            "date",
        )

    frame = est.join(signal_frame, on="date", how="left").sort(
        "date", maintain_order=True
    )
    frame = frame.with_columns(
        floor_vol(pl.col("vol_a"), p.vol_floor).alias("_vol_a"),
        floor_vol(pl.col("vol_b"), p.vol_floor).alias("_vol_b"),
    )

    signal = pl.col("signal")
    vol_a = pl.col("_vol_a")
    vol_b = pl.col("_vol_b")
    raw_corr = pl.col("corr")
    corr = raw_corr.clip(lower_bound=-1.0, upper_bound=1.0)
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
    # The vol-target book is alpha * scale, so the gross cap must apply to the
    # alpha-scaled book, not to the bare scale.  Dividing by max(1, |alpha|)
    # gives |w_a| + |w_b| = (1 + h) * scale * |alpha| / max(1, |alpha|) <=
    # max_gross for every signal_cap, and is a no-op when |alpha| <= 1.
    alpha_scale = scale / pl.max_horizontal(pl.lit(1.0), alpha.abs())
    valid = _validity(signal, pl.col("vol_a"), pl.col("vol_b"), raw_corr)

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
        weight_a = alpha * alpha_scale
        weight_b = (-alpha) * h * alpha_scale

    return frame.select(
        pl.col("date"),
        _safe_weight(weight_a, valid).alias("w_a"),
        _safe_weight(weight_b, valid).alias("w_b"),
    )
