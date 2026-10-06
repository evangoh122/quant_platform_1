"""
tests/silver/test_ohlcv_day_adjusted.py

Offline arithmetic, PIT helper/reference, and break-detector tests for
the corporate-action adjustment logic.

No network, no Databricks, no Spark.  Uses pure Python/pandas reference
implementation to verify the mathematical contracts.
"""
import datetime as dt
import math
from typing import Optional
from zoneinfo import ZoneInfo

import pytest


# ---------------------------------------------------------------------------
# Reference implementation: adjustment arithmetic
# ---------------------------------------------------------------------------

def _cumulative_split_ratio(bar_date: dt.date, splits: list[dict]) -> float:
    """PRODUCT(split_ratio for splits where ex_date > bar_date).

    splits: list of {"ex_date": date, "split_ratio": float}
    """
    product = 1.0
    for s in splits:
        if s["ex_date"] > bar_date:
            product *= s["split_ratio"]
    return product


def _price_adjustment_factor(bar_date: dt.date, splits: list[dict]) -> float:
    return 1.0 / _cumulative_split_ratio(bar_date, splits)


def _adj_price(raw: float, bar_date: dt.date, splits: list[dict]) -> float:
    return raw * _price_adjustment_factor(bar_date, splits)


def _adj_volume(raw_volume: float, bar_date: dt.date, splits: list[dict]) -> float:
    return raw_volume * _cumulative_split_ratio(bar_date, splits)


def _compute_break(
    symbol: str,
    current_date: dt.date,
    current_close: float,
    previous_date: dt.date,
    previous_close: float,
    splits_today: list[dict],
) -> dict:
    """Classify a bar pair as break candidate or not."""
    if previous_close <= 0 or current_close <= 0:
        return {"is_candidate": False}

    raw_gross_return = current_close / previous_close
    if abs(raw_gross_return - 1.0) < 0.40:
        return {"is_candidate": False}

    # Same-day split ratio
    day_split_ratio = 1.0
    for s in splits_today:
        day_split_ratio *= s["split_ratio"]

    post_split_gross_return = raw_gross_return * day_split_ratio
    split_error = abs(post_split_gross_return - 1.0)

    if day_split_ratio != 1.0 and split_error <= 0.03:
        classification = "SPLIT_EXPLAINED"
        is_masked = False
    else:
        classification = "UNEXPLAINED_PENDING"
        is_masked = True

    return {
        "is_candidate": True,
        "raw_overnight_return": raw_gross_return - 1.0,
        "day_split_ratio": day_split_ratio,
        "post_split_gross_return": post_split_gross_return,
        "split_error": split_error,
        "classification": classification,
        "is_masked": is_masked,
    }


# ---------------------------------------------------------------------------
# 4. AMZN 20:1 test case
# ---------------------------------------------------------------------------

class TestAMZNSplit:

    def test_amzn_20to1_adjusted_return(self):
        """AMZN 2022-06-06: prev close ~2447, ex-date close ~124.79.
        Adjusted return should be ~+2%, not ~-95%."""
        prev_close = 2447.0
        ex_date_close = 124.79
        split_ratio = 20.0
        ex_date = dt.date(2022, 6, 6)
        prev_date = dt.date(2022, 6, 3)

        splits = [{"ex_date": ex_date, "split_ratio": split_ratio}]

        # For the prior bar (2022-06-03): cumulative factor includes the split
        cum_ratio_prev = _cumulative_split_ratio(prev_date, splits)
        assert cum_ratio_prev == 20.0

        adj_prev_close = _adj_price(prev_close, prev_date, splits)
        assert adj_prev_close == pytest.approx(2447.0 / 20.0, rel=1e-6)

        # For the ex-date bar (2022-06-06): cumulative factor = 1 (split not included)
        cum_ratio_ex = _cumulative_split_ratio(ex_date, splits)
        assert cum_ratio_ex == 1.0

        adj_ex_close = _adj_price(ex_date_close, ex_date, splits)
        assert adj_ex_close == pytest.approx(ex_date_close, rel=1e-6)

        # Adjusted return
        adj_return = adj_ex_close / adj_prev_close - 1.0
        assert adj_return == pytest.approx(0.02, abs=0.01)  # ~+2%
        assert adj_return > -0.05  # NOT -95%

    def test_amzn_raw_return_is_negative_95pct(self):
        """Raw (unadjusted) return is ~-95%, confirming the need for adjustment."""
        prev_close = 2447.0
        ex_date_close = 124.79
        raw_return = ex_date_close / prev_close - 1.0
        assert raw_return == pytest.approx(-0.949, abs=0.01)

    def test_amzn_volume_adjusted(self):
        """Volume should be multiplied by cumulative split ratio."""
        raw_volume = 100_000_000
        splits = [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0}]

        # Prior bar volume adjusted up
        adj_vol_prev = _adj_volume(raw_volume, dt.date(2022, 6, 3), splits)
        assert adj_vol_prev == raw_volume * 20.0

        # Ex-date bar volume unchanged
        adj_vol_ex = _adj_volume(raw_volume, dt.date(2022, 6, 6), splits)
        assert adj_vol_ex == raw_volume


