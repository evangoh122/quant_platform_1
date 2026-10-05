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

from ml.baseline_labels import forward_labels, purged_split, refit_rows


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


# ── F1: midnight-straddle mutation test ──────────────────────────────────────

def test_midnight_straddle_is_nan():
    """Two snapshots 30 min apart straddling midnight US/Eastern → NaN.

    23:45 ET (03:45 UTC) and 00:15 ET (04:15 UTC next day) are exactly 30 min
    apart (within tolerance) but on different US/Eastern calendar dates. The
    same-day check must reject this row.

    This test MUST fail when the same-day check is removed from valid
    (mutation: ``valid = ok_gap & nxt_ret.notna()``).
    """
    # 23:45 ET on 2026-06-01 = 03:45 UTC on 2026-06-02
    ts_a = pd.Timestamp("2026-06-02 03:45:00", tz="UTC")
    # 00:15 ET on 2026-06-02 = 04:15 UTC on 2026-06-02
    ts_b = pd.Timestamp("2026-06-02 04:15:00", tz="UTC")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": ts_a, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": ts_b, "return_30m": 0.02},
    ])
    out = forward_labels(df)
    assert pd.isna(out.loc[0, "label"]), (
        "Midnight-straddle row must be NaN (different US/Eastern dates)"
    )
    assert pd.isna(out.loc[0, "label_ts"]), (
        "Midnight-straddle row must have NaT label_ts"
    )


# ── N3: sort-handling tests ──────────────────────────────────────────────────

def test_forward_labels_handles_shuffled_input():
    """forward_labels must sort by [symbol, prediction_ts] internally and
    produce the same labels regardless of input row order."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    rows = [
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("30min"), "return_30m": 0.02},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("60min"), "return_30m": -0.01},
    ]
    sorted_out = forward_labels(_make_df(rows))

    import random
    shuffled_rows = rows.copy()
    random.Random(42).shuffle(shuffled_rows)
    shuffled_out = forward_labels(_make_df(shuffled_rows))

    # Both should produce the same (symbol, prediction_ts, label) triples
    # regardless of input row order. Sort by [symbol, prediction_ts] to align.
    cols = ["symbol", "prediction_ts", "label"]
    sorted_cmp = sorted_out[cols].sort_values(["symbol", "prediction_ts"]).reset_index(drop=True)
    shuffled_cmp = shuffled_out[cols].sort_values(["symbol", "prediction_ts"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(sorted_cmp, shuffled_cmp)


# ── N2/N4: duplicate prediction_ts and tz-naive input ───────────────────────

def test_duplicate_prediction_ts_earlier_gets_nan():
    """Duplicate prediction_ts for a symbol: gap=0 < tol → earlier row gets NaN,
    later row labels forward correctly. No crash."""
    base = pd.Timestamp("2026-06-01 10:00:00", tz="US/Eastern")
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.02},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("30min"), "return_30m": -0.01},
    ])
    out = forward_labels(df)
    # Row 0 (first duplicate): gap=0 → NaN
    assert pd.isna(out.loc[0, "label"])
    # Row 1 (second duplicate): next is +30min → labelled from row 2
    assert out.loc[1, "label"] == 0.0  # -0.01 <= 0
    # Row 2 (last): NaN
    assert pd.isna(out.loc[2, "label"])


def test_tz_naive_input_treated_as_utc():
    """tz-naive timestamps are treated as UTC by _eastern_date."""
    # 2026-06-01 10:00 naive-as-UTC = 06:00 ET → same day
    base = pd.Timestamp("2026-06-01 10:00:00")  # tz-naive
    df = _make_df([
        {"symbol": "AAPL", "prediction_ts": base, "return_30m": 0.01},
        {"symbol": "AAPL", "prediction_ts": base + pd.Timedelta("30min"), "return_30m": 0.02},
    ])
    out = forward_labels(df)
    # Same UTC day → same ET day → labelled
    assert out.loc[0, "label"] == 1.0


# ── refit_rows tests ────────────────────────────────────────────────────────

def test_refit_rows_staggered_symbols():
    """Staggered-symbol regression test for refit_rows.

    Symbol A's latest snapshot at 10:00, symbol B's at 15:00.  A label on a
    B row is observed at 12:00 (label_ts).  Since scoring_ts.min() = 10:00,
    that 12:00-label row must be EXCLUDED from the refit set.

    This test MUST fail if refit_rows returns all of lab (i.e. uses
    max(scoring_ts) or ignores the cutoff).
    """
    base = pd.Timestamp("2026-06-01 09:00:00", tz="US/Eastern")
    # A: snapshots at 09:00, 09:30, 10:00 (latest)
    # B: snapshots at 09:00, 09:30, 10:00, 10:30, 11:00, 11:30, 12:00, 12:30, 13:00, 13:30, 14:00, 14:30, 15:00 (latest)
    a_times = [base + pd.Timedelta(minutes=30 * i) for i in range(3)]
    b_times = [base + pd.Timedelta(minutes=30 * i) for i in range(16)]
    rows = (
        [{"symbol": "A", "prediction_ts": t, "return_30m": 0.01} for t in a_times]
        + [{"symbol": "B", "prediction_ts": t, "return_30m": 0.02} for t in b_times]
    )
    df = pd.DataFrame(rows)
    lab = forward_labels(df)
    lab = lab[lab.label.notna()].copy()
    assert len(lab) > 0, "fixture must produce labelled rows"

    # scoring rows: each symbol's latest snapshot
    latest = df.sort_values("prediction_ts").groupby("symbol").tail(1)
    scoring_ts = latest["prediction_ts"]

    # earliest scoring snapshot = A's latest = 10:00
    assert scoring_ts.min() == a_times[-1]

    refit = refit_rows(lab, scoring_ts)

    # B has a label at 12:00 (label_ts from the 09:30→10:00 pair is 10:00,
    # but later pairs have label_ts > 10:00).  Verify no refit row has
    # label_ts > scoring_ts.min().
    cutoff = scoring_ts.min()
    assert (refit["label_ts"] <= cutoff).all(), (
        f"refit contains row with label_ts > cutoff={cutoff}"
    )

    # The refit set must be a strict subset of all labelled rows
    assert len(refit) < len(lab), (
        f"refit_rows returned all {len(lab)} labelled rows; "
        "expected fewer (some B rows with label_ts > 10:00 must be excluded)"
    )
