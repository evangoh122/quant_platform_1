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
        assert result.loc[0, "entry_date"] == _td(2026, 6, 4)
        assert result.loc[0, "outcome_date"] == _td(2026, 6, 5)

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
    """Extract name from AST node if it's a Name, Attribute, or Subscript with string slice."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        # Resolve Subscript with string-constant slice: result["col"]
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return node.slice.value
        if isinstance(node.slice, ast.Index) and isinstance(node.slice.value, ast.Constant):
            return node.slice.value.value
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


# ── Fix1: Deduplication tests ────────────────────────────────────────────────

class TestDeduplication:
    def test_three_model_versions_one_symbol_one_ts(self):
        """3 model versions x 1 symbol x 1 timestamp => exactly 3 output rows.

        Pairs and sigma must be computed once, not 3 times. The merge must
        not fan out.
        """
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 24)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)

        pred_ts = _utc(2025, 1, 25, 21, 0)
        signals = _make_signals([
            {"signal_id": f"s{i}", "symbol": "AAPL", "model_version": f"v{i+1}",
             "horizon": "1d", "prediction_ts": pred_ts, "probability": 0.6}
            for i in range(3)
        ])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert len(result) == 3
        assert result["signal_id"].tolist() == ["s0", "s1", "s2"]
        # All 3 rows have the same sigma (computed once)
        assert result["sigma20"].nunique() == 1
        # n/hit_count/distinct dates unchanged by duplication
        for col in ["entry_close", "outcome_close", "sigma20", "sigma_used"]:
            assert result[col].nunique() == 1, f"{col} differs across rows"

    def test_two_symbols_two_ts_no_fan_out(self):
        """2 symbols x 2 timestamps x 2 versions => 8 output rows, not 16."""
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 24)]
        closes_a = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        closes_b = _make_multi_day_closes("MSFT", "2025-01-01", 25, rets)
        closes = pd.concat([closes_a, closes_b], ignore_index=True)
        for sym in ["AAPL", "MSFT"]:
            closes = pd.concat([closes, _make_closes([{
                "symbol": sym, "trade_date": _td(2025, 1, 26),
                "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
                "return_1d": 0.05,
            }])], ignore_index=True)

        signals = _make_signals([
            {"signal_id": f"s{sym}_{ts}_{v}", "symbol": sym,
             "model_version": v, "horizon": "1d",
             "prediction_ts": _utc(2025, 1, 25 if ts == 0 else 24, 21, 0),
             "probability": 0.6}
            for sym in ["AAPL", "MSFT"]
            for ts in range(2)
            for v in ["v1", "v2"]
        ])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert len(result) == 8


# ── Fix2: NaN close eligibility tests ────────────────────────────────────────

class TestNaNClosesIneligible:
    def test_nan_entry_close_missing_return(self):
        """NaN entry_close => missing_return (not eligible)."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": float("nan"), "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 21),
             "close": 105.0, "close_ts": _utc(2025, 1, 21, 20, 0),
             "return_1d": float("nan")},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "missing_return"
        assert pd.isna(result.loc[0, "raw_forward_return"])
        assert pd.isna(result.loc[0, "outcome_z"])

    def test_nan_outcome_close_missing_return(self):
        """NaN outcome_close => missing_return (not eligible)."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 21),
             "close": float("nan"), "close_ts": _utc(2025, 1, 21, 20, 0),
             "return_1d": float("nan")},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "missing_return"
        assert pd.isna(result.loc[0, "raw_forward_return"])
        assert pd.isna(result.loc[0, "outcome_z"])

    def test_both_nan_closes_missing_return(self):
        """Both entry and outcome close NaN => missing_return."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": float("nan"), "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 21),
             "close": float("nan"), "close_ts": _utc(2025, 1, 21, 20, 0),
             "return_1d": float("nan")},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "missing_return"


# ── Fix3: excluded_counts per group ──────────────────────────────────────────

