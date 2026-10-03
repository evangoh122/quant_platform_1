"""Robustness round-6 guard tests.

Every test in this file must FAIL on the pre-round-6 HEAD and PASS after the
round-6 fixes.  Tests cover:
  1. PCA loadings depend only on [t-window, t-1], not day-t availability.
  2. AST-based guard: every imported compute_* from strategies.robustness is
     actually called in run_residual_reversion.py.
  3. PCA component count validated to [10, 15].
"""

import ast
import inspect
import textwrap

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


# ---------------------------------------------------------------------------
# Fix 1: PCA loadings use only [t-window, t-1]
# ---------------------------------------------------------------------------

class TestPCALoadingPIT:
    def test_nan_day_t_does_not_change_loading_shape(self):
        """Setting one day-t return to NaN must leave the loading matrix at t
        IDENTICAL in shape and values for every other symbol.

        This FAILS on pre-round-6 code because day_t.notna() is part of the
        valid_mask, so a NaN on day t removes that symbol from the fit.
        """
        returns = _synth_returns(n_days=150, n_symbols=8, seed=77)
        window, lookback, K = 60, 5, 10

        base = compute_pca_residuals(returns, window=window, lookback=lookback,
                                     n_components=K)

        t_idx = 100
        t_date = returns.index[t_idx]

        # Set one stock's return on day t to NaN.
        perturbed = returns.copy()
        perturbed.iloc[t_idx, 0] = np.nan

        alt = compute_pca_residuals(perturbed, window=window, lookback=lookback,
                                    n_components=K)

        base_lt = base["loadings"][base["loadings"]["date"] == t_date]
        alt_lt = alt["loadings"][alt["loadings"]["date"] == t_date]

        assert base_lt.shape == alt_lt.shape, (
            f"Loading shape changed: {base_lt.shape} vs {alt_lt.shape}"
        )
        merged = base_lt.merge(alt_lt, on=["date", "symbol", "component"],
                               suffixes=("_base", "_alt"))
        np.testing.assert_array_equal(
            merged["loading_base"].values, merged["loading_alt"].values,
        )

    def test_huge_day_t_does_not_change_loadings(self):
        """Setting one day-t return to a huge value must leave loadings at t
        IDENTICAL in shape and values.

        This FAILS on pre-round-6 code only if the huge value triggers a
        different code path; with the fix it is guaranteed because day-t is
        excluded from fitting entirely.
        """
        returns = _synth_returns(n_days=150, n_symbols=8, seed=88)
        window, lookback, K = 60, 5, 10

        base = compute_pca_residuals(returns, window=window, lookback=lookback,
                                     n_components=K)

        t_idx = 100
        t_date = returns.index[t_idx]

        perturbed = returns.copy()
        perturbed.iloc[t_idx, 0] = 999.0

        alt = compute_pca_residuals(perturbed, window=window, lookback=lookback,
                                    n_components=K)

        base_lt = base["loadings"][base["loadings"]["date"] == t_date]
        alt_lt = alt["loadings"][alt["loadings"]["date"] == t_date]

        assert base_lt.shape == alt_lt.shape
        merged = base_lt.merge(alt_lt, on=["date", "symbol", "component"],
                               suffixes=("_base", "_alt"))
        np.testing.assert_array_equal(
            merged["loading_base"].values, merged["loading_alt"].values,
        )


# ---------------------------------------------------------------------------
# Fix 2: AST-based unused-import guard
# ---------------------------------------------------------------------------

