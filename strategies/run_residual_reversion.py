"""End-to-end residual mean-reversion baseline on the real tradable universe.

Pulls a compact daily dataset (universe membership, closes, SPY/RSP/QQQ,
breadth regime) from the SQL warehouse via ``databricks-sdk`` and runs the
pandas signal + backtest pipeline locally. A ~300-symbol daily book does not
need a Spark cluster; the SQL warehouse returns the data and the driver runs the
regression.

Usage:
    python strategies/run_residual_reversion.py [--output strategies/results/residual_reversion_r1.md]

Credentials come from ``~/.databrickscfg`` (``DATABRICKS_PROFILE``, default
``evangohsg``). No secrets are stored in the repo.
"""
from __future__ import annotations

import argparse
import os
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from databricks.sdk import WorkspaceClient

from strategies.backtest import run_backtest
from strategies.cost_model import CostParams
from strategies.residual_reversion import (
    compute_daily_returns,
    compute_industry_factor,
    compute_residuals,
    generate_signals,
    load_industry_map,
)

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
FQN = f"{CATALOG}.{SCHEMA}"
WAREHOUSE = os.getenv("DATABRICKS_WAREHOUSE_ID", "b15d3d6f837ba428")

# Factor / regime instruments — never traded, only used as factors.
FACTOR_INSTRUMENTS = {"SPY", "RSP", "QQQ"}


def _fetch(w: WorkspaceClient, sql: str) -> pd.DataFrame:
    st = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE, statement=sql, wait_timeout="50s",
    )
    for _ in range(300):
        if st.status.state.value in ("SUCCEEDED", "FAILED", "CANCELED", "CLOSED"):
            break
        time.sleep(2)
        st = w.statement_execution.get_statement(st.statement_id)
    if st.status.state.value != "SUCCEEDED":
        err = st.status.error
        raise RuntimeError(f"query failed: {err.message if err else '?'}\n{sql[:300]}")
    cols = [c.name for c in st.manifest.schema.columns]
    rows = list(st.result.data_array) if st.result and st.result.data_array else []
    total_chunks = st.manifest.total_chunk_count or 0
    for ci in range(1, total_chunks):
        r = w.statement_execution.get_statement_result_chunk_n(st.statement_id, ci)
        if r and r.data_array:
            rows.extend(r.data_array)
    return pd.DataFrame(rows, columns=cols)


def fetch_data(w: WorkspaceClient, price_table: str = "silver_ohlcv_day_adjusted") -> Dict[str, pd.DataFrame]:
    universe = _fetch(w, f"""
        SELECT trade_date, symbol, med_adv_60d, adv_rank
        FROM {FQN}.gold_tradable_universe
    """)
    universe = universe.assign(
        trade_date=pd.to_datetime(universe["trade_date"]),
        med_adv_60d=pd.to_numeric(universe["med_adv_60d"], errors="coerce"),
    )

    is_adjusted = price_table == "silver_ohlcv_day_adjusted"
    if is_adjusted:
        close_col = "adj_close AS close"
    else:
        import warnings
        warnings.warn(
            f"Using UNADJUSTED prices from {price_table}. "
            "Split events will contaminate returns and signals. "
            "Use silver_ohlcv_day_adjusted for production runs.",
            stacklevel=2,
        )
        close_col = "close"

    closes = _fetch(w, f"""
        SELECT symbol, event_date, {close_col}
        FROM {FQN}.{price_table}
        WHERE symbol IN (
            SELECT DISTINCT symbol FROM {FQN}.gold_tradable_universe
            UNION ALL SELECT 'SPY' UNION ALL SELECT 'RSP' UNION ALL SELECT 'QQQ'
        )
        AND close IS NOT NULL AND close > 0
    """)
    closes = closes.assign(
        event_date=pd.to_datetime(closes["event_date"]),
        close=pd.to_numeric(closes["close"], errors="coerce"),
    )

    regime = _fetch(w, f"""
        SELECT trade_date, breadth_regime
        FROM {FQN}.gold_regime_features
    """)
    regime = regime.assign(trade_date=pd.to_datetime(regime["trade_date"]))

    return {"universe": universe, "closes": closes, "regime": regime, "price_table": price_table}


