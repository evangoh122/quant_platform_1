"""Training for the ML ablation lane.

* Walk-forward / time-series split only. There is deliberately **no**
  randomized cross-validation anywhere in this module — randomized k-fold
  across time leaks future information.
* Baseline model: logistic regression. Challenger: XGBoost (lazily imported).
* The ablation runner trains the A/B/C/D feature-set arms identically.

Models are imported lazily so the pure-logic tests can run on a box that has
scikit-learn but not XGBoost.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ml.features import (
    FEATURE_SETS,
    assert_no_lookahead,
    average_uniqueness_weights,
    neutralize_features,
)
from ml import evaluate


# ── Walk-forward split ───────────────────────────────────────────────────────

def walk_forward_splits(
    n_rows: int,
    n_splits: int = 5,
    min_train: int = 8,
    test_size: Optional[int] = None,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Expanding-window walk-forward splits over a time-ordered index.

    Guarantees, for every split:
      * ``max(train_idx) < min(val_idx)`` — training never sees the future;
      * ``len(val_idx) >= 1``.

    Rows are assumed already sorted chronologically (``train.py`` sorts the
    matrix by ``prediction_ts`` before calling this).
    """
    if n_rows <= 0:
        return []
    if test_size is None:
        test_size = max(1, n_rows // (n_splits + 1))

    splits: List[Tuple[np.ndarray, np.ndarray]] = []
    start = min_train
    # Slide the validation window forward; train expands from the beginning.
    while start < n_rows:
        val_end = min(start + test_size, n_rows)
        train_idx = np.arange(0, start)
        val_idx = np.arange(start, val_end)
        if len(train_idx) > 0 and len(val_idx) > 0:
            splits.append((train_idx, val_idx))
        start = val_end
        if len(splits) >= n_splits:
            break
    return splits


def purged_walk_forward_splits(
    label_start: Sequence,
    label_end: Sequence,
    n_splits: int = 5,
    min_train: int = 8,
    test_size: Optional[int] = None,
    embargo: int = 1,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Walk forward over timestamp groups, purging overlapping label windows.

    ``min_train``, ``test_size`` and ``embargo`` are counts of unique timestamp
    groups, not rows. Purging removes a candidate training event when its
    inclusive ``[label_start, label_end]`` intersects the validation interval.
    After each validation block, embargoed timestamps are never admitted to a
    later training fold. The default one-bar embargo protects against immediate
    post-validation dependence while retaining scarce daily observations.
    """
    starts = pd.Series(pd.to_datetime(label_start)).reset_index(drop=True)
    ends = pd.Series(pd.to_datetime(label_end)).reset_index(drop=True)
    if len(starts) != len(ends):
        raise ValueError("label_start and label_end must have equal length")
    if embargo < 0:
        raise ValueError("embargo must be non-negative")
    if len(starts) == 0:
        return []
    unique_times = pd.Index(starts.drop_duplicates().sort_values())
    if test_size is None:
        test_size = max(1, len(unique_times) // (n_splits + 1))
    embargoed_times = set()
    splits = []
    # With an inferred fold size, reserve one full block for initial training;
    # otherwise a legacy ``min_train=8`` would create a nearly empty first
    # daily fold on a multi-year sample.
    cursor = max(min_train, test_size)
    while cursor < len(unique_times) and len(splits) < n_splits:
        val_times = unique_times[cursor : min(cursor + test_size, len(unique_times))]
        if len(val_times) == 0:
            break
        val_start, val_end = val_times[0], val_times[-1]
        val_mask = starts.isin(val_times)
        candidate = (starts < val_start) & ~starts.isin(embargoed_times)
        overlap = (starts <= val_end) & (ends >= val_start)
        train_idx = np.flatnonzero((candidate & ~overlap).to_numpy())
        val_idx = np.flatnonzero(val_mask.to_numpy())
        if len(train_idx) and len(val_idx):
            splits.append((train_idx, val_idx))
        embargo_times = unique_times[
            min(cursor + test_size, len(unique_times)) :
            min(cursor + test_size + embargo, len(unique_times))
        ]
        embargoed_times.update(embargo_times.tolist())
        cursor += test_size + embargo
    return splits


# ── Model factories ──────────────────────────────────────────────────────────

def make_baseline(seed: int = 42):
    """Logistic regression baseline (linear, interpretable)."""
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs", random_state=seed)


def make_challenger(seed: int = 42):
    """XGBoost challenger (nonlinear interactions). Imported lazily."""
    import xgboost as xgb

    return xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=1,
        eval_metric="logloss",
    )


MODEL_FACTORIES: Dict[str, Callable[..., object]] = {
    "baseline": make_baseline,
    "challenger": make_challenger,
}


# Non-numeric feature handling. ``cot_regime_label`` is a categorical string in
# gold_model_features; ``sec_material_event`` is a boolean. Both are encoded to
# numeric before training. One-hot encoding is fit on the feature matrix only
# (never on the label), so it does not leak the target.
CATEGORICAL_FEATURES: Tuple[str, ...] = ("cot_regime_label",)
BOOLEAN_FEATURES: Tuple[str, ...] = ("sec_material_event",)


def prepare_features(matrix: pd.DataFrame, feature_cols: Sequence[str]) -> pd.DataFrame:
    """Encode categorical/boolean features and impute 'no observation yet' NaN.

    Returns a numeric-only matrix aligned to ``matrix``. Remaining NaN values
    (features not yet observed at the row's decision time) are filled with 0.0.
    """
    X = matrix[list(feature_cols)].copy()
    for col in BOOLEAN_FEATURES:
        if col in X.columns:
            X[col] = X[col].fillna(False).astype(float)
    for col in CATEGORICAL_FEATURES:
        if col in X.columns:
            dummies = pd.get_dummies(X[col], prefix=col, dtype=float)
            X = pd.concat([X.drop(columns=col), dummies], axis=1)
    return X.astype(float).fillna(0.0)


def _predict_proba(model, X: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    # XGBoost with `output_margin`-style or regressor fallback.
    p = model.predict(X)
    return np.asarray(p, dtype=float)


# ── Ablation runner ──────────────────────────────────────────────────────────

def run_ablation(
    matrix: pd.DataFrame,
    label_col: str = "label",
    feature_sets: Optional[Dict[str, List[str]]] = None,
    models: Optional[Dict[str, Callable[..., object]]] = None,
    n_splits: int = 5,
    min_train: int = 8,
    seed: int = 42,
    prediction_col: str = "prediction_ts",
    label_end_col: str = "label_end_ts",
    embargo: int = 1,
    use_uniqueness_weights: bool = True,
    neutralize: bool = True,
) -> Dict:
    """Run the A/B/C/D study with purged, embargoed walk-forward validation.

    Returns a dict with:
      * ``comparison`` — DataFrame of per-(arm, model) metrics;
      * ``features_used`` — the exact feature columns each arm trained on;
      * ``predictions`` — out-of-fold predictions per (arm, model).

    The no-lookahead guard runs on the assembled matrix before any training.
    """
    assert_no_lookahead(matrix, prediction_col=prediction_col)

    if feature_sets is None:
        feature_sets = FEATURE_SETS
    if models is None:
        models = {"baseline": make_baseline}

    matrix = matrix.sort_values([prediction_col, "symbol"]).reset_index(drop=True)
    if label_end_col not in matrix:
        raise ValueError(
            f"matrix must include '{label_end_col}' for overlap-safe validation"
        )
    raw_y = matrix[label_col].to_numpy()
    # Triple-barrier labels are {-1, 0, +1}; the current classifiers estimate
    # the probability of an upper-barrier hit, so stop/time outcomes are 0.
    y = (raw_y > 0).astype(int) if np.any(raw_y < 0) else raw_y
    sample_weight = average_uniqueness_weights(
        matrix, start_col=prediction_col, end_col=label_end_col
    ).to_numpy()
    splits = purged_walk_forward_splits(
        matrix[prediction_col], matrix[label_end_col], n_splits=n_splits,
        min_train=min_train, embargo=embargo,
    )
    forward_return = (
        matrix["forward_return"].to_numpy()
        if "forward_return" in matrix.columns
        else None
    )

    comparison_rows: List[Dict] = []
    features_used: Dict[str, List[str]] = {}
    predictions: Dict[Tuple[str, str], pd.DataFrame] = {}

    for arm_name, feature_cols in feature_sets.items():
        missing = [c for c in feature_cols if c not in matrix.columns]
        if missing:
            raise ValueError(f"arm '{arm_name}' missing columns: {missing}")
        arm_matrix = neutralize_features(matrix, feature_cols) if neutralize else matrix
        X = prepare_features(arm_matrix, feature_cols)
        features_used[arm_name] = list(feature_cols)

        for model_name, factory in models.items():
            oof_prob = np.full(len(matrix), np.nan)
            for train_idx, val_idx in splits:
                model = factory(seed)
                fit_kwargs = {}
                if use_uniqueness_weights:
                    fit_kwargs["sample_weight"] = sample_weight[train_idx]
                try:
                    model.fit(X.iloc[train_idx], y[train_idx], **fit_kwargs)
                except TypeError:
                    model.fit(X.iloc[train_idx], y[train_idx])
                oof_prob[val_idx] = _predict_proba(model, X.iloc[val_idx])

            pred_df = matrix[[prediction_col, "symbol"]].copy()
            pred_df["y_true"] = y
            pred_df["y_prob"] = oof_prob
            if forward_return is not None:
                pred_df["forward_return"] = forward_return
            pred_df = pred_df[pred_df["y_prob"].notna()]

            metrics = evaluate.evaluate_predictions(pred_df)
            row = {"arm": arm_name, "model": model_name}
            row.update(metrics)
            comparison_rows.append(row)
            predictions[(arm_name, model_name)] = pred_df

    comparison = pd.DataFrame(comparison_rows)
    return {
        "comparison": comparison,
        "features_used": features_used,
        "predictions": predictions,
        "splits": splits,
        "mean_uniqueness": float(np.nanmean(sample_weight)),
        "split_sample_counts": [
            {"train": len(train), "validation": len(val)} for train, val in splits
        ],
    }
