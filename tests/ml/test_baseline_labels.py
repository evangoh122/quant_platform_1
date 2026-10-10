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
from datetime import date

from ml.baseline_labels import daily_close_labels, forward_labels, purged_split, refit_rows


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


# ── daily_close_labels tests ────────────────────────────────────────────────

def _make_closes(rows):
    """Build a closes DataFrame with symbol, trade_date, close, close_ts."""
    return pd.DataFrame(rows)


# ── D1: snapshot after D's close → labelled from D→N ────────────────────────

def test_daily_snapshot_after_close_labels_from_d_to_n():
    """Feature row with prediction_ts after close_ts of trade_date D
    → labelled from D → next trade_date N."""
    # Fri 2026-06-05 close at 20:00 UTC, Mon 2026-06-08 close at 20:00 UTC
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 102.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
    ])
    # prediction_ts after Friday's close → D = Fri, N = Mon
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    assert out.loc[0, "label"] == 1.0  # 102 > 100
    assert out.loc[0, "label_ts"] == pd.Timestamp("2026-06-08 20:00", tz="UTC")


# ── D2: snapshot BEFORE D's close (same date) → uses previous trading day ──

def test_daily_snapshot_before_close_uses_previous_day():
    """Feature row with prediction_ts before close_ts of the same date
    → D is the PREVIOUS trading day, not the current one."""
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 4),
         "close": 99.0, "close_ts": pd.Timestamp("2026-06-04 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 102.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
    ])
    # prediction_ts on Friday 10:00 ET (14:00 UTC) → before Friday's close
    # → D = Thu, N = Fri → label from Thu→Fri
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 14:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    assert out.loc[0, "label"] == 1.0  # Fri 100 > Thu 99
    assert out.loc[0, "label_ts"] == pd.Timestamp("2026-06-05 20:00", tz="UTC")


# ── D3: weekend gap, gap > max_gap_days, last trading date, symbol isolation ──

def test_daily_friday_snapshot_labels_friday_to_monday():
    """Friday snapshot → labelled from Fri → Mon (gap=3 calendar days, OK)."""
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 103.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    assert out.loc[0, "label"] == 1.0  # 103 > 100
    assert out.loc[0, "label_ts"] == pd.Timestamp("2026-06-08 20:00", tz="UTC")


