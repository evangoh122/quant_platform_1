"""Ablation runner tests.

The critical regression here: a bug that silently trains the *same* feature
columns four times would still produce a clean-looking null result, so we pin
that the runner genuinely varies the feature set between arms A/B/C/D.
"""

import pytest
from pandas import Timedelta

from ml.features import FEATURE_SETS, LookaheadError
from ml.synthetic_data import make_synthetic_matrix
from ml.train import make_baseline, run_ablation


def test_feature_sets_are_strictly_nested():
    assert set(FEATURE_SETS["A"]) < set(FEATURE_SETS["B"])
    assert set(FEATURE_SETS["B"]) < set(FEATURE_SETS["C"])
    assert set(FEATURE_SETS["C"]) < set(FEATURE_SETS["D"])


def test_ablation_runner_varies_feature_set_between_arms():
    matrix = make_synthetic_matrix(n_symbols=4, n_bars=200, seed=7)

    result = run_ablation(
        matrix,
        feature_sets=FEATURE_SETS,
        models={"baseline": make_baseline},
        n_splits=3,
        min_train=40,
        seed=7,
    )

    features_used = result["features_used"]
    assert set(features_used.keys()) == {"A", "B", "C", "D"}

    # The whole point: no two arms may train on identical columns.
    for arm, cols in features_used.items():
        assert len(cols) == len(FEATURE_SETS[arm]), f"arm {arm} dropped columns"

    assert features_used["A"] != features_used["B"]
    assert features_used["B"] != features_used["C"]
    assert features_used["C"] != features_used["D"]
    assert len(features_used["D"]) > len(features_used["A"])

    # All four arms produced a metrics row.
    assert set(result["comparison"]["arm"]) == {"A", "B", "C", "D"}


def test_ablation_runner_rejects_leaky_matrix():
    matrix = make_synthetic_matrix(n_symbols=2, n_bars=80, seed=3)
    # Inject a leak into the assembled matrix's availability timestamp.
    matrix.loc[matrix.index[-1], "max_information_available_ts"] = (
        matrix.loc[matrix.index[-1], "prediction_ts"] + Timedelta(minutes=30)
    )
    with pytest.raises(LookaheadError):
        run_ablation(matrix, models={"baseline": make_baseline}, n_splits=2, min_train=20)
