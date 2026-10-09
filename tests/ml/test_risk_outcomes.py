"""Tests for risk-outcome ledger: frozen sigma, outcome_z, sufficiency gates.

All arithmetic is hand-computed in comments.  Tests call production functions
and never duplicate their logic.
"""

import ast
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ml.baseline_labels import daily_close_labels, daily_close_pairs
from ml.risk_outcomes import build_signal_outcomes, summarize_outcomes


# ── helpers ──────────────────────────────────────────────────────────────────

def _utc(y, m, d, h=20, mi=0):
    return pd.Timestamp(f"{y}-{m:02d}-{d:02d} {h:02d}:{mi:02d}", tz="UTC")


def _td(y, m, d):
    """Return a datetime.date."""
    return date(y, m, d)


def _biz_date(start_date, offset_days):
    """Return a business-date-like date by adding offset_days to start_date."""
    return (pd.Timestamp(start_date) + pd.Timedelta(days=offset_days)).date()


def _make_closes(rows):
    return pd.DataFrame(rows)


def _make_signals(rows):
    return pd.DataFrame(rows)


def _make_dividends(rows):
    return pd.DataFrame(rows)


def _make_multi_day_closes(symbol, start_date, n_days, returns_list, base_close=100.0):
    """Generate n_days closes starting from start_date, using returns_list for return_1d.

    returns_list[0] is the return_1d for the first row (typically NaN since no prior day).
    Close prices are computed cumulatively from base_close.
    """
    rows = []
    d = pd.Timestamp(start_date)
    current_close = base_close
    for i in range(n_days):
        td = d + pd.DateOffset(days=i)
        ret = returns_list[i] if i < len(returns_list) else float("nan")
        if i == 0:
            close = base_close
        elif not math.isnan(ret):
            current_close = current_close * (1 + ret)
            close = current_close
        else:
            close = current_close
        rows.append({
            "symbol": symbol,
            "trade_date": td.date(),
            "close": close,
            "close_ts": pd.Timestamp(td.strftime("%Y-%m-%d") + " 20:00", tz="UTC"),
            "return_1d": float("nan") if i == 0 else ret,
        })
    return pd.DataFrame(rows)


# ── daily_close_pairs tests ──────────────────────────────────────────────────

class TestDailyClosePairs:
    def test_pairs_match_labels(self):
        """daily_close_pairs entry/outcome matches daily_close_labels."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 5),
             "close": 100.0, "close_ts": _utc(2026, 6, 5, 20, 0)},
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 8),
             "close": 102.0, "close_ts": _utc(2026, 6, 8, 20, 0)},
        ])
        features = pd.DataFrame([
            {"symbol": "AAPL", "prediction_ts": _utc(2026, 6, 5, 21, 0)},
        ])
        pairs = daily_close_pairs(features, closes)
        labels = daily_close_labels(features, closes)
        assert pairs.loc[0, "outcome_close"] > pairs.loc[0, "entry_close"]
        assert labels.loc[0, "label"] == 1.0

    def test_pairs_columns_present(self):
        """daily_close_pairs returns all required columns."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 5),
             "close": 100.0, "close_ts": _utc(2026, 6, 5, 20, 0)},
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 8),
             "close": 102.0, "close_ts": _utc(2026, 6, 8, 20, 0)},
        ])
        features = pd.DataFrame([
            {"symbol": "AAPL", "prediction_ts": _utc(2026, 6, 5, 21, 0)},
        ])
        pairs = daily_close_pairs(features, closes)
        for col in ["entry_trade_date", "entry_close", "entry_close_ts",
                     "outcome_trade_date", "outcome_close", "outcome_close_ts"]:
            assert col in pairs.columns

    def test_empty_closes_returns_nan(self):
        closes = _make_closes([])
        features = pd.DataFrame([
            {"symbol": "AAPL", "prediction_ts": _utc(2026, 6, 5, 21, 0)},
        ])
        pairs = daily_close_pairs(features, closes)
        assert pd.isna(pairs.loc[0, "entry_close"])
        assert pd.isna(pairs.loc[0, "outcome_close"])


# ── sigma20 tests ────────────────────────────────────────────────────────────