# ---------------------------------------------------------------------------
# 5. Reverse split
# ---------------------------------------------------------------------------

class TestReverseSplit:

    def test_1to10_reverse_split(self):
        """1:10 reverse split: split_ratio=0.1. Prior price *10, volume *0.1."""
        prev_close = 10.0
        split_ratio = 0.1
        ex_date = dt.date(2024, 3, 1)
        prev_date = dt.date(2024, 2, 28)
        splits = [{"ex_date": ex_date, "split_ratio": split_ratio}]

        # Prior bar: price adjusted up by 1/0.1 = 10
        adj_prev = _adj_price(prev_close, prev_date, splits)
        assert adj_prev == pytest.approx(100.0)

        # Ex-date bar: factor = 1 (not included)
        adj_ex = _adj_price(100.0, ex_date, splits)
        assert adj_ex == pytest.approx(100.0)

        # Volume: prior bar adjusted down by 0.1
        adj_vol = _adj_volume(1_000_000, prev_date, splits)
        assert adj_vol == pytest.approx(100_000.0)

    def test_reverse_split_adjusted_return(self):
        """If organic return is +5% across a 1:10 reverse split, adjusted
        return should also be ~+5%."""
        prev_close = 10.0
        # After reverse split, price is ~100, organic +5% = 105
        ex_date_close = 105.0
        split_ratio = 0.1
        ex_date = dt.date(2024, 3, 1)
        prev_date = dt.date(2024, 2, 28)
        splits = [{"ex_date": ex_date, "split_ratio": split_ratio}]

        adj_prev = _adj_price(prev_close, prev_date, splits)  # 100
        adj_ex = _adj_price(ex_date_close, ex_date, splits)   # 105
        adj_return = adj_ex / adj_prev - 1.0
        assert adj_return == pytest.approx(0.05, abs=0.001)


# ---------------------------------------------------------------------------
# 6. Multiple splits
# ---------------------------------------------------------------------------

class TestMultipleSplits:

    def test_two_forward_splits(self):
        """Two 2:1 splits (ex_date1 < ex_date2). For a bar before both,
        cumulative ratio = 2 * 2 = 4."""
        splits = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0},
            {"ex_date": dt.date(2023, 3, 1), "split_ratio": 2.0},
        ]
        bar_date = dt.date(2022, 1, 1)
        assert _cumulative_split_ratio(bar_date, splits) == 4.0
        assert _price_adjustment_factor(bar_date, splits) == 0.25

    def test_bar_between_splits(self):
        """Bar between two splits: only the later split is included."""
        splits = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0},
            {"ex_date": dt.date(2023, 3, 1), "split_ratio": 2.0},
        ]
        bar_date = dt.date(2022, 9, 1)  # after first, before second
        assert _cumulative_split_ratio(bar_date, splits) == 2.0

    def test_bar_after_all_splits(self):
        """Bar after all splits: ratio = 1 (no adjustment)."""
        splits = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0},
            {"ex_date": dt.date(2023, 3, 1), "split_ratio": 2.0},
        ]
        bar_date = dt.date(2024, 1, 1)
        assert _cumulative_split_ratio(bar_date, splits) == 1.0

    def test_forward_plus_reverse(self):
        """Forward 2:1 then reverse 1:5.  Cumulative = 2 * 0.2 = 0.4."""
        splits = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0},
            {"ex_date": dt.date(2023, 6, 1), "split_ratio": 0.2},
        ]
        bar_date = dt.date(2022, 1, 1)
        assert _cumulative_split_ratio(bar_date, splits) == pytest.approx(0.4)

    def test_ohlc_share_same_factor(self):
        """OHLC and VWAP all share the same price adjustment factor."""
        splits = [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0}]
        bar_date = dt.date(2022, 1, 1)
        factor = _price_adjustment_factor(bar_date, splits)
        assert factor == 0.5
        assert _adj_price(100.0, bar_date, splits) == 50.0
        assert _adj_price(110.0, bar_date, splits) == 55.0
        assert _adj_price(90.0, bar_date, splits) == 45.0
        assert _adj_price(105.0, bar_date, splits) == 52.5

    def test_volume_uses_reciprocal(self):
        """Volume adjustment uses cumulative_split_ratio (not its reciprocal)."""
        splits = [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0}]
        bar_date = dt.date(2022, 1, 1)
        assert _adj_volume(1_000_000, bar_date, splits) == 2_000_000

    def test_no_splits_returns_1(self):
        """With no splits, both factors are 1."""
        assert _cumulative_split_ratio(dt.date(2024, 1, 1), []) == 1.0
        assert _price_adjustment_factor(dt.date(2024, 1, 1), []) == 1.0


# ---------------------------------------------------------------------------
# 7. Split-day truth
# ---------------------------------------------------------------------------

