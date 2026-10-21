"""Past-only volatility-percentile regime labels (low / mid / high).

The percentile at ``t`` ranks the vol estimate dated ``t`` against the trailing
``percentile_window`` observations, so no future bar can change a past label.
A history shorter than ``percentile_min_history`` stays ``unknown`` rather than
inventing a number — the guard a short-lived instrument needs.
"""
from __future__ import annotations

import polars as pl

from risk.config import RegimeParams, load_config
from risk.estimators import vol_percentile


def regime_from_percentile(
    percentile: pl.Expr,
    params: RegimeParams | None = None,
) -> pl.Expr:
    """Map a vol percentile to ``low`` / ``mid`` / ``high`` / ``unknown``."""
    p = params or load_config().regimes
    return (
        pl.when(percentile.is_null())
        .then(pl.lit(p.unknown_label))
        .when(percentile < p.low_threshold)
        .then(pl.lit("low"))
        .when(percentile > p.high_threshold)
        .then(pl.lit("high"))
        .otherwise(pl.lit("mid"))
    )


def label_regimes(
    estimates: pl.DataFrame,
    params: RegimeParams | None = None,
    vol_column: str = "vol_a",
) -> pl.DataFrame:
    """Attach ``vol_pct`` and ``regime`` to an estimates frame."""
    p = params or load_config().regimes
    frame = estimates.with_columns(
        vol_percentile(
            pl.col(vol_column),
            p.percentile_window,
            p.percentile_min_history,
        ).alias("vol_pct")
    )
    return frame.with_columns(
        regime_from_percentile(pl.col("vol_pct"), p).alias("regime")
    )
