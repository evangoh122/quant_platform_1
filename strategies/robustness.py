"""Pure robustness library for residual mean-reversion strategies.

All functions are pure pandas/numpy/scikit-learn and testable with synthetic
frames.  No Databricks imports or network calls belong here.

Public API:
    VariantSpec, build_variant_registry,
    run_cost_stress, run_universe_stress, run_parameter_stress,
    remove_top_pnl_contributors,
    compute_fold_metrics, compute_exposures, compute_capacity,
    compute_margin_bps, compute_rank_ic,
    evaluate_gates, render_robustness_report.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


# ── Variant registry ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VariantSpec:
    """A single tried parameter vector with stable ID and fingerprint."""
    variant_id: str
    fingerprint: str
    params: dict
    category: str  # e.g. "baseline", "cost_stress", "universe_stress", etc.


def _fingerprint(params: dict) -> str:
    """Stable hash of a parameter dict."""
    blob = json.dumps(params, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def build_variant_registry(base_config: Mapping) -> list[VariantSpec]:
    """Build the single ledger for multiple testing.

    Every unique tried parameter vector gets a stable ID and fingerprint.
    The nominal 1x/top-300/unperturbed baseline is deduplicated (counted once).
    """
    rr = base_config.get("residual_reversion", {})
    robustness = base_config.get("robustness", {})

    factor_models = ["ols_mkt_ind", "pca"]
    hold_candidates = list(rr.get("max_hold_candidates", [3, 5, 10]))
    cost_multipliers = list(robustness.get("cost_multipliers", [1.0, 2.0, 3.0]))
    universe_sizes = list(robustness.get("universe_sizes", [200, 300, 500]))
    perturbation = robustness.get("parameter_perturbation", 0.20)
    drop_top = robustness.get("drop_top_pnl_contributors", 3)

    entry = rr.get("entry_threshold", 2.5)
    exit_thresh = rr.get("exit_threshold", 0.5)
    factor_window = rr.get("factor_window", 60)

    seen_fingerprints: set[str] = set()
    registry: list[VariantSpec] = []

    def _add(variant_id: str, params: dict, category: str) -> None:
        fp = _fingerprint(params)
        if fp in seen_fingerprints:
            return
        seen_fingerprints.add(fp)
        registry.append(VariantSpec(
            variant_id=variant_id, fingerprint=fp,
            params=params, category=category,
        ))

    # Baseline: nominal 1x/top-300/unperturbed, both factor models.
    for fm in factor_models:
        for h in hold_candidates:
            _add(
                f"baseline_{fm}_h{h}",
                {"factor_model": fm, "max_hold": h, "universe_size": 300,
                 "cost_multiplier": 1.0, "entry_threshold": entry,
                 "exit_threshold": exit_thresh, "factor_window": factor_window},
                "baseline",
            )

    # Cost stress: 2x and 3x.
    for cm in cost_multipliers:
        if cm == 1.0:
            continue  # already in baseline
        for fm in factor_models:
            for h in hold_candidates:
                _add(
                    f"cost_{fm}_h{h}_{cm}x",
                    {"factor_model": fm, "max_hold": h, "universe_size": 300,
                     "cost_multiplier": cm, "entry_threshold": entry,
                     "exit_threshold": exit_thresh, "factor_window": factor_window},
                    "cost_stress",
                )

    # Universe stress: 200, 500 (300 is baseline).
    for us in universe_sizes:
        if us == 300:
            continue
        for fm in factor_models:
            for h in hold_candidates:
                _add(
                    f"univ_{fm}_h{h}_n{us}",
                    {"factor_model": fm, "max_hold": h, "universe_size": us,
                     "cost_multiplier": 1.0, "entry_threshold": entry,
                     "exit_threshold": exit_thresh, "factor_window": factor_window},
                    "universe_stress",
                )

    # Parameter perturbation: ±20% on entry_threshold, exit_threshold, factor_window.
    for param_name, base_val in [("entry_threshold", entry),
                                  ("exit_threshold", exit_thresh),
                                  ("factor_window", factor_window)]:
        for direction, factor in [("lo", 1.0 - perturbation), ("hi", 1.0 + perturbation)]:
            perturbed_val = base_val * factor
            if param_name == "factor_window":
                perturbed_val = max(10, int(round(perturbed_val)))
            for fm in factor_models:
                for h in hold_candidates:
                    p = {
                        "factor_model": fm, "max_hold": h, "universe_size": 300,
                        "cost_multiplier": 1.0, "entry_threshold": entry,
                        "exit_threshold": exit_thresh, "factor_window": factor_window,
                    }
                    p[param_name] = perturbed_val
                    _add(
                        f"param_{fm}_h{h}_{param_name}_{direction}",
                        p,
                        "parameter_stress",
                    )

    # Top-PNL contributor removal (counted as one variant per factor model).
    for fm in factor_models:
        for h in hold_candidates:
            _add(
                f"drop_top_{fm}_h{h}",
                {"factor_model": fm, "max_hold": h, "universe_size": 300,
                 "cost_multiplier": 1.0, "entry_threshold": entry,
                 "exit_threshold": exit_thresh, "factor_window": factor_window,
                 "drop_top_pnl": drop_top},
                "top_pnl_removal",
            )

    return registry


# ── Stress tests ──────────────────────────────────────────────────────────────

def run_cost_stress(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    adv: pd.DataFrame,
    book_capital: float,
    cost_params: Any,
    cost_multiplier: float,
) -> dict:
    """Rerun backtest with same weights/signals at a cost multiplier.

    At 2x/3x every bps component (including borrow) scales exactly once,
    while ADV participation and gross P&L do not change.
    """
    from strategies.backtest import compute_costs
    costs = compute_costs(weights, adv, book_capital, cost_params,
                          cost_multiplier=cost_multiplier)
    gross = (weights.shift(1).fillna(0.0) * returns).sum(axis=1)
    net = gross - costs["total"]
    return {"net": net, "gross": gross, "costs": costs}


def run_universe_stress(
    closes: pd.DataFrame,
    universe: pd.DataFrame,
    n: int,
    build_signals_fn,
    run_one_fn,
    **kwargs,
) -> dict:
    """Build independent daily PIT membership for *n* and run signals."""
    univ_sub = universe[universe["adv_rank"] <= n].copy()
    return run_one_fn(universe=univ_sub, **kwargs)


def run_parameter_stress(
    base_params: dict,
    param_name: str,
    factor: float,
) -> dict:
    """Return params with one parameter perturbed by *factor*."""
    p = dict(base_params)
    p[param_name] = p[param_name] * factor
    return p


def remove_top_pnl_contributors(
    net_returns: pd.Series,
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    n_remove: int,
) -> dict:
    """Identify top *n_remove* P&L contributors and recompute without them.

    Uses executed/lagged weights and allocated costs.  No future information
    is fed back into the original strategy.
    """
    # Per-symbol total realized net P&L contribution.
    pnl_by_sym = (weights.shift(1).fillna(0.0) * returns).sum()
    top_syms = pnl_by_sym.nlargest(n_remove).index.tolist()

    # Zero out those symbols and recompute.
    weights_trimmed = weights.copy()
    weights_trimmed[top_syms] = 0.0
    net_trimmed = (weights_trimmed.shift(1).fillna(0.0) * returns).sum(axis=1)

    return {
        "removed_symbols": top_syms,
        "net_trimmed": net_trimmed,
        "original_net": net_returns,
    }


# ── Fold metrics ──────────────────────────────────────────────────────────────

def compute_fold_metrics(
    net_returns: pd.Series,
    splits: list[tuple[np.ndarray, np.ndarray]],
) -> list[dict]:
    """Report each fold's net Sharpe and net annualized return.

    Uses the same purged/embargoed walk-forward validation folds.
    """
    from strategies.backtest import _sharpe
    folds = []
    for fold_i, (train_idx, val_idx) in enumerate(splits):
        val_returns = net_returns.iloc[val_idx]
        sharpe = _sharpe(val_returns)
        ann_return = float(val_returns.mean() * 252)
        folds.append({
            "fold": fold_i,
            "net_sharpe": sharpe,
            "net_ann_return": ann_return,
            "profitable": bool(val_returns.sum() > 0),
        })
    return folds


# ── Exposures ─────────────────────────────────────────────────────────────────

def compute_exposures(
    weights: pd.DataFrame,
    beta: Optional[pd.DataFrame] = None,
    industry: Optional[pd.Series] = None,
) -> dict:
    """Daily and summarized exposure metrics.

    Returns max absolute and mean absolute dollar exposure (sum(w) / gross),
    beta exposure (sum(w*beta) / gross), and per-sector max |net exposure|.
    The overall max |sector net exposure| is also reported.
    """
    gross = weights.abs().sum(axis=1)
    gross = gross.replace(0.0, np.nan)

    # Dollar exposure: sum(weights) / gross.
    dollar_exp = weights.sum(axis=1) / gross
    max_abs_dollar = float(dollar_exp.abs().max()) if len(dollar_exp.dropna()) > 0 else float("nan")
    mean_abs_dollar = float(dollar_exp.abs().mean()) if len(dollar_exp.dropna()) > 0 else float("nan")

    # Beta exposure: sum(w * beta) / gross.
    if beta is not None:
        beta_aligned = beta.reindex(index=weights.index, columns=weights.columns)
        beta_exp = (weights * beta_aligned).sum(axis=1) / gross
        max_abs_beta = float(beta_exp.abs().max()) if len(beta_exp.dropna()) > 0 else float("nan")
        mean_abs_beta = float(beta_exp.abs().mean()) if len(beta_exp.dropna()) > 0 else float("nan")
    else:
        max_abs_beta = float("nan")
        mean_abs_beta = float("nan")

    # Industry exposure: max |sector net exposure| per sector.
    industry_exp = {}
    max_abs_sector = float("nan")
    if industry is not None:
        sector_nets: dict[str, list[float]] = {}
        for date in weights.index:
            w = weights.loc[date]
            active = w[w != 0.0]
            if active.empty:
                continue
            ind = industry.reindex(active.index)
            for ind_name in ind.unique():
                mask = ind == ind_name
                exp = float(active[mask].sum())
                if ind_name not in sector_nets:
                    sector_nets[ind_name] = []
                sector_nets[ind_name].append(exp)
        industry_exp = {k: float(np.max(np.abs(v))) for k, v in sector_nets.items()}
        if industry_exp:
            max_abs_sector = float(np.max(list(industry_exp.values())))

    return {
        "max_abs_dollar_exposure": max_abs_dollar,
        "mean_abs_dollar_exposure": mean_abs_dollar,
        "max_abs_beta_exposure": max_abs_beta,
        "mean_abs_beta_exposure": mean_abs_beta,
        "industry_exposure": industry_exp,
        "max_abs_sector_exposure": max_abs_sector,
    }


# ── Capacity ──────────────────────────────────────────────────────────────────

def compute_capacity(
    weights: pd.DataFrame,
    adv: pd.DataFrame,
    book_capital: float,
    participation_cap: float = 0.01,
) -> dict:
    """Maximum deployable capital implied by each nonzero executed order.

    ``participation_cap * ADV / abs(delta_weight_open_leg)`` per symbol-day.
    Summarized conservatively by the minimum finite constraint.
    """
    dw = weights.diff().abs()
    dw.iloc[0] = weights.iloc[0].abs()
    # Only the open leg (increase) counts for capacity.
    adv_aligned = adv.reindex(index=weights.index, columns=weights.columns).fillna(0.0)

    caps = pd.DataFrame(np.nan, index=weights.index, columns=weights.columns)
    for date in weights.index:
        for sym in weights.columns:
            delta = dw.loc[date, sym]
            a = adv_aligned.loc[date, sym]
            if delta > 0 and a > 0:
                caps.loc[date, sym] = participation_cap * a / delta

    # Minimum finite constraint across all dates/symbols.
    finite_caps = caps.values[np.isfinite(caps.values)]
    min_cap = float(np.min(finite_caps)) if len(finite_caps) > 0 else float("nan")
    p5 = float(np.percentile(finite_caps, 5)) if len(finite_caps) > 0 else float("nan")
    p10 = float(np.percentile(finite_caps, 10)) if len(finite_caps) > 0 else float("nan")
    p50 = float(np.percentile(finite_caps, 50)) if len(finite_caps) > 0 else float("nan")

    return {
        "min_capacity": min_cap,
        "p5_capacity": p5,
        "p10_capacity": p10,
        "p50_capacity": p50,
    }


# ── Margin ────────────────────────────────────────────────────────────────────

def compute_margin_bps(
    net_returns: pd.Series,
    turnover: pd.Series,
) -> float:
    """Margin in basis points: ``sum(net_return) / sum(one_way_turnover) * 10_000``.

    Returns ``N/A`` (NaN) when denominator is zero.
    """
    total_turnover = turnover.sum()
    if total_turnover == 0:
        return float("nan")
    return float(net_returns.sum() / total_turnover * 10_000)


# ── Rank IC ───────────────────────────────────────────────────────────────────

def _newey_west_se(x: np.ndarray, max_lag: int) -> float:
    """Newey-West (HAC) standard error of the mean.

    Uses Bartlett kernel: w_j = 1 - j/(max_lag+1) for j = 0..max_lag.
    Returns the HAC standard error of the sample mean.
    """
    n = len(x)
    if n < 2:
        return float("nan")
    mu = x.mean()
    demeaned = x - mu
    # Gamma_0 (variance).
    gamma_0 = float(np.dot(demeaned, demeaned) / n)
    # Gamma_j for j = 1..max_lag with Bartlett weights.
    hac_var = gamma_0
    for j in range(1, max_lag + 1):
        if j >= n:
            break
        gamma_j = float(np.dot(demeaned[j:], demeaned[:-j]) / n)
        weight = 1.0 - j / (max_lag + 1)
        hac_var += 2.0 * weight * gamma_j
    if hac_var <= 0:
        return float("nan")
    return np.sqrt(hac_var / n)


def compute_rank_ic(
    s_score: pd.DataFrame,
    residual_returns: pd.DataFrame,
    horizon_days: int = 5,
) -> dict:
    """Per-date Spearman rank correlation between s_score[t] and next-H-day
    cumulative residual return.

    Under mean reversion, raw s-score should predict **negative** future
    residual return.  The target is shifted so no future value enters the
    signal.

    The t-stat uses a Newey-West (HAC) standard error with lag = H-1 to
    account for the overlap in the H-day forward windows.  Also reports
    the effective sample size n/H (non-overlapping count).
    """
    # Future cumulative residual return over horizon_days.
    future_ret = residual_returns.rolling(horizon_days, min_periods=horizon_days).sum().shift(-horizon_days)

    ic_values = []
    for date in s_score.index:
        s = s_score.loc[date].dropna()
        f = future_ret.loc[date].dropna()
        common = s.index.intersection(f.index)
        if len(common) < 2:
            continue
        s_c = s[common]
        f_c = f[common]
        if s_c.nunique() < 2 or f_c.nunique() < 2:
            continue
        corr, _ = spearmanr(s_c.to_numpy(), f_c.to_numpy())
        ic_values.append({"date": date, "ic": corr})

    if not ic_values:
        return {"mean_ic": float("nan"), "std_ic": float("nan"),
                "t_stat": float("nan"), "n": 0, "effective_n": 0,
                "sign": "N/A"}

    ic_series = pd.Series([v["ic"] for v in ic_values])
    mean = float(ic_series.mean())
    std = float(ic_series.std(ddof=1)) if len(ic_series) > 1 else float("nan")
    n = len(ic_values)
    # Effective n: non-overlapping count (every H-th observation).
    effective_n = max(n // horizon_days, 1)
    # Newey-West HAC t-stat with lag = H - 1.
    hac_se = _newey_west_se(ic_series.to_numpy(), max_lag=horizon_days - 1)
    t_stat = mean / hac_se if np.isfinite(hac_se) and hac_se > 0 else float("nan")
    sign = "negative (expected under mean reversion)" if mean < 0 else "positive"

    hit_rate = float((ic_series < 0).sum() / n) if n > 0 else float("nan")

    return {
        "mean_ic": mean,
        "std_ic": std,
        "t_stat": t_stat,
        "n": n,
        "effective_n": effective_n,
        "sign": sign,
        "hit_rate": hit_rate,
    }


# ── Gate evaluation ───────────────────────────────────────────────────────────

def evaluate_gates(metrics: Mapping, gates: Mapping) -> dict[str, str]:
    """Evaluate configured gates.  Returns ``PASS``, ``FAIL``, or ``N/A`` per gate."""
    results = {}

    # sharpe_min
    if "net_sharpe" in metrics and "sharpe_min" in gates:
        v = metrics["net_sharpe"]
        if np.isfinite(v):
            results["sharpe_min"] = "PASS" if v >= gates["sharpe_min"] else "FAIL"
        else:
            results["sharpe_min"] = "N/A"
    else:
        results["sharpe_min"] = "N/A"

    # max_drawdown_max: abs(max_drawdown) <= threshold
    if "net_max_drawdown" in metrics and "max_drawdown_max" in gates:
        v = metrics["net_max_drawdown"]
        if np.isfinite(v):
            results["max_drawdown_max"] = "PASS" if abs(v) <= gates["max_drawdown_max"] else "FAIL"
        else:
            results["max_drawdown_max"] = "N/A"
    else:
        results["max_drawdown_max"] = "N/A"

    # return_to_dd_min: annualized return / abs(max_drawdown)
    if "net_ann_return" in metrics and "net_max_drawdown" in metrics and "return_to_dd_min" in gates:
        ret = metrics["net_ann_return"]
        dd = metrics["net_max_drawdown"]
        if np.isfinite(ret) and np.isfinite(dd) and abs(dd) > 0:
            ratio = ret / abs(dd)
            results["return_to_dd_min"] = "PASS" if ratio >= gates["return_to_dd_min"] else "FAIL"
        else:
            results["return_to_dd_min"] = "N/A"
    else:
        results["return_to_dd_min"] = "N/A"

    # margin_min_bps
    if "margin_bps" in metrics and "margin_min_bps" in gates:
        v = metrics["margin_bps"]
        if np.isfinite(v):
            results["margin_min_bps"] = "PASS" if v >= gates["margin_min_bps"] else "FAIL"
        else:
            results["margin_min_bps"] = "N/A"
    else:
        results["margin_min_bps"] = "N/A"

    # oos_ratio_min: OOS Sharpe >= 0.5 * IS Sharpe
    if "oos_sharpe" in metrics and "is_sharpe" in metrics and "oos_ratio_min" in gates:
        oos = metrics["oos_sharpe"]
        is_sr = metrics["is_sharpe"]
        if np.isfinite(oos) and np.isfinite(is_sr) and abs(is_sr) > 1e-9:
            ratio = oos / is_sr
            results["oos_ratio_min"] = "PASS" if ratio >= gates["oos_ratio_min"] else "FAIL"
        else:
            results["oos_ratio_min"] = "N/A"
    else:
        results["oos_ratio_min"] = "N/A"

    return results


# ── Report ────────────────────────────────────────────────────────────────────

def render_robustness_report(
    registry: list[VariantSpec],
    variant_results: list[dict],
    gates: Mapping,
    config: Mapping,
    n_trials: int,
    executed_trials: int,
    splits: Optional[list] = None,
    rank_ic_results: Optional[Mapping[str, dict]] = None,
    drop_top3_results: Optional[Mapping[int, dict]] = None,
) -> str:
    """Render the full robustness report in Markdown.

    Every variant row shows net Sharpe, absolute max drawdown, return/drawdown,
    margin bps, IS Sharpe, OOS Sharpe, OOS/IS ratio, DSR, trial count, and
    separate PASS/FAIL/N/A columns for the five configured gates.
    """
    from strategies.backtest import _sharpe, _max_drawdown
    from ml.evaluate import deflated_sharpe_ratio

    rr = config.get("residual_reversion", {})
    robustness_cfg = config.get("robustness", {})
    rank_ic_horizon = robustness_cfg.get("rank_ic_horizon_days", 5)

    L = []
    L.append("# Robustness report — residual mean-reversion")
    L.append("")
    L.append("PASS/FAIL denotes configured research gates, not evidence or a claim of edge.")
    L.append("")

    # ── Methodology / Configuration ───────────────────────────────────────
    L.append("## Methodology / Configuration")
    L.append("")
    L.append(f"- factor_model: {rr.get('factor_model', 'ols_mkt_ind')} (baseline), pca (statistical)")
    L.append(f"- factor_window: {rr.get('factor_window', 60)}")
    L.append(f"- residual_lookback: {rr.get('residual_lookback', 5)}")
    L.append(f"- entry_threshold: {rr.get('entry_threshold', 2.5)}")
    L.append(f"- exit_threshold: {rr.get('exit_threshold', 0.5)}")
    L.append(f"- max_hold_candidates: {rr.get('max_hold_candidates', [3, 5, 10])}")
    L.append(f"- universe_size: {rr.get('universe_size', 300)}")
    L.append(f"- cost_multipliers: {robustness_cfg.get('cost_multipliers', [1.0, 2.0, 3.0])}")
    L.append(f"- universe_sizes: {robustness_cfg.get('universe_sizes', [200, 300, 500])}")
    L.append(f"- parameter_perturbation: {robustness_cfg.get('parameter_perturbation', 0.20)}")
    L.append(f"- walk_forward_folds: {robustness_cfg.get('walk_forward_folds', 5)}")
    L.append(f"- min_profitable_folds: {robustness_cfg.get('min_profitable_folds', 3)}")
    L.append(f"- Total registry size (all unique configurations): **{n_trials}**")
    L.append(f"- Executed trials in this run: **{executed_trials}**")
    L.append("")

    # Resolve the first valid baseline variant once for reuse.
    baseline_vr = None
    for vr in variant_results:
        if "error" not in vr:
            baseline_vr = vr
            break

    # ── Helper: extract per-variant metrics ───────────────────────────────
    def _variant_metrics(vr: dict) -> dict:
        """Extract standardised metrics dict from a variant result."""
        if "error" in vr:
            return {"error": vr["error"]}
        net = vr.get("net", pd.Series(dtype=float))
        m = vr.get("metrics", {})
        net_sharpe = _sharpe(net)
        max_dd = _max_drawdown(net)
        ann_ret = float(net.mean() * 252)
        ret_dd = ann_ret / abs(max_dd) if abs(max_dd) > 1e-9 else float("nan")
        margin = compute_margin_bps(net, vr.get("turnover", pd.Series(dtype=float)))
        dsr = deflated_sharpe_ratio(net.to_numpy(), n_trials=n_trials, periods_per_year=252)
        is_sharpe = vr.get("is_sharpe", float("nan"))
        oos_sharpe = vr.get("oos_sharpe", float("nan"))
        oos_ratio = oos_sharpe / is_sharpe if np.isfinite(is_sharpe) and abs(is_sharpe) > 1e-9 else float("nan")
        return {
            "net_sharpe": net_sharpe,
            "max_dd": max_dd,
            "ann_ret": ann_ret,
            "ret_dd": ret_dd,
            "margin": margin,
            "dsr": dsr,
            "is_sharpe": is_sharpe,
            "oos_sharpe": oos_sharpe,
            "oos_ratio": oos_ratio,
        }

    def _gate_row(vm: dict) -> dict:
        """Evaluate gates for a variant metrics dict."""
        gate_metrics = {
            "net_sharpe": vm.get("net_sharpe", float("nan")),
            "net_max_drawdown": vm.get("max_dd", float("nan")),
            "net_ann_return": vm.get("ann_ret", float("nan")),
            "margin_bps": vm.get("margin", float("nan")),
            "is_sharpe": vm.get("is_sharpe", float("nan")),
            "oos_sharpe": vm.get("oos_sharpe", float("nan")),
        }
        return evaluate_gates(gate_metrics, gates)

    def _g(gate_results: dict, key: str) -> str:
        return gate_results.get(key, "N/A")

    # ── Factor-model comparison table ─────────────────────────────────────
    L.append("## Factor-model comparison")
    L.append("")
    L.append("| variant | factor model | net Sharpe | IS Sharpe | OOS Sharpe | OOS/IS | DSR |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for vs, vr in zip(registry, variant_results):
        if vs.category != "baseline":
            continue
        vm = _variant_metrics(vr)
        if "error" in vm:
            L.append(f"| {vs.variant_id} | {vs.params.get('factor_model', '?')} | ERROR | — | — | — | — |")
            continue
        fm = vs.params.get("factor_model", "?")
        L.append(
            f"| {vs.variant_id} | {fm} | "
            f"{vm['net_sharpe']:.3f} | {vm['is_sharpe']:.3f} | "
            f"{vm['oos_sharpe']:.3f} | {vm['oos_ratio']:.2f} | {vm['dsr']:.3f} |"
        )
    L.append("")

    # ── Cost stress table (1×/2×/3×) ─────────────────────────────────────
    L.append("## Cost stress (1×/2×/3×)")
    L.append("")
    L.append("| variant | cost mult | net Sharpe | IS Sharpe | OOS Sharpe | OOS/IS | abs maxDD | return/DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for vs, vr in zip(registry, variant_results):
        if vs.category not in ("baseline", "cost_stress"):
            continue
        vm = _variant_metrics(vr)
        if "error" in vm:
            continue
        cm = vs.params.get("cost_multiplier", 1.0)
        L.append(
            f"| {vs.variant_id} | {cm:.1f}× | "
            f"{vm['net_sharpe']:.3f} | {vm['is_sharpe']:.3f} | "
            f"{vm['oos_sharpe']:.3f} | {vm['oos_ratio']:.2f} | "
            f"{abs(vm['max_dd']):.4f} | {vm['ret_dd']:.2f} |"
        )
    L.append("")

    # ── Universe stress table (200/300/500) ───────────────────────────────
    L.append("## Universe stress (200/300/500)")
    L.append("")
    L.append("| variant | universe | net Sharpe | IS Sharpe | OOS Sharpe | OOS/IS | abs maxDD | return/DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for vs, vr in zip(registry, variant_results):
        if vs.category not in ("baseline", "universe_stress"):
            continue
        vm = _variant_metrics(vr)
        if "error" in vm:
            continue
        us = vs.params.get("universe_size", 300)
        L.append(
            f"| {vs.variant_id} | {us} | "
            f"{vm['net_sharpe']:.3f} | {vm['is_sharpe']:.3f} | "
            f"{vm['oos_sharpe']:.3f} | {vm['oos_ratio']:.2f} | "
            f"{abs(vm['max_dd']):.4f} | {vm['ret_dd']:.2f} |"
        )
    L.append("")

    # ── Parameter perturbation table (±20%) ───────────────────────────────
    L.append("## Parameter perturbation (±20%)")
    L.append("")
    L.append("| variant | parameter | direction | net Sharpe | IS Sharpe | OOS Sharpe | OOS/IS |")
    L.append("|---|---|---|---:|---:|---:|---:|")
    for vs, vr in zip(registry, variant_results):
        if vs.category != "parameter_stress":
            continue
        vm = _variant_metrics(vr)
        if "error" in vm:
            continue
        # Extract param name and direction from variant_id.
        parts = vs.variant_id.split("_")
        param_name = parts[-2] if len(parts) >= 2 else "?"
        direction = parts[-1] if len(parts) >= 1 else "?"
        L.append(
            f"| {vs.variant_id} | {param_name} | {direction} | "
            f"{vm['net_sharpe']:.3f} | {vm['is_sharpe']:.3f} | "
            f"{vm['oos_sharpe']:.3f} | {vm['oos_ratio']:.2f} |"
        )
    L.append("")

    # ── Top-3 removal table ───────────────────────────────────────────────
    L.append("## Top-3 P&L contributor removal")
    L.append("")
    L.append("| variant | dropped symbols | net Sharpe | IS Sharpe | OOS Sharpe | OOS/IS |")
    L.append("|---|---|---:|---:|---:|---:|")
    for vs, vr in zip(registry, variant_results):
        if vs.category != "top_pnl_removal":
            continue
        vm = _variant_metrics(vr)
        if "error" in vm:
            continue
        dropped = vr.get("dropped_symbols", [])
        dropped_str = ", ".join(dropped) if dropped else "none"
        L.append(
            f"| {vs.variant_id} | {dropped_str} | "
            f"{vm['net_sharpe']:.3f} | {vm['is_sharpe']:.3f} | "
            f"{vm['oos_sharpe']:.3f} | {vm['oos_ratio']:.2f} |"
        )
    L.append("")

    # ── Per-fold drop-top-3 analysis (training-window P&L only) ──────────
    if drop_top3_results:
        for h, d3 in sorted(drop_top3_results.items()):
            L.append(f"### Drop-top-3 (max_hold={h}, training-window P&L)")
            L.append("")
            fold_rows = d3.get("folds", [])
            if fold_rows:
                L.append("| fold | dropped symbols | OOS Sharpe (full) | OOS Sharpe (drop3) |")
                L.append("|---|---|---:|---:|")
                for fr in fold_rows:
                    ds = ", ".join(fr["dropped"]) if fr["dropped"] else "none"
                    L.append(
                        f"| {fr['fold']} | {ds} | "
                        f"{fr['oos_sharpe']:.3f} | {fr['oos_sharpe_drop3']:.3f} |"
                    )
                all_dropped = d3.get("all_dropped_symbols", [])
                if all_dropped:
                    L.append("")
                    L.append(f"Symbols dropped in ≥1 fold: {', '.join(sorted(set(all_dropped)))}")
            else:
                L.append("_No baseline variant available for this hold period._")
            L.append("")

    # ── Walk-forward folds table ──────────────────────────────────────────
    L.append("## Walk-forward folds")
    L.append("")
    if splits is not None and len(splits) > 0:
        if baseline_vr is not None:
            fold_metrics = compute_fold_metrics(baseline_vr["net"], splits)
            min_profitable = robustness_cfg.get("min_profitable_folds", 3)
            profitable_count = sum(1 for f in fold_metrics if f["profitable"])
            flag = "PASS" if profitable_count >= min_profitable else "FAIL"
            L.append(f"| fold | net Sharpe | net ann return | profitable |")
            L.append(f"|---|---:|---:|---:|")
            for fm in fold_metrics:
                prof = "yes" if fm["profitable"] else "no"
                L.append(f"| {fm['fold']} | {fm['net_sharpe']:.3f} | {fm['net_ann_return']:.4f} | {prof} |")
            L.append(f"| **≥{min_profitable} of {len(splits)} profitable** | | | **{flag}** |")
        else:
            L.append("_No valid baseline results for fold metrics._")
    else:
        L.append("_Walk-forward splits not available._")
    L.append("")

    # ── Exposures table ───────────────────────────────────────────────────
    L.append("## Exposures / industry (baseline)")
    L.append("")
    if baseline_vr is not None:
        weights = baseline_vr.get("weights", pd.DataFrame())
        beta = baseline_vr.get("beta_mkt")
        ind = baseline_vr.get("industry")
        exp = compute_exposures(weights, beta=beta, industry=ind)
        L.append("| metric | value |")
        L.append("|---|---:|")
        L.append(f"| max |dollar exposure| | {exp['max_abs_dollar_exposure']:.4f} |")
        L.append(f"| mean |dollar exposure| | {exp['mean_abs_dollar_exposure']:.4f} |")
        L.append(f"| max |beta exposure| | {exp.get('max_abs_beta_exposure', float('nan')):.4f} |")
        L.append(f"| mean |beta exposure| | {exp.get('mean_abs_beta_exposure', float('nan')):.4f} |")
        if exp.get("industry_exposure"):
            for ind_name, ind_exp in sorted(exp["industry_exposure"].items()):
                L.append(f"| max |sector net| ({ind_name}) | {ind_exp:.4f} |")
        if np.isfinite(exp.get("max_abs_sector_exposure", float("nan"))):
            L.append(f"| max |sector net| (overall) | {exp['max_abs_sector_exposure']:.4f} |")
    else:
        L.append("_No valid baseline results for exposure computation._")
    L.append("")

    # ── Turnover / capacity / margin bps table ────────────────────────────
    L.append("## Turnover / capacity / margin")
    L.append("")
    if baseline_vr is not None:
        net = baseline_vr.get("net", pd.Series(dtype=float))
        turnover = baseline_vr.get("turnover", pd.Series(dtype=float))
        margin = compute_margin_bps(net, turnover)
        L.append("| metric | value |")
        L.append("|---|---:|")
        L.append(f"| avg daily turnover | {turnover.mean():.4f} |")
        L.append(f"| margin (bps) | {margin:.1f} |")
        weights_cap = baseline_vr.get("weights", pd.DataFrame())
        adv_cap = baseline_vr.get("adv_wide")
        if not weights_cap.empty and adv_cap is not None:
            cap = compute_capacity(weights_cap, adv_cap, book_capital=1.0)
            L.append(f"| capacity p50 (median) | ${cap['p50_capacity']:,.0f} |")
            L.append(f"| capacity p5 | ${cap['p5_capacity']:,.0f} |")
            # Compute book size at which cap binds on >X% of trades.
            dw = weights_cap.diff().abs()
            dw.iloc[0] = weights_cap.iloc[0].abs()
            adv_a = adv_cap.reindex(index=weights_cap.index, columns=weights_cap.columns).fillna(0.0)
            participation_cap = 0.01
            raw_caps = pd.DataFrame(np.nan, index=weights_cap.index, columns=weights_cap.columns)
            for date in weights_cap.index:
                for sym in weights_cap.columns:
                    delta = dw.loc[date, sym]
                    a = adv_a.loc[date, sym]
                    if delta > 0 and a > 0:
                        raw_caps.loc[date, sym] = participation_cap * a / delta
            finite_raw = raw_caps.values[np.isfinite(raw_caps.values)]
            if len(finite_raw) > 0:
                for x in [5, 10, 25]:
                    threshold = float(np.percentile(finite_raw, x))
                    pct_bound = float(np.sum(finite_raw <= threshold) / len(finite_raw) * 100)
                    L.append(f"| book size binding >{x}% trades | ${threshold:,.0f} |")
    else:
        L.append("_No valid baseline results._")
    L.append("")

    # ── Rank IC table ─────────────────────────────────────────────────────
    L.append("## Rank IC")
    L.append("")
    if rank_ic_results:
        L.append("| factor model | mean IC | IC t-stat | n | sign | hit rate |")
        L.append("|---|---:|---:|---:|---|---:|")
        for fm, ric in sorted(rank_ic_results.items()):
            L.append(
                f"| {fm} | {ric['mean_ic']:.4f} | {ric['t_stat']:.2f} | "
                f"{ric['n']} | {ric['sign']} | {ric['hit_rate']:.2f} |"
            )
    else:
        L.append("_Rank IC not available; s_score and residual_returns not in variant results._")
    L.append("")

    # ── Gate summary ──────────────────────────────────────────────────────
    L.append("## Gate summary (all variants)")
    L.append("")
    L.append("| variant | category | net Sharpe | IS Sharpe | OOS Sharpe | OOS/IS | "
              "abs maxDD | return/DD | margin bps | DSR | trials | "
              "sharpe_min | max_dd_max | return_dd_min | margin_min | oos_ratio |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

    for vs, vr in zip(registry, variant_results):
        vm = _variant_metrics(vr)
        if "error" in vm:
            L.append(f"| {vs.variant_id} | {vs.category} | ERROR | — | — | — | — | — | — | — | {n_trials} | — | — | — | — | — |")
            continue
        gr = _gate_row(vm)
        L.append(
            f"| {vs.variant_id} | {vs.category} | "
            f"{vm['net_sharpe']:.3f} | {vm['is_sharpe']:.3f} | "
            f"{vm['oos_sharpe']:.3f} | {vm['oos_ratio']:.2f} | "
            f"{abs(vm['max_dd']):.4f} | {vm['ret_dd']:.2f} | "
            f"{vm['margin']:.1f} | {vm['dsr']:.3f} | {n_trials} | "
            f"{_g(gr, 'sharpe_min')} | {_g(gr, 'max_drawdown_max')} | "
            f"{_g(gr, 'return_to_dd_min')} | {_g(gr, 'margin_min_bps')} | {_g(gr, 'oos_ratio_min')} |"
        )

    L.append("")
    L.append(f"Total unique trials: {n_trials}")
    L.append(f"Executed trials: {executed_trials}")
    L.append("")
    return "\n".join(L)