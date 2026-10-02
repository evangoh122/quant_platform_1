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

from ml.features import FEATURE_SETS, assert_no_lookahead
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
) -> Dict:
    """Run the A/B/C/D ablation study with walk-forward validation.

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

    matrix = matrix.sort_values([prediction_col]).reset_index(drop=True)
    y = matrix[label_col].to_numpy()
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
        X = prepare_features(matrix, feature_cols)
        features_used[arm_name] = list(feature_cols)

        for model_name, factory in models.items():
            oof_prob = np.full(len(matrix), np.nan)
            for train_idx, val_idx in walk_forward_splits(
                len(matrix), n_splits=n_splits, min_train=min_train
            ):
                model = factory(seed)
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
    }
