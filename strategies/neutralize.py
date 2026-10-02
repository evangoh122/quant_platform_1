"""Portfolio neutralization helpers: dollar-, sector-, and gross-neutralization.
  - dollar_neutral(weights): scale/shift so sum(weights) ≈ 0
  - sector_neutral(signal, sector): subtract sector mean
  - unit_gross(weights, target_gross): scale so sum(abs(weights)) = target_gross
"""
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
