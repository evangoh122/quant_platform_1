"""Seeded synthetic two-asset panel for the Phase-1 plumbing experiment.

The generator is intentionally simple and fully deterministic: correlated
GARCH(1,1)-like daily shocks, split into an overnight gap and an intraday move
so that the two volatility definitions genuinely differ.  It is a test fixture,
not a market model, and it proves plumbing rather than alpha.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl

from risk.config import ExperimentParams, GarchParams, load_config


def _garch_path(
    shocks: np.ndarray,
    params: GarchParams,
    annualization: int,
    n_days: int,
) -> np.ndarray:
    """One GARCH variance path driven by standardized ``shocks``."""
    daily_var = params.long_run_vol**2 / annualization
    variance = np.empty(n_days)
    returns = np.empty(n_days)
    variance[0] = daily_var
    returns[0] = math.sqrt(variance[0]) * shocks[0]
    for index in range(1, n_days):
        variance[index] = (
            params.omega
            + params.alpha * returns[index - 1] ** 2
            + params.beta * variance[index - 1]
        )
        returns[index] = math.sqrt(variance[index]) * shocks[index]
    return returns


def synthetic_pair_panel(
    params: ExperimentParams | None = None,
    annualization: int | None = None,
) -> pl.DataFrame:
    """Build ``date, open_a, close_a, open_b, close_b`` from seeded GARCH shocks.

    ``annualization`` defaults to the estimator annualization in the config so
    the generated long-run vol matches the units the estimators report.
    """
    p = params or load_config().experiment
    ann = (
        int(annualization)
        if annualization is not None
        else int(load_config().estimators.annualization)
    )
    rng = np.random.default_rng(p.seed)
    n_days = p.n_days

    z = rng.standard_normal((n_days, 2))
    z[:, 1] = p.rho * z[:, 0] + math.sqrt(1.0 - p.rho**2) * z[:, 1]
    returns_a = _garch_path(z[:, 0], p.garch_a, ann, n_days)
    returns_b = _garch_path(z[:, 1], p.garch_b, ann, n_days)

    gap_noise = rng.standard_normal((n_days, 2)) * p.gap_idio_vol
    gap_a = p.overnight_share * returns_a + gap_noise[:, 0]
    gap_b = p.overnight_share * returns_b + gap_noise[:, 1]

    start = date.fromisoformat(p.start_date)
    dates = [start + timedelta(days=offset) for offset in range(n_days)]

    log_close_a = np.log(100.0) + np.cumsum(returns_a)
    log_close_b = np.log(100.0) + np.cumsum(returns_b)
    log_open_a = np.empty(n_days)
    log_open_b = np.empty(n_days)
    log_open_a[0] = np.log(100.0) + gap_a[0]
    log_open_b[0] = np.log(100.0) + gap_b[0]
    log_open_a[1:] = log_close_a[:-1] + gap_a[1:]
    log_open_b[1:] = log_close_b[:-1] + gap_b[1:]

    return pl.DataFrame(
        {
            "date": pl.Series("date", dates, dtype=pl.Date),
            "open_a": np.exp(log_open_a),
            "close_a": np.exp(log_close_a),
            "open_b": np.exp(log_open_b),
            "close_b": np.exp(log_close_b),
        }
    )