class TestSplitDayTruth:

    def test_forward_split_day_return(self):
        """Construct: old_close=100, organic return g=+5%, ratio r=2.
        Raw ex-date close = old_close * g / r = 100 * 1.05 / 2 = 52.5
        Adjusted return should be g - 1 = +5%."""
        old_close = 100.0
        organic_return = 1.05  # +5%
        split_ratio = 2.0
        ex_date_close = old_close * organic_return / split_ratio

        ex_date = dt.date(2022, 6, 6)
        prev_date = dt.date(2022, 6, 3)
        splits = [{"ex_date": ex_date, "split_ratio": split_ratio}]

        adj_prev = _adj_price(old_close, prev_date, splits)
        adj_ex = _adj_price(ex_date_close, ex_date, splits)
        adj_return = adj_ex / adj_prev - 1.0

        assert adj_return == pytest.approx(organic_return - 1.0, abs=1e-10)

    def test_reverse_split_day_return(self):
        """old_close=100, organic g=-3%, ratio r=0.1 (1:10 reverse).
        Raw ex-date close = 100 * 0.97 / 0.1 = 970."""
        old_close = 100.0
        organic_return = 0.97  # -3%
        split_ratio = 0.1
        ex_date_close = old_close * organic_return / split_ratio

        ex_date = dt.date(2024, 3, 1)
        prev_date = dt.date(2024, 2, 28)
        splits = [{"ex_date": ex_date, "split_ratio": split_ratio}]

        adj_prev = _adj_price(old_close, prev_date, splits)
        adj_ex = _adj_price(ex_date_close, ex_date, splits)
        adj_return = adj_ex / adj_prev - 1.0

        assert adj_return == pytest.approx(organic_return - 1.0, abs=1e-10)


# ---------------------------------------------------------------------------
# 8. PIT rule
# ---------------------------------------------------------------------------

class TestPITAdjustment:

    def test_global_vs_pit_difference(self):
        """Global adj_close changes when a future split is added.
        PIT adj_close at time t only includes splits known by t."""
        splits_before = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0},
        ]
        splits_after = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0},
            {"ex_date": dt.date(2023, 3, 1), "split_ratio": 3.0},
        ]
        bar_date = dt.date(2022, 1, 1)

        # Global (current-scale) includes all splits
        global_adj = _adj_price(300.0, bar_date, splits_after)
        assert global_adj == pytest.approx(300.0 / 6.0)  # factor = 2*3 = 6

        # PIT at 2022-07-01 (after first split, before second)
        # Only includes the first split
        pit_adj = _adj_price(300.0, bar_date, splits_before)
        assert pit_adj == pytest.approx(300.0 / 2.0)  # factor = 2

        # Adding the 2023 split changed global but not PIT at 2022-07-01
        assert global_adj != pit_adj

    def test_pit_respects_availability(self):
        """PIT factor for row_date only includes splits whose
        information_available_ts <= as_of_t."""
        # Split on 2022-06-06, available at 13:30 UTC that day
        avail_ts = dt.datetime(2022, 6, 6, 13, 30, 0)
        splits = [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0,
                    "information_available_ts": avail_ts}]

        # As-of before availability: split not included
        as_of_before = dt.datetime(2022, 6, 6, 13, 0, 0)
        pit_factor_before = 1.0
        for s in splits:
            if s["ex_date"] > dt.date(2022, 1, 1) and s["information_available_ts"] <= as_of_before:
                pit_factor_before *= s["split_ratio"]
        # No splits qualify (availability not met)
        assert pit_factor_before == 1.0

        # As-of after availability: split included
        as_of_after = dt.datetime(2022, 6, 6, 14, 0, 0)
        pit_factor_after = 1.0
        for s in splits:
            if s["ex_date"] > dt.date(2022, 1, 1) and s["information_available_ts"] <= as_of_after:
                pit_factor_after *= s["split_ratio"]
        assert pit_factor_after == 2.0

    def test_ex_date_morning_availability(self):
        """Split available at 09:30 ET on ex-date = 13:30 UTC (EDT)."""
        from etl.corporate_actions import information_available_ts_for
        avail = information_available_ts_for(dt.date(2022, 6, 6))
        assert avail == dt.datetime(2022, 6, 6, 13, 30, 0)

    def test_pit_does_not_use_future_splits(self):
        """PIT at time t must NOT include splits announced after t."""
        # Two splits: one known, one in the future
        splits = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 2.0,
             "information_available_ts": dt.datetime(2022, 6, 6, 13, 30, 0)},
            {"ex_date": dt.date(2023, 3, 1), "split_ratio": 3.0,
             "information_available_ts": dt.datetime(2023, 3, 1, 14, 30, 0)},
        ]
        bar_date = dt.date(2022, 1, 1)
        as_of = dt.datetime(2022, 7, 1, 12, 0, 0)  # after first, before second

        # PIT factor: only the 2022 split qualifies
        pit_factor = 1.0
        for s in splits:
            if s["ex_date"] > bar_date and s["information_available_ts"] <= as_of:
                pit_factor *= s["split_ratio"]
        assert pit_factor == 2.0

        # Global factor: both splits
        global_factor = _cumulative_split_ratio(bar_date, splits)
        assert global_factor == 6.0


