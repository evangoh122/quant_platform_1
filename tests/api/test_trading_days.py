"""tests/api/test_trading_days.py — Fix 2: weekday-approximation trading-day helper.

Verifies that ``start_for_trading_days`` correctly skips weekends when counting
trading days backward from a reference date.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from api.trading_days import start_for_trading_days


class TestStartForTradingDays:
    """Unit tests for the pure ``start_for_trading_days`` function."""

    def test_wednesday_back_5_trading_days(self):
        """5 trading days back from a Wednesday = the previous Wednesday
        (spans one weekend: Wed→Tue→Mon→Fri→Thu→Wed)."""
        end = date(2026, 10, 7)  # Wednesday
        result = start_for_trading_days(end, 5)
        assert result == date(2026, 9, 30)  # Previous Wednesday

    def test_monday_back_1_trading_day(self):
        """1 trading day back from Monday = Friday."""
        end = date(2026, 10, 5)  # Monday
        result = start_for_trading_days(end, 1)
        assert result == date(2026, 10, 2)  # Friday

    def test_saturday_end_rolls_back_to_friday(self):
        """If end is Saturday, we roll back to Friday without consuming a count,
        then count 1 more trading day back = Thursday."""
        end = date(2026, 10, 3)  # Saturday
        result = start_for_trading_days(end, 1)
        assert result == date(2026, 10, 1)  # Thursday (1 trading day back from Friday)

    def test_sunday_end_rolls_back_to_friday(self):
        """If end is Sunday, we roll back to Friday without consuming a count,
        then count 1 more trading day back = Thursday."""
        end = date(2026, 10, 4)  # Sunday
        result = start_for_trading_days(end, 1)
        assert result == date(2026, 10, 1)  # Thursday (1 trading day back from Friday)

    def test_n252_lands_approximately_one_year_back(self):
        """252 trading days ≈ 1 year of weekdays. From 2026-10-07 (Wed),
        252 weekdays back should land around early October 2025."""
        end = date(2026, 10, 7)  # Wednesday
        result = start_for_trading_days(end, 252)
        # 252 weekdays ≈ 50.4 weeks ≈ 353 calendar days
        # 2026-10-07 minus 353 days ≈ 2025-10-19 (a Sunday, but start lands on a weekday)
        assert result.weekday() < 5, f"Result {result} must be a weekday"
        # Should be roughly 1 year back (within a month)
        assert result.year == 2025
        assert 9 <= result.month <= 12

    def test_one_trading_day_from_friday(self):
        """1 trading day back from Friday = Thursday."""
        end = date(2026, 10, 2)  # Friday
        result = start_for_trading_days(end, 1)
        assert result == date(2026, 10, 1)  # Thursday

    def test_weekend_span(self):
        """Spanning a weekend: 3 trading days back from Monday = Wednesday."""
        end = date(2026, 10, 5)  # Monday
        result = start_for_trading_days(end, 3)
        assert result == date(2026, 9, 30)  # Wednesday


class TestWeekendEndConsistency:
    """CodeRabbit finding (d): Fri/Sat/Sun ends must produce the same start.

    Contract: end rolls back to the latest session on or before end, then
    counts back n sessions.  Saturday and Sunday's session is the preceding
    Friday, so Fri/Sat/Sun with the same n yield identical starts.
    """

    @pytest.mark.parametrize("end,n,expected", [
        # n=1: Fri 2026-10-02 → roll back to Fri (no count) → 1 back = Thu 10-01
        #       Sat 2026-10-03 → roll back to Fri (no count) → 1 back = Thu 10-01
        #       Sun 2026-10-04 → roll back to Fri (no count) → 1 back = Thu 10-01
        (date(2026, 10, 2), 1, date(2026, 10, 1)),  # Friday
        (date(2026, 10, 3), 1, date(2026, 10, 1)),  # Saturday
        (date(2026, 10, 4), 1, date(2026, 10, 1)),  # Sunday
        # n=5: Fri → 5 back = Fri 2026-09-25
        #       Sat → roll to Fri → 5 back = Fri 2026-09-25
        #       Sun → roll to Fri → 5 back = Fri 2026-09-25
        (date(2026, 10, 2), 5, date(2026, 9, 25)),  # Friday
        (date(2026, 10, 3), 5, date(2026, 9, 25)),  # Saturday
        (date(2026, 10, 4), 5, date(2026, 9, 25)),  # Sunday
    ], ids=[
        "fri-n1", "sat-n1", "sun-n1",
        "fri-n5", "sat-n5", "sun-n5",
    ])
    def test_weekend_ends_same_as_friday(self, end, n, expected):
        """Fri/Sat/Sun with same n must all return the same start date.

        Arithmetic (n=1):
          Fri 10-02: session is Fri 10-02 → count 1 back → Thu 10-01
          Sat 10-03: roll to Fri 10-02 → count 1 back → Thu 10-01
          Sun 10-04: roll to Fri 10-02 → count 1 back → Thu 10-01

        Arithmetic (n=5):
          Fri 10-02: Thu→Wed→Tue→Mon→Fri = 5 back → Fri 09-25
          Sat 10-03: roll to Fri 10-02, same 5 back → Fri 09-25
          Sun 10-04: roll to Fri 10-02, same 5 back → Fri 09-25
        """
        result = start_for_trading_days(end, n)
        assert result == expected

    def test_result_is_always_weekday(self):
        """For various n values, the result must always be a weekday."""
        end = date(2026, 10, 7)
        for n in range(1, 300):
            result = start_for_trading_days(end, n)
            assert result.weekday() < 5, f"n={n}: result {result} is not a weekday"

    def test_weekday_label_anchor(self):
        """2026-09-25 is a Friday (weekday=4). Anchors the labels above."""
        assert date(2026, 9, 25).weekday() == 4, "2026-09-25 must be Friday"
        assert date(2026, 10, 1).weekday() == 3, "2026-10-01 must be Thursday"


class TestMarketRouteTradingDays:
    """API-level test: verify the market route uses the helper (not timedelta)."""

    @pytest.fixture
    def client(self, fake_lakebase):
        from fastapi.testclient import TestClient
        from api.main import create_app
        return TestClient(create_app())

    def test_start_time_matches_helper_output(self, client, monkeypatch):
        """The start_time passed to get_market_features must equal the output
        of start_for_trading_days, not a simple timedelta."""
        from datetime import date, datetime, timezone
        from api.trading_days import start_for_trading_days

        frozen_now = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
        captured = {}

        def _mock_get_market_features(symbol, start_time, end_time, *, limit=5000):
            captured["start_time"] = start_time
            return []

        def _mock_get_options_features(symbol, expiry=None, *, limit=5000):
            return []

        # Create a datetime subclass that returns frozen_now from now()
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen_now

        monkeypatch.setattr("api.routes.market.datetime", FrozenDatetime)

        with patch("agent.tools_retrieval.get_market_features", side_effect=_mock_get_market_features), \
             patch("agent.tools_retrieval.get_options_features", side_effect=_mock_get_options_features), \
             patch("api.routes.market.read_delta", side_effect=lambda fn: (fn(), "fresh", "ok")):
            resp = client.get("/api/market/AAPL?days=252", headers={"x-forwarded-email": "u@test.com"})

        assert resp.status_code == 200
        expected_start = start_for_trading_days(frozen_now.date(), 252)
        expected_str = expected_start.strftime("%Y-%m-%dT") + frozen_now.strftime("%H:%M:%SZ")
        assert captured["start_time"] == expected_str, (
            f"start_time {captured['start_time']} != helper output {expected_str}"
        )