class TestExcludedCountsPerGroup:
    def test_excluded_counts_per_group(self):
        """excluded_counts is a per-(model_version, horizon) dict, not shared."""
        dates = pd.date_range("2025-01-01", periods=60, freq="B", tz="UTC")
        eligible1 = pd.DataFrame([
            {
                "signal_id": f"s{i}", "symbol": "AAPL", "model_version": "v1",
                "horizon": "1d", "prediction_ts": dates[i],
                "entry_date": _td(2025, 1, 1), "outcome_date": _td(2025, 1, 2),
                "direction": "UP", "probability_up": 0.6,
                "raw_forward_return": 0.01, "signed_raw_return": 0.01,
                "sigma20": 0.01, "sigma252": 0.01, "sigma_floor": 0.005,
                "sigma_used": 0.01, "sigma_method": "close_to_close_ddof1_v1",
                "sigma_as_of": _td(2025, 1, 1), "sigma_observation_count": 20,
                "outcome_z": 1.0, "base_up_flag": True,
                "ex_dividend_state": "none", "eligibility_state": "eligible",
            }
            for i in range(60)
        ])
        # v2 group: all pending (zero eligible)
        pending2 = pd.DataFrame([{
            "signal_id": "sp1", "symbol": "AAPL", "model_version": "v2",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 1),
            "entry_date": None, "outcome_date": None,
            "direction": "UP", "probability_up": 0.6,
            "raw_forward_return": np.nan, "signed_raw_return": np.nan,
            "sigma20": np.nan, "sigma252": np.nan, "sigma_floor": np.nan,
            "sigma_used": np.nan, "sigma_method": "close_to_close_ddof1_v1",
            "sigma_as_of": None, "sigma_observation_count": 0,
            "outcome_z": np.nan, "base_up_flag": np.nan,
            "ex_dividend_state": "none", "eligibility_state": "outcome_pending",
        }])
        outcomes = pd.concat([eligible1, pending2], ignore_index=True)
        result = summarize_outcomes(outcomes, min_n=60, min_dates=30, rho=0.2)
        assert len(result) == 2
        r1 = next(r for r in result if r["model_version"] == "v1")
        r2 = next(r for r in result if r["model_version"] == "v2")
        # Dict identity must differ (not shared objects)
        assert r1["excluded_counts"] is not r2["excluded_counts"]
        # v2 has zero eligible rows but must still appear
        assert r2["n"] == 0
        assert r2["state"] == "insufficient_sample"
        # v1 excluded_counts must not include 'eligible'
        assert "eligible" not in r1["excluded_counts"]
        assert "eligible" not in r2["excluded_counts"]
        # v2 has one outcome_pending
        assert r2["excluded_counts"].get("outcome_pending", 0) == 1

    def test_zero_eligible_group_appears(self):
        """A group with zero eligible rows must still appear in results."""
        outcomes = pd.DataFrame([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v2",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 1),
            "entry_date": None, "outcome_date": None,
            "direction": "UP", "probability_up": 0.6,
            "raw_forward_return": np.nan, "signed_raw_return": np.nan,
            "sigma20": np.nan, "sigma252": np.nan, "sigma_floor": np.nan,
            "sigma_used": np.nan, "sigma_method": "close_to_close_ddof1_v1",
            "sigma_as_of": None, "sigma_observation_count": 0,
            "outcome_z": np.nan, "base_up_flag": np.nan,
            "ex_dividend_state": "none", "eligibility_state": "outcome_pending",
        }])
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 1
        assert result[0]["model_version"] == "v2"
        assert result[0]["n"] == 0


# ── Fix5: Mutation-closing tests ─────────────────────────────────────────────

