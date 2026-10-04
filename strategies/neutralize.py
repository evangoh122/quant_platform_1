"""Portfolio neutralization helpers: dollar-, sector-, and gross-neutralization.
  - dollar_neutral(weights): scale/shift so sum(weights) ≈ 0
  - sector_neutral(signal, sector): subtract sector mean
  - unit_gross(weights, target_gross): scale so sum(abs(weights)) = target_gross
"""
from typing import Optional

import numpy as np
import pandas as pd

def dollar_neutral(weights: pd.Series) -> pd.Series:
    """Shift/scale so sum(weights) ≈ 0."""
    total = weights.sum()
    n = len(weights)
    adj = total / n if n > 0 else 0.0
    return weights - adj

def sector_neutral(signal: pd.Series, sector: pd.Series) -> pd.Series:
    """Subtract sector mean (per unique sector).
    signal: pd.Series of values
    sector: pd.Series of sector labels
    Returns: signal with sector-wise mean removed.
    """
    return signal - signal.groupby(sector).transform('mean')


def beta_neutral(weights: pd.Series, beta: pd.Series) -> pd.Series:
    """Remove the market-beta exposure of a weight vector.

    Projects ``weights`` onto the subspace orthogonal to ``beta`` so that
    ``sum(weights * beta) == 0`` (to numerical precision). A long-tech /
    short-utilities book is a macro bet, not alpha — this neutralises that.

    ``weights`` and ``beta`` must share an index. Names with NaN beta are
    treated as beta == 1.0 (the fallback market exposure), never dropped.
    """
    b = beta.reindex(weights.index).astype(float).fillna(1.0)
    w = weights.astype(float)
    b2 = float(b.dot(b))
    if b2 == 0.0:
        return w
    wb = float(w.dot(b))
    return w - (wb / b2) * b


def industry_neutral(weights: pd.Series, industry: pd.Series) -> pd.Series:
    """Remove within-industry net exposure: each industry's weights sum to ~0.

    ``industry`` must share ``weights``'s index. This is :func:`sector_neutral`
    applied to a weight vector (same operation, clearer name for book building).
    """
    return sector_neutral(weights, industry)


def neutralize_book(
    weights: pd.Series,
    beta: Optional[pd.Series] = None,
    industry: Optional[pd.Series] = None,
    target_gross: float = 1.0,
    position_cap: Optional[float] = None,
) -> pd.Series:
    """Build a dollar-, beta-, and industry-neutral book from target weights.

    Projects ``weights`` onto the orthogonal complement of the span of
    ``[ones, beta, industry dummies]`` — a single least-squares projection that
    satisfies dollar-, beta- and industry-neutrality *jointly* (sequential
    demeaning cannot: removing industry exposure re-introduces beta). Then clips
    and scales to ``target_gross``. ``beta`` / ``industry`` are optional.
    """
    w = weights.astype(float)
    design_cols = [pd.Series(1.0, index=w.index)]  # intercept -> dollar neutrality
    if beta is not None:
        design_cols.append(beta.reindex(w.index).astype(float).fillna(1.0))
    if industry is not None:
        dummies = pd.get_dummies(industry.reindex(w.index).astype(str), dtype=float)
        for c in dummies.columns:
            design_cols.append(dummies[c].reindex(w.index))
    if len(design_cols) > 1:
        X = pd.concat(design_cols, axis=1).to_numpy(dtype=float)
        coef, *_ = np.linalg.lstsq(X, w.to_numpy(dtype=float), rcond=None)
        w = w - pd.Series(X @ coef, index=w.index)
    if position_cap is not None:
        w = clip(w, -position_cap, position_cap)
    return unit_gross(w, target_gross=target_gross)

def unit_gross(weights: pd.Series, target_gross: float = 1.0) -> pd.Series:
    """Scale weights so sum(abs(weights)) = target_gross."""
    gross = weights.abs().sum()
    scale = target_gross / gross if gross > 0 else 1.0
    return weights * scale

def clip(weights: pd.Series, min_val: float, max_val: float) -> pd.Series:
    """Clip weights to specified min/max per-position cap."""
    return weights.clip(lower=min_val, upper=max_val)

def liquidity_filter(dollar_volume: pd.Series, threshold: float) -> pd.Series:
    """Return boolean index of tradable names by dollar volume."""
    return dollar_volume > threshold
