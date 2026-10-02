import numpy as np
import pandas as pd
import pytest

from ml.evaluate import daily_rank_ic, deflated_sharpe_ratio
from ml.features import (
    FEATURE_SETS,
    _detect_market_wide_columns,
    average_uniqueness_weights,
    compute_labels,
    compute_triple_barrier_labels,
    neutralize_features,
)
from ml.synthetic_data import make_synthetic_matrix


def test_triple_barrier_hits_first_path_barrier_and_fixed_label_remains():
    times = pd.date_range("2025-01-01", periods=10, freq="D")
    prices = [100, 100, 100, 100, 102, 98, 98, 98, 98, 98]
    bars = pd.DataFrame({"symbol": "A", "event_ts": times, "close": prices})
    triple = compute_triple_barrier_labels(
        bars, horizon_bars=3, volatility_window=2, profit_target=0.5, stop_loss=0.5
    )
    assert set(triple["label"].unique()) <= {-1.0, 0.0, 1.0}
    assert "label_end_ts" in triple
    fixed = compute_labels(bars, horizon_minutes=3, bar_seconds=60)
    assert set(fixed["label"].unique()) <= {0, 1}


def test_uniqueness_penalises_overlapping_events():
    times = pd.date_range("2025-01-01", periods=4, freq="D")
    events = pd.DataFrame(
        {"symbol": "A", "prediction_ts": times, "label_end_ts": times + pd.Timedelta(days=2)}
    )
    weights = average_uniqueness_weights(events)
    assert (weights > 0).all() and (weights <= 1).all()
    assert weights.iloc[1] < weights.iloc[0]


def test_neutralisation_removes_beta_and_industry_loadings():
    frame = pd.DataFrame(
        {
            "prediction_ts": pd.Timestamp("2025-01-01"),
            "market_beta": [-1.5, -0.5, 0.5, 1.5, -1.0, 1.0],
            "industry": ["tech"] * 3 + ["bank"] * 3,
        }
    )
    frame["feature"] = 3 * frame["market_beta"] + (frame["industry"] == "tech") * 2
    result = neutralize_features(frame, ["feature"], report=False)
    assert np.max(np.abs(result["feature"])) < 1e-10


def test_neutralisation_raises_when_inputs_missing():
    frame = pd.DataFrame(
        {
            "prediction_ts": pd.Timestamp("2025-01-01"),
            "feature": [1.0, 2.0, 3.0],
        }
    )
    with pytest.raises(ValueError, match="neutralisation requires"):
        neutralize_features(frame, ["feature"], report=False)

    frame_beta_only = frame.copy()
    frame_beta_only["market_beta"] = [0.1, 0.2, 0.3]
    with pytest.raises(ValueError, match="neutralisation requires"):
        neutralize_features(frame_beta_only, ["feature"], report=False)


def test_neutralisation_reduces_beta_correlation():
    rng = np.random.default_rng(99)
    n = 50
    beta = rng.normal(0, 1, n)
    industry = np.where(rng.random(n) > 0.5, "tech", "bank")
    feature = 2.5 * beta + rng.normal(0, 0.1, n)
    frame = pd.DataFrame(
        {
            "prediction_ts": pd.Timestamp("2025-01-01"),
            "market_beta": beta,
            "industry": industry,
            "feature": feature,
        }
    )
    corr_before = pd.Series(feature).corr(pd.Series(beta))
    result = neutralize_features(frame, ["feature"], report=False)
    corr_after = result["feature"].corr(result["market_beta"])
    assert abs(corr_after) < abs(corr_before)
    assert abs(corr_after) < 0.15


def test_synthetic_matrix_has_market_beta_and_industry():
    matrix = make_synthetic_matrix(n_symbols=4, n_bars=100, seed=42)
    assert "market_beta" in matrix.columns
    assert "industry" in matrix.columns
    assert matrix["market_beta"].notna().any()
    assert matrix["industry"].nunique() > 1