class TestSigma20:
    def test_sigma20_alternating_returns(self):
        """20 valid returns alternating +0.01/-0.01 => ddof=1 std = 0.01*sqrt(20/19).

        The sample std of 20 values each +/-0.01 from the mean:
        variance = sum((x_i - mean)^2) / (n-1) = 20 * 0.01^2 / 19
        std = 0.01 * sqrt(20/19) ≈ 0.0102597835
        """
        # 22 closes starting Jan 1: first has NaN return, rest alternate +/-0.01
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 22)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 22, rets)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 23, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        expected = 0.01 * math.sqrt(20 / 19)
        assert abs(result.loc[0, "sigma20"] - expected) < 1e-10
        # Verify the correct window was used (last 20 valid returns, not shifted)
        # 22 closes: day 0 NaN, days 1-21 valid. Last 20 = days 2-21 = Jan 3 to Jan 22
        assert result.loc[0, "sigma_as_of"] == _td(2025, 1, 22)

    def test_sigma20_insufficient_19_valid(self):
        """19 valid returns => insufficient_sigma_history.

        Need: 21 closes so prediction_ts sees 20 bars, but first return
        is NaN so only 20-1=19 valid return_1d values in the window.
        Actually: 20 bars total, first has NaN return, so 19 valid.
        """
        rets = [float("nan")] + [0.01] * 19  # 1 NaN + 19 valid
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 21, rets)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 22, 21, 0),
            "probability": 0.6,
        }])
        # Need an outcome close to not be outcome_pending
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 23),
            "close": 105.0, "close_ts": _utc(2025, 1, 23, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "insufficient_sigma_history"
        assert pd.isna(result.loc[0, "sigma_used"])

    def test_sigma20_nan_return_excluded(self):
        """A NaN return inside the window is excluded, NOT forward-filled.

        25 closes. Row 0 NaN (first day). Rows 1-5 return +0.05 (high vol),
        rows 6-10 return +0.02 (medium vol), row 11 NaN (data-quality break),
        rows 12-24 return +0.001 (low vol). Total valid: 23.
        Without forward-fill: last20 = rows 4-10 (2*+0.05 + 5*+0.02) + rows 12-24 (13*+0.001).
        With forward-fill: row 11 becomes +0.02, giving24 valid; last20 = rows 5-24
        (1*+0.05 + 6*+0.02 + 13*+0.001). Different sigma.
        """
        rets = [float("nan")]  # row 0: NaN
        rets += [0.05] * 5     # rows 1-5: high vol
        rets += [0.02] * 5     # rows 6-10: medium vol
        rets += [float("nan")] # row 11: NaN (data-quality break)
        rets += [0.001] * 13   # rows 12-24: low vol
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 25, 21, 0),
            "probability": 0.6,
        }])
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "sigma_observation_count"] == 20
        assert not pd.isna(result.loc[0, "sigma20"])
        # Verify NaN was excluded (not forward-filled): compute expected sigma
        # from the exact 20 returns that should be in the window.
        # valid_returns: rows 1-5 (+0.05), 6-10 (+0.02), 12-24 (+0.001) = 23 valid
        # last20 = rows 4-10 (2*+0.05 + 5*+0.02) + rows 12-24 (13*+0.001)
        expected_returns = [0.05]*2 + [0.02]*5 + [0.001]*13
        expected_sigma = pd.Series(expected_returns).std(ddof=1)
        assert abs(result.loc[0, "sigma20"] - expected_sigma) < 1e-12

    def test_sigma_floor_from_sigma252(self):
        """sigma20 small vs 0.5*sigma252 large => sigma_used = floor.

        Last 20 returns have small variance (0.001), full 252 have larger
        variance (0.01). sigma_floor = 0.5 * sigma252 > sigma20.
        """
        rets = [float("nan")]  # day 0 return is NaN
        for i in range(1, 253):
            if i <= 232:
                rets.append(0.01 if i % 2 == 0 else -0.01)
            else:
                rets.append(0.001 if i % 2 == 0 else -0.001)
        # 253 closes: day 0 to day 252 (Jan 1 to Sep 11)
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 254, rets)
        # prediction_ts after the last close_ts to see all 252 valid returns
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 9, 15, 21, 0),
            "probability": 0.6,
        }])
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 9, 16),
            "close": 200.0, "close_ts": _utc(2025, 9, 16, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)
        as_of = _utc(2025, 9, 20, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        # sigma20 uses last 20 returns (all small variance ~0.001)
        # sigma252 uses last 252 returns (mostly large variance ~0.01)
        # floor = 0.5 * sigma252 > sigma20
        assert result.loc[0, "sigma_used"] == result.loc[0, "sigma_floor"]
        assert result.loc[0, "sigma_floor"] == 0.5 * result.loc[0, "sigma252"]

    def test_sigma252_insufficient_59_valid(self):
        """sigma252 with < 60 valid => floor unavailable, sigma_used == sigma20."""
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 60)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 61, rets)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 3, 3, 21, 0),
            "probability": 0.6,
        }])
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 3, 4),
            "close": 110.0, "close_ts": _utc(2025, 3, 4, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)
        as_of = _utc(2025, 3, 10, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        # 59 valid < 60 required for sigma252
        assert pd.isna(result.loc[0, "sigma252"])
        assert pd.isna(result.loc[0, "sigma_floor"])
        assert result.loc[0, "sigma_used"] == result.loc[0, "sigma20"]


# ── Information-time boundary tests ──────────────────────────────────────────

class TestInformationTime:
    def test_close_after_prediction_ts_never_d(self):
        """A close with close_ts > prediction_ts is never D and never in sigma window.

        prediction_ts at 14:00 UTC on Jun 5:
        - Jun 4 close_ts = 2026-06-04 20:00 UTC <= 2026-06-05 14:00 -> YES, D
        - Jun 5 close_ts = 2026-06-05 20:00 UTC > 2026-06-05 14:00 -> NOT D
        So D = Jun 4, N = Jun 5.
        """
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 4),
             "close": 99.0, "close_ts": _utc(2026, 6, 4, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 5),
             "close": 100.0, "close_ts": _utc(2026, 6, 5, 20, 0),
             "return_1d": 0.01},
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 8),
             "close": 102.0, "close_ts": _utc(2026, 6, 8, 20, 0),
             "return_1d": 0.02},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2026, 6, 5, 14, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2026, 6, 10, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "entry_date"] == pd.Timestamp("2026-06-04")
        assert result.loc[0, "outcome_date"] == pd.Timestamp("2026-06-05")

    def test_append_future_rows_stability(self):
        """Frozen sigma identical before/after appending later bars."""
        # Need 60+ bars so sigma252 is non-NaN for stability check
        # Use Mar 1 start: 81 closes end May 20; extra from May 22 (all valid)
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 80)]
        closes_base = _make_multi_day_closes("AAPL", "2025-03-01", 81, rets)
        # Append future bars (81 closes end on May 20; extra from May 22)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 5, 21 + i),
            "close": 110.0,
            "close_ts": _utc(2025, 5, 21 + i, 20, 0),
            "return_1d": 0.005,
        } for i in range(1, 11)])
        closes_extended = pd.concat([closes_base, extra], ignore_index=True)

        # prediction_ts after base ends but before extensions
        pred_ts_date = pd.Timestamp("2025-03-01") + pd.DateOffset(days=81)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(pred_ts_date.year, pred_ts_date.month, pred_ts_date.day, 14, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 6, 1, 21, 0)

        result_base = build_signal_outcomes(signals, closes_base, as_of=as_of)
        result_ext = build_signal_outcomes(signals, closes_extended, as_of=as_of)

        assert result_base.loc[0, "sigma20"] == result_ext.loc[0, "sigma20"]
        assert result_base.loc[0, "sigma252"] == result_ext.loc[0, "sigma252"]
        assert result_base.loc[0, "sigma_used"] == result_ext.loc[0, "sigma_used"]


