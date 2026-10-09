"""Point-in-time labelling and purged train/test split for baseline signals.

Two labelling modes
-------------------
1. **Intraday** (``forward_labels``): 30-min horizon on snapshot-to-snapshot
   returns.  Requires a dense snapshot grid.
2. **Daily** (``daily_close_labels``): 1-trading-day horizon on close-to-close
   returns.  Works when there is exactly one snapshot per (symbol, day), e.g.
   the daily feature rows in ``gold_model_features``.

Purged split
------------
``purged_split`` partitions labelled rows into train and test so that **no
training row has a label observed after the cut-off time**.  The cut is the
``frac``-quantile of ``prediction_ts``.  Train rows satisfy ``label_ts <= cut``;
test rows satisfy ``prediction_ts > cut``.  This prevents the last training
snapshot per symbol from leaking a label that is only known in the test period.
"""

from __future__ import annotations

import pandas as pd


def _eastern_date(ts: pd.Series) -> pd.Series:
    """US/Eastern calendar date; naive timestamps are treated as UTC."""
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    return ts.dt.tz_convert("America/New_York").dt.date


def forward_labels(
    df: pd.DataFrame,
    horizon: pd.Timedelta = pd.Timedelta("30min"),
    tol: pd.Timedelta = pd.Timedelta("1min"),
) -> pd.DataFrame:
    """Add PIT-safe ``label`` and ``label_ts`` columns.

    Parameters
    ----------
    df : DataFrame
        Must contain ``symbol``, ``prediction_ts`` and ``return_30m``.
        Sorted internally by ``[symbol, prediction_ts]`` (stable sort).
    horizon : Timedelta
        Target forward window (default 30 min).
    tol : Timedelta
        Tolerance around *horizon* (default 1 min).

    Returns
    -------
    DataFrame
        Copy of *df* with two new columns:
        - ``label``: 1.0 if the forward return is positive, 0.0 otherwise, NaN
          if no valid forward snapshot exists.
        - ``label_ts``: the timestamp of the snapshot that provided the label.
    """
    out = df.copy()
    out["label"] = float("nan")
    out["label_ts"] = pd.Series(pd.NaT, index=out.index, dtype=out["prediction_ts"].dtype)

    # Sort by [symbol, prediction_ts] so shift(-1) gives the true next snapshot.
    sort_keys = ["symbol", "prediction_ts"]
    out = out.sort_values(sort_keys, kind="stable")

    for sym, grp in out.groupby("symbol", sort=False):
        idx = grp.index
        ts = grp["prediction_ts"]
        nxt_ts = ts.shift(-1)
        nxt_ret = grp["return_30m"].shift(-1)

        gap = nxt_ts - ts
        ok_gap = gap >= (horizon - tol)
        ok_gap &= gap <= (horizon + tol)

        same_day = _eastern_date(ts) == _eastern_date(nxt_ts)

        valid = ok_gap & same_day & nxt_ret.notna()

        out.loc[idx[valid], "label"] = (nxt_ret[valid] > 0).astype(float)
        out.loc[idx[valid], "label_ts"] = nxt_ts[valid]

    return out


def daily_close_pairs(
    features: pd.DataFrame,
    closes: pd.DataFrame,
    max_gap_days: int = 5,
) -> pd.DataFrame:
    """PIT-safe entry/outcome close pairs for daily horizons.

    For each feature row (symbol, prediction_ts):

    * **D** = the latest trade_date of that symbol with ``close_ts <= prediction_ts``.
    * **N** = the next trade_date after D for that symbol.

    A close with ``close_ts > prediction_ts`` is **never** used as D.

    Parameters
    ----------
    features : DataFrame
        Must contain ``symbol`` and ``prediction_ts``.
    closes : DataFrame
        One row per (symbol, trade_date) with ``close`` (float) and
        ``close_ts`` (tz-aware UTC timestamp of the last regular-session
        minute bar of that US/Eastern date).
    max_gap_days : int
        Maximum calendar-day gap between D and N (default 5).

    Returns
    -------
    DataFrame
        Copy of *features* with columns added:
        ``entry_trade_date``, ``entry_close``, ``entry_close_ts``,
        ``outcome_trade_date``, ``outcome_close``, ``outcome_close_ts``.
        NaN/NaT when D or N is missing or N − D > max_gap_days.
    """
    out = features.copy()
    na_ts = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    out["entry_trade_date"] = pd.NaT
    out["entry_close"] = float("nan")
    out["entry_close_ts"] = na_ts.copy()
    out["outcome_trade_date"] = pd.NaT
    out["outcome_close"] = float("nan")
    out["outcome_close_ts"] = na_ts.copy()

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

    has_d = merged["D_date"].notna()
    has_n = merged["N_date"].notna()
    d_with_n = has_d & has_n
    valid = has_n & (gap > 0) & (gap <= max_gap_days)

    # Set entry columns where D was found AND N exists (even if gap too large)
    d_rows = merged.loc[d_with_n]
    out.loc[d_rows["orig_idx"].values, "entry_trade_date"] = d_rows["D_date"].values
    out.loc[d_rows["orig_idx"].values, "entry_close"] = d_rows["D_close"].values
    out.loc[d_rows["orig_idx"].values, "entry_close_ts"] = pd.array(
        d_rows["_cts"].values, dtype="datetime64[ns, UTC]"
    )

    # Set outcome columns only when N exists and gap <= max_gap_days
    vr = merged.loc[valid]
    out.loc[vr["orig_idx"].values, "outcome_trade_date"] = vr["N_date"].values
    out.loc[vr["orig_idx"].values, "outcome_close"] = vr["N_close"].values
    out.loc[vr["orig_idx"].values, "outcome_close_ts"] = pd.array(
        vr["N_close_ts"].values, dtype="datetime64[ns, UTC]"
    )

    return out


