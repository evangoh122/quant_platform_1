"""Market / industry residual mean-reversion signal (QUANT_STRATEGIES.md §1).

Regress each stock's daily return on the market (SPY) and an equal-weight
industry factor over a rolling 60-day window that ends **strictly before** the
current day. The s-score is the cumulative residual over a lookback L, scaled by
the residual volatility:

    R_{i,t} = alpha_i + beta_mkt_i * F_mkt,t + beta_ind_i * F_ind,t + eps_{i,t}
    s_{i,t} = sum_{tau=t-L}^{t} eps_{i,tau} / sigma(eps_i)

Trade mean reversion: long at s <= -2.5, short at s >= +2.5, exit when |s| < 0.5
or after the maximum holding period. The industry factor is the equal-weight
average return of the *other* names in the same repo-taxonomy industry — this is
``config/tickers.yaml`` grouping, **not** GICS/SIC (see QUANT_STRATEGIES.md §1
caveat).

Everything here is pure ``pandas``/``numpy`` so the signal and the no-lookahead
invariant are unit-testable without Spark. The Spark/Databricks read path lives
in the runner (``strategies/results`` / ``strategies/backtest`` consumers).
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from config.tickers import get_tickers_by_group


# ── Industry labels ───────────────────────────────────────────────────────────

def load_industry_map() -> Dict[str, str]:
    """Return ``symbol -> industry`` from ``config/tickers.yaml``.

    The group names in ``tickers.yaml`` are a hand-rolled repo taxonomy, not a
    vendor classification (GICS/SIC). This is documented here and must be
    repeated in any downstream write-up — do not present these labels as GICS.
    """
    groups = get_tickers_by_group()
    mapping: Dict[str, str] = {}
    for industry, symbols in groups.items():
        for sym in symbols:
            mapping.setdefault(sym, industry)
    return mapping


# ── Returns ───────────────────────────────────────────────────────────────────

def compute_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Close-to-close returns from a wide prices frame.

    ``prices``: DataFrame indexed by date with one column per symbol. The first
    return of each symbol is undefined and remains NaN — missing returns must
    stay NaN so that industry factors and regressions never treat absent data as
    a zero return.
    """
    return prices.pct_change(fill_method=None)


def compute_industry_factor(
    returns: pd.DataFrame,
    industry_map: Dict[str, str],
) -> pd.DataFrame:
    """Equal-weight industry return excluding the stock itself.

    ``returns``: wide frame (dates x symbols). ``industry_map`` maps each symbol
    to its industry. For a symbol whose industry has a single member the factor
    is 0.0 (there is no "other" name), so the regression collapses to a market
    regression for that symbol.

    Missing returns (NaN) are excluded from both the sum and the member count
    on each date.  Industry factors are date-specific: only symbols with a valid
    return on a given date contribute to that day's factor.  This means appending
    a symbol that only exists after date ``d`` leaves every industry factor and
    residual before ``d`` unchanged.
    """
    symbols = list(returns.columns)
    ind = pd.Series([industry_map.get(s, "__unknown__") for s in symbols],
                    index=symbols, dtype=object)
    # Date-specific non-NaN member count per industry.
    n_ind = returns.notna().T.groupby(ind, sort=False).sum().T  # dates x industry
    industry_totals = returns.T.groupby(ind, sort=False).sum().T  # NaN excluded by pandas
    # Per-symbol industry size aligned to each date (ind maps symbol -> industry).
    n = n_ind[ind].to_numpy(dtype=float)           # (n_dates, n_symbols)
    total = industry_totals[ind].to_numpy(dtype=float)
    ret = returns.to_numpy(dtype=float)
    denom = np.maximum(n - 1.0, 1.0)
    factor = np.where(n > 1.0, (total - ret) / denom, 0.0)
    # Where all other members are NaN (n <= 1 after excluding self), result is
    # 0.0 (singleton industry).  Where the stock itself is NaN, (total - ret)
    # propagates NaN correctly since ret is NaN.
    return pd.DataFrame(factor, index=returns.index, columns=returns.columns)