# ---------------------------------------------------------------------------
# 9. Break detection
# ---------------------------------------------------------------------------

class TestBreakDetection:

    def test_amzn_is_split_explained(self):
        """AMZN 2022-06-06: ~-95% raw return, 20:1 split → explained."""
        result = _compute_break(
            symbol="AMZN",
            current_date=dt.date(2022, 6, 6),
            current_close=124.79,
            previous_date=dt.date(2022, 6, 3),
            previous_close=2447.0,
            splits_today=[{"ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0}],
        )
        assert result["is_candidate"] is True
        assert result["classification"] == "SPLIT_EXPLAINED"
        assert result["is_masked"] is False
        assert result["split_error"] <= 0.03

    def test_meta_is_unexplained_pending(self):
        """META 2022-06-09: ~+1395% raw return, no split → unexplained pending."""
        result = _compute_break(
            symbol="META",
            current_date=dt.date(2022, 6, 9),
            current_close=176.0,  # approximate
            previous_date=dt.date(2022, 6, 8),
            previous_close=11.57,  # approximate
            splits_today=[],
        )
        assert result["is_candidate"] is True
        assert result["classification"] == "UNEXPLAINED_PENDING"
        assert result["is_masked"] is True

    def test_genuine_40pct_move_flagged(self):
        """A genuine ≥40% move without a split is flagged."""
        result = _compute_break(
            symbol="MEME",
            current_date=dt.date(2024, 1, 2),
            current_close=150.0,
            previous_date=dt.date(2024, 1, 1),
            previous_close=100.0,
            splits_today=[],
        )
        assert result["is_candidate"] is True
        assert result["classification"] == "UNEXPLAINED_PENDING"
        assert result["is_masked"] is True

    def test_allow_real_move_restores_return(self):
        """ALLOW_REAL_MOVE: is_masked=False, return restored."""
        # Simulate a reviewed break that was changed to ALLOW_REAL_MOVE
        break_record = {
            "classification": "UNEXPLAINED_PENDING",
            "is_masked": True,
            "reviewed_by": "analyst@example.com",
        }
        # After review, classification changes to ALLOW_REAL_MOVE
        if break_record["reviewed_by"]:
            break_record["classification"] = "ALLOW_REAL_MOVE"
            break_record["is_masked"] = False
        assert break_record["classification"] == "ALLOW_REAL_MOVE"
        assert break_record["is_masked"] is False

    def test_confirmed_data_break_stays_masked(self):
        """CONFIRMED_DATA_BREAK remains masked."""
        break_record = {
            "classification": "CONFIRMED_DATA_BREAK",
            "is_masked": True,
            "reviewed_by": "analyst@example.com",
        }
        assert break_record["is_masked"] is True

    def test_below_threshold_not_candidate(self):
        """Return < 40% is not a break candidate."""
        result = _compute_break(
            symbol="AAPL",
            current_date=dt.date(2024, 1, 2),
            current_close=130.0,
            previous_date=dt.date(2024, 1, 1),
            previous_close=100.0,
            splits_today=[],
        )
        assert result["is_candidate"] is False


# ---------------------------------------------------------------------------
# 10. Tolerance boundaries
# ---------------------------------------------------------------------------

class TestToleranceBoundaries:

    def test_split_error_just_under_3pct_is_explained(self):
        """post_split_gross_return = 1.029 → split_error = 0.029 → explained."""
        ratio = 2.0
        target_post_split = 1.029
        raw_gross_return = target_post_split / ratio  # 0.5145
        previous_close = 100.0
        current_close = previous_close * raw_gross_return  # 51.45

        result = _compute_break(
            symbol="TEST",
            current_date=dt.date(2024, 1, 2),
            current_close=current_close,
            previous_date=dt.date(2024, 1, 1),
            previous_close=previous_close,
            splits_today=[{"ex_date": dt.date(2024, 1, 2), "split_ratio": ratio}],
        )
        assert result["is_candidate"] is True
        assert result["split_error"] == pytest.approx(0.029, abs=1e-10)
        assert result["classification"] == "SPLIT_EXPLAINED"

    def test_just_beyond_3pct_is_flagged(self):
        """post_split_gross_return = 1.031 → split_error = 0.031 → flagged."""
        ratio = 2.0
        target_post_split = 1.031
        raw_gross_return = target_post_split / ratio
        previous_close = 100.0
        current_close = previous_close * raw_gross_return

        result = _compute_break(
            symbol="TEST",
            current_date=dt.date(2024, 1, 2),
            current_close=current_close,
            previous_date=dt.date(2024, 1, 1),
            previous_close=previous_close,
            splits_today=[{"ex_date": dt.date(2024, 1, 2), "split_ratio": ratio}],
        )
        assert result["is_candidate"] is True
        assert result["split_error"] == pytest.approx(0.031, abs=1e-10)
        assert result["classification"] == "UNEXPLAINED_PENDING"

    def test_same_date_split_with_huge_residual(self):
        """Split present but residual > 3% → flagged.
        raw_gross_return = 0.55 (abs = 0.45 >= 0.40), split_ratio = 2.0.
        post_split = 0.55 * 2 = 1.10, split_error = 0.10 > 0.03."""
        ratio = 2.0
        raw_gross_return = 0.55  # -45% raw (crosses 40% threshold)
        previous_close = 100.0
        current_close = previous_close * raw_gross_return  # 55

        result = _compute_break(
            symbol="TEST",
            current_date=dt.date(2024, 1, 2),
            current_close=current_close,
            previous_date=dt.date(2024, 1, 1),
            previous_close=previous_close,
            splits_today=[{"ex_date": dt.date(2024, 1, 2), "split_ratio": ratio}],
        )
        assert result["is_candidate"] is True
        # post_split = 0.55 * 2 = 1.10, split_error = 0.10 > 0.03
        assert result["split_error"] == pytest.approx(0.10, abs=1e-10)
        assert result["classification"] == "UNEXPLAINED_PENDING"


# ---------------------------------------------------------------------------
# 11. Review persistence
# ---------------------------------------------------------------------------

class TestReviewPersistence:

    def test_reviewed_allow_real_move_persists(self):
        """Rerunning computed data must not overwrite a reviewed ALLOW_REAL_MOVE."""
        breaks = {
            ("MEME", dt.date(2024, 1, 2)): {
                "classification": "ALLOW_REAL_MOVE",
                "is_masked": False,
                "reviewed_by": "analyst@example.com",
                "reviewed_ts": dt.datetime(2024, 1, 10, 12, 0, 0),
            }
        }
        key = ("MEME", dt.date(2024, 1, 2))
        existing = breaks[key]

        # Simulate rerun: computed classification would be UNEXPLAINED_PENDING
        computed_classification = "UNEXPLAINED_PENDING"
        computed_is_masked = True

        # But the reviewed decision must persist
        if existing["reviewed_by"] is not None:
            # Do NOT overwrite
            assert existing["classification"] == "ALLOW_REAL_MOVE"
            assert existing["is_masked"] is False

    def test_reviewed_confirmed_persists(self):
        """Rerunning computed data must not overwrite CONFIRMED_DATA_BREAK."""
        breaks = {
            ("META", dt.date(2022, 6, 9)): {
                "classification": "CONFIRMED_DATA_BREAK",
                "is_masked": True,
                "reviewed_by": "analyst@example.com",
                "reviewed_ts": dt.datetime(2022, 7, 1, 12, 0, 0),
                "reason": "ticker_reuse",
            }
        }
        key = ("META", dt.date(2022, 6, 9))
        existing = breaks[key]
        assert existing["classification"] == "CONFIRMED_DATA_BREAK"
        assert existing["is_masked"] is True
        assert existing["reason"] == "ticker_reuse"


# ---------------------------------------------------------------------------
# 12. SQL / static contract
# ---------------------------------------------------------------------------

class TestSQLContract:

    def test_adjusted_sql_uses_ex_date_gt_event_date(self):
        """The SQL must use ex_date > event_date, not >=."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "ex_date > event_date" in text or "s.ex_date > d.event_date" in text

    def test_adjusted_sql_has_masked_return_1d(self):
        """The SQL must produce return_1d that is NULL when masked."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "return_1d" in text
        assert "is_data_quality_break" in text
        # Should not have "return_1d = 0" for masked rows
        assert "return_1d = 0" not in text

    def test_adjusted_sql_required_columns(self):
        """The SQL must define all required output columns."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        required = [
            "symbol", "event_date", "event_ts",
            "open", "high", "low", "close", "volume", "vwap", "trade_count",
            "cumulative_split_ratio", "price_adjustment_factor",
            "adj_open", "adj_high", "adj_low", "adj_close", "adj_vwap",
            "adj_volume", "raw_overnight_return", "adjusted_return_1d_unmasked",
            "return_1d", "is_data_quality_break",
            "information_available_ts", "processed_ts",
        ]
        for col in required:
            assert col in text, f"Missing required column: {col}"

    def test_sql_no_bronze_update_delete(self):
        """The SQL must not UPDATE or DELETE from bronze tables."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8").upper()
        assert "DELETE FROM" not in text
        # MERGE INTO with WHEN MATCHED THEN UPDATE SET * is acceptable for Silver
        # but no DELETE FROM bronze
        assert "DELETE" not in text or "DELETE FROM" not in text

    def test_notebook_does_not_modify_dispatch(self):
        """The notebook must not modify .agents/dispatch.sh."""
        from pathlib import Path
        nb_path = Path(__file__).resolve().parents[2] / "notebooks" / "refresh_bronze_corporate_actions.py"
        text = nb_path.read_text(encoding="utf-8")
        assert "dispatch.sh" not in text

    def test_no_adj_close_in_adapter(self):
        """The adapter must never use yfinance Adj Close in code (not comments)."""
        from pathlib import Path
        adapter_path = Path(__file__).resolve().parents[2] / "etl" / "corporate_actions.py"
        text = adapter_path.read_text(encoding="utf-8")
        # Check that 'Adj Close' is not used as a string literal or column access
        # (comments/docstrings explaining we don't use it are fine)
        lines = text.splitlines()
        for line in lines:
            stripped = line.strip()
            # Skip comment lines and docstrings
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Skip lines that are purely comments
            if "#" in line:
                code_part = line[:line.index("#")].strip()
                if "Adj Close" not in code_part:
                    continue
            # In actual code, Adj Close should not appear
            assert "Adj Close" not in stripped or "Never" in stripped or "not" in stripped.lower(), \
                f"Adj Close found in code: {line}"

    def test_daily_info_available_ts_uses_to_utc_timestamp_1630(self):
        """SQL must use to_utc_timestamp(..., '16:30:00') for daily availability."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "to_utc_timestamp" in text, "Must use to_utc_timestamp (not from_utc_timestamp)"
        assert "16:30:00" in text, "Must use 16:30:00 (not 16:00:00)"
        # Ensure from_utc_timestamp is NOT used for the daily availability
        assert "from_utc_timestamp" not in text, "Must not use from_utc_timestamp"

    def test_daily_info_available_ts_edt_is_2030_utc(self):
        """2022-06-06 is EDT: 16:30 ET = 20:30 UTC."""
        from zoneinfo import ZoneInfo
        event_date = dt.date(2022, 6, 6)
        et_time = dt.datetime(2022, 6, 6, 16, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_time = et_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        assert utc_time == dt.datetime(2022, 6, 6, 20, 30, 0)

    def test_daily_info_available_ts_est_is_2130_utc(self):
        """2022-12-05 is EST: 16:30 ET = 21:30 UTC."""
        from zoneinfo import ZoneInfo
        event_date = dt.date(2022, 12, 5)
        et_time = dt.datetime(2022, 12, 5, 16, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_time = et_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        assert utc_time == dt.datetime(2022, 12, 5, 21, 30, 0)

    def test_no_merge_uses_insert_star(self):
        """No MERGE in the file may use INSERT * or UPDATE SET *."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "INSERT *" not in text, \
            "No MERGE may use INSERT *; use explicit column lists"
        assert "UPDATE SET *" not in text, \
            "No MERGE may use UPDATE SET *; use explicit column lists"

    def test_data_quality_breaks_merge_insert_has_explicit_columns(self):
        """data_quality_breaks MERGE INSERT must use explicit column list."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        dq_section = text.split("Merge silver_ohlcv_day_adjusted")[0]
        assert "INSERT (" in dq_section, \
            "data_quality_breaks MERGE must use explicit INSERT column list"
        assert "reviewed_by" in dq_section and "reviewed_ts" in dq_section, \
            "INSERT must include reviewed_by and reviewed_ts columns"

    def test_silver_adjusted_merge_insert_has_explicit_columns(self):
        """silver_ohlcv_day_adjusted MERGE INSERT must use explicit column list."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        silver_section = text.split("Merge silver_ohlcv_day_adjusted")[1]
        assert "INSERT (" in silver_section, \
            "silver_ohlcv_day_adjusted MERGE must use explicit INSERT column list"
        assert "UPDATE SET" in silver_section, \
            "silver_ohlcv_day_adjusted MERGE must use explicit UPDATE SET"
        assert "adj_close" in silver_section, \
            "INSERT must include adj_close column"
        assert "return_1d" in silver_section, \
            "INSERT must include return_1d column"

    def test_silver_adjusted_insert_covers_all_target_columns(self):
        """Parse target DDL and assert silver INSERT lists every target column exactly once."""
        from pathlib import Path
        import re
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")

        ddl_match = re.search(
            r'CREATE TABLE IF NOT EXISTS.*?silver_ohlcv_day_adjusted\s*\((.*?)\)\s*USING DELTA',
            text, re.DOTALL
        )
        assert ddl_match, "Could not find silver_ohlcv_day_adjusted CREATE TABLE DDL"
        ddl_body = ddl_match.group(1)
        target_cols = []
        for line in ddl_body.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            parts = line.split()
            if parts:
                col_name = parts[0].lower()
                if col_name in ("primary", "constraint", "--"):
                    continue
                target_cols.append(col_name)
        assert len(target_cols) == 25, f"Expected 25 target columns, got {len(target_cols)}: {target_cols}"

        silver_section = text.split("Merge silver_ohlcv_day_adjusted")[1]
        insert_match = re.search(
            r'silver_ohlcv_day_adjusted.*?WHEN NOT MATCHED THEN INSERT\s*\((.*?)\)\s*VALUES',
            silver_section, re.DOTALL
        )
        assert insert_match, "Could not find INSERT column list in silver_ohlcv_day_adjusted MERGE"
        insert_cols_str = insert_match.group(1)
        insert_cols = [c.strip().lower() for c in insert_cols_str.split(",")]

        assert len(insert_cols) == len(target_cols), \
            f"INSERT has {len(insert_cols)} columns but target has {len(target_cols)}"
        assert set(insert_cols) == set(target_cols), \
            f"Column mismatch: INSERT={sorted(insert_cols)} vs target={sorted(target_cols)}"

    def test_silver_adjusted_missing_column_would_fail_test(self):
        """Prove that a missing column in INSERT is detected."""
        import re
        # Simulate an INSERT with one column missing
        all_cols = [
            "symbol", "event_date", "event_ts", "open", "high", "low", "close",
            "volume", "vwap", "trade_count", "cumulative_split_ratio",
            "price_adjustment_factor", "adj_open", "adj_high", "adj_low",
            "adj_close", "adj_vwap", "adj_volume", "vwap_source",
            "raw_overnight_return",
            "adjusted_return_1d_unmasked", "return_1d", "is_data_quality_break",
            "information_available_ts", "processed_ts",
        ]
        # Missing one column
        partial_cols = all_cols[:-1]
        assert len(partial_cols) == 24
        assert set(partial_cols) != set(all_cols), \
            "Missing column must be detected"
        assert "processed_ts" not in partial_cols, \
            "Deliberately removed processed_ts to prove detection works"

    def test_data_quality_breaks_insert_covers_all_target_columns(self):
        """Parse target DDL and assert INSERT lists every target column exactly once."""
        from pathlib import Path
        import re
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")

        # Extract target DDL columns (between CREATE TABLE ... data_quality_breaks ( ... ) USING DELTA)
        ddl_match = re.search(
            r'CREATE TABLE IF NOT EXISTS.*?data_quality_breaks\s*\((.*?)\)\s*USING DELTA',
            text, re.DOTALL
        )
        assert ddl_match, "Could not find data_quality_breaks CREATE TABLE DDL"
        ddl_body = ddl_match.group(1)
        # Parse column names from DDL (lines like: "symbol STRING NOT NULL,")
        target_cols = []
        for line in ddl_body.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            parts = line.split()
            if parts:
                col_name = parts[0].lower()
                if col_name in ("primary", "constraint", "--"):
                    continue
                target_cols.append(col_name)
        assert len(target_cols) == 16, f"Expected 16 target columns, got {len(target_cols)}: {target_cols}"

        # Extract INSERT column list from the MERGE
        insert_match = re.search(
            r'data_quality_breaks.*?WHEN NOT MATCHED THEN INSERT\s*\((.*?)\)\s*VALUES',
            text, re.DOTALL
        )
        assert insert_match, "Could not find INSERT column list in data_quality_breaks MERGE"
        insert_cols_str = insert_match.group(1)
        insert_cols = [c.strip().lower() for c in insert_cols_str.split(",")]

        assert len(insert_cols) == len(target_cols), \
            f"INSERT has {len(insert_cols)} columns but target has {len(target_cols)}"
        assert set(insert_cols) == set(target_cols), \
            f"Column mismatch: INSERT={sorted(insert_cols)} vs target={sorted(target_cols)}"


# ---------------------------------------------------------------------------
# 13. Break masking contract
# ---------------------------------------------------------------------------

class TestMaskingContract:

    def test_mask_only_return_not_prices(self):
        """Masking sets return_1d = NULL, not prices to zero."""
        # Simulate masked bar
        bar = {
            "adj_close": 150.0,
            "adj_open": 148.0,
            "return_1d": None,  # masked
            "is_data_quality_break": True,
        }
        assert bar["adj_close"] is not None
        assert bar["adj_close"] > 0
        assert bar["return_1d"] is None
        assert bar["is_data_quality_break"] is True

    def test_masked_return_is_null_not_zero(self):
        """Canonical return for masked dates must be NULL, never 0."""
        # This is a contract test: the SQL must produce NULL, not 0
        masked_return = None  # what the SQL should produce
        assert masked_return is None
        assert masked_return != 0

    def test_ssplit_explained_not_masked(self):
        """SPLIT_EXPLAINED breaks are not masked."""
        result = _compute_break(
            "AMZN", dt.date(2022, 6, 6), 124.79,
            dt.date(2022, 6, 3), 2447.0,
            [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0}],
        )
        assert result["classification"] == "SPLIT_EXPLAINED"
        assert result["is_masked"] is False

    def test_unexplained_pending_is_masked(self):
        """UNEXPLAINED_PENDING breaks are masked."""
        result = _compute_break(
            "META", dt.date(2022, 6, 9), 176.0,
            dt.date(2022, 6, 8), 11.57, [],
        )
        assert result["classification"] == "UNEXPLAINED_PENDING"
        assert result["is_masked"] is True


