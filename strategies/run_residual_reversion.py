"""End-to-end residual mean-reversion baseline on the real tradable universe.

Pulls a compact daily dataset (universe membership, closes, SPY/RSP/QQQ,
breadth regime) from the SQL warehouse via ``databricks-sdk`` and runs the
pandas signal + backtest pipeline locally. A ~300-symbol daily book does not
need a Spark cluster; the SQL warehouse returns the data and the driver runs the
regression.

Usage:
    python strategies/run_residual_reversion.py [--config strategies/config.yaml] [--output strategies/results/residual_reversion_r1.md]

Credentials come from ``~/.databrickscfg`` (``DATABRICKS_PROFILE``, default
``evangohsg``). No secrets are stored in the repo.
"""
from __future__ import annotations

import argparse
import copy
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

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

# ── Config helpers ────────────────────────────────────────────────────────────

_RESIDUAL_VALID_KEYS = frozenset({
    "status", "bar_freq", "factor_model", "factor_window", "pca_components",
    "residual_lookback", "entry_threshold", "exit_threshold",
    "max_hold_candidates", "min_obs_fraction", "universe_size", "target_gross",
    "book_capital", "execution_lag_bars",
})


def load_strategy_config(path: str | Path) -> dict:
    """Load and return the strategy YAML config from *path*."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_cost_params(config: Mapping) -> CostParams:
    """Build a :class:`CostParams` from the ``cost_model`` section of config."""
    cm = config.get("cost_model", {})
    borrow_daily = cm.get("borrow_bps_daily", {"liquid": 0.25, "medium": 0.75, "illiquid": 2.00})
    borrow_thresholds = cm.get("borrow_bucket_thresholds", [5.0e7, 2.0e7])
    return CostParams(
        commission_bps=cm.get("commission_bps", 0.5),
        spread_bps=cm.get("spread_bps", 3.0),
        slippage_bps=cm.get("slippage_bps", 2.0),
        adv_participation_cap=cm.get("adv_participation_cap", 0.01),
        borrow_bps_daily=borrow_daily if isinstance(borrow_daily, dict) else dict(borrow_daily),
        borrow_bucket_thresholds=tuple(borrow_thresholds),
    )


def validate_residual_config(config: Mapping) -> None:
    """Reject unknown or missing keys in the ``residual_reversion`` block."""
    rr = config.get("residual_reversion")
    if rr is None:
        raise ValueError("config missing 'residual_reversion' block")
    unknown = set(rr.keys()) - _RESIDUAL_VALID_KEYS
    if unknown:
        raise ValueError(f"unknown residual_reversion keys: {sorted(unknown)}")
    missing = _RESIDUAL_VALID_KEYS - set(rr.keys())
    if missing:
        raise ValueError(f"missing residual_reversion keys: {sorted(missing)}")

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


def fetch_data(w: WorkspaceClient) -> Dict[str, pd.DataFrame]:
    from strategies.universe import screen_universe

    bronze = _fetch(w, f"""
        SELECT symbol, event_date, close, volume
        FROM {FQN}.bronze_ohlcv_day
        WHERE close IS NOT NULL AND close > 0
          AND volume IS NOT NULL AND volume > 0
    """)
    bronze = bronze.assign(
        event_date=pd.to_datetime(bronze["event_date"]),
        close=pd.to_numeric(bronze["close"], errors="coerce"),
        volume=pd.to_numeric(bronze["volume"], errors="coerce"),
    )
    bronze["dollar_volume"] = bronze["close"] * bronze["volume"]

    # Full panel for universe screening.
    panel = bronze[["symbol", "event_date", "close", "dollar_volume"]].copy()

    # Close-only long frame for signal building.
    closes = bronze[["symbol", "event_date", "close"]].copy()

    # Screen top-500 universe from the full bronze panel.
    universe = screen_universe(panel[["symbol", "event_date", "dollar_volume"]], n=500)

    # Gold membership for parity check only.
    gold = _fetch(w, f"""
        SELECT trade_date, symbol, med_adv_60d, adv_rank
        FROM {FQN}.gold_tradable_universe
    """)
    gold = gold.assign(
        trade_date=pd.to_datetime(gold["trade_date"]),
        med_adv_60d=pd.to_numeric(gold["med_adv_60d"], errors="coerce"),
    )

    regime = _fetch(w, f"""
        SELECT trade_date, breadth_regime
        FROM {FQN}.gold_regime_features
    """)
    regime = regime.assign(trade_date=pd.to_datetime(regime["trade_date"]))

    return {"universe": universe, "closes": closes, "regime": regime,
            "panel": panel, "gold": gold}


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
    factor_model: str = "ols_mkt_ind",
    pca_components: int = 10,
    min_obs_fraction: float = 0.8,
) -> Dict[str, pd.DataFrame]:
    """Compute residual s-scores and desired positions for the tradable set.

    Dispatches between OLS market/industry (``ols_mkt_ind``) and PCA
    statistical-factor (``pca``) models based on *factor_model*.
    """
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

    market = returns["SPY"]
    industry = pd.Series(
        {s: industry_map.get(s, "__unknown__") for s in tradeable}, dtype=object,
    )

    if factor_model == "ols_mkt_ind":
        ind_factor = compute_industry_factor(tradeable_returns, industry)
        min_obs = int(np.ceil(min_obs_fraction * window))
        res = compute_residuals(tradeable_returns, market, ind_factor,
                                window=window, lookback=lookback,
                                min_obs=min_obs)
    elif factor_model == "pca":
        from strategies.residual_reversion import compute_pca_residuals
        min_obs = int(np.ceil(min_obs_fraction * window))
        res = compute_pca_residuals(
            tradeable_returns, window=window, lookback=lookback,
            n_components=pca_components,
            min_obs=min_obs,
        )
    else:
        raise ValueError(f"unknown factor_model: {factor_model!r}")

    positions = generate_signals(res["s_score"], entry=entry, exit_thresh=exit_thresh,
                                 max_hold=max_hold)
    result = {
        "returns": tradeable_returns,
        "market": market,
        "industry": industry,
        "s_score": res["s_score"],
        "positions": positions,
    }
    # Include model-specific keys for downstream use.
    if factor_model == "ols_mkt_ind":
        result["beta_mkt"] = res["beta_mkt"]
    elif factor_model == "pca":
        result["loadings"] = res.get("loadings")
    return result


def run_one(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    universe: pd.DataFrame,
    adv_wide: pd.DataFrame,
    beta_mkt: pd.DataFrame,
    industry: pd.Series,
    book_capital: float,
    n_trials: int,
    cost_params: Optional[CostParams] = None,
    target_gross: float = 1.0,
    execution_lag_bars: int = 1,
) -> Dict:
    """Run the backtest for a single configuration, restricted to the dates in
    ``positions``. Returns the daily series and the metric bundle."""
    dates = positions.index
    adv = adv_wide.reindex(index=dates, columns=positions.columns).fillna(0.0)
    beta_aligned = beta_mkt.reindex(dates) if beta_mkt is not None else None
    res = run_backtest(
        positions,
        returns.reindex(dates), universe, adv,
        beta=beta_aligned, industry=industry,
        book_capital=book_capital, target_gross=target_gross,
        cost_params=cost_params,
        n_trials=n_trials,
        execution_lag_bars=execution_lag_bars,
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
    ap.add_argument("--config", default="strategies/config.yaml")
    ap.add_argument("--output", default="strategies/results/residual_reversion_r4.md")
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--book-capital", type=float, default=None)
    ap.add_argument("--factor-model", choices=["ols_mkt_ind", "pca"], default=None)
    ap.add_argument("--pca-components", type=int, default=None)
    ap.add_argument("--robustness", action="store_true",
                    help="Run full robustness suite and write report")
    ap.add_argument("--robustness-output",
                    default="strategies/results/robustness_r1.md")
    args = ap.parse_args()

    if args.round is None:
        args.round = parse_round_from_output(args.output)

    cfg = load_strategy_config(args.config)
    validate_residual_config(cfg)
    rr = cfg["residual_reversion"]

    # CLI overrides are applied to a fresh config copy, never mutate module/global state.
    factor_model = args.factor_model if args.factor_model is not None else rr["factor_model"]
    pca_components = args.pca_components if args.pca_components is not None else rr["pca_components"]
    book_capital = args.book_capital if args.book_capital is not None else rr["book_capital"]

    WINDOW = rr["factor_window"]
    LOOKBACK = rr["residual_lookback"]
    ENTRY = rr["entry_threshold"]
    EXIT = rr["exit_threshold"]
    hold_candidates = list(rr["max_hold_candidates"])
    min_obs_fraction = rr.get("min_obs_fraction", 0.8)
    target_gross = rr.get("target_gross", 1.0)
    execution_lag_bars = rr.get("execution_lag_bars", 1)

    cost_params = build_cost_params(cfg)

    w = WorkspaceClient(profile=os.getenv("DATABRICKS_PROFILE", "evangohsg"))
    data = fetch_data(w)

    closes = data["closes"]
    universe = data["universe"]
    regime = data["regime"]
    panel = data["panel"]

    # Wide ADV (trailing median dollar volume) from the universe table.
    adv_wide = universe.pivot(index="trade_date", columns="symbol",
                              values="med_adv_60d").sort_index()

    # Signals per max-hold candidate (shared s-scores).
    signals = {}
    for h in hold_candidates:
        signals[h] = build_signals(closes, universe, WINDOW, LOOKBACK, ENTRY, EXIT, h,
                                   factor_model=factor_model,
                                   pca_components=pca_components,
                                   min_obs_fraction=min_obs_fraction)

    industry = signals[hold_candidates[0]]["industry"]

    # For OLS model, use beta_mkt for neutralisation; for PCA, no market beta.
    beta_mkt = signals[hold_candidates[0]].get("beta_mkt")

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
            r = run_one(signals[h]["positions"], signals[h]["returns"], universe,
                        adv_wide, beta_mkt, industry, book_capital, n_trials,
                        cost_params=cost_params, target_gross=target_gross,
                        execution_lag_bars=execution_lag_bars)
            tr = r["net"].loc[train_dates].dropna()
            sr = _sharpe(tr)
            if sr > best_sr:
                best_h, best_sr = h, sr
        # Evaluate the chosen config out-of-sample on the validation fold.
        r = run_one(signals[best_h]["positions"], signals[best_h]["returns"], universe,
                    adv_wide, beta_mkt, industry, book_capital, n_trials,
                    cost_params=cost_params, target_gross=target_gross,
                    execution_lag_bars=execution_lag_bars)
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

    base_res = run_one(base_pos, signals[h_default]["returns"], universe, adv_wide,
                       beta_mkt, industry, book_capital, n_trials,
                       cost_params=cost_params, target_gross=target_gross,
                       execution_lag_bars=execution_lag_bars)
    gated_res = run_one(gated_positions, signals[h_default]["returns"], universe, adv_wide,
                        beta_mkt, industry, book_capital, n_trials,
                        cost_params=cost_params, target_gross=target_gross,
                        execution_lag_bars=execution_lag_bars)

    capacity = _capacity(adv_wide)

    # ── Robustness suite ─────────────────────────────────────────────────────
    if args.robustness:
        from strategies.robustness import (
            build_variant_registry,
            render_robustness_report,
            run_cost_stress,
            run_universe_stress,
            run_parameter_stress,
            remove_top_pnl_contributors,
            compute_fold_metrics,
            compute_exposures,
            compute_capacity,
            compute_margin_bps,
            compute_rank_ic,
            evaluate_gates,
        )
        robustness_cfg = cfg.get("robustness", {})
        gates_cfg = cfg.get("metric_gates", {})

        registry = build_variant_registry(cfg)
        exec_count = len(registry)

        variant_results = []
        for vs in registry:
            try:
                vr = _run_variant(vs, closes, universe, adv_wide, industry,
                                  book_capital, cost_params, cfg, panel=panel)
                variant_results.append(vr)
            except Exception as e:
                variant_results.append({"variant_id": vs.variant_id, "error": str(e)})

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=gates_cfg,
            config=cfg,
            n_trials=len(registry),
            executed_trials=exec_count,
            splits=splits,
        )
        os.makedirs(os.path.dirname(args.robustness_output), exist_ok=True)
        with open(args.robustness_output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"wrote {args.robustness_output}", flush=True)

    # ── Render the results file ──────────────────────────────────────────────
    lines = _render(
        base_res, gated_res, oos_net, n_trials, capacity, book_capital,
        WINDOW, LOOKBACK, ENTRY, EXIT, dates[0], dates[-1], len(dates), len(splits),
        round_num=args.round,
    )
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {args.output}", flush=True)


def _run_variant(variant_spec, closes, universe, adv_wide, industry,
                 book_capital, cost_params, cfg, panel=None):
    """Run a single variant for the robustness suite."""
    from strategies.robustness import VariantSpec, build_variant_registry, remove_top_pnl_contributors
    from strategies.universe import screen_universe
    vs = variant_spec
    vc = copy.deepcopy(cfg["residual_reversion"])
    vc.update(vs.params)
    # Apply parameter overrides
    window = vc.get("factor_window", 60)
    lookback = vc.get("residual_lookback", 5)
    entry = vc.get("entry_threshold", 2.5)
    exit_thresh = vc.get("exit_threshold", 0.5)
    max_hold = vc.get("max_hold", 5)
    factor_model = vc.get("factor_model", "ols_mkt_ind")
    pca_components = vc.get("pca_components", 10)
    universe_size = vc.get("universe_size", 300)
    min_obs_fraction = vc.get("min_obs_fraction", 0.8)
    target_gross = vc.get("target_gross", 1.0)
    execution_lag_bars = vc.get("execution_lag_bars", 1)
    cost_mult = vs.params.get("cost_multiplier", 1.0)
    drop_top = vs.params.get("drop_top_pnl", 0)

    # Filter universe to the requested size using screen_universe.
    if panel is not None:
        univ_sub = screen_universe(
            panel[["symbol", "event_date", "dollar_volume"]], n=universe_size,
        )
        closes_sub = closes[closes["symbol"].isin(set(univ_sub["symbol"]))].copy()
    else:
        univ_sub = universe[universe["adv_rank"] <= universe_size].copy()
        closes_sub = closes

    sig = build_signals(closes_sub, univ_sub, window, lookback, entry, exit_thresh,
                        max_hold, factor_model=factor_model,
                        pca_components=pca_components,
                        min_obs_fraction=min_obs_fraction)
    beta_mkt = sig.get("beta_mkt")
    n_trials = len(build_variant_registry(cfg))

    # Handle top-P&L contributor removal.
    if drop_top > 0:
        # Run baseline backtest first to identify top contributors.
        base_res = run_one(sig["positions"], sig["returns"], univ_sub, adv_wide,
                          beta_mkt, industry, book_capital, n_trials,
                          cost_params=cost_params, target_gross=target_gross,
                          execution_lag_bars=execution_lag_bars)
        drop_result = remove_top_pnl_contributors(
            base_res["net"], base_res["weights"], sig["returns"],
            n_remove=drop_top,
        )
        # Remove top contributors from eligible set and rebuild.
        dropped_syms = set(drop_result["removed_symbols"])
        keep = [s for s in univ_sub["symbol"] if s not in dropped_syms]
        univ_trimmed = univ_sub[univ_sub["symbol"].isin(keep)].copy()
        closes_trimmed = closes_sub[closes_sub["symbol"].isin(keep)].copy()
        sig = build_signals(closes_trimmed, univ_trimmed, window, lookback,
                            entry, exit_thresh, max_hold,
                            factor_model=factor_model,
                            pca_components=pca_components,
                            min_obs_fraction=min_obs_fraction)
        beta_mkt = sig.get("beta_mkt")

    res = run_one(sig["positions"], sig["returns"], univ_sub, adv_wide,
                  beta_mkt, industry, book_capital, n_trials,
                  cost_params=cost_params, target_gross=target_gross,
                  execution_lag_bars=execution_lag_bars)

    # If cost multiplier != 1, rerun with scaled costs.
    if cost_mult != 1.0:
        from strategies.backtest import compute_costs
        from strategies.cost_model import CostParams as CP
        weights = res["weights"]
        returns = sig["returns"].reindex(weights.index)
        adv_aligned = adv_wide.reindex(index=returns.index, columns=returns.columns).fillna(0.0)
        costs_stress = compute_costs(weights, adv_aligned, book_capital, cost_params,
                                     cost_multiplier=cost_mult)
        gross = res["gross"]
        net_stress = gross - costs_stress["total"]
        res["net"] = net_stress
        res["metrics"]["net_sharpe"] = _sharpe(net_stress)
        res["metrics"]["net_ann_return"] = float(net_stress.mean() * 252)

    # Compute IS/OOS Sharpe (80/20 split of the net series).
    net = res["net"]
    split_idx = int(len(net) * 0.8)
    is_sharpe = _sharpe(net.iloc[:split_idx]) if split_idx > 1 else float("nan")
    oos_sharpe = _sharpe(net.iloc[split_idx:]) if len(net) - split_idx > 1 else float("nan")

    return {
        "variant_id": vs.variant_id,
        "fingerprint": vs.fingerprint,
        "net": res["net"],
        "gross": res["gross"],
        "metrics": res["metrics"],
        "weights": res["weights"],
        "turnover": res["turnover"],
        "is_sharpe": is_sharpe,
        "oos_sharpe": oos_sharpe,
        "dropped_symbols": list(dropped_syms) if drop_top > 0 else [],
    }


def _render(base_res, gated_res, oos_net, n_trials, capacity, book_capital,
            window, lookback, entry, exit_thresh, date_start, date_end, n_dates, n_folds,
            round_num: int = 3) -> List[str]:
    bm = base_res["metrics"]
    gm = gated_res["metrics"]
    prev = round_num - 1
    L = []
    L.append(f"# Residual mean-reversion — round {round_num} (real data)")
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
    L.append(f"- book capital: ${book_capital:,.0f}; target gross 1.0 (100% long / 100% short)")
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
    return L


if __name__ == "__main__":
    main()