# ── Rolling residual + s-score ────────────────────────────────────────────────

def _rolling_lagged_sum(x: np.ndarray, window: int) -> np.ndarray:
    """``s[t] = sum(x[t-window : t])`` — a window ending strictly before ``t``.

    Returns NaN for ``t < window`` (insufficient history). The exclusion of the
    current row is what makes the beta used for day ``t`` independent of day
    ``t``'s own return.
    """
    x = np.asarray(x, dtype=float)
    t = len(x)
    cs = np.concatenate(([0.0], np.nan_to_num(x).cumsum()))
    s = np.full(t, np.nan)
    idx = np.arange(window, t)
    s[idx] = cs[idx] - cs[idx - window]
    return s


def _rolling_residuals_one_symbol(
    y: np.ndarray,
    m: np.ndarray,
    f: np.ndarray,
    window: int,
    min_obs: Optional[int] = None,
) -> Dict[str, np.ndarray]:
    """OLS residual of ``y`` on ``[1, m, f]`` with a lagged rolling window.

    Betas for day ``t`` are estimated on days ``[t-window, t-1]``. Returns
    ``alpha``, ``beta_mkt``, ``beta_ind``, ``residual`` and ``sigma`` arrays.

    Rows where any of ``y``, ``m``, ``f`` is non-finite are excluded from the
    cross-product sums (zeroed) and from the effective observation count.  The
    OLS output is NaN when the number of valid rows in the window is below
    ``min_obs`` (default ``ceil(0.8 * window)``).
    """
    y = np.asarray(y, dtype=float)
    m = np.asarray(m, dtype=float)
    f = np.asarray(f, dtype=float)
    t = len(y)
    if min_obs is None:
        min_obs = int(np.ceil(0.8 * window))

    # Per-row validity mask: all three inputs must be finite.
    valid = np.isfinite(y) & np.isfinite(m) & np.isfinite(f)
    # Zero invalid rows so cross-products use the same set of rows.
    y_z = np.where(valid, y, 0.0)
    m_z = np.where(valid, m, 0.0)
    f_z = np.where(valid, f, 0.0)

    # Rolling (lagged) sums of the design-matrix cross-products on zeroed inputs.
    s1y = _rolling_lagged_sum(y_z, window)
    smy = _rolling_lagged_sum(m_z * y_z, window)
    sfy = _rolling_lagged_sum(f_z * y_z, window)
    s1m = _rolling_lagged_sum(m_z, window)
    s1f = _rolling_lagged_sum(f_z, window)
    smm = _rolling_lagged_sum(m_z * m_z, window)
    sff = _rolling_lagged_sum(f_z * f_z, window)
    smf = _rolling_lagged_sum(m_z * f_z, window)
    # Effective observation count per window (lagged).
    n_valid = _rolling_lagged_sum(valid.astype(float), window)

    alpha = np.full(t, np.nan)
    beta_mkt = np.full(t, np.nan)
    beta_ind = np.full(t, np.nan)
    residual = np.full(t, np.nan)

    for i in range(window, t):
        ni = n_valid[i]
        if ni < min_obs:
            continue  # insufficient valid observations
        g = np.array([
            [ni, s1m[i], s1f[i]],
            [s1m[i], smm[i], smf[i]],
            [s1f[i], smf[i], sff[i]],
        ])
        rhs = np.array([s1y[i], smy[i], sfy[i]])
        try:
            coef = np.linalg.solve(g, rhs)
        except np.linalg.LinAlgError:
            continue  # singular design (e.g. constant industry factor) -> no signal
        alpha[i] = coef[0]
        beta_mkt[i] = coef[1]
        beta_ind[i] = coef[2]
        residual[i] = y[i] - (coef[0] + coef[1] * m[i] + coef[2] * f[i])

    return {"alpha": alpha, "beta_mkt": beta_mkt, "beta_ind": beta_ind,
            "residual": residual}