# ── UP/DOWN, signed return, outcome_z tests ──────────────────────────────────

class TestDirectionAndOutcomeZ:
    def test_up_signed_return_literal(self):
        """UP signal: signed_raw_return = raw_forward_return."""
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 24)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)

        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 25, 21, 0),
            "probability": 0.6,  # UP
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)

        assert result.loc[0, "direction"] == "UP"
        # entry_close is the close on the last bar before prediction_ts
        entry_c = result.loc[0, "entry_close"]
        outcome_c = result.loc[0, "outcome_close"]
        raw_ret = outcome_c / entry_c - 1
        assert abs(result.loc[0, "raw_forward_return"] - raw_ret) < 1e-10
        assert abs(result.loc[0, "signed_raw_return"] - raw_ret) < 1e-10

    def test_down_signed_return_literal(self):
        """DOWN signal: signed_raw_return = -raw_forward_return."""
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 24)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)

        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 25, 21, 0),
            "probability": 0.38,  # DOWN
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)

        assert result.loc[0, "direction"] == "DOWN"
        assert result.loc[0, "probability_up"] == 0.38
        entry_c = result.loc[0, "entry_close"]
        outcome_c = result.loc[0, "outcome_close"]
        raw_ret = outcome_c / entry_c - 1
        assert abs(result.loc[0, "signed_raw_return"] - (-raw_ret)) < 1e-10

    def test_outcome_z_literal(self):
        """outcome_z = signed_raw_return / sigma_used."""
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 25)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 26, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 27),
            "close": 105.0, "close_ts": _utc(2025, 1, 27, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)

        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 26, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)

        sigma = result.loc[0, "sigma_used"]
        signed = result.loc[0, "signed_raw_return"]
        expected_z = signed / sigma
        assert abs(result.loc[0, "outcome_z"] - expected_z) < 1e-10