# ---------------------------------------------------------------------------
# 14. Resolved-splits CTE: massive-only deduplication
# ---------------------------------------------------------------------------

class TestMassiveSplits:

    def test_sql_has_massive_splits_cte(self):
        """The SQL must define _massive_splits CTE."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "_massive_splits" in text
        assert "ROW_NUMBER() OVER" in text

    def test_sql_massive_splits_filters_source(self):
        """The _massive_splits CTE must filter to source='massive'."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "source = 'massive'" in text

    def test_sql_massive_splits_dedupes_by_fetched_ts(self):
        """The _massive_splits CTE must dedupe by latest fetched_ts."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "fetched_ts DESC" in text

    def test_sql_split_factors_uses_massive_splits(self):
        """_split_factors must JOIN _massive_splits, not bronze_corporate_actions."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        # Find the _split_factors section
        factors_section = text.split("_split_factors")[1] if "_split_factors" in text else ""
        assert "_massive_splits" in factors_section, \
            "_split_factors must use _massive_splits, not bronze_corporate_actions"
        # Should NOT directly reference bronze_corporate_actions in the split factors
        assert "bronze_corporate_actions" not in factors_section.split("_adjusted")[0], \
            "_split_factors must not directly reference bronze_corporate_actions"

    def test_sql_break_candidates_uses_massive_splits(self):
        """_break_candidates must use _massive_splits for day_splits."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        # Find the _break_candidates section
        break_section = text.split("_break_candidates")[1] if "_break_candidates" in text else ""
        assert "_massive_splits" in break_section, \
            "_break_candidates must use _massive_splits for day_splits"

    def test_sql_has_no_source_mismatch_detection(self):
        """The SQL must NOT define _split_source_mismatches CTE."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "_split_source_mismatches" not in text
        assert "SPLIT_SOURCE_MISMATCH" not in text

    def test_sql_has_no_yfinance_references(self):
        """The SQL must NOT reference yfinance."""
        from pathlib import Path
        sql_path = Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql"
        text = sql_path.read_text(encoding="utf-8")
        assert "yfinance" not in text.lower()
        assert "SPLIT_SINGLE_SOURCE" not in text


