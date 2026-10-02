"""Deterministic synthetic data for the ML lane.

The Unity Catalog gold/silver tables this lane consumes were empty at build
time (0 rows), so the ablation demo and the fast tests run on data generated
here. The generator mirrors the real column names/semantics so the pipeline is
exercised against the *actual* schema, but the numbers themselves are synthetic
and MUST NOT be reported as live results. See ml/results/ablation_abcd.md.

This module is pure pandas/numpy and is shared by tests and the demo runner.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from ml.features import (
    COT_FEATURES,
    OHLCV_FEATURES,
    OPTIONS_FEATURES,
    SEC_FEATURES,
    assemble_features,
    compute_labels,
    compute_triple_barrier_labels,
)


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def make_synthetic_matrix(
    n_symbols: int = 6,
    n_bars: int = 400,
    seed: int = 42,
    bar_freq: str = "1min",
    label_method: str = "fixed",
) -> pd.DataFrame:
    """Build a clean, PIT-correct assembled feature matrix + labels.

    ``label_method`` selects the labelling scheme: ``"fixed"`` for fixed-horizon
    (30-min forward returns) or ``"triple_barrier"`` for path-dependent,
    volatility-scaled triple-barrier labels.

    Returns a DataFrame with columns: symbol, prediction_ts, every feature in
    OHLCV/OPTIONS/SEC/COT, max_information_available_ts, market_beta, industry,
    forward_return, label.
    """
    rng = _rng(seed)
    start = pd.Timestamp("2026-01-05T09:30:00", tz="UTC")
    freq = pd.tseries.frequencies.to_offset(bar_freq)
    times = pd.date_range(start, periods=n_bars, freq=freq)

    symbols = [f"TKR{i:02d}" for i in range(n_symbols)]
    _INDUSTRIES = ["tech", "bank", "healthcare", "energy", "consumer"]
    industry_map = {sym: _INDUSTRIES[i % len(_INDUSTRIES)] for i, sym in enumerate(symbols)}

    # --- Labels: random-walk prices → forward returns -------------------------
    bars = []
    for sym in symbols:
        log_ret = rng.normal(0.0, 0.0004, size=n_bars)
        close = 100.0 * np.exp(np.cumsum(log_ret))
        bars.append(
            pd.DataFrame(
                {
                    "symbol": sym,
                    "event_ts": times,
                    "close": close,
                    "open": close,
                    "high": close,
                    "low": close,
                    "volume": rng.integers(1_000, 100_000, size=n_bars),
                }
            )
        )
    ohlcv_bars = pd.concat(bars, ignore_index=True)

    if label_method == "triple_barrier":
        labels = compute_triple_barrier_labels(
            ohlcv_bars,
            horizon_bars=20,
            volatility_window=20,
            profit_target=1.0,
            stop_loss=1.0,
        )
        labels = labels.rename(columns={"event_ts": "prediction_ts"})
    else:
        labels = compute_labels(ohlcv_bars, horizon_minutes=30, bar_seconds=60)
        labels = labels.rename(columns={"event_ts": "prediction_ts"})

    prediction_frame = labels[["symbol", "prediction_ts"]].copy()
    forward_return = labels.set_index(["symbol", "prediction_ts"])["forward_return"]
    label_end = labels.set_index(["symbol", "prediction_ts"])["label_end_ts"]

    # A latent signal that the features will carry, drawn per (symbol, bar).
    # Forward returns are influenced by a subset of the features, so arms with
    # more families can (but need not) score higher.
    signal = labels.set_index(["symbol", "prediction_ts"])["forward_return"]

    def _feature_matrix(feature_cols: list, n_signal: int, scale: float) -> pd.DataFrame:
        n = len(labels)
        X = rng.normal(0.0, scale, size=(n, len(feature_cols)))
        for j in range(min(n_signal, len(feature_cols))):
            X[:, j] += signal.values * rng.uniform(0.5, 1.5)
        return pd.DataFrame(X, columns=feature_cols)

    n_ohlcv_signal, n_opt_signal, n_sec_signal = 2, 1, 1

    # OHLCV + options are dense, per-bar, available at bar close.
    ohlcv_feat = _feature_matrix(OHLCV_FEATURES, n_ohlcv_signal, 0.3)
    options_feat = _feature_matrix(OPTIONS_FEATURES, n_opt_signal, 0.3)

    ohlcv = pd.concat(
        [
            labels[["symbol", "prediction_ts"]].rename(
                columns={"prediction_ts": "feature_ts"}
            ),
            ohlcv_feat,
        ],
        axis=1,
    )
    ohlcv["information_available_ts"] = ohlcv["feature_ts"]

    options = pd.concat(
        [
            labels[["symbol", "prediction_ts"]].rename(
                columns={"prediction_ts": "feature_ts"}
            ),
            options_feat,
        ],
        axis=1,
    )
    options["information_available_ts"] = options["feature_ts"]

    # SEC: sparse filings, forward-filled until the next filing.
    sec_rows = []
    filing_every = max(1, n_bars // 8)
    for sym in symbols:
        for i in range(0, n_bars, filing_every):
            t = times[i]
            sec_rows.append(
                {
                    "ticker": sym,
                    "accession_number": f"{sym}-{i:05d}",
                    "form_type": "10-Q",
                    "information_available_ts": t,
                    "sentiment_score": rng.normal(0.0, 0.5),
                    "risk_factor_change": rng.normal(0.0, 0.5),
                    "material_event_flag": bool(rng.random() < 0.1),
                }
            )
    sec = pd.DataFrame(sec_rows)

    # COT: regime-level, weekly release, broadcast to all symbols.
    cot_rows = []
    cot_every = max(1, n_bars // 20)
    for i in range(0, n_bars, cot_every):
        cot_rows.append(
            {
                "mapped_asset": "equities",
                "report_date": times[i].date(),
                "information_available_ts": times[i],
                "lev_money_zscore_52w": rng.normal(0.0, 1.0),
                "crowding_score": rng.normal(0.0, 1.0),
                "regime_label": str(rng.choice(["risk-on", "risk-off", "neutral"])),
            }
        )
    cot = pd.DataFrame(cot_rows)

    matrix = assemble_features(
        prediction_frame, ohlcv, options=options, sec=sec, cot=cot
    )

    # --- Market beta (trailing rolling beta) and industry assignment -----------
    ohlcv_bars["return"] = ohlcv_bars.groupby("symbol")["close"].pct_change()
    market_ret = ohlcv_bars.groupby("event_ts")["return"].mean().rename("mkt_return")
    ohlcv_bars = ohlcv_bars.merge(market_ret, on="event_ts", how="left")

    beta_pieces = []
    for sym, grp in ohlcv_bars.groupby("symbol", sort=False):
        cov = (
            grp["return"]
            .rolling(20, min_periods=5)
            .cov(grp["mkt_return"])
        )
        var = grp["mkt_return"].rolling(20, min_periods=5).var()
        beta = (cov / var).rename("market_beta")
        piece = pd.DataFrame(
            {"symbol": sym, "event_ts": grp["event_ts"].values, "market_beta": beta.values}
        )
        beta_pieces.append(piece)
    beta_df = pd.concat(beta_pieces, ignore_index=True)
    beta_df["event_ts"] = pd.to_datetime(beta_df["event_ts"], utc=True)

    matrix = matrix.merge(
        beta_df.rename(columns={"event_ts": "prediction_ts"}),
        on=["symbol", "prediction_ts"],
        how="left",
    )
    matrix["industry"] = matrix["symbol"].map(industry_map)

    matrix["forward_return"] = matrix.set_index(
        ["symbol", "prediction_ts"]
    ).index.map(forward_return)
    matrix["label_end_ts"] = matrix.set_index(
        ["symbol", "prediction_ts"]
    ).index.map(label_end)
    matrix["label"] = (matrix["forward_return"] > 0).astype(int)

    return matrix


def feature_families() -> Dict[str, list]:
    """The four feature families for reference/tests."""
    return {
        "A": OHLCV_FEATURES,
        "B": OHLCV_FEATURES + OPTIONS_FEATURES,
        "C": OHLCV_FEATURES + OPTIONS_FEATURES + SEC_FEATURES,
        "D": OHLCV_FEATURES + OPTIONS_FEATURES + SEC_FEATURES + COT_FEATURES,
    }