def _trailing_std(x: np.ndarray, window: int, min_periods: Optional[int] = None) -> np.ndarray:
    """Trailing (inclusive) standard deviation.

    ``min_periods`` defaults to ``window`` (the old behaviour) but callers
    should pass ``min_obs`` so that sigma uses the same gap tolerance as the
    beta regression.
    """
    x = np.asarray(x, dtype=float)
    s = pd.Series(x)
    if min_periods is None:
        min_periods = window
    return s.rolling(window, min_periods=min_periods).std().to_numpy()


def compute_residuals(
    returns: pd.DataFrame,
    market_returns: pd.Series,
    industry_factor: Optional[pd.DataFrame] = None,
    window: int = 60,
    lookback: int = 5,
    min_obs: Optional[int] = None,
) -> Dict[str, pd.DataFrame]:
    """Compute per-symbol rolling residuals and s-scores.

    Args:
        returns: wide frame (dates x symbols) of close-to-close returns.
        market_returns: Series of market (SPY) returns, aligned to ``returns``'s
            index. Must not contain NaN over the estimation window.
        industry_factor: wide frame (dates x symbols) of the equal-weight
            industry return excluding the stock itself. If None, only the market
            is used as the systematic factor.
        window: rolling estimation window (default 60).
        lookback: cumulative-residual window for the s-score (default 5).
        min_obs: minimum valid observations per window; rows with fewer are NaN.
            Default ``ceil(0.8 * window)``.

    Returns a dict of wide frames aligned to ``returns``: ``alpha``,
    ``beta_mkt``, ``beta_ind``, ``residual``, ``sigma`` and ``s_score``.
    """
    market = np.asarray(market_returns.reindex(returns.index).to_numpy(dtype=float))
    if industry_factor is None:
        industry_factor = pd.DataFrame(
            0.0, index=returns.index, columns=returns.columns,
        )
    else:
        industry_factor = industry_factor.reindex(
            index=returns.index, columns=returns.columns,
        )

    symbols = list(returns.columns)
    y_all = returns.to_numpy(dtype=float)
    f_all = industry_factor.to_numpy(dtype=float)

    alpha = pd.DataFrame(np.nan, index=returns.index, columns=symbols)
    beta_mkt = pd.DataFrame(np.nan, index=returns.index, columns=symbols)
    beta_ind = pd.DataFrame(np.nan, index=returns.index, columns=symbols)
    residual = pd.DataFrame(np.nan, index=returns.index, columns=symbols)

    for j, sym in enumerate(symbols):
        res = _rolling_residuals_one_symbol(y_all[:, j], market, f_all[:, j],
                                            window, min_obs=min_obs)
        alpha[sym] = res["alpha"]
        beta_mkt[sym] = res["beta_mkt"]
        beta_ind[sym] = res["beta_ind"]
        residual[sym] = res["residual"]

    if min_obs is None:
        min_obs = int(np.ceil(0.8 * window))
    sigma = residual.apply(lambda c: _trailing_std(c.to_numpy(), window, min_periods=min_obs))
    sigma.index = returns.index
    # s-score = cumulative residual over `lookback` / residual sigma (spec §1).
    s_cum = residual.rolling(lookback, min_periods=lookback).sum()
    s_score = s_cum / sigma

    return {
        "alpha": alpha,
        "beta_mkt": beta_mkt,
        "beta_ind": beta_ind,
        "residual": residual,
        "sigma": sigma,
        "s_score": s_score,
    }


# ── PCA (statistical) factor model ───────────────────────────────────────────