def daily_close_labels(
    features: pd.DataFrame,
    closes: pd.DataFrame,
    max_gap_days: int = 5,
) -> pd.DataFrame:
    """Add PIT-safe 1-day-horizon ``label`` and ``label_ts`` columns.

    Thin wrapper over :func:`daily_close_pairs`.

    Parameters
    ----------
    features : DataFrame
        Must contain ``symbol`` and ``prediction_ts``.
    closes : DataFrame
        One row per (symbol, trade_date) with ``close`` (float) and
        ``close_ts`` (tz-aware UTC timestamp of the last regular-session
        minute bar of that US/Eastern date).
    max_gap_days : int
        Maximum calendar-day gap between D and N (default 5).  Labels are
        NaN when the gap exceeds this value (e.g. holidays, delistings).

    Returns
    -------
    DataFrame
        Copy of *features* with ``label`` and ``label_ts`` columns added.
    """
    pairs = daily_close_pairs(features, closes, max_gap_days=max_gap_days)
    pairs["label"] = float("nan")
    pairs["label_ts"] = pairs["outcome_close_ts"]
    has_outcome = pairs["outcome_close"].notna()
    has_entry = pairs["entry_close"].notna()
    both = has_outcome & has_entry
    pairs.loc[both, "label"] = (
        pairs.loc[both, "outcome_close"] > pairs.loc[both, "entry_close"]
    ).astype(float)
    pairs.loc[~has_outcome, "label_ts"] = pd.NaT
    return pairs


def purged_split(
    lab: pd.DataFrame,
    frac: float = 0.8,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Purged train/test split that prevents label leakage.

    Parameters
    ----------
    lab : DataFrame
        Output of ``forward_labels`` (must contain ``prediction_ts`` and
        ``label_ts``).  Rows with NaN ``label`` are assumed already dropped.
    frac : float
        Quantile of ``prediction_ts`` used as the cut-off (default 0.8).

    Returns
    -------
    (train, test) : tuple of DataFrames
        Train: rows with ``label_ts <= cut``.
        Test: rows with ``prediction_ts > cut``.
    """
    cut = lab["prediction_ts"].quantile(frac)
    train = lab[lab["label_ts"] <= cut].copy()
    test = lab[lab["prediction_ts"] > cut].copy()
    return train, test


def refit_rows(
    lab: pd.DataFrame,
    scoring_ts: pd.Series,
) -> pd.DataFrame:
    """Return labelled rows safe to use for the final refit.

    The refit must not see any label observed after the *earliest* scoring
    snapshot.  This prevents a symbol scored at an earlier time from using
    another symbol's labels that were only observed later.

    Parameters
    ----------
    lab : DataFrame
        Labelled rows (output of ``forward_labels`` with NaN labels dropped).
        Must contain ``label_ts``.
    scoring_ts : Series
        ``prediction_ts`` of every row that will be scored (the latest
        snapshot per symbol).  The earliest value becomes the cutoff.

    Returns
    -------
    DataFrame
        Subset of *lab* with ``label_ts <= cutoff``.
    """
    cutoff = scoring_ts.min()
    return lab[lab["label_ts"] <= cutoff].copy()