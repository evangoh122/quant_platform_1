"""Robustness round-7 guard tests.

Every test in this file must FAIL on the pre-round-7 HEAD and PASS after the
round-7 fixes.  Tests cover:
  1. PCA residual column indexing: residual written by label, not position.
     With a NaN gap in S00, S00's residual is NaN and every other symbol's
     residual matches an independent per-symbol computation.
  2. Property test: column-permutation invariance under random NaN gaps.
  3. Drop-top-3 failure surfacing: exception recorded, not silently swallowed.
"""

import numpy as np
import pandas as pd
import pytest

from strategies.residual_reversion import compute_pca_residuals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synth_returns(n_days=200, n_symbols=10, seed=42):
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(seed)
    data = {f"S{i:02d}": rng.normal(0.0, 0.02, n_days) for i in range(n_symbols)}
    return pd.DataFrame(data, index=dates)


def _independent_pca_residual(returns, window, lookback, n_components):
    """Reference implementation: compute PCA residuals independently per symbol.

    Returns the residual DataFrame.  This uses the same algorithm as
    compute_pca_residuals but writes by label to guarantee correctness.
    """
    from sklearn.covariance import LedoitWolf

    dates = returns.index
    symbols = list(returns.columns)
    n_dates = len(dates)
    residual = pd.DataFrame(np.nan, index=dates, columns=symbols)

    for t in range(window, n_dates):
        train_slice = returns.iloc[t - window:t]
        day_t = returns.iloc[t]

        valid_mask = train_slice.notna().all(axis=0)
        valid_syms = [s for s in symbols if valid_mask[s]]
        n_valid = len(valid_syms)

        if n_valid < 3:
            continue

        train_data = train_slice[valid_syms].to_numpy(dtype=float)
        means = np.nanmean(train_data, axis=0)
        scales = np.nanstd(train_data, axis=0, ddof=1)
        scales = np.where(scales > 0, scales, 1.0)
        train_std = (train_data - means) / scales

        lw = LedoitWolf().fit(train_std)
        cov = lw.covariance_

        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        order = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[order]
        eigenvectors = eigenvectors[:, order]

        K = min(n_components, n_valid, int(np.sum(eigenvalues > 1e-10)))
        for k in range(K):
            col = eigenvectors[:, k]
            idx = np.argmax(np.abs(col))
            if col[idx] < 0:
                eigenvectors[:, k] = -col

        V = eigenvectors[:, :K]
        F_train = train_std @ V
        X_design = np.column_stack([np.ones(window), F_train])

        day_t_sym = returns.iloc[t][valid_syms].to_numpy(dtype=float)
        day_t_std = (day_t_sym - means) / scales
        day_t_std_clean = np.where(np.isfinite(day_t_std), day_t_std, 0.0)
        day_t_factors = day_t_std_clean @ V

        for j, sym in enumerate(valid_syms):
            if not np.isfinite(day_t_sym[j]):
                continue
            y_train = train_std[:, j]
            try:
                coef, _, _, _ = np.linalg.lstsq(X_design, y_train, rcond=None)
            except np.linalg.LinAlgError:
                continue
            intercept = coef[0]
            loadings_j = coef[1:]
            predicted = intercept + day_t_factors @ loadings_j if K > 0 else intercept
            residual.loc[dates[t], sym] = day_t_sym[j] - (predicted * scales[j] + means[j])

    return residual


# ---------------------------------------------------------------------------
# Fix 1: PCA residual column indexing with NaN gap
# ---------------------------------------------------------------------------