def fetch_masked_breaks(w: WorkspaceClient) -> set:
    """Return set of (symbol, event_date) tuples where returns are masked.

    A masked break is a (symbol, event_date) pair where `return_1d IS NULL`
    in `silver_ohlcv_day_adjusted` (i.e. `is_masked=true` in
    `data_quality_breaks`).  Returns on these days must not be used as signal
    inputs or P&L; positions held across a masked day earn 0 that day.
    """
    rows = _fetch(w, f"""
        SELECT symbol, event_date
        FROM {FQN}.data_quality_breaks
        WHERE is_masked = true
    """)
    return set(zip(rows["symbol"], pd.to_datetime(rows["event_date"])))


def build_wide(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.pivot(index="event_date", columns="symbol", values="close").sort_index()


def _sharpe(r: pd.Series, periods: int = 252) -> float:
    r = r.dropna()
    if len(r) < 2 or r.std(ddof=0) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=0) * np.sqrt(periods))


def _ann_return(r: pd.Series) -> float:
    return float(r.mean() * 252)


def _max_dd(r: pd.Series) -> float:
    eq = (1.0 + r).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def _deflated_sharpe(r: pd.Series, n_trials: int) -> float:
    from ml.evaluate import deflated_sharpe_ratio
    return deflated_sharpe_ratio(r.to_numpy(), n_trials=n_trials, periods_per_year=252)


def _capacity(adv_wide: pd.DataFrame, universe_daily: int = 300) -> float:
    """Median total 1%-of-ADV budget across the tradable universe ($)."""
    budget = (0.01 * adv_wide).sum(axis=1)
    return float(budget.median())


def build_signals(
    closes: pd.DataFrame,
    universe: pd.DataFrame,
    window: int,
    lookback: int,
    entry: float,
    exit_thresh: float,
    max_hold: int,
    masked_breaks: Optional[set] = None,
) -> Dict[str, pd.DataFrame]:
    """Compute residual s-scores and desired positions for the tradable set."""
    industry_map = load_industry_map()
    prices = build_wide(closes)
    tradeable = [c for c in prices.columns if c not in FACTOR_INSTRUMENTS]
    prices = prices[["SPY"] + tradeable]

    returns = compute_daily_returns(prices)

    # Mask returns to the point-in-time universe.  A symbol that is not in the
    # universe on date t must have NaN returns on t (never 0), so it does not
    # contribute to industry factors or regressions on that date.
    members = set(zip(universe["trade_date"], universe["symbol"]))
    mask = pd.DataFrame(
        [[(d, s) in members for s in tradeable] for d in returns.index],
        index=returns.index,
        columns=tradeable,
    )
    tradeable_returns = returns[tradeable].where(mask)

    # Masked break days: set returns to NaN so no signal or P&L is generated.
    # Positions held across a masked day earn 0 that day (the return is NaN,
    # which .sum() skips in the backtest gross calculation).
    if masked_breaks:
        for sym, dt in masked_breaks:
            if sym in tradeable_returns.columns and dt in tradeable_returns.index:
                tradeable_returns.loc[dt, sym] = np.nan

    market = returns["SPY"]
    industry = pd.Series(
        {s: industry_map.get(s, "__unknown__") for s in tradeable}, dtype=object,
    )
    ind_factor = compute_industry_factor(tradeable_returns, industry)

    res = compute_residuals(tradeable_returns, market, ind_factor,
                            window=window, lookback=lookback)
    positions = generate_signals(res["s_score"], entry=entry, exit_thresh=exit_thresh,
                                 max_hold=max_hold)
    # valuation_returns: unmasked for universe (so exit-day P&L is preserved),
    # but masked for break days (so masked days contribute 0 P&L).
    valuation_returns = returns[tradeable].copy()
    if masked_breaks:
        for sym, dt in masked_breaks:
            if sym in valuation_returns.columns and dt in valuation_returns.index:
                valuation_returns.loc[dt, sym] = np.nan
    return {
        "returns": tradeable_returns,
        "valuation_returns": valuation_returns,
        "market": market,
        "industry": industry,
        "beta_mkt": res["beta_mkt"],
        "s_score": res["s_score"],
        "positions": positions,
    }


def run_one(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    universe: pd.DataFrame,
    adv_wide: pd.DataFrame,
    beta_mkt: pd.DataFrame,
    industry: pd.Series,
    book_capital: float,
    n_trials: int,
) -> Dict:
    """Run the backtest for a single configuration, restricted to the dates in
    ``positions``. Returns the daily series and the metric bundle."""
    dates = positions.index
    # Do NOT fillna(0) here — cap_weight_changes_by_adv forward-fills per
    # symbol so the last known ADV is used for names that leave the universe.
    # Passing NaN lets the cap helper see which names have no ADV history.
    adv = adv_wide.reindex(index=dates, columns=positions.columns)
    res = run_backtest(
        positions, returns.reindex(dates), universe, adv,
        beta=beta_mkt.reindex(dates), industry=industry,
        book_capital=book_capital, target_gross=1.0,
        n_trials=n_trials,
    )
    return res