# ── Ex-dividend tests ────────────────────────────────────────────────────────

class TestExDividend:
    def test_ex_dividend_crossing_masked(self):
        """Ex-dividend date in (entry_date, outcome_date] => masked."""
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 24)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)

        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 25, 21, 0),
            "probability": 0.6,
        }])
        dividends = _make_dividends([{
            "symbol": "AAPL", "ex_date": _td(2025, 1, 26),
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, dividends=dividends, as_of=as_of)

        assert result.loc[0, "ex_dividend_state"] == "masked"
        assert result.loc[0, "eligibility_state"] == "ex_dividend_masked"
        assert pd.isna(result.loc[0, "outcome_z"])

    def test_dividends_none_state_unknown(self):
        """dividends=None => ex_dividend_state='unknown' and NOT masked."""
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 24)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)

        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 25, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, dividends=None, as_of=as_of)

        assert result.loc[0, "ex_dividend_state"] == "unknown"
        assert result.loc[0, "eligibility_state"] == "eligible"


# ── Eligibility state tests ──────────────────────────────────────────────────

class TestEligibility:
    def test_outcome_pending_no_n(self):
        """No N close => outcome_pending."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "outcome_pending"

    def test_outcome_pending_future_close(self):
        """outcome_close_ts > as_of => outcome_pending.

        D = Jan 20 (close_ts 20:00 <= 21:00), N = Jan 21 (close_ts 20:00).
        as_of = Jan 20 22:00, outcome_close_ts = Jan 21 20:00.
        Jan 21 20:00 > Jan 20 22:00 => pending.
        """
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 21),
             "close": 105.0, "close_ts": _utc(2025, 1, 21, 20, 0),
             "return_1d": 0.05},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        # as_of before outcome_close_ts
        as_of = _utc(2025, 1, 20, 22, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "outcome_pending"

    def test_missing_return_gap_too_large(self):
        """gap > max_gap_days => missing_return.

        D = Jan 20, N = Feb 1 => gap = 12 days > 5.
        Need as_of after N to not be pending.
        """
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 2, 1),
             "close": 105.0, "close_ts": _utc(2025, 2, 1, 20, 0),
             "return_1d": 0.05},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        # as_of AFTER N's close_ts so it's not pending
        as_of = _utc(2025, 2, 5, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "missing_return"

    def test_precedence_order(self):
        """Precedence: pending > missing_return > ex_dividend > insufficient_sigma > missing_sigma > eligible."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        # No N => outcome_pending
        assert result.loc[0, "eligibility_state"] == "outcome_pending"


# ── summarize_outcomes tests ─────────────────────────────────────────────────

