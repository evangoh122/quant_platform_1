"""Point-in-time labelling and purged train/test split for baseline signals.

Labelling rule
--------------
For each row at snapshot time *s* for a given symbol, the label is derived from
the **next** snapshot *s'* of the same symbol **only if**:

1. The gap between *s* and *s'* falls within ``[horizon - tol, horizon + tol]``.
2. *s* and *s'* fall on the same US/Eastern trading date.

Otherwise the label is NaN (row is excluded from training).

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
    out["label_ts"] = pd.NaT

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