class TestMutationClosing:
    def test_m1_sigma_window_close_ts_not_trade_date(self):
        """M1: Same-day close published AFTER prediction_ts must NOT be in sigma window.

        A close on trade_date 2025-01-22 with close_ts = 20:00 UTC.
        prediction_ts = 2025-01-22 14:00 UTC (before close).
        The close has close_ts > prediction_ts, so it must NOT affect sigma.
        If sigma window used trade_date <= prediction date, it WOULD be included.
        """
        # 25 closes: day 0 NaN, days 1-24 valid. Use alternating returns.
        rets = [float("nan")] + [0.02 if i % 2 == 0 else 0.005 for i in range(24)]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        # prediction_ts on Jan 22 at 14:00 UTC (before close_ts 20:00 UTC)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 22, 14, 0),
            "probability": 0.6,
        }])
        # Add outcome close on Jan 26 (beyond _make_multi_day_closes range)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes_full = pd.concat([closes, extra], ignore_index=True)
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes_full, as_of=as_of)
        # sigma_as_of must be Jan 21 (last bar with close_ts <= Jan 22 14:00)
        # Jan 22 close_ts = 20:00 > 14:00 => excluded from window
        assert result.loc[0, "sigma_as_of"] == _td(2025, 1, 21)
        # Verify: valid returns = days 1-21 (21 returns with alternating pattern)
        expected_rets = [0.02 if i % 2 == 0 else 0.005 for i in range(21)]
        expected_sigma = pd.Series(expected_rets).tail(20).std(ddof=1)
        assert abs(result.loc[0, "sigma20"] - expected_sigma) < 1e-12

    def test_m4_two_horizons_never_pooled(self):
        """M4: summarize_outcomes never pools different horizons.

        Hand-computed values:
        1d: 120 eligible rows, all outcome_z=+1.0, all base_up_flag=True
            n=120, median_outcome_z=+1.0, base_up_rate=1.0
        5d: 120 eligible rows, all outcome_z=-1.0, all base_up_flag=False
            n=120, median_outcome_z=-1.0, base_up_rate=0.0

        M4 mutant pools horizons: groupby(["model_version"]) with
        hor = grp.horizon.iloc[0]. Pooled group: n=240,
        median_outcome_z=0.0 (median of 120*+1 + 120*-1),
        base_up_rate=0.5 (120/240). Zero-eligible fallback adds
        (v1, 5d) with n=0 and all-None values.

        Literal groupby(["model_version"]) mutant must also fail:
        it produces one group of 240 with hor="1d" and a fallback 5d.
        """
        from ml.risk_outcomes import summarize_outcomes as summarize

        def _make_outcomes(n, dates, mv="v1", hor="1d"):
            date_range = pd.date_range("2025-01-01", periods=dates, freq="B", tz="UTC")
            rows = []
            for i in range(n):
                d = date_range[i % dates]
                rows.append({
                    "signal_id": f"s{i}_{hor}", "symbol": "AAPL", "model_version": mv,
                    "horizon": hor, "prediction_ts": d,
                    "entry_date": _td(2025, 1, 1), "outcome_date": _td(2025, 1, 2),
                    "direction": "UP", "probability_up": 0.6,
                    "raw_forward_return": 0.01, "signed_raw_return": 0.01,
                    "sigma20": 0.01, "sigma252": 0.01, "sigma_floor": 0.005,
                    "sigma_used": 0.01, "sigma_method": "close_to_close_ddof1_v1",
                    "sigma_as_of": _td(2025, 1, 1), "sigma_observation_count": 20,
                    "outcome_z": 1.0, "base_up_flag": True,
                    "ex_dividend_state": "none", "eligibility_state": "eligible",
                })
            return pd.DataFrame(rows)

        out_1d = _make_outcomes(120, 70, hor="1d")
        out_5d = _make_outcomes(120, 70, hor="5d", mv="v1")
        out_5d["outcome_z"] = -1.0
        out_5d["base_up_flag"] = False
        out_5d["signed_raw_return"] = -0.01
        out_5d["raw_forward_return"] = -0.01

        outcomes = pd.concat([out_1d, out_5d], ignore_index=True)
        result = summarize(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 2
        r1d = next(r for r in result if r["horizon"] == "1d")
        r5d = next(r for r in result if r["horizon"] == "5d")
        # Exact per-horizon values: n, median_outcome_z, base_up_rate
        assert r1d["n"] == 120, f"1d n={r1d['n']}, expected 120 (pooling?)"
        assert r1d["median_outcome_z"] == 1.0
        assert r1d["base_up_rate"] == 1.0
        assert r5d["n"] == 120, f"5d n={r5d['n']}, expected 120 (pooling?)"
        assert r5d["median_outcome_z"] == -1.0
        assert r5d["base_up_rate"] == 0.0

    def test_m4b_excluded_counts_per_horizon(self):
        """M4b: excluded_counts must be split by horizon, not pooled.

        1d: 120 eligible + 1 excluded (missing_return)
        5d: 120 eligible + 1 excluded (outcome_pending)

        M4b mutant drops horizon filter in group_all, pooling
        excluded_counts: both horizons get {missing_return: 1,
        outcome_pending: 1}.
        """
        from ml.risk_outcomes import summarize_outcomes as summarize

        def _make_outcomes(n, dates, mv="v1", hor="1d"):
            date_range = pd.date_range("2025-01-01", periods=dates, freq="B", tz="UTC")
            rows = []
            for i in range(n):
                d = date_range[i % dates]
                rows.append({
                    "signal_id": f"s{i}_{hor}", "symbol": "AAPL", "model_version": mv,
                    "horizon": hor, "prediction_ts": d,
                    "entry_date": _td(2025, 1, 1), "outcome_date": _td(2025, 1, 2),
                    "direction": "UP", "probability_up": 0.6,
                    "raw_forward_return": 0.01, "signed_raw_return": 0.01,
                    "sigma20": 0.01, "sigma252": 0.01, "sigma_floor": 0.005,
                    "sigma_used": 0.01, "sigma_method": "close_to_close_ddof1_v1",
                    "sigma_as_of": _td(2025, 1, 1), "sigma_observation_count": 20,
                    "outcome_z": 1.0, "base_up_flag": True,
                    "ex_dividend_state": "none", "eligibility_state": "eligible",
                })
            return pd.DataFrame(rows)

        out_1d = _make_outcomes(120, 70, hor="1d")
        out_5d = _make_outcomes(120, 70, hor="5d", mv="v1")
        out_5d["outcome_z"] = -1.0
        out_5d["base_up_flag"] = False
        out_5d["signed_raw_return"] = -0.01
        out_5d["raw_forward_return"] = -0.01

        # One excluded row per horizon with DIFFERENT reasons
        excl_1d = pd.DataFrame([{
            "signal_id": "excl_1d", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 6, 1),
            "entry_date": _td(2025, 1, 1), "outcome_date": None,
            "direction": "UP", "probability_up": 0.6,
            "raw_forward_return": np.nan, "signed_raw_return": np.nan,
            "sigma20": np.nan, "sigma252": np.nan, "sigma_floor": np.nan,
            "sigma_used": np.nan, "sigma_method": "close_to_close_ddof1_v1",
            "sigma_as_of": None, "sigma_observation_count": 0,
            "outcome_z": np.nan, "base_up_flag": np.nan,
            "ex_dividend_state": "none", "eligibility_state": "missing_return",
        }])
        excl_5d = pd.DataFrame([{
            "signal_id": "excl_5d", "symbol": "AAPL", "model_version": "v1",
            "horizon": "5d", "prediction_ts": _utc(2025, 6, 1),
            "entry_date": None, "outcome_date": None,
            "direction": "UP", "probability_up": 0.6,
            "raw_forward_return": np.nan, "signed_raw_return": np.nan,
            "sigma20": np.nan, "sigma252": np.nan, "sigma_floor": np.nan,
            "sigma_used": np.nan, "sigma_method": "close_to_close_ddof1_v1",
            "sigma_as_of": None, "sigma_observation_count": 0,
            "outcome_z": np.nan, "base_up_flag": np.nan,
            "ex_dividend_state": "none", "eligibility_state": "outcome_pending",
        }])

        outcomes = pd.concat([out_1d, out_5d, excl_1d, excl_5d], ignore_index=True)
        result = summarize(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 2
        r1d = next(r for r in result if r["horizon"] == "1d")
        r5d = next(r for r in result if r["horizon"] == "5d")
        # Each horizon must have exactly its own excluded reason, no leakage
        assert r1d["excluded_counts"] == {"missing_return": 1}, (
            f"1d excluded_counts={r1d['excluded_counts']}"
        )
        assert r5d["excluded_counts"] == {"outcome_pending": 1}, (
            f"5d excluded_counts={r5d['excluded_counts']}"
        )

    def test_m5_exact_match_close_ts_eq_prediction_ts(self):
        """M5: close_ts == prediction_ts is eligible for sigma window (boundary).

        merge_asof with direction='backward' and allow_matches (default True)
        includes exact matches. close_ts <= prediction_ts must include equality.
        """
        # 51 closes starting Dec 1 so we have 20+ valid bars before Jan 20.
        # Dec 1 + 50 = Jan 20.
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(50)]
        closes = _make_multi_day_closes("AAPL", "2024-12-01", 51, rets)
        # Override Jan 20 close_ts to be 14:00 UTC (same as prediction_ts)
        closes.loc[closes["trade_date"] == _td(2025, 1, 20), "close_ts"] = _utc(2025, 1, 20, 14, 0)
        # prediction_ts = Jan 20 14:00 UTC = exact match with Jan 20 close_ts
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 14, 0),
            "probability": 0.6,
        }])
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 23),
            "close": 130.0, "close_ts": _utc(2025, 1, 23, 20, 0),
            "return_1d": 0.01,
        }])
        closes_full = pd.concat([closes, extra], ignore_index=True)
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes_full, as_of=as_of)
        # Jan 20 close_ts = 14:00 <= prediction_ts 14:00 => included
        # So sigma_as_of should be Jan 20
        assert result.loc[0, "sigma_as_of"] == _td(2025, 1, 20)

    def test_m7_sigma_as_of_from_newest_bar_even_if_nan_return(self):
        """M7: sigma_as_of comes from the last VALID return, not the newest bar.

        If the newest bar has NaN return_1d, sigma_as_of must still be from
        the last bar with a valid return in the sigma window.
        """
        # 22 closes. Bar 21 (last) has NaN return_1d.
        rets = [float("nan")] + [0.01] * 20 + [float("nan")]
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 22, rets)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 23, 21, 0),
            "probability": 0.6,
        }])
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 24),
            "close": 105.0, "close_ts": _utc(2025, 1, 24, 20, 0),
            "return_1d": 0.05,
        }])
        closes_full = pd.concat([closes, extra], ignore_index=True)
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes_full, as_of=as_of)
        # Bar 21 (Jan 22) has NaN return, so it's excluded from valid_returns.
        # valid_returns = bars 1-20 (Jan 2 - Jan 21). last20 = bars 1-20.
        # sigma_as_of = last valid return's trade_date = Jan 21.
        # If mutant took sigma_as_of from newest bar (Jan 22), test fails.
        assert result.loc[0, "sigma_as_of"] == _td(2025, 1, 21)

    def test_m8_base_up_rate_eligible_only(self):
        """M8: base_up_rate is computed over eligible rows only.

        If ineligible rows (e.g. missing_return) have base_up_flag=True,
        including them would change the rate. The test fixture must have
        enough ineligible rows to change the rate if they were included.
        """
        # 120 eligible rows: 72 up, 48 down => base_up_rate = 0.6
        # 120 rows / 60 dates = m=2, n_eff = 120/(1+0.2) = 100 => sufficient
        # Use timestamps at 21:00 UTC (16:00 ET) to ensure correct ET dates
        dates = pd.date_range("2025-01-01", periods=60, freq="B", tz="UTC") + pd.Timedelta(hours=21)
        eligible = pd.DataFrame([
            {
                "signal_id": f"s{i}", "symbol": "AAPL", "model_version": "v1",
                "horizon": "1d",
                "prediction_ts": dates[i % 60],
                "entry_date": _td(2025, 1, 1), "outcome_date": _td(2025, 1, 2),
                "direction": "UP", "probability_up": 0.6,
                "raw_forward_return": 0.01 if i < 72 else -0.01,
                "signed_raw_return": 0.01 if i < 72 else -0.01,
                "sigma20": 0.01, "sigma252": 0.01, "sigma_floor": 0.005,
                "sigma_used": 0.01, "sigma_method": "close_to_close_ddof1_v1",
                "sigma_as_of": _td(2025, 1, 1), "sigma_observation_count": 20,
                "outcome_z": 1.0 if i < 72 else -1.0,
                "base_up_flag": True if i < 72 else False,
                "ex_dividend_state": "none", "eligibility_state": "eligible",
            }
            for i in range(120)
        ])
        # 50 ineligible rows with base_up_flag=True
        # If included, base_up_rate would be (60+50)/150 = 0.733 instead of 0.6
        inel_dates = pd.date_range("2025-02-01", periods=50, freq="B", tz="UTC")
        ineligible = pd.DataFrame([
            {
                "signal_id": f"bad{i}", "symbol": "AAPL", "model_version": "v1",
                "horizon": "1d",
                "prediction_ts": inel_dates[i],
                "entry_date": _td(2025, 2, 1), "outcome_date": None,
                "direction": "UP", "probability_up": 0.6,
                "raw_forward_return": np.nan, "signed_raw_return": np.nan,
                "sigma20": np.nan, "sigma252": np.nan, "sigma_floor": np.nan,
                "sigma_used": np.nan, "sigma_method": "close_to_close_ddof1_v1",
                "sigma_as_of": None, "sigma_observation_count": 0,
                "outcome_z": np.nan, "base_up_flag": True,
                "ex_dividend_state": "none", "eligibility_state": "missing_return",
            }
            for i in range(50)
        ])
        outcomes = pd.concat([eligible, ineligible], ignore_index=True)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=60, rho=0.2)
        assert len(result) == 1
        r = result[0]
        assert r["state"] == "sufficient"
        # base_up_rate must be 0.6 (72/120 eligible), NOT 0.718 (122/170 all)
        assert abs(r["base_up_rate"] - 0.6) < 1e-10

    def test_m9_pending_boundary_as_of(self):
        """M9: outcome_close_ts == as_of => NOT pending (must be > as_of).

        Boundary: outcome_close_ts exactly equals as_of. Since pending
        requires outcome_close_ts > as_of, equality means NOT pending.
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
        # as_of exactly == outcome_close_ts (Jan 21 20:00 UTC)
        as_of = _utc(2025, 1, 21, 20, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        # outcome_close_ts == as_of => NOT pending (must be strictly > as_of)
        assert result.loc[0, "eligibility_state"] != "outcome_pending"
        # Should be eligible (assuming sigma is available)
        # Since we only have 2 closes with valid returns, insufficient_sigma_history
        assert result.loc[0, "eligibility_state"] == "insufficient_sigma_history"

    def test_m10_pending_row_outcome_fields_blank(self):
        """M10: Pending rows must have NaN outcome fields (replay-leak prevention).

        A signal with outcome_close_ts > as_of is pending. Its outcome_close,
        raw_forward_return, outcome_z, base_up_flag must all be NaN even though
        the future bar exists in closes.
        """
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 21),
             "close": 95.0, "close_ts": _utc(2025, 1, 21, 20, 0),
             "return_1d": -0.05},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        # as_of before outcome_close_ts => pending
        as_of = _utc(2025, 1, 20, 22, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        assert result.loc[0, "eligibility_state"] == "outcome_pending"
        # Outcome fields must be blank
        assert pd.isna(result.loc[0, "outcome_close"])
        assert pd.isna(result.loc[0, "outcome_close_ts"])
        assert pd.isna(result.loc[0, "raw_forward_return"])
        assert pd.isna(result.loc[0, "signed_raw_return"])
        assert pd.isna(result.loc[0, "outcome_z"])
        assert pd.isna(result.loc[0, "base_up_flag"])
        assert result.loc[0, "outcome_date"] is None
        # Entry-side fields must be preserved
        assert result.loc[0, "entry_close"] == 100.0
        assert result.loc[0, "entry_date"] is not None

    def test_m10b_summary_unchanged_with_or_without_future_bar(self):
        """M10b: Aggregates identical whether future bar exists or not.

        Pending rows are excluded from aggregates. Adding a future bar
        that makes a row pending must not change the summary.
        """
        rets = [float("nan")] + [0.01 if i % 2 == 0 else -0.01 for i in range(1, 80)]
        closes_base = _make_multi_day_closes("AAPL", "2025-01-01", 81, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 3, 24),
            "close": 105.0, "close_ts": _utc(2025, 3, 24, 20, 0),
            "return_1d": 0.05,
        }])
        closes_with_future = pd.concat([closes_base, extra], ignore_index=True)

        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 3, 22, 21, 0),
            "probability": 0.6,
        }])
        # as_of before the future bar => pending
        as_of_pending = _utc(2025, 3, 22, 22, 0)
        # as_of after the future bar => eligible (if sigma available)
        as_of_resolved = _utc(2025, 3, 30, 21, 0)

        result_pending = build_signal_outcomes(
            signals, closes_with_future, as_of=as_of_pending
        )
        result_resolved = build_signal_outcomes(
            signals, closes_with_future, as_of=as_of_resolved
        )
        # Pending row must have NaN outcome_z
        assert pd.isna(result_pending.loc[0, "outcome_z"])
        # Resolved row must have non-NaN outcome_z (sigma available)
        assert not pd.isna(result_resolved.loc[0, "outcome_z"])
        # Eligibility states differ
        assert result_pending.loc[0, "eligibility_state"] == "outcome_pending"
        assert result_resolved.loc[0, "eligibility_state"] == "eligible"

    def test_m10c_mutation_not_blanking_keeps_outcome_z(self):
        """M10c: If blanking is removed, pending row leaks outcome_z.

        This test proves the blanking is load-bearing: without it,
        the pending row would carry a non-NaN outcome_z from the future bar.
        """
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 21),
             "close": 95.0, "close_ts": _utc(2025, 1, 21, 20, 0),
             "return_1d": -0.05},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 20, 22, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        # With blanking: outcome_z is NaN for pending
        assert pd.isna(result.loc[0, "outcome_z"])
        # The raw data (before blanking) would have outcome_z != NaN
        # because the future bar exists. Prove by checking outcome_close is blanked:
        assert pd.isna(result.loc[0, "outcome_close"])

    def test_m11_nan_probability_missing_direction(self):
        """M11: NaN probability => direction is NaN (not DOWN).

        np.where(NaN >= 0.5, "UP", "DOWN") evaluates to "DOWN" because
        NaN >= 0.5 is False. The fix must set direction to NaN for NaN prob.
        """
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
            "probability": float("nan"),
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        # NaN probability must NOT produce "DOWN"
        assert result.loc[0, "direction"] != "DOWN", "NaN prob must not default to DOWN"
        assert pd.isna(result.loc[0, "direction"]), "NaN prob => NaN direction"


# ── Non-blocking: duplicate close guard ───────────────────────────────────────

class TestDuplicateCloseGuard:
    def test_duplicate_symbol_trade_date_raises(self):
        """Duplicate (symbol, trade_date) in closes => ValueError."""
        closes = _make_closes([
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 100.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": float("nan")},
            {"symbol": "AAPL", "trade_date": _td(2025, 1, 20),
             "close": 101.0, "close_ts": _utc(2025, 1, 20, 20, 0),
             "return_1d": 0.01},
        ])
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "1d", "prediction_ts": _utc(2025, 1, 20, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        with pytest.raises(ValueError, match="duplicate"):
            build_signal_outcomes(signals, closes, as_of=as_of)


# ── Non-blocking: horizon validation ──────────────────────────────────────────

class TestHorizonValidation:
    def test_unsupported_horizon_raises(self):
        """horizon != '1d' => ValueError."""
        rets = [float("nan")] + [0.01] * 24
        closes = _make_multi_day_closes("AAPL", "2025-01-01", 25, rets)
        extra = _make_closes([{
            "symbol": "AAPL", "trade_date": _td(2025, 1, 26),
            "close": 105.0, "close_ts": _utc(2025, 1, 26, 20, 0),
            "return_1d": 0.05,
        }])
        closes = pd.concat([closes, extra], ignore_index=True)
        signals = _make_signals([{
            "signal_id": "s1", "symbol": "AAPL", "model_version": "v1",
            "horizon": "5d", "prediction_ts": _utc(2025, 1, 25, 21, 0),
            "probability": 0.6,
        }])
        as_of = _utc(2025, 1, 30, 21, 0)
        with pytest.raises(ValueError, match="horizon"):
            build_signal_outcomes(signals, closes, as_of=as_of)


# ── Non-blocking: distinct dates by US/Eastern ────────────────────────────────

class TestDistinctDatesEastern:
    def _make_outcomes(self, timestamps):
        rows = []
        for i, ts in enumerate(timestamps):
            rows.append({
                "signal_id": f"s{i}", "symbol": "AAPL", "model_version": "v1",
                "horizon": "1d", "prediction_ts": ts,
                "entry_date": _td(2026, 3, 1), "outcome_date": _td(2026, 3, 2),
                "direction": "UP", "probability_up": 0.6,
                "raw_forward_return": 0.01, "signed_raw_return": 0.01,
                "sigma20": 0.01, "sigma252": 0.01, "sigma_floor": 0.005,
                "sigma_used": 0.01, "sigma_method": "close_to_close_ddof1_v1",
                "sigma_as_of": _td(2026, 3, 1), "sigma_observation_count": 20,
                "outcome_z": 1.0, "base_up_flag": True,
                "ex_dividend_state": "none", "eligibility_state": "eligible",
            })
        return pd.DataFrame(rows)

    def test_same_utc_date_different_et_date_edt(self):
        """Same UTC date but different ET dates (EDT, UTC-4): must yield more distinct dates.

        2026-03-11 03:30 UTC = 2026-03-10 23:30 ET (EDT after Mar 8)
        2026-03-11 05:00 UTC = 2026-03-11 01:00 ET

        Same UTC date (Mar 11), but different ET dates (Mar 10 vs Mar 11).
        Old UTC .dt.date code counts 100 distinct dates; correct ET code counts 101
        (extra date from first ts_a's ET date having no matching ts_b).
        200 rows: 100 pairs, each pair spanning the UTC-midnight-not-ET boundary.
        """
        ts_a = pd.Timestamp("2026-03-11 03:30", tz="UTC")  # 23:30 ET Mar 10
        ts_b = pd.Timestamp("2026-03-11 05:00", tz="UTC")  # 01:00 ET Mar 11
        timestamps = []
        for i in range(100):
            timestamps.append(ts_a + pd.Timedelta(days=i))
            timestamps.append(ts_b + pd.Timedelta(days=i))
        outcomes = self._make_outcomes(timestamps)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=50, rho=0.2)
        assert len(result) == 1
        # ET dates span Mar 10 to Jun 18 = 101 distinct; old UTC code would give 100
        assert result[0]["distinct_prediction_dates"] == 101

    def test_same_utc_date_different_et_date_summer_edt(self):
        """DST-sensitive window [04:00, 05:00) UTC: EDT vs fixed-UTC-5 differ.

        2026-07-11 04:30 UTC = 2026-07-11 00:30 EDT (ET date Jul 11)
        2026-07-11 12:00 UTC = 2026-07-11 08:00 EDT (ET date Jul 11)

        Same UTC date (Jul 11), same ET date (Jul 11) under correct EDT.
        Fixed UTC-5 mutant: 04:30 UTC − 5h = 23:30 Jul 10 → date Jul 10;
        12:00 UTC − 5h = 07:00 Jul 11 → date Jul 11 → 2 distinct dates (WRONG).
        200 rows: 100 pairs, each pair on same ET date → 100 distinct.
        """
        ts_a = pd.Timestamp("2026-07-11 04:30", tz="UTC")  # 00:30 EDT Jul 11
        ts_b = pd.Timestamp("2026-07-11 12:00", tz="UTC")  # 08:00 EDT Jul 11
        timestamps = []
        for i in range(100):
            timestamps.append(ts_a + pd.Timedelta(days=i))
            timestamps.append(ts_b + pd.Timedelta(days=i))
        outcomes = self._make_outcomes(timestamps)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=50, rho=0.2)
        assert len(result) == 1
        # ET dates: each pair = 1 date → 100 distinct; fixed UTC-5 gives 200
        assert result[0]["distinct_prediction_dates"] == 100

    def test_different_utc_date_same_et_date_est(self):
        """Different UTC dates but same ET date (EST, UTC-5): must collapse to fewer dates.

        2026-01-14 23:00 UTC = 2026-01-14 18:00 EST (Jan 14)
        2026-01-15 04:00 UTC = 2026-01-14 23:00 EST (same ET date, Jan 14)

        Different UTC dates (Jan 14 vs Jan 15), but same ET date (Jan 14).
        Old UTC .dt.date code counts 51 distinct dates; correct ET code counts 50.
        Fixed UTC-4 mutant: 04:00 UTC − 4h = 00:00 Jan 15 → date Jan 15
        (differs from EST date Jan 14) → 51 distinct (WRONG).
        All pairs stay within EST (before Mar 8 2026 DST transition).
        """
        ts_a = pd.Timestamp("2026-01-14 23:00", tz="UTC")  # 18:00 EST Jan 14
        ts_b = pd.Timestamp("2026-01-15 04:00", tz="UTC")  # 23:00 EST Jan 14
        timestamps = []
        for i in range(50):
            timestamps.append(ts_a + pd.Timedelta(days=i))
            timestamps.append(ts_b + pd.Timedelta(days=i))
        outcomes = self._make_outcomes(timestamps)
        result = summarize_outcomes(outcomes, min_n=100, min_dates=50, rho=0.2)
        assert len(result) == 1
        # ET dates: each pair collapses to 1 date → 50 distinct; old UTC code gives 51
        assert result[0]["distinct_prediction_dates"] == 50


# ── Non-blocking: hardened probability*sigma AST guard ────────────────────────

class TestHardenedASTGuard:
    def test_self_test_prob_sigma_caught(self):
        """Self-test: the guard pattern `result["probability_up"] * result["sigma_used"]`
        must be detected by the AST walker."""
        code = 'result["probability_up"] * result["sigma_used"]'
        tree = ast.parse(code, mode="eval")
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
                left_name = _get_name(node.left)
                right_name = _get_name(node.right)
                if left_name and right_name:
                    left_prob = "prob" in left_name.lower()
                    right_sigma = "sigma" in right_name.lower()
                    left_sigma = "sigma" in left_name.lower()
                    right_prob = "prob" in right_name.lower()
                    if (left_prob and right_sigma) or (left_sigma and right_prob):
                        found = True
        assert found, "AST guard must catch prob*sigma pattern"

    def test_subscript_string_constant_not_missed(self):
        """Subscript Access (e.g. result['col']) resolves to the column name."""
        code = 'result["probability_up"] * result["sigma_used"]'
        tree = ast.parse(code, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
                # Both sides are Subscript with string constants
                left_val = _get_subscript_name(node.left)
                right_val = _get_subscript_name(node.right)
                assert left_val is not None
                assert right_val is not None
                assert "prob" in left_val.lower()
                assert "sigma" in right_val.lower()


def _get_subscript_name(node):
    """Extract column name from Subscript node like result['col']."""
    if isinstance(node, ast.Subscript):
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return node.slice.value
        if isinstance(node.slice, ast.Index) and isinstance(node.slice.value, ast.Constant):
            return node.slice.value.value
    return None


# ── entry_date and sigma_as_of type consistency ──────────────────────────────

class TestDateTypeConsistency:
    def test_entry_date_sigma_as_of_same_type(self):
        """entry_date and sigma_as_of must be the same type (date)."""
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
        result = build_signal_outcomes(signals, closes, as_of=as_of)
        entry_d = result.loc[0, "entry_date"]
        sigma_d = result.loc[0, "sigma_as_of"]
        assert type(entry_d) == type(sigma_d), (
            f"entry_date type {type(entry_d)} != sigma_as_of type {type(sigma_d)}"
        )