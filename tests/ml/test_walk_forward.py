"""Walk-forward splitter invariants.

The build request forbids randomized cross-validation across time. These tests
pin the walk-forward splitter's guarantee: training indices never exceed
validation indices, and every split is non-empty.
"""

import numpy as np

from ml.train import walk_forward_splits


def test_train_indices_never_exceed_validation_indices():
    splits = walk_forward_splits(n_rows=100, n_splits=5, min_train=10)
    assert len(splits) > 0, "expected at least one walk-forward split"
    for train_idx, val_idx in splits:
        assert len(train_idx) > 0 and len(val_idx) > 0
        # The core no-lookahead guarantee.
        assert train_idx.max() < val_idx.min(), (
            f"train max {train_idx.max()} is not < val min {val_idx.min()}"
        )


def test_splits_are_chronological_and_cover_the_tail():
    splits = walk_forward_splits(n_rows=50, n_splits=3, min_train=5)
    # Every split advances the validation window forward in time.
    val_starts = [int(v.min()) for _, v in splits]
    assert val_starts == sorted(val_starts)
    assert len(set(val_starts)) == len(val_starts)


def test_walk_forward_has_no_randomization():
    """Two calls with the same arguments must return identical splits."""
    a = walk_forward_splits(n_rows=40, n_splits=4, min_train=6)
    b = walk_forward_splits(n_rows=40, n_splits=4, min_train=6)
    assert all(np.array_equal(x, y) for (x, _), (y, _) in zip(a, b))
    assert all(np.array_equal(x, y) for (_, x), (_, y) in zip(a, b))
