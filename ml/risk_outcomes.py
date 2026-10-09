"""Risk-outcome ledger: frozen-sigma outcome_z and sufficiency gates.

Per-signal outcome in units of an ex-ante daily sigma frozen at prediction
time.  Sigma is computed from information-time bars only (close_ts <=
prediction_ts).  Ex-dividend days are masked.  Aggregates require minimum
sample size, distinct prediction dates, and effective sample size.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from ml.baseline_labels import _eastern_date, daily_close_pairs


def build_signal_outcomes(
    signals: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    dividends: Optional[pd.DataFrame] = None,
    as_of: pd.Timestamp,
    max_gap_days: int = 5,
) -> pd.DataFrame:
    """Build per-signal outcome ledger with frozen sigma and outcome_z.

    Parameters
    ----------
    signals : DataFrame
        Columns: signal_id, symbol, model_version, horizon,
        prediction_ts (tz-aware UTC), probability (= P(next close > today's close)).
    closes : DataFrame
        One row per (symbol, trade_date): close, close_ts (tz-aware UTC),
        return_1d (float; NaN where pipeline masked a data-quality break).
    dividends : DataFrame, optional
        Columns: symbol, ex_date.  If None, every row has
        ex_dividend_state="unknown" and is NOT masked.
    as_of : Timestamp
        tz-aware UTC "now"; outcomes with outcome_close_ts > as_of are pending.
    max_gap_days : int
        Maximum calendar-day gap between entry and outcome dates.

    Returns
    -------
    DataFrame
        One row per signal with all required output columns.
    """
    signals = signals.copy()
    signals = signals.rename(columns={"probability": "probability_up"})
    signals["direction"] = np.where(signals["probability_up"] >= 0.5, "UP", "DOWN")

    if "horizon" in signals.columns:
        unsupported = signals["horizon"].unique()
        unsupported = [h for h in unsupported if h != "1d"]
        if unsupported:
            raise ValueError(f"Only horizon='1d' is supported, got: {unsupported}")

    if closes.empty:
        raise ValueError("closes DataFrame must not be empty")

    dup_close = closes.duplicated(subset=["symbol", "trade_date"], keep=False)
    if dup_close.any():
        raise ValueError(
            "closes contains duplicate (symbol, trade_date) rows: "
            + str(closes.loc[dup_close, ["symbol", "trade_date"]].head(5).to_dict("records"))
        )

    # Deduplicate: compute pairs and sigma once per unique (symbol, prediction_ts)
    pair_cols = ["symbol", "prediction_ts"]
    unique_pairs = signals[pair_cols].drop_duplicates().reset_index(drop=True)
    pairs = daily_close_pairs(unique_pairs, closes, max_gap_days=max_gap_days)

    # Merge pairs back onto signals (one row per signal, no fan-out)
    result = signals.merge(
        pairs[["symbol", "prediction_ts", "entry_trade_date", "entry_close",
               "entry_close_ts", "outcome_trade_date", "outcome_close",
               "outcome_close_ts"]],
        on=["symbol", "prediction_ts"],
        how="left",
    )

    # Raw forward return
    has_entry = result["entry_close"].notna()
    has_outcome = result["outcome_close"].notna()
    both = has_entry & has_outcome
    result["raw_forward_return"] = np.where(
        both, result["outcome_close"] / result["entry_close"] - 1, np.nan
    )
    result["signed_raw_return"] = np.where(
        result["direction"] == "UP",
        result["raw_forward_return"],
        -result["raw_forward_return"],
    )
    result["base_up_flag"] = np.where(
        has_outcome & has_entry,
        result["outcome_close"] > result["entry_close"],
        np.nan,
    )

    # Frozen sigma: compute from unique pairs, then join back
    sigma_results = _compute_frozen_sigma(unique_pairs, closes)
    result = result.merge(sigma_results, on=["symbol", "prediction_ts"], how="left")

    # Sigma method and floor logic
    result["sigma_method"] = "close_to_close_ddof1_v1"
    result["sigma_floor"] = np.where(
        result["sigma252"].notna(),
        0.5 * result["sigma252"],
        np.nan,
    )
    result["sigma_used"] = result["sigma20"].copy()
    has_floor = result["sigma_floor"].notna()
    result.loc[has_floor, "sigma_used"] = np.maximum(
        result.loc[has_floor, "sigma20"],
        result.loc[has_floor, "sigma_floor"],
    )

    # outcome_z
    result["outcome_z"] = np.where(
        result["sigma_used"].notna() & (result["sigma_used"] > 0) & both,
        result["signed_raw_return"] / result["sigma_used"],
        np.nan,
    )

    # Rename trade_date columns early (needed by ex-dividend and eligibility)
    result = result.rename(columns={
        "entry_trade_date": "entry_date",
        "outcome_trade_date": "outcome_date",
    })

    # Normalize date columns to date objects for consistency
    for col in ["entry_date", "outcome_date"]:
        result[col] = result[col].apply(
            lambda x: x.date() if isinstance(x, pd.Timestamp) and not pd.isna(x) else x
        )

    # Ex-dividend state
    if dividends is None or dividends.empty:
        result["ex_dividend_state"] = "unknown"
    else:
        result = _apply_ex_dividend_mask(result, dividends, max_gap_days)

    # Eligibility state (precedence order)
    result["eligibility_state"] = _compute_eligibility(result, as_of, both)

    # Mask ex-dividend rows
    ex_masked = result["ex_dividend_state"] == "masked"
    result.loc[ex_masked, "outcome_z"] = np.nan

    # Select and order output columns
    output_cols = [
        "signal_id", "symbol", "model_version", "horizon", "prediction_ts",
        "entry_date", "entry_close", "entry_close_ts",
        "outcome_date", "outcome_close", "outcome_close_ts",
        "direction", "probability_up",
        "raw_forward_return", "signed_raw_return", "sigma20", "sigma252",
        "sigma_floor", "sigma_used", "sigma_method", "sigma_as_of",
        "sigma_observation_count", "outcome_z", "base_up_flag",
        "ex_dividend_state", "eligibility_state",
    ]

    # Ensure all output columns exist
    for col in output_cols:
        if col not in result.columns:
            result[col] = np.nan

    return result[output_cols]


def _compute_frozen_sigma(
    signals: pd.DataFrame,
    closes: pd.DataFrame,
) -> pd.DataFrame:
    """Compute frozen sigma20 and sigma252 for each signal at prediction time."""
    closes = closes.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

    records = []
    for _, sig in signals.iterrows():
        sym = sig["symbol"]
        pred_ts = sig["prediction_ts"]

        sym_closes = closes[
            (closes["symbol"] == sym) & (closes["close_ts"] <= pred_ts)
        ].copy()
        sym_closes = sym_closes.sort_values("trade_date")

        # Drop rows with NaN return_1d
        valid_returns = sym_closes.dropna(subset=["return_1d"])
        n_valid = len(valid_returns)

        sigma20 = np.nan
        sigma252 = np.nan
        sigma_obs = 0
        sigma_as_of = pd.NaT

        if n_valid >= 20:
            last20 = valid_returns.tail(20)
            sigma20 = last20["return_1d"].std(ddof=1)
            sigma_obs = len(last20)
            sigma_as_of = last20.iloc[-1]["trade_date"]

        if n_valid >= 60:
            last252 = valid_returns.tail(252)
            sigma252 = last252["return_1d"].std(ddof=1)

        records.append({
            "symbol": sym,
            "prediction_ts": pred_ts,
            "sigma20": sigma20,
            "sigma252": sigma252,
            "sigma_as_of": sigma_as_of,
            "sigma_observation_count": sigma_obs,
        })

    return pd.DataFrame(records)


def _apply_ex_dividend_mask(
    result: pd.DataFrame,
    dividends: pd.DataFrame,
    max_gap_days: int,
) -> pd.DataFrame:
    """Mark rows where an ex-dividend date falls in (entry_date, outcome_date]."""
    result = result.copy()
    result["ex_dividend_state"] = "none"

    if dividends.empty:
        return result

    for idx, row in result.iterrows():
        sym = row["symbol"]
        entry_d = row.get("entry_date")
        outcome_d = row.get("outcome_date")

        if pd.isna(entry_d) or pd.isna(outcome_d):
            continue

        # Normalize to date objects for comparison
        if isinstance(entry_d, pd.Timestamp):
            entry_d = entry_d.date()
        if isinstance(outcome_d, pd.Timestamp):
            outcome_d = outcome_d.date()

        sym_divs = dividends[dividends["symbol"] == sym]
        if sym_divs.empty:
            continue

        for _, div in sym_divs.iterrows():
            ex_d = div["ex_date"]
            if isinstance(ex_d, str):
                ex_d = pd.Timestamp(ex_d).date()
            elif isinstance(ex_d, pd.Timestamp):
                ex_d = ex_d.date()
            if entry_d < ex_d <= outcome_d:
                result.loc[idx, "ex_dividend_state"] = "masked"
                break

    return result


def _compute_eligibility(
    result: pd.DataFrame,
    as_of: pd.Timestamp,
    both: pd.Series,
) -> pd.Series:
    """Compute eligibility_state with precedence order.

    Precedence (first match):
    outcome_pending -> missing_return -> ex_dividend_masked ->
    insufficient_sigma_history -> missing_sigma -> eligible
    """
    elig = pd.Series("eligible", index=result.index)

    # 1. outcome_pending: no N (and no D), or outcome_close_ts > as_of
    #    - If entry_date is NaT: no D found at all => pending
    #    - If outcome_close_ts > as_of: outcome is in the future => pending
    no_entry = result["entry_date"].isna()
    future_outcome = result["outcome_close_ts"].notna() & (result["outcome_close_ts"] > as_of)
    elig[no_entry | future_outcome] = "outcome_pending"

    # 2. missing_return: D exists but N is missing/NaN or gap > max_gap_days
    #    (entry_date not NaT, outcome_close_ts is NaT, and not already pending)
    d_exists_no_n = result["entry_date"].notna() & result["outcome_close_ts"].isna() & (elig == "eligible")
    elig[d_exists_no_n] = "missing_return"

    # 2b. NaN entry_close or outcome_close => missing_return
    nan_close = (result["entry_close"].isna() | result["outcome_close"].isna()) & (elig == "eligible")
    elig[nan_close] = "missing_return"

    # 3. ex_dividend_masked
    ex_masked = (result["ex_dividend_state"] == "masked") & (elig == "eligible")
    elig[ex_masked] = "ex_dividend_masked"

    # 4. insufficient_sigma_history: sigma20 is NaN but eligible
    no_sigma20 = result["sigma20"].isna() & (elig == "eligible")
    elig[no_sigma20] = "insufficient_sigma_history"

    # 5. missing_sigma: sigma_used == 0
    zero_sigma = (result["sigma_used"] == 0) & (elig == "eligible")
    elig[zero_sigma] = "missing_sigma"

    return elig


def summarize_outcomes(
    outcomes: pd.DataFrame,
    *,
    min_n: int = 100,
    min_dates: int = 60,
    rho: float = 0.2,
) -> list[dict]:
    """Summarize outcomes per (model_version, horizon).

    Parameters
    ----------
    outcomes : DataFrame
        Output of build_signal_outcomes.
    min_n : int
        Minimum number of eligible rows.
    min_dates : int
        Minimum number of distinct prediction dates.
    rho : float
        Fixed conservative prior for effective sample size.

    Returns
    -------
    list[dict]
        One dict per (model_version, horizon).
    """
    results = []

    eligible = outcomes[outcomes["eligibility_state"] == "eligible"]

    for (mv, hor), grp in eligible.groupby(["model_version", "horizon"]):
        n = len(grp)
        # Distinct prediction dates by US/Eastern trading date
        distinct_dates = _eastern_date(grp["prediction_ts"]).nunique()

        if distinct_dates == 0:
            m = 0.0
        else:
            m = n / distinct_dates

        n_eff = n / (1 + (m - 1) * rho) if distinct_dates > 0 else 0.0

        hit_count = int((grp["signed_raw_return"] > 0).sum())

        sufficient = n >= min_n and distinct_dates >= min_dates and n_eff >= min_n

        # Per-group excluded_counts (does NOT include eligible count)
        group_all = outcomes[
            (outcomes["model_version"] == mv) & (outcomes["horizon"] == hor)
        ]
        excluded = group_all["eligibility_state"].value_counts().to_dict()
        excluded.pop("eligible", None)

        entry: dict = {
            "model_version": mv,
            "horizon": hor,
            "state": "sufficient" if sufficient else "insufficient_sample",
            "n": int(n),
            "distinct_prediction_dates": int(distinct_dates),
            "n_eff": float(n_eff),
            "rho_assumption": rho,
            "hit_count": hit_count,
        }

        if sufficient:
            p = hit_count / n
            z = 1.96
            denom = 1 + z**2 / n_eff
            centre = (p + z**2 / (2 * n_eff)) / denom
            spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * n_eff)) / n_eff) / denom
            entry["hit_rate"] = p
            entry["hit_rate_interval"] = {
                "low": max(0.0, centre - spread),
                "high": min(1.0, centre + spread),
            }
            entry["median_outcome_z"] = float(grp["outcome_z"].median())
            entry["mean_outcome_z"] = float(grp["outcome_z"].mean())
            entry["base_up_rate"] = float(grp["base_up_flag"].mean())
        else:
            entry["hit_rate"] = None
            entry["hit_rate_interval"] = None
            entry["median_outcome_z"] = None
            entry["mean_outcome_z"] = None
            entry["base_up_rate"] = None

        entry["excluded_counts"] = excluded
        results.append(entry)

    # Include groups with zero eligible rows
    all_groups = outcomes[["model_version", "horizon"]].drop_duplicates()
    existing = {(r["model_version"], r["horizon"]) for r in results}
    for _, row in all_groups.iterrows():
        mv, hor = row["model_version"], row["horizon"]
        if (mv, hor) not in existing:
            group_all = outcomes[
                (outcomes["model_version"] == mv) & (outcomes["horizon"] == hor)
            ]
            excluded = group_all["eligibility_state"].value_counts().to_dict()
            excluded.pop("eligible", None)
            results.append({
                "model_version": mv,
                "horizon": hor,
                "state": "insufficient_sample",
                "n": 0,
                "distinct_prediction_dates": 0,
                "n_eff": 0.0,
                "rho_assumption": rho,
                "hit_count": 0,
                "hit_rate": None,
                "hit_rate_interval": None,
                "median_outcome_z": None,
                "mean_outcome_z": None,
                "base_up_rate": None,
                "excluded_counts": excluded,
            })

    return results