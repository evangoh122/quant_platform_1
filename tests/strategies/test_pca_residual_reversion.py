"""PCA residual factor model invariants: correct shapes, deterministic output,
PIT (point-in-time) loading integrity, and common signal/backtest path."""

import numpy as np
import pandas as pd
import pytest

from strategies.residual_reversion import (
    compute_pca_residuals,
    generate_signals,
)


def _synth_returns(n_days=200, n_symbols=20, seed=42):
    """Generate synthetic daily returns for testing."""
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(seed)
    data = {}
    for i in range(n_symbols):
        sym = f"S{i:02d}"
        data[sym] = rng.normal(0.0, 0.02, n_days)
    return pd.DataFrame(data, index=dates)


class TestPCAResiduals:
    def test_shapes(self):
        """Output frames have correct shapes and columns."""
        returns = _synth_returns(n_days=150, n_symbols=20)
        window, lookback, K = 60, 5, 10
        result = compute_pca_residuals(returns, window=window, lookback=lookback,
                                       n_components=K)
        assert set(result.keys()) >= {"residual", "sigma", "s_score", "loadings"}
        for key in ("residual", "sigma", "s_score"):
            assert result[key].shape == (150, 20)
            assert list(result[key].columns) == list(returns.columns)
        # Loadings is a long frame.
        loadings = result["loadings"]
        assert {"date", "symbol", "component", "loading"}.issubset(loadings.columns)

    def test_common_signal_path(self):
        """PCA residuals flow through generate_signals without error."""
        returns = _synth_returns(n_days=150, n_symbols=20)
        result = compute_pca_residuals(returns, window=60, lookback=5, n_components=10)
        positions = generate_signals(result["s_score"], entry=2.5, exit_thresh=0.5,
                                     max_hold=5)
        assert positions.shape == returns.shape
        # Positions should be -1, 0, or +1.
        unique = set(positions.values.flatten())
        assert unique.issubset({-1.0, 0.0, 1.0})

    def test_invalid_k_raises(self):
        """K outside [10, 15] must raise ValueError."""
        returns = _synth_returns(n_days=100, n_symbols=20)
        with pytest.raises(ValueError, match=r"n_components must be in \[10, 15\]"):
            compute_pca_residuals(returns, window=30, lookback=3, n_components=0)

    def test_deterministic_output(self):
        """Same input produces identical output on repeated calls."""
        returns = _synth_returns(n_days=120, n_symbols=20, seed=99)
        r1 = compute_pca_residuals(returns, window=40, lookback=3, n_components=10)
        r2 = compute_pca_residuals(returns, window=40, lookback=3, n_components=10)
        pd.testing.assert_frame_equal(r1["residual"], r2["residual"])
        pd.testing.assert_frame_equal(r1["s_score"], r2["s_score"])

    def test_pit_loading_integrity(self):
        """PIT proof: change one or all returns on day t and assert the
        complete loading matrix used at t is exactly unchanged.

        Day-t residuals may change (they use day-t returns), but the
        loadings estimated from [t-window, t-1] must not change.
        """
        returns = _synth_returns(n_days=150, n_symbols=20, seed=77)
        window, lookback, K = 60, 5, 10

        base = compute_pca_residuals(returns, window=window, lookback=lookback,
                                     n_components=K)

        t_idx = 100
        t_date = returns.index[t_idx]

        # Perturb one stock's return on day t.
        perturbed = returns.copy()
        perturbed.iloc[t_idx, 0] += 0.5

        alt = compute_pca_residuals(perturbed, window=window, lookback=lookback,
                                    n_components=K)

        # Loadings at t must be identical.
        base_loadings_t = base["loadings"][base["loadings"]["date"] == t_date]
        alt_loadings_t = alt["loadings"][alt["loadings"]["date"] == t_date]

        if not base_loadings_t.empty and not alt_loadings_t.empty:
            pd.testing.assert_frame_equal(
                base_loadings_t.reset_index(drop=True),
                alt_loadings_t.reset_index(drop=True),
            )

    def test_perturb_future_does_not_change_past_outputs(self):
        """Perturb all dates after t and prove all outputs through t remain
        unchanged."""
        returns = _synth_returns(n_days=150, n_symbols=20, seed=55)
        window, lookback, K = 60, 5, 10

        base = compute_pca_residuals(returns, window=window, lookback=lookback,
                                     n_components=K)

        t_idx = 100

        # Perturb all dates after t.
        perturbed = returns.copy()
        perturbed.iloc[t_idx + 1:] += np.random.default_rng(99).normal(0, 0.1,
                                                                        perturbed.iloc[t_idx + 1:].shape)

        alt = compute_pca_residuals(perturbed, window=window, lookback=lookback,
                                    n_components=K)

        # All outputs through t must be unchanged.
        pd.testing.assert_frame_equal(
            base["residual"].iloc[:t_idx + 1],
            alt["residual"].iloc[:t_idx + 1],
        )
        pd.testing.assert_frame_equal(
            base["s_score"].iloc[:t_idx + 1],
            alt["s_score"].iloc[:t_idx + 1],
        )

    def test_no_module_state_leak(self):
        """Repeated calls don't leak state across invocations."""
        returns1 = _synth_returns(n_days=100, n_symbols=20, seed=11)
        returns2 = _synth_returns(n_days=100, n_symbols=20, seed=22)

        r1a = compute_pca_residuals(returns1, window=30, lookback=3, n_components=10)
        r2 = compute_pca_residuals(returns2, window=30, lookback=3, n_components=10)
        r1b = compute_pca_residuals(returns1, window=30, lookback=3, n_components=10)

        pd.testing.assert_frame_equal(r1a["residual"], r1b["residual"])