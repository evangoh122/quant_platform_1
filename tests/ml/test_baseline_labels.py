"""Tests for PIT-safe labelling and purged train/test split.

These tests MUST fail on the old ``shift(-1)`` logic (red phase). They verify:
  1. Exact 30-min gap on the same day → labelled.
  2. 5-min gap → NaN (overlap guard).
  3. Overnight gap → NaN (same-day guard).
  4. Last snapshot per symbol → NaN; symbols never mix.
  5. Purged split: no train row has label_ts > cut.
"""

import numpy as np
import pandas as pd
import pytest

from ml.baseline_labels import forward_labels, purged_split


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_df(rows):
    """Build a minimal DataFrame with symbol, prediction_ts, return_30m."""
    return pd.DataFrame(rows)


# ── forward_labels tests ─────────────────────────────────────────────────────

def test_exact_30min_gap_same_day_labelled():
    """Next snapshot exactly 30 min later on the same day → labelled from it."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("30min"), "return_30m": 0.02},
    ])
    out = forward_labels(df)
    assert out.loc[0, "label"] == 1.0  # 0.02 > 0
    assert out.loc[0, "label_ts"] == base + pd.Timedelta("30min")


def test_5min_gap_is_nan():
    """Next snapshot only 5 min later → NaN (overlap with 30-min window)."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("5min"), "return_30m": 0.02},
    ])
    out = forward_labels(df)
    assert pd.isna(out.loc[0, "label"])
    assert pd.isna(out.loc[0, "label_ts"])


def test_overnight_gap_is_nan():
    """Next snapshot on the next trading day → NaN (different US/Eastern date)."""
    day1 = pd.Timestamp("2026-06-01 15:55:00", tz="US/Eastern")
    day2 = pd.Timestamp("2026-06-02 09:30:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": day1, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": day2, "return_30m": 0.02},
    ])
    out = forward_labels(df)
    assert pd.isna(out.loc[0, "label"])
    assert pd.isna(out.loc[0, "label_ts"])


def test_last_snapshot_is_nan():
    """Last snapshot of a symbol has no next row → NaN."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
    ])
    out = forward_labels(df)
    assert pd.isna(out.loc[0, "label"])


def test_symbols_never_mix():
    """Labels for AAPL never come from MSFT's next snapshot."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "MSFT", "prediction_ts": base + pd.Timedelta("30min"), "return_30m": 0.05},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("60min"), "return_30m": -0.01},
    ])
    out = forward_labels(df)
    # AAPL row 0: next AAPL is at +60min, not +30min → NaN
    assert pd.isna(out.loc[0, "label"])
    # AAPL row 2: last AAPL → NaN
    assert pd.isna(out.loc[2, "label"])
    # MSFT row 1: last MSFT → NaN
    assert pd.isna(out.loc[1, "label"])


def test_negative_return_gives_label_0():
    """Next snapshot's return_30m < 0 → label = 0.0."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("30min"), "return_30m": -0.02},
    ])
    out = forward_labels(df)
    assert out.loc[0, "label"] == 0.0


# ── purged_split tests ───────────────────────────────────────────────────────

def test_purged_split_no_label_leak():
    """A row with prediction_ts <= cut but label_ts > cut must NOT be in train."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    # 5 snapshots, 30 min apart
    times = [base + pd.Timedelta(minutes=30 * i) for i in range(5)]
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": t, "return_30m": 0.01} for t in times
    ])
    lab = forward_labels(df)
    lab = lab[lab.label.notna()].copy()

    # cut at 0.5 quantile of prediction_ts → should be around times[2]
    train, test = purged_split(lab, frac=0.5)

    # No train row may have label_ts > cut
    cut = lab["prediction_ts"].quantile(0.5)
    assert (train["label_ts"] <= cut).all(), (
        f"Train contains row with label_ts > cut={cut}"
    )


def test_purged_split_train_test_disjoint():
    """Train and test index must not overlap."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    times = [base + pd.Timedelta(minutes=30 * i) for i in range(6)]
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": t, "return_30m": 0.01} for t in times
    ])
    lab = forward_labels(df)
    lab = lab[lab.label.notna()].copy()
    train, test = purged_split(lab, frac=0.5)
    assert set(train.index).isdisjoint(set(test.index))


# ── mutation tests (must FAIL on old shift(-1) logic) ────────────────────────

def _forward_labels_plain_shift(df):
    """Buggy version: plain shift(-1) without gap/same-day checks."""
    out = df.copy()
    out["label"] = float("nan")
    out["label_ts"] = pd.NaT
    for sym, grp in out.groupby("symbol", sort=False):
        idx = grp.index
        nxt_ret = grp["return_30m"].shift(-1)
        nxt_ts = grp["prediction_ts"].shift(-1)
        valid = nxt_ret.notna()
        out.loc[idx[valid], "label"] = (nxt_ret[valid] > 0).astype(float)
        out.loc[idx[valid], "label_ts"] = nxt_ts[valid]
    return out


def test_plain_shift_labels_5min_gap():
    """Mutation: plain shift(-1) incorrectly labels a 5-min gap row."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("5min"), "return_30m": 0.02},
    ])
    buggy = _forward_labels_plain_shift(df)
    correct = forward_labels(df)
    # Buggy: labels row 0 (incorrect). Correct: NaN.
    assert not pd.isna(buggy.loc[0, "label"]), "Plain shift should label 5-min gap (buggy)"
    assert pd.isna(correct.loc[0, "label"]), "Correct logic should NOT label 5-min gap"


def _purged_split_on_prediction_ts(lab, frac=0.8):
    """Buggy version: split train on prediction_ts <= cut instead of label_ts."""
    cut = lab["prediction_ts"].quantile(frac)
    train = lab[lab["prediction_ts"] <= cut].copy()
    test = lab[lab["prediction_ts"] > cut].copy()
    return train, test


def test_prediction_ts_split_leaks_label():
    """Mutation: splitting on prediction_ts <= cut leaks labels observed after cut."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    times = [base + pd.Timedelta(minutes=30 * i) for i in range(6)]
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": t, "return_30m": 0.01} for t in times
    ])
    lab = forward_labels(df)
    lab = lab[lab.label.notna()].copy()
    cut = lab["prediction_ts"].quantile(0.5)

    buggy_train, _ = _purged_split_on_prediction_ts(lab, frac=0.5)
    correct_train, _ = purged_split(lab, frac=0.5)

    # Buggy split may include rows with label_ts > cut
    leaked = buggy_train[buggy_train["label_ts"] > cut]
    assert len(leaked) > 0, "Buggy split should include leaked rows (mutation test)"
    # Correct split must NOT
    leaked_correct = correct_train[correct_train["label_ts"] > cut]
    assert len(leaked_correct) == 0, "Correct split must not include leaked rows"

def test_same_day_uses_us_eastern_date_for_utc_input():
    """UTC timestamps (as the warehouse returns them) are compared on the US/Eastern date:
    19:50 ET and 20:20 ET are the same trading date even though the UTC date differs."""
    base = pd.Timestamp("2026-06-01 23:50:00", tz="UTC")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("30min"), "return_30m": -0.02},
    ])
    out = forward_labels(df)
    assert out.loc[0, "label"] == 0.0
