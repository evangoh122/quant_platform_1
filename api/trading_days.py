"""api/trading_days.py — weekday-approximation trading-day helper.

Converts a count of trading days to a calendar start date by skipping
weekends (Saturday and Sunday).  NYSE holidays are *not* included; callers
that require holiday-awareness should layer a holiday calendar on top.

The approximation is conservative: the returned ``start`` is the earliest
calendar date that could contain ``n`` weekday (Mon-Fri) trading sessions
when counting backward from ``end``.
"""
from __future__ import annotations

from datetime import date, timedelta


def start_for_trading_days(end: date, n: int) -> date:
    """Return the start date ``n`` trading days (weekdays) before ``end``.

    A "trading day" is a Monday–Friday.  ``end`` itself is never counted:
    the helper walks back over ``n`` weekdays strictly before ``end``, so
    ``start_for_trading_days(Wed, 5)`` returns the preceding Wednesday
    (5 weekdays back, spanning a weekend).  If ``end`` falls on a weekend it
    is first rolled back to the preceding Friday without consuming a count.

    Parameters
    ----------
    end:
        The reference date (typically today / the query end date).
    n:
        Number of trading days to look back.  Must be >= 1.

    Returns
    -------
    date
        The calendar start date.  Falls back to a simple calendar-day
        subtraction for ``n < 1`` (degenerate, but guards against callers
        passing 0 or negative values).
    """
    if n < 1:
        return end - timedelta(days=n)

    # Walk backward from *end*, counting only weekdays.
    # If end is a weekend, the first step lands on the prior Friday without
    # consuming a trading-day count — the trading session for a Saturday or
    # Sunday is the preceding Friday.
    current = end
    remaining = n

    # Step 1: if end is a weekend, roll back to the prior Friday (no count).
    if current.weekday() == 5:  # Saturday
        current -= timedelta(days=1)
    elif current.weekday() == 6:  # Sunday
        current -= timedelta(days=2)

    # Step 2: count remaining trading days backward.
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            remaining -= 1

    return current