def compute_pca_residuals(
    returns: pd.DataFrame,
    window: int = 60,
    lookback: int = 5,
    n_components: int = 10,
    min_obs: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Causal PCA residual factor model.

    For each date *t*, fit Ledoit-Wolf shrinkage and eigendecomposition on
    rows ``[t-window, t-1]`` only.  Estimate each stock's intercept/loadings
    on the lagged factor scores; apply those frozen quantities to day *t* to
    produce its residual.  No fitting or imputation uses day *t* values.

    Returns a dict of wide frames: ``residual``, ``sigma``, ``s_score``, plus
    inspectable lagged ``loadings`` (long frame: date, symbol, component,
    loading) and factor diagnostics.
    """
    from sklearn.covariance import LedoitWolf

    if not (10 <= n_components <= 15):
        raise ValueError(
            f"n_components must be in [10, 15], got {n_components}"
        )

    if min_obs is None:
        min_obs = int(np.ceil(0.8 * window))

    dates = returns.index
    symbols = list(returns.columns)
    n_dates = len(dates)
    n_sym = len(symbols)

    residual = pd.DataFrame(np.nan, index=dates, columns=symbols)
    # Long-frame loadings: list of (date, symbol, component, loading) rows.
    loading_rows: list[tuple] = []

    for t in range(window, n_dates):
        # Training slice: [t-window, t-1], only symbols eligible/finite.
        train_slice = returns.iloc[t - window:t]
        # Day t values (for applying frozen loadings).
        day_t = returns.iloc[t]

        # Identify symbols with finite returns in the training slice ONLY.
        # Day-t availability must not influence which symbols are fitted.
        valid_mask = train_slice.notna().all(axis=0)
        valid_syms = [s for s in symbols if valid_mask[s]]
        n_valid = len(valid_syms)

        if n_valid < 3:
            continue  # too few symbols for PCA

        train_data = train_slice[valid_syms].to_numpy(dtype=float)
        # Standardize using means/scales from the lagged slice.
        means = np.nanmean(train_data, axis=0)
        scales = np.nanstd(train_data, axis=0, ddof=1)
        scales = np.where(scales > 0, scales, 1.0)
        train_std = (train_data - means) / scales

        # Ledoit-Wolf shrinkage covariance.
        lw = LedoitWolf().fit(train_std)
        cov = lw.covariance_

        # Eigendecomposition.
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        # Sort by descending eigenvalue.
        order = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[order]
        eigenvectors = eigenvectors[:, order]

        # Retain min(n_components, rank, n_valid) components.
        K = min(n_components, n_valid, int(np.sum(eigenvalues > 1e-10)))

        # Orient eigenvectors deterministically: largest-absolute loading positive.
        for k in range(K):
            col = eigenvectors[:, k]
            idx = np.argmax(np.abs(col))
            if col[idx] < 0:
                eigenvectors[:, k] = -col

        V = eigenvectors[:, :K]  # (n_valid, K)

        # Lagged factor scores for training slice.
        F_train = train_std @ V  # (window, K)

        # Estimate each stock's intercept/loadings on lagged factor scores.
        # Using OLS: stock = intercept + F @ loadings + eps
        X_design = np.column_stack([np.ones(window), F_train])  # (window, K+1)
        day_t_sym = returns.iloc[t][valid_syms].to_numpy(dtype=float)
        day_t_std = (day_t_sym - means) / scales

        # For each stock, fit on lagged data and apply to day t.
        # Project day-t standardized returns onto eigenvectors to get factor
        # scores.  NaN day-t returns are zeroed after standardisation so they
        # do not contaminate the projection.
        day_t_std_clean = np.where(np.isfinite(day_t_std), day_t_std, 0.0)
        day_t_factors = day_t_std_clean @ V  # (K,)
        for j, sym in enumerate(valid_syms):
            # A symbol with NaN on day t gets no residual (already NaN).
            if not np.isfinite(day_t_sym[j]):
                # Still record loadings for inspection.
                y_train = train_std[:, j]  # (window,)
                try:
                    coef, _, _, _ = np.linalg.lstsq(X_design, y_train, rcond=None)
                except np.linalg.LinAlgError:
                    continue
                for k in range(K):
                    loading_rows.append((dates[t], sym, k, float(coef[1 + k])))
                continue

            y_train = train_std[:, j]  # (window,)
            try:
                coef, _, _, _ = np.linalg.lstsq(X_design, y_train, rcond=None)
            except np.linalg.LinAlgError:
                continue
            intercept = coef[0]
            loadings_j = coef[1:]  # (K,)
            # Predicted return on day t (using frozen loadings and frozen factor projection).
            predicted = intercept + day_t_factors @ loadings_j if K > 0 else intercept
            residual.iloc[t, j] = day_t_sym[j] - (predicted * scales[j] + means[j])

            # Store loadings for inspection.
            for k in range(K):
                loading_rows.append((dates[t], sym, k, float(loadings_j[k])))

    # Trailing residual volatility and s-score (same as OLS path).
    min_obs_sigma = min_obs if min_obs is not None else int(np.ceil(0.8 * window))
    sigma = residual.apply(
        lambda c: _trailing_std(c.to_numpy(), window, min_periods=min_obs_sigma)
    )
    sigma.index = dates
    s_cum = residual.rolling(lookback, min_periods=lookback).sum()
    s_score = s_cum / sigma

    loadings_df = pd.DataFrame(loading_rows,
                               columns=["date", "symbol", "component", "loading"])

    return {
        "residual": residual,
        "sigma": sigma,
        "s_score": s_score,
        "loadings": loadings_df,
    }


# ── Signal state machine ──────────────────────────────────────────────────────

def generate_signals(
    s_score: pd.DataFrame,
    entry: float = 2.5,
    exit_thresh: float = 0.5,
    max_hold: int = 5,
) -> pd.DataFrame:
    """Translate s-scores into desired daily positions (+1 long / -1 short / 0 flat).

    Entry: long when ``s <= -entry``, short when ``s >= +entry``. Exit: a long is
    closed when ``s > -exit_thresh``, a short when ``s < +exit_thresh``, and any
    position is force-closed after ``max_hold`` consecutive bars.

    The returned frame is the **desired** target position as of each date's
    close. The backtester applies the one-bar execution lag; this module never
    does, so a signal produced on day ``t`` is unambiguous about what it knows.
    """
    s = s_score.to_numpy(dtype=float)
    n_dates, n_sym = s.shape
    out = np.zeros((n_dates, n_sym), dtype=float)
    for j in range(n_sym):
        pos = 0
        held = 0
        for i in range(n_dates):
            v = s[i, j]
            if not np.isfinite(v):
                # No estimate -> keep existing position (do not fabricate a signal).
                if pos != 0:
                    held += 1
                    if held >= max_hold:
                        pos = 0
                        held = 0
                out[i, j] = pos
                continue
            if pos == 0:
                if v <= -entry:
                    pos, held = 1, 0
                elif v >= entry:
                    pos, held = -1, 0
            elif pos > 0:
                held += 1
                if v > -exit_thresh or held >= max_hold:
                    pos, held = 0, 0
            else:  # pos < 0
                held += 1
                if v < exit_thresh or held >= max_hold:
                    pos, held = 0, 0
            out[i, j] = pos
    return pd.DataFrame(out, index=s_score.index, columns=s_score.columns)


# ── Convenience: full signal pipeline ─────────────────────────────────────────

def build_signal(
    prices: pd.DataFrame,
    market_returns: pd.Series,
    industry_map: Dict[str, str],
    window: int = 60,
    lookback: int = 5,
    entry: float = 2.5,
    exit_thresh: float = 0.5,
    max_hold: int = 5,
) -> Dict[str, pd.DataFrame]:
    """End-to-end residual signal from raw prices.

    Returns the same dict as :func:`compute_residuals` plus a ``positions`` wide
    frame of desired daily positions.
    """
    returns = compute_daily_returns(prices)
    ind = compute_industry_factor(returns, industry_map)
    out = compute_residuals(returns, market_returns, ind, window=window,
                            lookback=lookback)
    out["returns"] = returns
    out["positions"] = generate_signals(out["s_score"], entry=entry,
                                        exit_thresh=exit_thresh,
                                        max_hold=max_hold)
    return out