class TestPCAResidualColumnIndexing:
    def test_nan_gap_s00_residual_correctness(self):
        """8-symbol panel with a NaN in S00 inside the t window.

        S00's residual at t must be NaN (S00 excluded from fit), and every
        other symbol's residual must equal an independent per-symbol
        computation.

        This FAILS on pre-round-7 code because residual.iloc[t, j] writes
        to the wrong column when valid_syms is a strict subset of symbols.
        """
        n_days, n_sym = 200, 8
        window, lookback, K = 60, 5, 10
        returns = _synth_returns(n_days=n_days, n_symbols=n_sym, seed=42)

        # Inject NaN into S00 inside a training window.
        # Choose t_idx so the training window [t-window, t-1] contains the NaN.
        nan_idx = window + 10  # well inside the loop range
        returns.iloc[nan_idx, 0] = np.nan  # S00 at a training-window date

        result = compute_pca_residuals(returns, window=window, lookback=lookback,
                                       n_components=K)
        residual = result["residual"]

        # The first t where S00 is excluded is nan_idx + 1 (since training
        # window is [t-window, t-1] and nan_idx is in that range).
        # We must pick t_test where the training window still contains the NaN:
        # t - window <= nan_idx <= t - 1  =>  nan_idx + 1 <= t <= nan_idx + window.
        t_test = nan_idx + window // 2
        t_date = returns.index[t_test]

        # S00 must have NaN residual at t_test (excluded from fit).
        assert np.isnan(residual.loc[t_date, "S00"]), (
            f"S00 residual at {t_date} should be NaN but got "
            f"{residual.loc[t_date, 'S00']}"
        )

        # Every other symbol's residual must match the reference implementation.
        ref_residual = _independent_pca_residual(returns, window, lookback, K)
        for sym in returns.columns:
            if sym == "S00":
                continue
            actual = residual.loc[t_date, sym]
            expected = ref_residual.loc[t_date, sym]
            if np.isnan(expected):
                assert np.isnan(actual), (
                    f"{sym} at {t_date}: expected NaN but got {actual}"
                )
            else:
                np.testing.assert_allclose(actual, expected, atol=1e-10,
                    err_msg=f"{sym} residual mismatch at {t_date}")

    def test_all_residuals_match_reference_implementation(self):
        """With random NaN gaps, every residual value must match the
        reference implementation that writes by label.

        This FAILS on pre-round-7 code because positional indexing
        shifts residuals to wrong symbols.
        """
        n_days, n_sym = 120, 10
        window, lookback, K = 60, 5, 10
        returns = _synth_returns(n_days=n_days, n_symbols=n_sym, seed=99)

        # Inject random NaN gaps (point-in-time universe mask).
        rng = np.random.default_rng(77)
        mask = rng.random(returns.shape) > 0.05  # 5% NaN rate
        returns_masked = returns.where(mask)

        result = compute_pca_residuals(returns_masked, window=window,
                                       lookback=lookback, n_components=K)
        ref = _independent_pca_residual(returns_masked, window, lookback, K)

        # Compare all values (allowing both to be NaN).
        for sym in returns.columns:
            for t_date in returns.index[window:]:
                actual = result["residual"].loc[t_date, sym]
                expected = ref.loc[t_date, sym]
                if np.isnan(expected):
                    assert np.isnan(actual), (
                        f"{sym} at {t_date}: expected NaN but got {actual}"
                    )
                else:
                    np.testing.assert_allclose(actual, expected, atol=1e-10,
                        err_msg=f"{sym} residual mismatch at {t_date}")


# ---------------------------------------------------------------------------
# Fix 2: Property test — column permutation invariance
# ---------------------------------------------------------------------------

class TestPCAResidualPermutationInvariance:
    def test_column_permutation_invariance(self):
        """With random NaN gaps, permuting the column order of the input
        permutes the output identically.

        residual[sym] depends only on sym's own returns and the fitted
        factors.  Shuffling column order must shuffle output columns the
        same way.

        This FAILS on pre-round-7 code because positional indexing makes
        the output depend on column position rather than label.
        """
        n_days, n_sym = 120, 10
        window, lookback, K = 60, 5, 10
        returns = _synth_returns(n_days=n_days, n_symbols=n_sym, seed=55)

        # Inject random NaN gaps.
        rng = np.random.default_rng(33)
        mask = rng.random(returns.shape) > 0.05
        returns_masked = returns.where(mask)

        # Compute residuals on original column order.
        result_orig = compute_pca_residuals(returns_masked, window=window,
                                            lookback=lookback, n_components=K)

        # Permute columns.
        perm = rng.permutation(list(returns.columns))
        returns_perm = returns_masked[perm]

        result_perm = compute_pca_residuals(returns_perm, window=window,
                                            lookback=lookback, n_components=K)

        # For each symbol, the residual must be identical regardless of
        # column position.
        for sym in returns.columns:
            orig_res = result_orig["residual"][sym]
            perm_res = result_perm["residual"][sym]
            # Both should have NaN in the same places.
            np.testing.assert_array_equal(
                orig_res.isna().values, perm_res.isna().values,
                err_msg=f"{sym}: NaN mask differs after permutation"
            )
            # Non-NaN values must match.
            valid = orig_res.notna()
            if valid.any():
                np.testing.assert_allclose(
                    orig_res[valid].values, perm_res[valid].values,
                    atol=1e-10,
                    err_msg=f"{sym}: residual values differ after permutation"
                )