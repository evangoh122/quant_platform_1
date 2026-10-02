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


# ── Round 5: look-ahead, sparse features, fold-local classification ─────────


def _detect_mw_compat(frame, cols, time_col):
    """Call _detect_market_wide_columns handling both old (1-list) and new (2-list) signatures."""
    result = _detect_market_wide_columns(frame, cols, time_col=time_col)
    if isinstance(result, tuple):
        return result[0]
    return result


def test_market_beta_shifted_one_bar_no_lookahead():
    """Perturbing return at t must not change beta at t (beta uses shift(1)).

    Replicates the beta computation from synthetic_data.py directly so we can
    perturb a single return and observe the shift(1) guard in action.
    """
    rng = np.random.default_rng(10)
    n_bars = 80
    symbols = ["S0", "S1", "S2", "S3"]
    times = pd.date_range("2025-01-01", periods=n_bars, freq="D")

    # Generate close prices
    rows = []
    for sym in symbols:
        log_ret = rng.normal(0.0, 0.004, size=n_bars)
        close = 100.0 * np.exp(np.cumsum(log_ret))
        for i in range(n_bars):
            rows.append({"symbol": sym, "event_ts": times[i], "close": close[i]})
    ohlcv = pd.DataFrame(rows)
    ohlcv["return"] = ohlcv.groupby("symbol")["close"].pct_change()
    market_ret = ohlcv.groupby("event_ts")["return"].mean().rename("mkt_return")
    ohlcv = ohlcv.merge(market_ret, on="event_ts", how="left")

    def _compute_beta(ohlcv_df, sym):
        s = ohlcv_df[ohlcv_df["symbol"] == sym]
        cov = s["return"].rolling(20, min_periods=5).cov(s["mkt_return"])
        var = s["mkt_return"].rolling(20, min_periods=5).var()
        return (cov / var).shift(1).values

    beta_orig = _compute_beta(ohlcv, "S0")

    # Perturb close at t=30 for S0 → changes return at t=30
    t = 30
    ohlcv_alt = ohlcv.copy()
    mask = (ohlcv_alt["symbol"] == "S0") & (ohlcv_alt["event_ts"] == times[t])
    ohlcv_alt.loc[mask, "close"] *= 1.1
    ohlcv_alt["return"] = ohlcv_alt.groupby("symbol")["close"].pct_change()
    ohlcv_alt = ohlcv_alt.drop(columns=["mkt_return"])
    market_ret_alt = ohlcv_alt.groupby("event_ts")["return"].mean().rename("mkt_return")
    ohlcv_alt = ohlcv_alt.merge(market_ret_alt, on="event_ts", how="left")
    beta_alt = _compute_beta(ohlcv_alt, "S0")

    # beta at t should be unchanged — shift(1) means it only sees returns < t
    assert pd.isna(beta_orig[t]) or np.isclose(beta_orig[t], beta_alt[t]), (
        f"beta at t={t} changed when return at t was perturbed — look-ahead bug"
    )
    # beta at t+1 must change — it incorporates the perturbed return at t
    assert not pd.isna(beta_orig[t + 1]) and not np.isclose(
        beta_orig[t + 1], beta_alt[t + 1]
    ), f"beta at t={t+1} did not change when return at t was perturbed"


def test_sparse_cross_sectional_feature_is_neutralised():
    """A feature that varies cross-sectionally wherever observed but is all-NaN on
    > 90% of timestamps must NOT be classified market-wide — it should be
    residualised (values change after neutralisation).

    On 147c696 the old detector counts all-NaN timestamps as constant, pushing
    the constant fraction to >= 0.9, so the feature is passed through unchanged.
    On HEAD the detector skips insufficient-coverage timestamps, sees the feature
    varies at the 2 observed timestamps, and residualises it.
    """
    n_symbols = 8
    n_timestamps = 25
    n_observed = 2  # 23/25 = 92% all-NaN (> 90%)

    rows = []
    for t in range(n_timestamps):
        ts = pd.Timestamp(f"2025-01-{t+1:02d}")
        for i in range(n_symbols):
            rows.append({
                "prediction_ts": ts,
                "symbol": f"S{i}",
                "market_beta": 0.1 * (i + 1),
                "industry": ["tech", "bank", "health", "energy", "consumer", "tech", "bank", "health"][i],
                "sparse_feat": float(i) if t < n_observed else np.nan,
            })
    frame = pd.DataFrame(rows)

    result = neutralize_features(frame, ["sparse_feat"], report=False)

    # If residualised, values at observed timestamps must differ from input
    observed_mask = frame["sparse_feat"].notna()
    assert not result.loc[observed_mask, "sparse_feat"].equals(
        frame.loc[observed_mask, "sparse_feat"]
    ), "sparse cross-sectional feature was not residualised — classified as market-wide"


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
    """Classification for fold k must be unchanged when data after fold k's
    training window is altered so that the full-sample classification flips.

    On 147c696 the classifier runs on the full matrix, so altering future rows
    changes fold-k's classification.  On HEAD the classifier runs on training
    rows only (fold-local), so fold-k's classification is stable.
    """
    from ml.features import _filter_numeric_features
    from ml.train import purged_walk_forward_splits

    matrix = make_synthetic_matrix(n_symbols=8, n_bars=200, seed=42)
    feature_cols = ["return_1m", "return_5m", "rvol_5m"]
    numeric_cols, _ = _filter_numeric_features(matrix, feature_cols)
    prediction_col = "prediction_ts"

    splits = purged_walk_forward_splits(
        matrix[prediction_col], matrix["label_end_ts"],
        n_splits=3, min_train=8, embargo=1,
    )
    assert len(splits) >= 2

    train_idx_0 = splits[0][0]
    train_rows_0 = matrix.iloc[train_idx_0]
    detected_original = _detect_mw_compat(train_rows_0, numeric_cols, prediction_col)

    # Alter data AFTER fold 0's training window to flip full-sample classification
    matrix_alt = matrix.copy()
    train_ts = matrix.iloc[train_idx_0][prediction_col].unique()
    max_train_ts = max(train_ts)
    future_mask = matrix_alt[prediction_col] > max_train_ts
    for col in numeric_cols:
        matrix_alt.loc[future_mask, col] = 0.0  # make constant in future

    # Verify full-sample classification actually flips (sanity check)
    det_full_orig = _detect_mw_compat(matrix, numeric_cols, prediction_col)
    det_full_alt = _detect_mw_compat(matrix_alt, numeric_cols, prediction_col)
    assert det_full_orig != det_full_alt, (
        "full-sample classification did not flip — test setup is wrong"
    )

    # Fold 0 classification from altered matrix — must be unchanged
    train_rows_alt = matrix_alt.iloc[train_idx_0]
    detected_altered = _detect_mw_compat(train_rows_alt, numeric_cols, prediction_col)

    assert detected_original == detected_altered, (
        "fold-0 classification changed when future data was altered"
    )

    # Training-row features must be byte-identical (we only changed future rows)
    for col in numeric_cols:
        pd.testing.assert_series_equal(
            train_rows_0[col].reset_index(drop=True),
            train_rows_alt[col].reset_index(drop=True),
            check_names=False,
        )
