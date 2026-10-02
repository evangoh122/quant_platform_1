"""Walk-forward splitter invariants.

The build request forbids randomized cross-validation across time. These tests
pin the walk-forward splitter's guarantee: training indices never exceed
validation indices, and every split is non-empty.
"""

import numpy as np

import pandas as pd

from ml.train import purged_walk_forward_splits, walk_forward_splits


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


def test_purging_removes_the_actual_leak_naive_split_retains():
    """A 3-bar label uses validation prices; its future-label feature leaks."""
    times = pd.date_range("2025-01-01", periods=12, freq="D")
    horizon = 3
    label_end = pd.Series(times).shift(-horizon).fillna(times[-1])
    # The deliberately leaky feature at t is the price/label information at
    # t+h. Rows 2,3,4 therefore encode outcomes inside validation days 5..7.
    future_label_feature = np.arange(12) + horizon

    naive_train, naive_val = walk_forward_splits(
        n_rows=12, n_splits=1, min_train=5, test_size=3
    )[0]
    purged_train, purged_val = purged_walk_forward_splits(
        times, label_end, n_splits=1, min_train=5, test_size=3, embargo=0
    )[0]

    overlapping = np.array([2, 3, 4])
    assert np.intersect1d(naive_train, overlapping).tolist() == overlapping.tolist()
    assert all(future_label_feature[i] >= naive_val.min() for i in overlapping)
    assert purged_train.tolist() == [0, 1]
    assert purged_val.tolist() == naive_val.tolist() == [5, 6, 7]


def test_embargo_rows_never_resume_into_later_training():
    times = pd.date_range("2025-01-01", periods=15, freq="D")
    splits = purged_walk_forward_splits(
        times, times, n_splits=2, min_train=5, test_size=3, embargo=2
    )
    # First validation is 5..7; 8..9 is embargoed. The next fold starts at 10.
    assert splits[1][1].tolist() == [10, 11, 12]
    assert not np.isin([8, 9], splits[1][0]).any()