def test_ablation_uses_triple_barrier_labels():
    m_fixed = make_synthetic_matrix(n_symbols=3, n_bars=100, seed=1, label_method="fixed")
    m_triple = make_synthetic_matrix(n_symbols=3, n_bars=100, seed=1, label_method="triple_barrier")
    assert len(m_triple) > 0
    fixed_labels = set(m_fixed["label"].unique())
    triple_labels = set(m_triple["label"].unique())
    assert fixed_labels <= {0, 1}
    assert triple_labels <= {0, 1}
    assert len(m_triple) != len(m_fixed) or not m_triple["label"].equals(m_fixed["label"])


def test_daily_rank_ic_and_deflated_sharpe_are_reported():
    pred = pd.DataFrame(
        {
            "prediction_ts": list(pd.to_datetime(["2025-01-01"] * 3 + ["2025-01-02"] * 3)),
            "y_prob": [0.1, 0.5, 0.9] * 2,
            "forward_return": [-0.02, 0.0, 0.02] * 2,
        }
    )
    result = daily_rank_ic(pred)
    assert result["daily_rank_ic_mean"] == 1.0
    assert result["daily_rank_ic_n"] == 2.0
    dsr = deflated_sharpe_ratio(np.array([-0.01, 0.02, 0.01, -0.005, 0.03]))
    assert 0.0 <= dsr <= 1.0


def test_deflated_sharpe_decreases_with_more_trials():
    returns = np.array([0.01, -0.005, 0.02, 0.015, -0.01, 0.03, 0.005, -0.002])
    dsr_low = deflated_sharpe_ratio(returns, n_trials=2)
    dsr_high = deflated_sharpe_ratio(returns, n_trials=100)
    assert dsr_high <= dsr_low