class TestUnusedComputeImportGuard:
    """Every name imported from strategies.robustness in run_residual_reversion.py
    must be CALLED somewhere reachable from main or _run_variant."""

    def test_no_unused_robustness_imports(self):
        """Parse run_residual_reversion.py and check that every name imported
        from strategies.robustness is used at least once outside the import
        block itself.

        Mutation: adding an unused ``compute_*`` import MUST fail this test.
        """
        import strategies.run_residual_reversion as mod
        src = inspect.getsource(mod)
        tree = ast.parse(src)

        # Collect names imported from strategies.robustness.
        imported_names: set[str] = set()
        import_lines: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "robustness" in node.module:
                    for alias in node.names:
                        imported_names.add(alias.name)
                    import_lines.append(node.lineno)

        assert imported_names, "No imports from strategies.robustness found"

        # Collect all Name nodes that are NOT part of the import statement.
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                # Handle attribute access like module.func
                n = node
                while isinstance(n, ast.Attribute):
                    n = n.value
                if isinstance(n, ast.Name):
                    used_names.add(n.id)

        unused = imported_names - used_names
        assert not unused, (
            f"Unused imports from strategies.robustness: {sorted(unused)}. "
            f"Either wire them in or remove the dead imports."
        )


# ---------------------------------------------------------------------------
# Fix 3: PCA component count validated to [10, 15]
# ---------------------------------------------------------------------------

class TestPCAComponentValidation:
    def test_n_components_below_10_raises(self):
        """n_components < 10 must raise ValueError."""
        returns = _synth_returns(n_days=100, n_symbols=20, seed=42)
        with pytest.raises(ValueError, match=r"n_components must be in \[10, 15\]"):
            compute_pca_residuals(returns, window=30, lookback=3, n_components=5)

    def test_n_components_above_15_raises(self):
        """n_components > 15 must raise ValueError."""
        returns = _synth_returns(n_days=100, n_symbols=30, seed=42)
        with pytest.raises(ValueError, match=r"n_components must be in \[10, 15\]"):
            compute_pca_residuals(returns, window=30, lookback=3, n_components=20)

    def test_n_components_zero_raises(self):
        """n_components=0 must raise ValueError (not silently produce NaNs)."""
        returns = _synth_returns(n_days=100, n_symbols=20, seed=42)
        with pytest.raises(ValueError, match=r"n_components must be in \[10, 15\]"):
            compute_pca_residuals(returns, window=30, lookback=3, n_components=0)

    def test_n_components_10_succeeds(self):
        """n_components=10 is valid."""
        returns = _synth_returns(n_days=100, n_symbols=20, seed=42)
        result = compute_pca_residuals(returns, window=30, lookback=3,
                                       n_components=10)
        assert result["residual"].shape == (100, 20)

    def test_n_components_15_succeeds(self):
        """n_components=15 is valid."""
        returns = _synth_returns(n_days=100, n_symbols=20, seed=42)
        result = compute_pca_residuals(returns, window=30, lookback=3,
                                       n_components=15)
        assert result["residual"].shape == (100, 20)

    def test_config_validation_rejects_zero(self):
        """validate_residual_config must reject pca_components=0."""
        from strategies.run_residual_reversion import validate_residual_config
        cfg = {
            "residual_reversion": {
                "status": "primary", "bar_freq": "1d",
                "factor_model": "pca", "factor_window": 60,
                "pca_components": 0, "residual_lookback": 5,
                "entry_threshold": 2.5, "exit_threshold": 0.5,
                "max_hold_candidates": [3, 5, 10], "min_obs_fraction": 0.8,
                "universe_size": 300, "target_gross": 1.0,
                "book_capital": 10_000_000, "execution_lag_bars": 1,
            }
        }
        with pytest.raises(ValueError, match=r"pca_components must be in \[10, 15\]"):
            validate_residual_config(cfg)

    def test_config_validation_rejects_20(self):
        """validate_residual_config must reject pca_components=20."""
        from strategies.run_residual_reversion import validate_residual_config
        cfg = {
            "residual_reversion": {
                "status": "primary", "bar_freq": "1d",
                "factor_model": "pca", "factor_window": 60,
                "pca_components": 20, "residual_lookback": 5,
                "entry_threshold": 2.5, "exit_threshold": 0.5,
                "max_hold_candidates": [3, 5, 10], "min_obs_fraction": 0.8,
                "universe_size": 300, "target_gross": 1.0,
                "book_capital": 10_000_000, "execution_lag_bars": 1,
            }
        }
        with pytest.raises(ValueError, match=r"pca_components must be in \[10, 15\]"):
            validate_residual_config(cfg)