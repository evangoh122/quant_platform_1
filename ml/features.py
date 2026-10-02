"""Point-in-time (PIT) feature assembly with a hard no-lookahead guard.

This module is the single most important piece of the ML lane. It implements
the as-of join that answers the research question without leaking the future:

    For a prediction timestamp ``t``, a feature row is only usable if its
    ``information_available_ts <= t``. We never backward-fill future
    observations.

Everything here operates on plain ``pandas.DataFrame`` objects so the leakage
guard and the join logic can be unit-tested without Spark or a live warehouse.
The Spark/Databricks read paths live in ``ml/score.py`` and ``ml/run_ablation.py``.

Column naming follows the actual Unity Catalog tables (``gold_model_features``,
``gold_ohlcv_features``, ``gold_options_features``, ``gold_sec_features``,
``gold_cot_features``). The feature-set arms A/B/C/D below map one-to-one onto
the columns that ``gold_model_features`` actually carries.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import pandas as pd


class LookaheadError(ValueError):
    """Raised when an assembled training row uses information from the future."""


# ── Feature-set arms (A/B/C/D) — the ablation study ──────────────────────────
#
# These lists are the *target* column names (what gold_model_features carries).
# Each arm is a strict superset of the previous one, so the ablation varies
# exactly one feature family at a time.

OHLCV_FEATURES: List[str] = [
    "return_1m",
    "return_5m",
    "return_15m",
    "return_30m",
    "rvol_5m",
    "rvol_15m",
    "rvol_30m",
    "atr_14",
    "rsi_14",
    "vwap_deviation",
    "relative_volume",
]

OPTIONS_FEATURES: List[str] = [
    "put_call_ratio",
    "iv_atm",
    "iv_skew",
    "iv_term_slope",
    "volume_anomaly_zscore",
]

SEC_FEATURES: List[str] = [
    "sec_sentiment_score",
    "sec_risk_factor_change",
    "sec_material_event",
]

COT_FEATURES: List[str] = [
    "cot_lev_money_zscore",
    "cot_crowding_score",
    "cot_regime_label",
]

FEATURE_SETS: Dict[str, List[str]] = {
    "A": OHLCV_FEATURES,
    "B": OHLCV_FEATURES + OPTIONS_FEATURES,
    "C": OHLCV_FEATURES + OPTIONS_FEATURES + SEC_FEATURES,
    "D": OHLCV_FEATURES + OPTIONS_FEATURES + SEC_FEATURES + COT_FEATURES,
}

# ── Source → target column renames ────────────────────────────────────────────
# OHLCV and options sources use the same column names as the target matrix.
# SEC and COT sources use their own names and must be renamed on the way in.

SEC_SOURCE_MAP: Dict[str, str] = {
    "sentiment_score": "sec_sentiment_score",
    "risk_factor_change": "sec_risk_factor_change",
    "material_event_flag": "sec_material_event",
}

COT_SOURCE_MAP: Dict[str, str] = {
    "lev_money_zscore_52w": "cot_lev_money_zscore",
    "crowding_score": "cot_crowding_score",
    "regime_label": "cot_regime_label",
}


def _rename_columns(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    """Rename only the columns that exist in ``mapping``."""
    return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})


# ── As-of join ───────────────────────────────────────────────────────────────

def asof_join(
    pred: pd.DataFrame,
    feat: pd.DataFrame,
    feature_cols: Iterable[str],
    on: str = "information_available_ts",
    left_key: str = "symbol",
    right_key: str = "symbol",
    direction: str = "backward",
) -> pd.DataFrame:
    """Forward-filled as-of join keyed on the *availability* time.

    For each prediction row ``(left_key, prediction_ts)`` this selects the most
    recent feature row whose ``on`` timestamp is ``<= prediction_ts``. Because
    ``on`` is the information-availability time (not the bar-close time), a
    feature that is only known *after* ``t`` can never be selected.

    ``direction="backward"`` gives the forward-fill behaviour we need for sparse
    sources (SEC filings, COT reports): the last observation stays active until
    the next one arrives.

    Returns the prediction columns plus ``on`` and every ``feature_cols``.
    """
    left = pred[[left_key, "prediction_ts"]].copy()
    right = feat[[right_key, on] + list(feature_cols)].copy()
    if right_key != left_key:
        right = right.rename(columns={right_key: left_key})

    left = left.sort_values("prediction_ts")
    right = right.sort_values(on)

    merged = pd.merge_asof(
        left,
        right,
        left_on="prediction_ts",
        right_on=on,
        by=left_key,
        direction=direction,
        allow_exact_matches=True,
    )
    return merged


def asof_join_global(
    pred: pd.DataFrame,
    feat: pd.DataFrame,
    feature_cols: Iterable[str],
    on: str = "information_available_ts",
    direction: str = "backward",
) -> pd.DataFrame:
    """Market-wide as-of join (no per-symbol key).

    Used for regime-level sources such as COT that are keyed by ``mapped_asset``
    rather than symbol. Broadcasts the most recent observation at or before each
    ``prediction_ts`` to every prediction row.
    """
    left = pred[["prediction_ts"]].copy().sort_values("prediction_ts")
    right = feat[[on] + list(feature_cols)].copy().sort_values(on)
    merged = pd.merge_asof(
        left,
        right,
        left_on="prediction_ts",
        right_on=on,
        direction=direction,
        allow_exact_matches=True,
    )
    return merged


# ── Assembly ─────────────────────────────────────────────────────────────────

def assemble_features(
    pred: pd.DataFrame,
    ohlcv: pd.DataFrame,
    options: Optional[pd.DataFrame] = None,
    sec: Optional[pd.DataFrame] = None,
    cot: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Assemble the point-in-time feature matrix.

    Parameters
    ----------
    pred:
        DataFrame with at least ``symbol`` and ``prediction_ts``. This is the
        key of the training matrix.
    ohlcv:
        ``gold_ohlcv_features``-shaped frame. Must contain ``symbol``,
        ``information_available_ts`` and the OHLCV feature columns.
    options, sec, cot:
        Optional ``gold_options_features`` / ``gold_sec_features`` /
        ``gold_cot_features``-shaped frames. SEC is keyed by ``ticker``; COT by
        ``mapped_asset`` (regime-level, broadcast).

    Returns
    -------
    DataFrame keyed by ``(symbol, prediction_ts)`` with all feature columns plus
    a ``max_information_available_ts`` column — the latest availability time of
    any source joined into that row. This column is what the no-lookahead guard
    checks.
    """
    required = {"symbol", "prediction_ts"}
    missing = required - set(pred.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns: {sorted(missing)}")

    result = pred[["symbol", "prediction_ts"]].copy()
    availability: List[pd.Series] = []

    def _merge(joined: pd.DataFrame, avail_col: str, feature_cols: List[str]) -> None:
        nonlocal result
        keep = ["symbol", "prediction_ts", avail_col] + feature_cols
        result = result.merge(joined[keep], on=["symbol", "prediction_ts"], how="left")
        availability.append(result[avail_col])

    # OHLCV — dense, per-symbol.
    o = asof_join(result, ohlcv, OHLCV_FEATURES, on="information_available_ts")
    _merge(o, "information_available_ts", OHLCV_FEATURES)

    # Options — dense, per-symbol.
    if options is not None:
        op = asof_join(
            result,
            options,
            OPTIONS_FEATURES,
            on="information_available_ts",
        ).rename(columns={"information_available_ts": "opt_information_available_ts"})
        _merge(op, "opt_information_available_ts", OPTIONS_FEATURES)

    # SEC — sparse, per-ticker, forward-filled until next filing.
    if sec is not None:
        sec_renamed = _rename_columns(sec, SEC_SOURCE_MAP)
        s = asof_join(
            result,
            sec_renamed,
            list(SEC_SOURCE_MAP.values()),
            on="information_available_ts",
            right_key="ticker",
        ).rename(columns={"information_available_ts": "sec_information_available_ts"})
        _merge(s, "sec_information_available_ts", list(SEC_SOURCE_MAP.values()))

    # COT — regime-level, broadcast (forward-filled until next release).
    if cot is not None:
        cot_renamed = _rename_columns(cot, COT_SOURCE_MAP)
        unique_pred = result[["prediction_ts"]].drop_duplicates()
        c = asof_join_global(
            unique_pred,
            cot_renamed,
            list(COT_SOURCE_MAP.values()),
            on="information_available_ts",
        ).rename(columns={"information_available_ts": "cot_information_available_ts"})
        keep = ["prediction_ts", "cot_information_available_ts"] + list(
            COT_SOURCE_MAP.values()
        )
        result = result.merge(c[keep], on="prediction_ts", how="left")
        availability.append(result["cot_information_available_ts"])

    # Defence-in-depth timestamp: the latest availability across all sources.
    result["max_information_available_ts"] = pd.concat(availability, axis=1).max(axis=1)
    return result


# ── No-lookahead guard ───────────────────────────────────────────────────────

def assert_no_lookahead(
    matrix: pd.DataFrame,
    prediction_col: str = "prediction_ts",
    availability_col: str = "max_information_available_ts",
) -> None:
    """Fail loudly if any assembled row uses information from the future.

    This is the guard the whole lane is built around. ``train.py`` calls it
    before fitting anything. A row whose availability time exceeds its
    prediction time means a feature was observed after the decision point —
    i.e. lookahead — and the build must fail rather than train on it.
    """
    if prediction_col not in matrix.columns or availability_col not in matrix.columns:
        raise ValueError(
            f"matrix must have '{prediction_col}' and '{availability_col}' columns"
        )

    bad = matrix[matrix[availability_col] > matrix[prediction_col]]
    if len(bad) == 0:
        return

    n = len(bad)
    first = bad.iloc[0]
    raise LookaheadError(
        f"lookahead detected: {n} row(s) have {availability_col} > {prediction_col}. "
        f"Example: symbol={first.get('symbol')} "
        f"{availability_col}={first[availability_col]} "
        f">{prediction_col}={first[prediction_col]}"
    )


# ── Labels ───────────────────────────────────────────────────────────────────

def compute_labels(
    ohlcv: pd.DataFrame,
    horizon_minutes: int = 30,
    bar_seconds: int = 60,
    close_col: str = "close",
    ts_col: str = "event_ts",
    symbol_col: str = "symbol",
) -> pd.DataFrame:
    """Compute forward returns and the binary label from bar closes.

    Label = 1 if the ``horizon_minutes`` forward return is strictly positive.

    Labels are computed *after* feature assembly and are deliberately NOT part
    of ``assemble_features`` — they must never be persisted into a serving
    table, only used at training/evaluation time.
    """
    horizon_bars = max(int(round(horizon_minutes * 60 / bar_seconds)), 1)
    df = ohlcv[[symbol_col, ts_col, close_col]].copy()
    df = df.sort_values([symbol_col, ts_col])
    df["forward_close"] = df.groupby(symbol_col)[close_col].shift(-horizon_bars)
    df["forward_return"] = df["forward_close"] / df[close_col] - 1.0
    df["label"] = (df["forward_return"] > 0).astype(int)
    return (
        df[df["forward_close"].notna()]
        .drop(columns="forward_close")
        .reset_index(drop=True)
    )