CHANGELOG = {
    3: [
        {
            "fix": "Min-history gate now counts own trading sessions",
            "files": "`gold/06_gold_tradable_universe.sql`, `strategies/universe.py`",
            "rationale": "`COUNT(dollar_volume)` instead of `COUNT(*)` — pre-listing NULL rows no longer inflate history",
        },
        {
            "fix": "Date range derived from data",
            "files": "`strategies/run_residual_reversion.py`",
            "rationale": "No more hardcoded dates in results header",
        },
    ],
    4: [
        {
            "fix": "Missing returns are excluded, not treated as zero",
            "files": "`strategies/residual_reversion.py`",
            "rationale": "Per-row validity mask; the regression uses the true count of valid days and is NaN below `min_obs` = ceil(0.8 x window)",
        },
        {
            "fix": "Exits are never blocked by the ADV cap",
            "files": "`strategies/backtest.py`",
            "rationale": "Only increases are capped; ADV is forward-filled for names that leave the universe, so a position can always be reduced to zero",
        },
        {
            "fix": "Universe median requires a full 60-session window",
            "files": "`gold/06_gold_tradable_universe.sql`",
            "rationale": "`med_adv_60d` is NULL unless all 60 prior sessions have volume, matching the pandas reference `min_periods=60`",
        },
        {
            "fix": "Breadth SMA50 requires a full 50-day window",
            "files": "`gold/07_gold_regime_features.sql`",
            "rationale": "The first 49 dates are labelled MIXED instead of BROAD/NARROW from a partial average",
        },
    ],
    5: [
        {
            "fix": "Sign-flip ADV cap decomposes close leg (free) and open leg (capped)",
            "files": "`strategies/backtest.py`",
            "rationale": "Old `abs(cur) > abs(prev)` conflated net magnitude with new-leg opening; equal-magnitude flips were uncapped and reductions were wrongly capped. Now each day's change is decomposed: close toward 0 is always free, opening beyond 0 is ADV-capped",
        },
        {
            "fix": "Sigma uses same min_periods as beta regression",
            "files": "`strategies/residual_reversion.py`",
            "rationale": "`_trailing_std` used `min_periods=window` (60) while beta used `min_obs=ceil(0.8*window)` (48); one gap killed sigma for 60 days. Now sigma uses `min_periods=min_obs` for consistent gap tolerance",
        },
    ],
    6: [
        {
            "fix": "Same-side reductions are never ADV-capped",
            "files": "`strategies/backtest.py`",
            "rationale": "Round 6 routed same-side partial reductions (e.g. +0.4 to +0.2) into the capped open leg. Any move toward zero is now free and only moves away from zero are capped; a seeded 500-sequence property test enforces the invariants",
        },
    ],
    7: [
        {
            "fix": "Exit/reduction costs charged on full executed notional",
            "files": "`strategies/backtest.py`",
            "rationale": "`compute_costs` was re-capping orders through `scale_order_to_adv_cap`, charging costs on at most 1% of ADV even for large exits. Now charges on the actual executed notional with true participation for slippage",
        },
        {
            "fix": "Universe pandas matches SQL dense-grid semantics",
            "files": "`strategies/universe.py`",
            "rationale": "Reindex each symbol onto the full market calendar before rolling so missing sessions are NaN rows (matching SQL NULL rows), not absent rows",
        },
        {
            "fix": "Z-score guard counts non-NULL column values",
            "files": "`gold/07_gold_regime_features.sql`",
            "rationale": "`COUNT(*)` counted all rows in window regardless of NULL `rsp_spy_ratio`; `AVG`/`STDDEV` ignore NULLs, so partial windows produced z-scores. Changed to `COUNT(rsp_spy_ratio)`",
        },
        {
            "fix": "Leverage wording corrected to 50%/50%",
            "files": "`strategies/run_residual_reversion.py`",
            "rationale": "Gross 1.0 with dollar neutrality is 50% long / 50% short, not 100%/100%",
        },
    ],
    8: [
        {
            "fix": "pandas 3 read-only array guard",
            "files": "`strategies/backtest.py`",
            "rationale": "`cap_weight_changes_by_adv` wrote into a `.to_numpy()` array that pandas 3 may return as a read-only view (copy-on-write). Changed to `to_numpy(copy=True)` so the output array is always writeable regardless of pandas version",
        },
        {
            "fix": "ADV forward-fill before zero-fill",
            "files": "`strategies/run_residual_reversion.py`, `strategies/backtest.py`",
            "rationale": "`run_one` filled missing ADV with 0 before `cap_weight_changes_by_adv`, preventing the cap helper from forward-filling the last known ADV for names that leave the universe. Now ADV is passed with NaN so the cap function can ffill per symbol; exits use last known ADV instead of 100% participation",
        },
        {
            "fix": "Test paths resolved from __file__",
            "files": "`tests/strategies/test_universe.py`, `tests/lakebase/test_migrations.py`",
            "rationale": "Bare relative paths (`gold/...`, `db/migrations`) broke when pytest cwd differed from repo root. Now resolved via `Path(__file__).resolve().parents[2]`",
        },
    ],
    9: [
        {
            "fix": "Single ADV frame for cap and costs — dropped-name exit uses last known ADV",
            "files": "`strategies/backtest.py`",
            "rationale": "`run_backtest` rebuilt `adv_aligned` with `fillna(0.0)` before `compute_costs`, so a dropped name's exit was costed at 100% participation (~202 bps) instead of its last known ADV (~12 bps). Now builds ONE ADV frame: per-symbol forward-fill then `fillna(0)` for never-seen symbols; passes the SAME frame to both `cap_weight_changes_by_adv` and `compute_costs`",
        },
    ],
    10: [
        {
            "fix": "Exit-day P&L no longer dropped by masked returns",
            "files": "`strategies/run_residual_reversion.py`",
            "rationale": "`build_signals` masked returns to the PIT universe for signal construction, but the same masked frame was passed to `run_backtest` where `gross = (weights.shift(1) * returns).sum()` skipped NaN. When a held name left the universe on day t, the P&L of the position held from t-1 was silently dropped. Now returns unmasked `valuation_returns` for the backtest while keeping masked `returns` for signals",
        },
    ],
    12: [
        {
            "fix": "Split-adjusted prices from silver_ohlcv_day_adjusted",
            "files": "`strategies/run_residual_reversion.py`, `strategies/config.yaml`",
            "rationale": "bronze_ohlcv_day is NOT split-adjusted (AMZN 2022-06-06 shows −94.9%). Now uses `adj_close` from `silver_ohlcv_day_adjusted` by default; `--price-table bronze_ohlcv_day` falls back to raw prices with a loud WARNING",
        },
        {
            "fix": "Masked break days excluded from signals and P&L",
            "files": "`strategies/run_residual_reversion.py`",
            "rationale": "Returns on (symbol, event_date) where `return_1d IS NULL` in silver or `data_quality_breaks.is_masked` are set to NaN — no signal or P&L contribution on masked days. Positions held across a masked day earn 0 that day",
        },
    ],
}