def test_daily_gap_exceeds_max_gap_days_is_nan():
    """N - D > max_gap_days calendar days → NaN label."""
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        # 10 calendar days later → exceeds max_gap_days=5
        {"symbol": "AAPL", "trade_date": date(2026, 6, 15),
         "close": 105.0, "close_ts": pd.Timestamp("2026-06-15 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes, max_gap_days=5)
    assert pd.isna(out.loc[0, "label"])
    assert pd.isna(out.loc[0, "label_ts"])


def test_daily_last_trading_date_is_nan():
    """Last trade_date for a symbol → no N → NaN label."""
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    assert pd.isna(out.loc[0, "label"])


def test_daily_symbols_never_mix():
    """AAPL's label never comes from MSFT's closes."""
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "MSFT", "trade_date": date(2026, 6, 5),
         "close": 200.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 102.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
        {"symbol": "MSFT", "trade_date": date(2026, 6, 8),
         "close": 205.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
        {"symbol": "MSFT", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    # AAPL: 102 > 100 → label 1.0
    assert out.loc[0, "label"] == 1.0
    # MSFT: 205 > 200 → label 1.0
    assert out.loc[1, "label"] == 1.0
    # label_ts should be each symbol's own next close
    assert out.loc[0, "label_ts"] == pd.Timestamp("2026-06-08 20:00", tz="UTC")
    assert out.loc[1, "label_ts"] == pd.Timestamp("2026-06-08 20:00", tz="UTC")


def test_daily_no_eligible_close_is_nan():
    """prediction_ts before all closes → no D → NaN."""
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 10:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    assert pd.isna(out.loc[0, "label"])


def test_daily_empty_closes_returns_nan():
    """Empty closes DataFrame → all labels NaN."""
    closes = _make_closes([])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    assert pd.isna(out.loc[0, "label"])


# ── D4: look-ahead guard ────────────────────────────────────────────────────

def test_daily_close_after_prediction_ts_never_used_as_d():
    """A close with close_ts > prediction_ts must not be used as D.

    If prediction_ts is on Fri 10:00 ET (14:00 UTC), D should be Thu
    (the previous trading day), NOT Fri (whose close_ts is 20:00 UTC,
    which is after prediction_ts).
    """
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 4),
         "close": 99.0, "close_ts": pd.Timestamp("2026-06-04 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 102.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 14:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    # D = Thu (close_ts 20:00 UTC <= 14:00? NO — 20:00 > 14:00!)
    # Wait: Thu close_ts = 2026-06-04 20:00 UTC. prediction_ts = 2026-06-05 14:00 UTC.
    # 2026-06-04 20:00 <= 2026-06-05 14:00 → YES, Thu is eligible.
    # Fri close_ts = 2026-06-05 20:00 UTC > 2026-06-05 14:00 → NOT eligible.
    # So D = Thu, N = Fri. label = 1.0 (100 > 99), label_ts = Fri close_ts.
    assert out.loc[0, "label"] == 1.0
    assert out.loc[0, "label_ts"] == pd.Timestamp("2026-06-05 20:00", tz="UTC")


# ── D5: integration — daily_close_labels → purged_split → refit_rows ────────

def test_daily_purged_split_refit_no_lookahead():
    """3-symbol staggered fixture: no train or refit row has label_ts > cutoff.

    This is the integration test that ensures the full pipeline (labelling,
    purged split, refit) produces no look-ahead leakage.
    """
    from datetime import date as dt_date

    # Closes: 3 symbols, staggered last trading dates
    # A: Jun 1-5 (1 week), B: Jun 1-12 (2 weeks), C: Jun 1-19 (3 weeks)
    closes = _make_closes([
        # A
        {"symbol": "A", "trade_date": dt_date(2026, 6, 1), "close": 10.0, "close_ts": pd.Timestamp("2026-06-01 20:00", tz="UTC")},
        {"symbol": "A", "trade_date": dt_date(2026, 6, 2), "close": 10.1, "close_ts": pd.Timestamp("2026-06-02 20:00", tz="UTC")},
        {"symbol": "A", "trade_date": dt_date(2026, 6, 3), "close": 10.2, "close_ts": pd.Timestamp("2026-06-03 20:00", tz="UTC")},
        {"symbol": "A", "trade_date": dt_date(2026, 6, 4), "close": 10.3, "close_ts": pd.Timestamp("2026-06-04 20:00", tz="UTC")},
        {"symbol": "A", "trade_date": dt_date(2026, 6, 5), "close": 10.4, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        # B
        {"symbol": "B", "trade_date": dt_date(2026, 6, 1), "close": 20.0, "close_ts": pd.Timestamp("2026-06-01 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 2), "close": 20.1, "close_ts": pd.Timestamp("2026-06-02 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 3), "close": 20.2, "close_ts": pd.Timestamp("2026-06-03 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 4), "close": 20.3, "close_ts": pd.Timestamp("2026-06-04 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 5), "close": 20.4, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 8), "close": 20.5, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 9), "close": 20.6, "close_ts": pd.Timestamp("2026-06-09 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 10), "close": 20.7, "close_ts": pd.Timestamp("2026-06-10 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 11), "close": 20.8, "close_ts": pd.Timestamp("2026-06-11 20:00", tz="UTC")},
        {"symbol": "B", "trade_date": dt_date(2026, 6, 12), "close": 20.9, "close_ts": pd.Timestamp("2026-06-12 20:00", tz="UTC")},
        # C
        {"symbol": "C", "trade_date": dt_date(2026, 6, 1), "close": 30.0, "close_ts": pd.Timestamp("2026-06-01 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 2), "close": 30.1, "close_ts": pd.Timestamp("2026-06-02 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 3), "close": 30.2, "close_ts": pd.Timestamp("2026-06-03 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 4), "close": 30.3, "close_ts": pd.Timestamp("2026-06-04 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 5), "close": 30.4, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 8), "close": 30.5, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 9), "close": 30.6, "close_ts": pd.Timestamp("2026-06-09 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 10), "close": 30.7, "close_ts": pd.Timestamp("2026-06-10 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 11), "close": 30.8, "close_ts": pd.Timestamp("2026-06-11 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 12), "close": 30.9, "close_ts": pd.Timestamp("2026-06-12 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 15), "close": 31.0, "close_ts": pd.Timestamp("2026-06-15 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 16), "close": 31.1, "close_ts": pd.Timestamp("2026-06-16 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 17), "close": 31.2, "close_ts": pd.Timestamp("2026-06-17 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 18), "close": 31.3, "close_ts": pd.Timestamp("2026-06-18 20:00", tz="UTC")},
        {"symbol": "C", "trade_date": dt_date(2026, 6, 19), "close": 31.4, "close_ts": pd.Timestamp("2026-06-19 20:00", tz="UTC")},
    ])

    # Features: one row per symbol per day (after market close)
    features = pd.DataFrame([
        {"symbol": sym, "prediction_ts": pd.Timestamp(f"2026-06-{d:02d} 21:00", tz="UTC")}
        for sym in ["A", "B", "C"]
        for d in [1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19]
    ])

    lab = daily_close_labels(features, closes)
    lab = lab[lab.label.notna()].copy()
    assert len(lab) > 0, "fixture must produce labelled rows"

    # Purged split
    train, test = purged_split(lab, frac=0.8)
    cut = lab["prediction_ts"].quantile(0.8)
    assert (train["label_ts"] <= cut).all(), (
        f"train contains row with label_ts > cut={cut}"
    )

    # Refit rows
    latest = features.sort_values("prediction_ts").groupby("symbol").tail(1)
    refit = refit_rows(lab, latest["prediction_ts"])
    cutoff = latest["prediction_ts"].min()
    assert (refit["label_ts"] <= cutoff).all(), (
        f"refit contains row with label_ts > cutoff={cutoff}"
    )


# ── R6: merge_asof exact-match boundary ──────────────────────────────────────

def test_merge_asof_exact_match_close_ts_eq_prediction_ts():
    """close_ts == prediction_ts must be entry D (exact match boundary).

    merge_asof with direction='backward' includes exact matches by default.
    Mutation: allow_exact_matches=False must fail this test (label becomes NaN).
    """
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 102.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
    ])
    # prediction_ts == close_ts of Jun 5 (exact match)
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    # D = Jun 5 (exact match), N = Jun 8, label = 1.0 (102 > 100)
    assert not pd.isna(out.loc[0, "label"]), (
        "label must NOT be NaN — exact match close_ts==prediction_ts must be D"
    )
    assert out.loc[0, "label"] == 1.0
    assert out.loc[0, "label_ts"] == pd.Timestamp("2026-06-08 20:00", tz="UTC")


# ── D6: named mutation tests ────────────────────────────────────────────────

def test_mutation_lookahead_guard_trade_date_vs_close_ts():
    """Mutation: replace close_ts <= prediction_ts with
    trade_date <= prediction_ts.date() (same-day look-ahead).

    With the buggy predicate, a feature row at 10:00 ET on 2026-06-05
    would match D = 2026-06-05 (trade_date <= 2026-06-05), even though
    close_ts = 20:00 UTC is AFTER prediction_ts = 14:00 UTC.  This is
    a look-ahead violation.

    This test MUST FAIL when the predicate is mutated.
    """
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 4),
         "close": 99.0, "close_ts": pd.Timestamp("2026-06-04 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 102.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 14:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    # Correct: D = Thu (Jun 4), N = Fri (Jun 5), label = 1.0
    # Buggy (trade_date predicate): D = Fri (Jun 5), N = Mon (Jun 8), label = 1.0
    # Both give 1.0 here, but label_ts differs:
    # Correct: label_ts = Fri close_ts (2026-06-05 20:00 UTC)
    # Buggy:   label_ts = Mon close_ts (2026-06-08 20:00 UTC)
    assert out.loc[0, "label_ts"] == pd.Timestamp("2026-06-05 20:00", tz="UTC"), (
        "label_ts should be Fri close_ts, not Mon close_ts (look-ahead guard)"
    )


def test_mutation_drop_max_gap_check():
    """Mutation: drop the max_gap_days check.

    With gap > max_gap_days, the row should be NaN.  If the check is
    dropped, it gets a label instead.

    This test MUST FAIL when the gap check is removed.
    """
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        # 10 calendar days later
        {"symbol": "AAPL", "trade_date": date(2026, 6, 15),
         "close": 105.0, "close_ts": pd.Timestamp("2026-06-15 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes, max_gap_days=5)
    assert pd.isna(out.loc[0, "label"]), (
        "label must be NaN when gap=10 > max_gap_days=5"
    )


def test_mutation_label_from_n_plus_1():
    """Mutation: label from N+1 instead of N.

    With 3 trading days, using N+1 would give a different label_ts
    (and possibly a different label direction).

    This test MUST FAIL when the code labels from N+1 instead of N.
    """
    closes = _make_closes([
        {"symbol": "AAPL", "trade_date": date(2026, 6, 5),
         "close": 100.0, "close_ts": pd.Timestamp("2026-06-05 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 8),
         "close": 98.0, "close_ts": pd.Timestamp("2026-06-08 20:00", tz="UTC")},
        {"symbol": "AAPL", "trade_date": date(2026, 6, 9),
         "close": 105.0, "close_ts": pd.Timestamp("2026-06-09 20:00", tz="UTC")},
    ])
    features = pd.DataFrame([
        {"symbol": "AAPL", "prediction_ts": pd.Timestamp("2026-06-05 21:00", tz="UTC")},
    ])
    out = daily_close_labels(features, closes)
    # Correct: N = Mon (Jun 8), close=98 < 100 → label = 0.0
    # Buggy (N+1): N+1 = Tue (Jun 9), close=105 > 100 → label = 1.0
    assert out.loc[0, "label"] == 0.0, (
        "label should be 0.0 (N=Mon close 98 < Fri close 100), "
        "not 1.0 (N+1=Tue close 105)"
    )


# ── D7: Fix4 differential test — old 816e54b behavior preserved ──────────────

def _old_daily_close_labels(features, closes, max_gap_days=5):
    """Reference implementation from commit 816e54b (verbatim).

    Used to verify the wrapper preserves old behavior including NaN-close
    semantics (label=0.0 for NaN comparisons) and label_ts=NaT for invalid rows.
    """
    out = features.copy()
    out["label"] = float("nan")
    out["label_ts"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")

    if closes.empty:
        return out

    closes = closes.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

    next_lookup = closes[["symbol", "trade_date"]].copy()
    next_lookup["N_date"] = closes.groupby("symbol")["trade_date"].shift(-1)
    next_lookup["N_close"] = closes.groupby("symbol")["close"].shift(-1)
    next_lookup["N_close_ts"] = closes.groupby("symbol")["close_ts"].shift(-1)

    feat = (
        out[["symbol", "prediction_ts"]]
        .reset_index()
        .rename(columns={"index": "orig_idx"})
    )
    feat = feat.sort_values("prediction_ts").reset_index(drop=True)

    closes_for_merge = closes[["symbol", "close_ts", "trade_date", "close"]].sort_values(
        "close_ts"
    )

    merged = pd.merge_asof(
        feat,
        closes_for_merge.rename(
            columns={"close_ts": "_cts", "trade_date": "D_date", "close": "D_close"}
        ),
        left_on="prediction_ts",
        right_on="_cts",
        by="symbol",
        direction="backward",
    )

    merged = merged.merge(
        next_lookup.rename(columns={"trade_date": "D_date"}),
        on=["symbol", "D_date"],
        how="left",
    )

    d_dt = pd.to_datetime(merged["D_date"])
    n_dt = pd.to_datetime(merged["N_date"])
    gap = (n_dt - d_dt).dt.days

    valid = merged["N_date"].notna() & (gap > 0) & (gap <= max_gap_days)

    vr = merged.loc[valid]
    out.loc[vr["orig_idx"].values, "label"] = (
        vr["N_close"].values > vr["D_close"].values
    ).astype(float)
    label_ts_vals = pd.array(vr["N_close_ts"].values, dtype="datetime64[ns, UTC]")
    out.loc[vr["orig_idx"].values, "label_ts"] = label_ts_vals

    return out


def test_daily_close_labels_matches_old_behavior_with_nan_closes():
    """Differential test: current wrapper must match 816e54b behavior on NaN closes.

    10% NaN closes across 300 random seeds. Proves identical label, label_ts,
    index, and dtype to the old implementation.
    """
    import random
    for seed in range(300):
        rng = random.Random(seed)
        # Build closes: 20 days, some NaN closes
        closes_rows = []
        for d in range(20):
            td = date(2026, 6, 1 + d)
            close_val = float("nan") if rng.random() < 0.1 else (100.0 + d)
            closes_rows.append({
                "symbol": "AAPL", "trade_date": td,
                "close": close_val,
                "close_ts": pd.Timestamp(f"2026-06-{1+d:02d} 20:00", tz="UTC"),
            })
        closes = pd.DataFrame(closes_rows)

        # Build features: 10 rows
        features_rows = [
            {"symbol": "AAPL",
             "prediction_ts": pd.Timestamp(f"2026-06-{min(5+i, 20):02d} 21:00", tz="UTC")}
            for i in range(10)
        ]
        features = pd.DataFrame(features_rows)

        old_out = _old_daily_close_labels(features, closes)
        new_out = daily_close_labels(features, closes)

        # Compare label and label_ts (the behavioral contract)
        pd.testing.assert_series_equal(
            old_out["label"], new_out["label"],
            check_names=False, obj=f"label seed={seed}",
        )
        pd.testing.assert_series_equal(
            old_out["label_ts"], new_out["label_ts"],
            check_names=False, obj=f"label_ts seed={seed}",
        )
        # Index must match
        assert old_out.index.tolist() == new_out.index.tolist(), f"index mismatch seed={seed}"
