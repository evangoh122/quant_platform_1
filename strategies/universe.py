"""Reference (pandas) implementation of the point-in-time tradable universe.

This mirrors the production SQL ``gold/06_gold_tradable_universe.sql`` so the
point-in-time semantics — a symbol's membership on date ``t`` depends only on
bars strictly before ``t`` — can be unit-tested offline. The SQL is the
production implementation; this module is the executable spec.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def screen_universe(
    panel: pd.DataFrame,
    n: int = 300,
    adv_window: int = 60,
    min_history: int = 252,
    recency_sessions: int = 5,
) -> pd.DataFrame:
    """Top-``n`` symbols by trailing median dollar volume, point-in-time.

    Args:
        panel: long frame with columns ``symbol``, ``event_date``,
            ``dollar_volume``. One row per symbol-day.
        n: number of names per date (default 300).
        adv_window: trailing window (sessions) for the median dollar volume.
        min_history: minimum prior sessions required.
        recency_sessions: must have traded on each of the last N prior sessions.

    Returns a long frame ``[trade_date, symbol, med_adv_60d, adv_rank]`` where a
    symbol's membership on ``trade_date`` uses only bars with
    ``event_date < trade_date``.
    """
    df = panel.sort_values(["symbol", "event_date"]).reset_index(drop=True)
    g = df.groupby("symbol", sort=False)["dollar_volume"]

    med = g.transform(
        lambda s: s.rolling(adv_window, min_periods=adv_window).median().shift(1)
    )
    history = g.transform(
        lambda s: s.rolling(1, min_periods=1).count().cumsum().shift(1)
    )
    # Number of bars in the `recency_sessions` rows immediately before this one.
    recency = g.transform(
        lambda s: s.rolling(recency_sessions, min_periods=recency_sessions).count().shift(1)
    )
    df = df.assign(med_adv_60d=med, history=history, recency=recency)

    qual = df[
        (df["history"] >= min_history)
        & (df["recency"] >= recency_sessions)
        & df["med_adv_60d"].notna()
    ].copy()
    qual = qual.rename(columns={"event_date": "trade_date"})
    qual = qual.assign(
        adv_rank=qual.groupby("trade_date")["med_adv_60d"].rank(
            ascending=False, method="first"
        )
    )
    out = qual[qual["adv_rank"] <= n][
        ["trade_date", "symbol", "med_adv_60d", "adv_rank"]
    ]
    return out.reset_index(drop=True)


def universe_members(
    universe: pd.DataFrame,
    trade_date,
    symbols: Optional[list[str]] = None,
) -> set:
    """Set of symbols in the universe on ``trade_date`` (convenience)."""
    sub = universe[universe["trade_date"] == trade_date]
    if symbols is not None:
        sub = sub[sub["symbol"].isin(symbols)]
    return set(sub["symbol"])