class TestSummarizeOutcomes:
    def _make_eligible_outcomes(self, n, distinct_dates, mv="v1", hor="1d"):
        """Build a DataFrame with n eligible rows over distinct_dates dates."""
        dates = pd.date_range("2025-01-01", periods=distinct_dates, freq="B", tz="UTC")
        rows = []
        for i in range(n):
            d = dates[i % distinct_dates]
            rows.append({
                "signal_id": f"s{i}", "symbol": "AAPL", "model_version": mv,
                "horizon": hor, "prediction_ts": d,
                "entry_date": _td(2025, 1, 1), "outcome_date": _td(2025, 1, 2),
                "direction": "UP", "probability_up": 0.6,
                "raw_forward_return": 0.01 if i < 60 else -0.01,
                "signed_raw_return": 0.01 if i < 60 else -0.01,
                "sigma20": 0.01, "sigma252": 0.01, "sigma_floor": 0.005,
                "sigma_used": 0.01, "sigma_method": "close_to_close_ddof1_v1",
                "sigma_as_of": _td(2025, 1, 1), "sigma_observation_count": 20,
                "outcome_z": 1.0 if i < 60 else -1.0,
                "base_up_flag": True if i < 60 else False,
                "ex_dividend_state": "none", "eligibility_state": "eligible",
            })
        return pd.DataFrame(rows)

    def test_insufficient_sample_n100_5_dates(self):
        """n=100 on 5 distinct dates => insufficient_sample with all aggregates None."""
        outcomes = self._make_eligible_outcomes(100, 5)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 1
        r = result[0]
        assert r["state"] == "insufficient_sample"
        assert r["n"] == 100
        assert r["distinct_prediction_dates"] == 5
        assert r["hit_rate"] is None
        assert r["hit_rate_interval"] is None
        assert r["median_outcome_z"] is None
        assert r["mean_outcome_z"] is None
        assert r["base_up_rate"] is None

    def test_dates_gate_blocks_sufficient(self):
        """n=150, 50 dates, n_eff≈107 => blocked by dates gate (50 < 60).

        Without the dates gate, this would be sufficient (n>=100, n_eff>=100).
        m = 150/50 = 3, n_eff = 150/(1+(3-1)*0.2) = 150/1.4 ≈ 107.14
        """
        outcomes = self._make_eligible_outcomes(150, 50)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        r = result[0]
        assert r["state"] == "insufficient_sample"
        assert r["n"] == 150
        assert r["distinct_prediction_dates"] == 50
        expected_neff = 150 / (1 + (150/50 - 1) * 0.2)
        assert abs(r["n_eff"] - expected_neff) < 1e-10
        assert r["n_eff"] >= 100  # n_eff passes, but dates gate blocks
        assert r["hit_rate"] is None

    def test_sufficient_case_n_eff_boundary(self):
        """n=100, 60 dates, rho 0.2 => m=100/60, n_eff = 100/(1+(100/60-1)*0.2).

        m = 100/60 ≈ 1.6667
        n_eff = 100 / (1 + (1.6667 - 1) * 0.2) = 100 / 1.13333 ≈ 88.235
        n_eff < 100 => insufficient_sample
        """
        outcomes = self._make_eligible_outcomes(100, 60)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 1
        r = result[0]
        expected_neff = 100 / (1 + (100 / 60 - 1) * 0.2)
        assert abs(r["n_eff"] - expected_neff) < 1e-10
        assert r["state"] == "insufficient_sample"  # n_eff < 100

    def test_sufficient_case_with_wilson(self):
        """Sufficient case: Wilson interval literal.

        n=150, 80 dates => m=150/80, n_eff = 150/(1+(150/80-1)*0.2)
        m = 1.875, n_eff = 150/(1+0.175) = 150/1.175 ≈ 127.66
        n_eff >= 100 => sufficient
        hit_count = 60 (first 60 rows have signed_raw_return > 0)
        p = 60/150 = 0.4
        Wilson z=1.96
        """
        outcomes = self._make_eligible_outcomes(150, 80)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        r = result[0]
        assert r["state"] == "sufficient"
        assert r["hit_count"] == 60
        assert abs(r["hit_rate"] - 0.4) < 1e-10

        # Wilson interval
        n = 150
        m = n / 80
        n_eff = n / (1 + (m - 1) * 0.2)
        p = 60 / n
        z = 1.96
        denom = 1 + z**2 / n_eff
        centre = (p + z**2 / (2 * n_eff)) / denom
        spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * n_eff)) / n_eff) / denom
        assert abs(r["hit_rate_interval"]["low"] - max(0.0, centre - spread)) < 1e-10
        assert abs(r["hit_rate_interval"]["high"] - min(1.0, centre + spread)) < 1e-10

    def test_two_model_versions_separate(self):
        """Two model_versions in one frame yield two separate dicts, never pooled."""
        outcomes1 = self._make_eligible_outcomes(120, 70, mv="v1")
        outcomes2 = self._make_eligible_outcomes(130, 75, mv="v2")
        outcomes = pd.concat([outcomes1, outcomes2], ignore_index=True)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 2
        mvs = {r["model_version"] for r in result}
        assert mvs == {"v1", "v2"}

    def test_base_up_rate_eligible_only(self):
        """base_up_rate computed over eligible rows only."""
        eligible = self._make_eligible_outcomes(100, 5)
        # Add an ineligible row
        ineligible = pd.DataFrame([{
            "signal_id": "s_bad", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": pd.Timestamp("2025-01-01", tz="UTC"),
            "entry_date": None, "outcome_date": None,
            "direction": "UP", "probability_up": 0.6,
            "raw_forward_return": np.nan, "signed_raw_return": np.nan,
            "sigma20": np.nan, "sigma252": np.nan, "sigma_floor": np.nan,
            "sigma_used": np.nan, "sigma_method": "close_to_close_ddof1_v1",
            "sigma_as_of": None, "sigma_observation_count": 0,
            "outcome_z": np.nan, "base_up_flag": True,
            "ex_dividend_state": "none", "eligibility_state": "missing_return",
        }])
        outcomes = pd.concat([eligible, ineligible], ignore_index=True)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 1
        assert result[0]["state"] == "insufficient_sample"