def test_underdetermined_cross_section_raises():
    """Symbols <= design columns and all timestamps underdetermined → raise."""
    ts = pd.Timestamp("2025-01-01")
    # 5 industries, so design = beta + 5 dummies = 6 cols. Need > 6 symbols.
    # Only 5 symbols → underdetermined.
    frame = pd.DataFrame(
        {
            "prediction_ts": ts,
            "market_beta": [0.1, 0.2, 0.3, 0.4, 0.5],
            "industry": ["tech", "bank", "health", "energy", "consumer"],
            "feature": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    with pytest.raises(ValueError, match="all.*timestamps were skipped"):
        neutralize_features(frame, ["feature"], report=False)


def test_mixed_underdetermined_cross_section_warns(caplog):
    """Some timestamps OK, some underdetermined → warning with counts."""
    ts1 = pd.Timestamp("2025-01-01")
    ts2 = pd.Timestamp("2025-01-02")
    # ts1: 8 symbols (OK), ts2: 5 symbols (underdetermined with 5 industries)
    rows = []
    for i in range(8):
        rows.append({
            "prediction_ts": ts1,
            "market_beta": 0.1 * (i + 1),
            "industry": ["tech", "bank", "health", "energy", "consumer", "tech", "bank", "health"][i],
            "feature": float(i),
        })
    for i in range(5):
        rows.append({
            "prediction_ts": ts2,
            "market_beta": 0.1 * (i + 1),
            "industry": ["tech", "bank", "health", "energy", "consumer"][i],
            "feature": float(i),
        })
    frame = pd.DataFrame(rows)
    import logging
    with caplog.at_level(logging.WARNING, logger="ml.features"):
        result = neutralize_features(frame, ["feature"], report=False)
    assert "skipped" in caplog.text
    # ts1 should have been neutralised (residuals should differ from input)
    ts1_result = result[result["prediction_ts"] == ts1]
    # The feature should have been residualised for ts1
    assert not ts1_result["feature"].equals(frame[frame["prediction_ts"] == ts1]["feature"])


def test_real_runner_neutralises_timestamps():
    """The real runner path neutralises > 0 timestamps and removes beta correlation."""
    from ml.synthetic_data import make_synthetic_matrix
    from ml.features import neutralize_features

    matrix = make_synthetic_matrix(n_symbols=18, n_bars=100, seed=7)
    feature_cols = ["return_1m", "return_5m", "rvol_5m"]
    result = neutralize_features(matrix, feature_cols, report=False)
    # Check that the function actually ran (not all skipped — would have raised)
    # Verify post-neutralisation |corr(feature, beta)| < 1e-6 on neutralised timestamps
    corrs = []
    for ts_val, idx in result.groupby("prediction_ts").groups.items():
        frame = result.loc[idx]
        beta_vals = pd.to_numeric(frame["market_beta"], errors="coerce")
        if beta_vals.nunique() < 2:
            continue
        for col in feature_cols:
            feat_vals = pd.to_numeric(frame[col], errors="coerce")
            c = feat_vals.corr(beta_vals)
            if np.isfinite(c):
                corrs.append(abs(c))
    assert len(corrs) > 0, "no timestamps were evaluated"
    mean_abs_corr = float(np.mean(corrs))
    assert mean_abs_corr < 1e-6, f"mean |corr| after neutralisation = {mean_abs_corr}"


def test_market_wide_constant_feature_survives_neutralisation(caplog):
    """A cross-sectionally constant feature must pass through unchanged."""
    import logging

    ts1 = pd.Timestamp("2025-01-01")
    ts2 = pd.Timestamp("2025-01-02")
    n = 8
    rows = []
    for ts in [ts1, ts2]:
        for i in range(n):
            rows.append({
                "prediction_ts": ts,
                "symbol": f"S{i}",
                "market_beta": 0.1 * (i + 1),
                "industry": ["tech", "bank", "health", "energy", "consumer", "tech", "bank", "health"][i],
                "varying_feat": float(i) + (0.1 if ts == ts2 else 0.0),
                "constant_feat": 42.0,  # same for all symbols at every timestamp
            })
    frame = pd.DataFrame(rows)
    original_constant = frame["constant_feat"].copy()

    with caplog.at_level(logging.INFO, logger="ml.features"):
        result = neutralize_features(frame, ["varying_feat", "constant_feat"], report=False)

    # constant_feat must survive unchanged (within floating-point tolerance)
    np.testing.assert_allclose(
        result["constant_feat"].to_numpy(),
        original_constant.to_numpy(),
        atol=1e-12,
        err_msg="market-wide constant feature was modified by neutralisation",
    )
    # varying_feat should have been residualised (values should differ)
    assert not result["varying_feat"].equals(frame["varying_feat"])
    # Log should mention the excluded market-wide column
    assert "market-wide" in caplog.text.lower() or "constant_feat" in caplog.text


def test_market_wide_cols_override(caplog):
    """Explicit market_wide_cols override skips those columns from residualisation."""
    import logging

    ts = pd.Timestamp("2025-01-01")
    n = 10
    rng = np.random.default_rng(42)
    frame = pd.DataFrame({
        "prediction_ts": ts,
        "symbol": [f"S{i}" for i in range(n)],
        "market_beta": rng.normal(0, 1, n),
        "industry": ["tech", "bank"] * 5,
        "feat_a": 2.0 * rng.normal(0, 1, n),
        "feat_b": [7.7] * n,  # constant but we'll override detection
    })
    original_b = frame["feat_b"].copy()

    with caplog.at_level(logging.INFO, logger="ml.features"):
        result = neutralize_features(
            frame, ["feat_a", "feat_b"], report=False, market_wide_cols=["feat_b"],
        )

    np.testing.assert_allclose(result["feat_b"].to_numpy(), original_b.to_numpy(), atol=1e-12)
    assert "feat_b" in caplog.text


def test_non_numeric_columns_excluded(caplog):
    """Non-numeric and timestamp columns are excluded from neutralisation."""
    import logging

    ts = pd.Timestamp("2025-01-01")
    n = 8
    frame = pd.DataFrame({
        "prediction_ts": ts,
        "symbol": [f"S{i}" for i in range(n)],
        "market_beta": np.linspace(0.1, 0.8, n),
        "industry": ["tech", "bank"] * 4,
        "numeric_feat": np.arange(n, dtype=float),
        "string_col": ["alpha", "beta"] * 4,
        "ts_col": pd.Timestamp("2025-01-01"),
    })

    with caplog.at_level(logging.INFO, logger="ml.features"):
        result = neutralize_features(
            frame, ["numeric_feat", "string_col", "ts_col"], report=False,
        )
    # Should have excluded non-numeric/timestamp columns
    assert "non-numeric" in caplog.text.lower() or "excluded" in caplog.text.lower()
    # numeric_feat should still be residualised
    assert not result["numeric_feat"].equals(frame["numeric_feat"])


def test_cot_features_nonzero_after_neutralisation():
    """COT (market-wide) features must survive neutralisation with non-zero values."""
    from ml.features import COT_FEATURES

    matrix = make_synthetic_matrix(n_symbols=18, n_bars=200, seed=42)
    cot_numeric = [c for c in COT_FEATURES if c != "cot_regime_label"]
    # Ensure COT features exist and have non-zero values before neutralisation
    for col in cot_numeric:
        assert col in matrix.columns, f"{col} missing from matrix"
        assert matrix[col].abs().sum() > 0, f"{col} is all zeros before neutralisation"

    all_features = FEATURE_SETS["D"]
    result = neutralize_features(matrix, all_features, report=False)

    # After neutralisation, COT market-wide features must still be non-zero
    for col in cot_numeric:
        assert result[col].abs().sum() > 0, (
            f"{col} was zeroed by neutralisation — market-wide feature erased"
        )
        # And must match original (unchanged)
        np.testing.assert_allclose(
            result[col].to_numpy(), matrix[col].to_numpy(), atol=1e-12,
        )


def test_arm_d_differs_from_arm_c_in_cot_columns():
    """Arm D's matrix must differ from arm C's in COT columns after neutralisation."""
    from ml.features import COT_FEATURES

    matrix = make_synthetic_matrix(n_symbols=18, n_bars=200, seed=42)
    cot_numeric = [c for c in COT_FEATURES if c != "cot_regime_label"]

    features_c = FEATURE_SETS["C"]
    features_d = FEATURE_SETS["D"]

    result_c = neutralize_features(matrix, features_c, report=False)
    result_d = neutralize_features(matrix, features_d, report=False)

    for col in cot_numeric:
        # Arm D should have the COT column; arm C should not (or it should be NaN)
        assert col in result_d.columns
        # The COT columns in arm D should be non-zero (market-wide, passed through)
        assert result_d[col].abs().sum() > 0, f"{col} is zero in arm D"


# ── Round 7: look-ahead, sparse features, fold-local classification ─────────


class _PerturbingGenerator:
    """Wrap a ``numpy.random.Generator`` and perturb one symbol's log-return.

    ``make_synthetic_matrix`` draws each symbol's log-returns via
    ``rng.normal(0.0, 0.0004, size=n_bars)`` in symbol order. Adding ``delta``
    to the ``bar_t``-th draw of the ``target_symbol``-th symbol moves exactly
    that symbol's return at ``bar_t`` (``return[t] == exp(log_ret[t]) - 1``)
    without disturbing the rest of the random stream.
    """

    def __init__(self, base, target_symbol_idx, bar_t, delta):
        self._base = base
        self._target = target_symbol_idx
        self._bar_t = bar_t
        self._delta = delta
        self._logret_calls = 0

    def normal(self, loc=0.0, scale=1.0, size=None):
        if scale == 0.0004 and size is not None:
            arr = self._base.normal(loc, scale, size)
            if self._logret_calls == self._target:
                arr = arr.copy()
                arr[self._bar_t] = arr[self._bar_t] + self._delta
            self._logret_calls += 1
            return arr
        return self._base.normal(loc, scale, size)

    def __getattr__(self, name):
        return getattr(self._base, name)


def test_market_beta_shifted_one_bar_no_lookahead(monkeypatch):
    """Changing one symbol's close at bar t must not change market_beta at t.

    market_beta is a trailing rolling beta. The buggy revision includes the
    return at bar t when computing beta at t (no ``.shift(1)``); the fix shifts
    beta by one bar so beta at t only sees bars < t. We build the matrix twice,
    perturbing a single symbol's log-return at bar t the second time, and assert
    beta at t is unchanged while beta at t+1 moves.
    """
    import ml.synthetic_data as sd

    n_symbols = 18
    n_bars = 200
    seed = 42
    target_symbol = 0  # "TKR00"
    bar_t = 50
    delta = 0.05

    matrix_orig = make_synthetic_matrix(n_symbols=n_symbols, n_bars=n_bars, seed=seed)

    def _perturbed_rng(s):
        return _PerturbingGenerator(np.random.default_rng(s), target_symbol, bar_t, delta)

    monkeypatch.setattr(sd, "_rng", _perturbed_rng)
    matrix_pert = make_synthetic_matrix(n_symbols=n_symbols, n_bars=n_bars, seed=seed)

    sym = f"TKR{target_symbol:02d}"
    b_orig = (
        matrix_orig[matrix_orig["symbol"] == sym]
        .sort_values("prediction_ts")["market_beta"]
        .reset_index(drop=True)
    )
    b_pert = (
        matrix_pert[matrix_pert["symbol"] == sym]
        .sort_values("prediction_ts")["market_beta"]
        .reset_index(drop=True)
    )

    assert np.isclose(b_orig.iloc[bar_t], b_pert.iloc[bar_t]), (
        f"market_beta at bar {bar_t} changed when the return at bar {bar_t} was "
        "perturbed — beta is not shifted and leaks the current bar"
    )
    assert not np.isclose(b_orig.iloc[bar_t + 1], b_pert.iloc[bar_t + 1]), (
        f"market_beta at bar {bar_t + 1} did not change when the return at bar "
        f"{bar_t} was perturbed — the perturbation did not propagate"
    )


def test_sparse_cross_sectional_feature_is_neutralised():
    """A feature observed on a small fraction of timestamps (NaN elsewhere) must
    be residualised, not classified market-wide.

    The buggy detector counts all-NaN timestamps as "constant", so a feature
    that varies across symbols wherever it is observed but is NaN on > 90% of
    timestamps was wrongly classed market-wide and passed through unchanged.
    The fix skips timestamps with too few observations, so the feature is
    correctly residualised. A dense, varying control feature guarantees the
    neutralisation loop actually runs (and never trips the cross-section guard).
    """
    n_symbols = 8
    n_timestamps = 25
    n_observed = 2  # 23/25 = 92% all-NaN (> 90%)
    industries = ["tech", "bank", "health", "energy", "consumer", "tech", "bank", "health"]

    rows = []
    for t in range(n_timestamps):
        ts = pd.Timestamp(f"2025-01-{t+1:02d}")
        for i in range(n_symbols):
            beta = 0.1 * (i + 1)
            rows.append({
                "prediction_ts": ts,
                "symbol": f"S{i}",
                "market_beta": beta,
                "industry": industries[i],
                "control_feat": 2.0 * beta + float(i % 3),
                "sparse_feat": (3.0 * beta + float(i % 2)) if t < n_observed else np.nan,
            })
    frame = pd.DataFrame(rows)

    result = neutralize_features(frame, ["control_feat", "sparse_feat"], report=False)

    observed = frame["sparse_feat"].notna()
    orig = frame.loc[observed, "sparse_feat"].to_numpy(dtype=float)
    new = result.loc[observed, "sparse_feat"].to_numpy(dtype=float)
    assert not np.allclose(orig, new), (
        "sparse cross-sectional feature was not residualised — classified as market-wide"
    )


def test_insufficient_coverage_columns_reported():
    """A column with zero qualifying timestamps is reported, not silently skipped."""
    ts1 = pd.Timestamp("2025-01-01")
    n = 8
    rows = []
    for i in range(n):
        rows.append({
            "prediction_ts": ts1,
            "symbol": f"S{i}",
            "all_nan_feat": np.nan,
        })
    frame = pd.DataFrame(rows)

    detected, insufficient = _detect_market_wide_columns(
        frame, ["all_nan_feat"], threshold=0.9, min_non_null=2,
    )
    assert "all_nan_feat" in insufficient
    assert "all_nan_feat" not in detected


def test_fold_local_classification_unchanged_by_future_data():
    """Fold k's training features (and thus its out-of-fold predictions) must not
    change when data after its training window is altered.

    The buggy runner classified market-wide features from the full matrix before
    the walk-forward loop, so changing future rows flipped the classification and
    changed every fold's training features. The fix classifies from each fold's
    training rows only. Here a feature varies across symbols in fold 0's train/val
    windows but is constant in the far future; making the far future vary flips
    the full-sample classification, yet fold 0's predictions must be identical.
    """
    from ml.train import make_baseline, purged_walk_forward_splits, run_ablation

    n_symbols = 8
    n_timestamps = 230
    n_splits = 22
    industries = ["tech", "bank", "health", "energy", "consumer", "tech", "bank", "health"]
    times = pd.date_range("2025-01-01", periods=n_timestamps, freq="h")

    rows = []
    for t, ts in enumerate(times):
        for i in range(n_symbols):
            beta = 0.1 * (i + 1)
            rows.append({
                "symbol": f"S{i}",
                "prediction_ts": ts,
                "label_end_ts": ts,
                "max_information_available_ts": ts,
                "market_beta": beta,
                "industry": industries[i],
                "control_feat": float((i * 13 + t * 7) % 101) / 101.0,
                "forward_return": beta - 0.45,
                "label": int(beta >= 0.45),
            })
    base = pd.DataFrame(rows)

    # Determine fold 0's train/val boundary the same way run_ablation does.
    splits = purged_walk_forward_splits(
        base["prediction_ts"], base["label_end_ts"],
        n_splits=n_splits, min_train=8, embargo=1,
    )
    assert len(splits) >= 1
    _, val_idx = splits[0]
    val_ts = pd.to_datetime(base.loc[val_idx, "prediction_ts"].unique())
    val_start, val_end = val_ts.min(), val_ts.max()
    future_mask = (base["prediction_ts"] > val_end).to_numpy()

    def _flip_feat(df, constant_in_future):
        df = df.copy()
        vals = df["market_beta"].to_numpy(dtype=float).copy()
        if constant_in_future:
            # Constant across symbols in the far future so the full sample is
            # market-wide; train/val rows (which vary) are left untouched.
            vals[future_mask] = 0.0
        df["flip_feat"] = vals
        return df

    matrix = _flip_feat(base, constant_in_future=True)
    matrix_alt = _flip_feat(base, constant_in_future=False)

    kwargs = dict(
        feature_sets={"A": ["control_feat", "flip_feat"]},
        models={"baseline": make_baseline},
        n_splits=n_splits,
        min_train=8,
        seed=42,
    )
    result_orig = run_ablation(matrix, **kwargs)
    result_alt = run_ablation(matrix_alt, **kwargs)

    key = ("A", "baseline")
    p_orig = result_orig["predictions"][key].loc[val_idx, "y_prob"].to_numpy()
    p_alt = result_alt["predictions"][key].loc[val_idx, "y_prob"].to_numpy()
    assert np.allclose(p_orig, p_alt), (
        "fold-0 predictions changed when only future data was altered — "
        "market-wide classification is not fold-local"
    )