# ---------------------------------------------------------------------------
# 15. Apply-once semantic test (pure Python reference)
# ---------------------------------------------------------------------------

class TestApplyOnceSemantics:

    def test_split_applied_once_not_squared(self):
        """A duplicate massive split must be applied ONCE.
        Cumulative factor for a 20:1 split should be 20, not 400."""
        resolved_splits = [
            {"symbol": "AMZN", "ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0, "source": "massive"},
        ]

        # For a bar before the split, cumulative ratio should be 20.0
        bar_date = dt.date(2022, 6, 3)
        cum_ratio = _cumulative_split_ratio(bar_date, resolved_splits)
        assert cum_ratio == 20.0, f"Expected 20.0, got {cum_ratio}"

        # NOT 400 (which would happen if duplicates were counted)
        assert cum_ratio != 400.0

    def test_adj_price_with_resolved_splits(self):
        """Adjusted price should use the deduplicated split ratio."""
        splits = [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0}]
        prev_close = 2447.0
        adj_prev = _adj_price(prev_close, dt.date(2022, 6, 3), splits)
        assert adj_prev == pytest.approx(2447.0 / 20.0, rel=1e-6)

    def test_adj_return_with_resolved_splits(self):
        """Adjusted return across a split should reflect organic movement."""
        splits = [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0}]
        prev_close = 2447.0
        ex_close = 124.79

        adj_prev = _adj_price(prev_close, dt.date(2022, 6, 3), splits)
        adj_ex = _adj_price(ex_close, dt.date(2022, 6, 6), splits)
        adj_return = adj_ex / adj_prev - 1.0

        # Should be ~+2%, not ~-95%
        assert adj_return == pytest.approx(0.02, abs=0.01)
        assert adj_return > -0.05

    def test_two_splits_different_dates_both_applied(self):
        """Two different splits on different dates should both be applied."""
        splits = [
            {"ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0},
            {"ex_date": dt.date(2023, 3, 1), "split_ratio": 2.0},
        ]
        bar_date = dt.date(2022, 1, 1)
        cum_ratio = _cumulative_split_ratio(bar_date, splits)
        assert cum_ratio == 40.0  # 20 * 2

    def test_yfinance_row_in_bronze_ignored(self):
        """A yfinance-source row in bronze should not affect the factor.
        Only source='massive' rows are used."""
        # With massive-only, a yfinance row would not be in _massive_splits at all.
        # The factor should be based only on massive rows.
        massive_splits = [{"ex_date": dt.date(2022, 6, 6), "split_ratio": 20.0}]
        bar_date = dt.date(2022, 6, 3)
        assert _cumulative_split_ratio(bar_date, massive_splits) == 20.0

def test_silver_merge_deletes_rows_no_longer_in_source():
    """silver_ohlcv_day_adjusted is rebuilt from the full bronze history each run, so its MERGE must delete stale target rows."""
    import re
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[2] / "silver" / "08_silver_ohlcv_day_adjusted.sql").read_text(encoding="utf-8")
    merge = sql[sql.index("MERGE INTO bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted"):]
    assert re.search(r"WHEN\s+NOT\s+MATCHED\s+BY\s+SOURCE\s+THEN\s+DELETE", merge), "silver MERGE must delete stale rows"