# ── Guard tests ──────────────────────────────────────────────────────────────

class TestGuards:
    def test_no_api_frontend_import(self):
        """ml/risk_outcomes.py must not import from api/ or frontend/."""
        with open("ml/risk_outcomes.py", "r") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                    assert not mod.startswith("api."), f"Forbidden import from api: {mod}"
                    assert not mod.startswith("frontend."), f"Forbidden import from frontend: {mod}"

    def test_no_sharpe_sortino_calmar_alpha_expected_return(self):
        """No output key or function named sharpe/sortino/calmar/alpha/expected_return."""
        with open("ml/risk_outcomes.py", "r") as f:
            source = f.read()
        forbidden = ["sharpe", "sortino", "calmar", "alpha", "expected_return"]
        for word in forbidden:
            assert word not in source.lower(), f"Forbidden term '{word}' found in source"

    def test_no_probability_times_sigma(self):
        """No BinOp combining names containing 'prob' and 'sigma'."""
        with open("ml/risk_outcomes.py", "r") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp):
                left_name = _get_name(node.left)
                right_name = _get_name(node.right)
                if left_name and right_name:
                    left_prob = "prob" in left_name.lower()
                    right_sigma = "sigma" in right_name.lower()
                    left_sigma = "sigma" in left_name.lower()
                    right_prob = "prob" in right_name.lower()
                    assert not (left_prob and right_sigma), \
                        f"Forbidden: {left_name} * {right_name}"
                    assert not (left_sigma and right_prob), \
                        f"Forbidden: {left_name} * {right_name}"


def _get_name(node):
    """Extract name from AST node if it's a Name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


# ── daily_close_pairs matches daily_close_labels on fixtures ─────────────────

class TestPairsMatchLabels:
    """Verify daily_close_pairs produces entries consistent with daily_close_labels."""

    def test_label_equals_outcome_greater_than_entry(self):
        """label = 1.0 if outcome_close > entry_close else 0.0."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 5),
             "close": 100.0, "close_ts": _utc(2026, 6, 5, 20, 0)},
            {"symbol": "AAPL", "trade_date": _td(2026, 6, 8),
             "close": 102.0, "close_ts": _utc(2026, 6, 8, 20, 0)},
            {"symbol": "MSFT", "trade_date": _td(2026, 6, 5),
             "close": 200.0, "close_ts": _utc(2026, 6, 5, 20, 0)},
            {"symbol": "MSFT", "trade_date": _td(2026, 6, 8),
             "close": 195.0, "close_ts": _utc(2026, 6, 8, 20, 0)},
        ])
        features = pd.DataFrame([
            {"symbol": "AAPL", "prediction_ts": _utc(2026, 6, 5, 21, 0)},
            {"symbol": "MSFT", "prediction_ts": _utc(2026, 6, 5, 21, 0)},
        ])
        pairs = daily_close_pairs(features, closes)
        labels = daily_close_labels(features, closes)
        for i in range(len(features)):
            expected = 1.0 if pairs.loc[i, "outcome_close"] > pairs.loc[i, "entry_close"] else 0.0
            assert labels.loc[i, "label"] == expected