def parse_round_from_output(path: str) -> int:
    """Derive the round number from an output filename like ``residual_reversion_r4.md``.

    Raises ``ValueError`` if the filename does not match ``_r<N>.md``.
    """
    import re
    m = re.search(r"_r(\d+)\.md$", path)
    if not m:
        raise ValueError(f"cannot derive round from output path: {path!r}")
    return int(m.group(1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="strategies/results/residual_reversion_r4.md")
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--book-capital", type=float, default=10_000_000.0)
    ap.add_argument("--price-table", default="silver_ohlcv_day_adjusted",
                    help="Price source table (default: silver_ohlcv_day_adjusted)")
    args = ap.parse_args()

    if args.round is None:
        args.round = parse_round_from_output(args.output)

    w = WorkspaceClient(profile=os.getenv("DATABRICKS_PROFILE", "evangohsg"))
    data = fetch_data(w, price_table=args.price_table)
    masked_breaks = fetch_masked_breaks(w)

    closes = data["closes"]
    universe = data["universe"]
    regime = data["regime"]

    # Wide ADV (trailing median dollar volume) from the universe table.
    adv_wide = universe.pivot(index="trade_date", columns="symbol",
                              values="med_adv_60d").sort_index()

    WINDOW, LOOKBACK, ENTRY, EXIT = 60, 5, 2.5, 0.5
    hold_candidates = [3, 5, 10]

    # Signals per max-hold candidate (shared s-scores).
    signals = {}
    for h in hold_candidates:
        signals[h] = build_signals(closes, universe, WINDOW, LOOKBACK, ENTRY, EXIT, h,
                                   masked_breaks=masked_breaks)

    industry = signals[hold_candidates[0]]["industry"]
    beta_mkt = signals[hold_candidates[0]]["beta_mkt"]

    # ── Walk-forward: choose max-hold on training folds only ──────────────────
    from ml.train import purged_walk_forward_splits

    # Evaluate only on dates the point-in-time universe actually covers (a signal
    # cannot trade outside it). Net series are causal, so slicing by date is safe.
    dates = pd.DatetimeIndex(sorted(set(universe["trade_date"])))
    label_end = dates + pd.Timedelta(days=max(hold_candidates) + 5)
    splits = purged_walk_forward_splits(
        dates, label_end, n_splits=5, min_train=8, test_size=None, embargo=max(hold_candidates),
    )
    # n_trials = number of hold configs actually compared on training folds.
    n_trials = len(hold_candidates)

    oos_frames = []
    for fold_i, (train_idx, val_idx) in enumerate(splits):
        train_dates = dates[train_idx]
        val_dates = dates[val_idx]
        best_h, best_sr = None, -np.inf
        for h in hold_candidates:
            r = run_one(signals[h]["positions"], signals[h]["valuation_returns"], universe,
                        adv_wide, beta_mkt, industry, args.book_capital, n_trials)
            tr = r["net"].loc[train_dates].dropna()
            sr = _sharpe(tr)
            if sr > best_sr:
                best_h, best_sr = h, sr
        # Evaluate the chosen config out-of-sample on the validation fold.
        r = run_one(signals[best_h]["positions"], signals[best_h]["valuation_returns"], universe,
                    adv_wide, beta_mkt, industry, args.book_capital, n_trials)
        oos_frames.append(r["net"].loc[val_dates])
        print(f"fold {fold_i}: train chose max_hold={best_h} (train sharpe {best_sr:.3f}), "
              f"val days={len(val_dates)}", flush=True)

    oos_net = pd.concat(oos_frames).sort_index()

    # ── Ablation: unconditioned vs gated by breadth_regime (NARROW) ──────────
    regime_map = regime.set_index("trade_date")["breadth_regime"]
    h_default = 5
    base_pos = signals[h_default]["positions"]
    gate = regime_map.reindex(base_pos.index).eq("NARROW").astype(float)
    gated_positions = base_pos.mul(gate, axis=0)

    base_res = run_one(base_pos, signals[h_default]["valuation_returns"], universe, adv_wide,
                       beta_mkt, industry, args.book_capital, n_trials)
    gated_res = run_one(gated_positions, signals[h_default]["valuation_returns"], universe, adv_wide,
                        beta_mkt, industry, args.book_capital, n_trials)

    capacity = _capacity(adv_wide)

    # ── Render the results file ──────────────────────────────────────────────
    lines = _render(
        base_res, gated_res, oos_net, n_trials, capacity, args.book_capital,
        WINDOW, LOOKBACK, ENTRY, EXIT, dates[0], dates[-1], len(dates), len(splits),
        round_num=args.round, price_table=data.get("price_table", "silver_ohlcv_day_adjusted"),
        n_masked_breaks=len(masked_breaks),
    )
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {args.output}", flush=True)


def _render(base_res, gated_res, oos_net, n_trials, capacity, book_capital,
            window, lookback, entry, exit_thresh, date_start, date_end, n_dates, n_folds,
            round_num: int = 3, price_table: str = "silver_ohlcv_day_adjusted",
            n_masked_breaks: int = 0) -> List[str]:
    bm = base_res["metrics"]
    gm = gated_res["metrics"]
    prev = round_num - 1
    L = []
    L.append(f"# Residual mean-reversion — round {round_num} (real data)")
    L.append("")
    L.append(f"**Price source:** `{price_table}`" +
             (" (split-adjusted)" if "adjusted" in price_table else " (**UNADJUSTED — splits contaminate results**)"))
    if n_masked_breaks > 0:
        L.append(f"**Masked breaks:** {n_masked_breaks} (symbol, date) pairs excluded from signals and P&L")
    L.append("")
    L.append("Market/industry residual mean-reversion on the point-in-time top-300")
    L.append(f"tradable universe (`gold_tradable_universe`), {date_start:%Y-%m-%d} → {date_end:%Y-%m-%d}.")
    L.append("Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.")
    L.append("")
    L.append(f"## What changed vs r{prev}")
    L.append("")

    rows = CHANGELOG.get(round_num, [])
    if rows:
        L.append("| # | Fix | Files | Rationale |")
        L.append("|---|-----|-------|-----------|")
        for i, row in enumerate(rows, 1):
            L.append(f"| {i} | {row['fix']} | {row['files']} | {row['rationale']} |")
    else:
        L.append("_No changelog entries for this round._")
    L.append("")
    L.append("## Configuration")
    L.append("")
    L.append(f"- universe: top 300 by trailing 60-day median dollar volume (recency 5, min history 252)")
    L.append(f"- residual regression: rolling window {window} days, lookback L = {lookback}")
    L.append(f"- entry: long s <= -{entry}, short s >= +{entry}; exit |s| < {exit_thresh}")
    L.append(f"- book capital: ${book_capital:,.0f}; target gross 1.0 (50% long / 50% short)")
    L.append(f"- dates: {n_dates} trading days; purged walk-forward folds: {n_folds}")
    L.append(f"- ADV cap: 1% of trailing median dollar volume per name per day")
    L.append("")
    L.append("## Results — unconditional baseline (max_hold = 5)")
    L.append("")
    L.append("| metric | gross | net | net @ 2x costs |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| annualised return | {bm['gross_ann_return']:.4f} | {bm['net_ann_return']:.4f} | {bm['net_2x_ann_return']:.4f} |")
    L.append(f"| Sharpe | {bm['gross_sharpe']:.3f} | {bm['net_sharpe']:.3f} | {bm['net_2x_sharpe']:.3f} |")
    L.append(f"| max drawdown | {bm['gross_max_drawdown']:.4f} | {bm['net_max_drawdown']:.4f} | {bm['net_2x_max_drawdown']:.4f} |")
    L.append(f"| hit rate (daily) | {bm['hit_rate']:.4f} | | |")
    L.append(f"| avg turnover (daily, one-way) | {bm['turnover_avg_daily']:.4f} | | |")
    L.append(f"| average hold (days) | {bm['avg_hold_days']:.2f} | | |")
    L.append("")
    L.append("## Ablation — unconditioned vs gated by `breadth_regime == NARROW`")
    L.append("")
    L.append("**Caveat:** The gated comparison below is an **in-sample / full-period exploratory ablation**.")
    L.append("It is not evidence of an edge. The gated net Sharpe at 2× costs is "
             f"{gm['net_2x_sharpe']:.3f} and the deflated Sharpe ratio (DSR) is "
             f"{gm.get('deflated_sharpe_ratio', float('nan')):.3f}. "
             "This result should not be used to justify live deployment without "
             "out-of-sample validation on a held-out period.")
    L.append("")
    L.append("| metric | unconditioned | gated (NARROW only) |")
    L.append("|---|---:|---:|")
    L.append(f"| annualised return (net) | {bm['net_ann_return']:.4f} | {gm['net_ann_return']:.4f} |")
    L.append(f"| Sharpe (net) | {bm['net_sharpe']:.3f} | {gm['net_sharpe']:.3f} |")
    L.append(f"| Sharpe (net @ 2x) | {bm['net_2x_sharpe']:.3f} | {gm['net_2x_sharpe']:.3f} |")
    L.append("")
    L.append("## Walk-forward (max_hold chosen on training folds only)")
    L.append("")
    L.append(f"| configs compared | {n_trials} (max_hold in [3, 5, 10]) |")
    L.append("|---|---:|")
    L.append(f"| out-of-sample net Sharpe | {_sharpe(oos_net):.3f} |")
    L.append(f"| out-of-sample net annualised return | {_ann_return(oos_net):.4f} |")
    L.append(f"| deflated Sharpe (Bailey/LdP, n_trials={n_trials}) | {_deflated_sharpe(oos_net, n_trials):.3f} |")
    L.append("")
    L.append("## Capacity")
    L.append("")
    L.append(f"- median total 1%-of-ADV budget across the universe: ${capacity:,.0f}")
    L.append("- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;")
    L.append("  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).")
    L.append("")
    L.append("## Limitations")
    L.append("")
    L.append("- Masked break days (unexplained jumps such as ticker reuse, renames, leveraged ETFs)")
    L.append("  have `return_1d IS NULL` in silver. Positions held across a masked day earn **0** that")
    L.append("  day — the return is NaN and skipped by the P&L summation. No signal is generated on")
    L.append("  masked days.")
    L.append("")
    return L


if __name__ == "__main__":
    main()
