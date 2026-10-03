"""Market-neutral residual mean-reversion backtester.

Responsibilities (EXECUTION_PLAN.md):

* consume dated target positions (the residual signal engine's output);
* enforce a **one-bar execution lag** structurally — a signal at day ``t``'s
  close fills at day ``t+1``'s close and cannot produce a same-bar fill;
* prevent trades outside the point-in-time ``gold_tradable_universe``;
* neutralise the book (dollar-, beta- and industry-neutral) via
  ``strategies/neutralize.py``;
* apply transaction costs and short-borrow via ``strategies/cost_model.py`` and
  report gross, net and net-at-2x-costs.

Pure ``pandas``/``numpy`` so the lag and universe invariants are unit-testable
without Spark.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from strategies.cost_model import (
    CostParams,
    borrow_bps_daily,
    cost_per_trade,
    scale_order_to_adv_cap,
)
from strategies.neutralize import neutralize_book


# ── Execution lag ─────────────────────────────────────────────────────────────

def enforce_execution_lag(desired: pd.DataFrame, bars: int = 1) -> pd.DataFrame:
    """Shift desired positions *bars* so ``fills[t] = desired[t-bars]``.

    A signal produced at day ``t``'s close can only be filled at day ``t+1``
    (default ``bars=1``).  The first *bars* fills are 0 (no signal precedes
    them). This is the structural guarantee: the backtester has no code path
    that fills on the signal bar.
    """
    return desired.shift(bars).fillna(0.0)


def filter_to_universe(
    weights: pd.DataFrame,
    universe: pd.DataFrame,
) -> pd.DataFrame:
    """Zero out any position whose ``(trade_date, symbol)`` is not in the PIT
    universe. ``universe`` is the long frame ``[trade_date, symbol]`` produced by
    ``gold_tradable_universe``. Filtering is applied to the *executed* weights,
    so a signal outside the universe is structurally prevented, not dropped
    after the fact."""
    members = set(zip(universe["trade_date"], universe["symbol"]))
    mask = pd.DataFrame(
        [[(d, s) in members for s in weights.columns] for d in weights.index],
        index=weights.index,
        columns=weights.columns,
    )
    return weights.where(mask, 0.0)


def cap_weight_changes_by_adv(
    weights: pd.DataFrame,
    adv: pd.DataFrame,
    book_capital: float,
    params: Optional[CostParams] = None,
) -> pd.DataFrame:
    """Cap each daily weight *change* at ``adv_participation_cap`` of ADV.

    The capped change is accumulated into the running position, so oversized
    orders are spread across multiple days.

    *Reductions toward zero are never capped* — a position that needs to exit
    (e.g. after a name leaves the universe) must be allowed to liquidate even
    when ADV is zero or unknown.  Increases are still capped: zero-ADV names
    cannot accumulate new positions.  ADV is forward-filled per symbol so that
    the last known ADV is used for names whose ADV becomes NaN (e.g. after
    leaving the universe).

    Must be called *after* ``filter_to_universe`` and *before* cost computation.
    """
    if params is None:
        params = CostParams()
    cap_frac = params.adv_participation_cap  # e.g. 0.01
    out = weights.copy().to_numpy(dtype=float)
    prev = np.zeros(out.shape[1])
    # Forward-fill ADV per symbol so the last known ADV is used for names
    # whose ADV becomes NaN (e.g. after leaving the universe).
    adv_ff = adv.reindex(index=weights.index, columns=weights.columns).ffill()
    adv_np = adv_ff.fillna(0.0).to_numpy(dtype=float)
    for i in range(out.shape[0]):
        cur = out[i]
        dw = cur - prev
        # Decompose each name's change into a close leg (toward 0, always
        # free) and an open leg (away from 0, capped).  Defined by direction
        # relative to zero per name:
        #   close_leg: part that moves prev toward 0, ending at 0 at most.
        #   open_leg:  part that moves away from 0.  ADV-capped.
        # Same-side reduction (|cur|<|prev|): close_leg = dw, no open leg.
        # Same-side increase (|cur|>|prev|): no close, open_leg = dw.
        # Sign flip or exit: close_leg = -prev (free), open_leg = cur (capped).
        close_leg = np.where(
            prev == 0.0,
            0.0,
            np.where(
                (np.sign(prev) * np.sign(cur)) > 0,
                np.where(np.abs(cur) < np.abs(prev), dw, 0.0),
                -prev,
            ),
        )
        open_leg = dw - close_leg

        # Cap only the open leg at cap_frac * ADV / book_capital.
        open_notional = np.abs(open_leg) * book_capital
        caps = cap_frac * adv_np[i]
        over_cap = open_notional > caps
        if over_cap.any():
            open_leg_capped = np.where(
                caps > 0,
                np.sign(open_leg) * caps / book_capital,
                0.0,
            )
            open_leg = np.where(over_cap, open_leg_capped, open_leg)

        out[i] = prev + close_leg + open_leg
        prev = out[i]
    return pd.DataFrame(out, index=weights.index, columns=weights.columns)


# ── Neutralisation ────────────────────────────────────────────────────────────

def neutralize_daily(
    weights: pd.DataFrame,
    beta: Optional[pd.DataFrame] = None,
    industry: Optional[pd.Series] = None,
    target_gross: float = 1.0,
) -> pd.DataFrame:
    """Per-day dollar/beta/industry neutralisation over *active* names only.

    Inactive names (weight == 0) are left at 0 — neutralising over the full
    cross-section would leak a nonzero weight onto names with no signal.
    """
    out = weights.copy()
    for date in weights.index:
        w = weights.loc[date]
        active = w[w != 0.0]
        if active.empty:
            continue
        b = beta.loc[date].reindex(active.index) if beta is not None else None
        ind = industry.reindex(active.index) if industry is not None else None
        out.loc[date, active.index] = neutralize_book(
            active, beta=b, industry=ind, target_gross=target_gross,
        )
    return out


# ── Costs ─────────────────────────────────────────────────────────────────────

def _scale_params(params: CostParams, mult: float) -> CostParams:
    """Return a copy of ``params`` with every bps component scaled by ``mult``."""
    return CostParams(
        commission_bps=params.commission_bps * mult,
        spread_bps=params.spread_bps * mult,
        slippage_bps=params.slippage_bps * mult,
        adv_participation_cap=params.adv_participation_cap,
        borrow_bps_daily={k: v * mult for k, v in params.borrow_bps_daily.items()},
        borrow_bucket_thresholds=params.borrow_bucket_thresholds,
    )


def compute_costs(
    weights: pd.DataFrame,
    adv: pd.DataFrame,
    book_capital: float,
    params: Optional[CostParams] = None,
    cost_multiplier: float = 1.0,
) -> Dict[str, pd.Series]:
    """Daily cost drag (fraction of capital) from turnover and short borrow.

    Turnover is one-way (``0.5 * sum |dw|``). Each traded notional pays
    ``cost_per_trade`` bps; the order is first capped at 1 % of the name's ADV
    (``scale_order_to_adv_cap``) so a position sized beyond capacity is reduced.
    Shorts additionally pay the daily borrow haircut by liquidity bucket.

    Returns ``{"turnover_cost": Series, "borrow_cost": Series, "total": Series}``
    in units of fraction of ``book_capital``.
    """
    if params is None:
        params = CostParams()
    params = _scale_params(params, cost_multiplier)

    dw = weights.diff()
    dw.iloc[0] = weights.iloc[0]  # entering the initial book is a trade
    traded = dw.abs()

    turnover_cost = pd.Series(0.0, index=weights.index)
    borrow_cost = pd.Series(0.0, index=weights.index)

    for date in weights.index:
        w = weights.loc[date]
        tr = traded.loc[date]
        adv_t = adv.loc[date] if date in adv.index else pd.Series(
            0.0, index=weights.columns)

        cost_dollars = 0.0
        for s in w.index:
            notional = abs(tr[s]) * book_capital
            if notional <= 0:
                continue
            a = float(adv_t[s]) if pd.notna(adv_t[s]) else 0.0
            capped_notional, _ = scale_order_to_adv_cap(notional, a, params)
            if capped_notional <= 0:
                continue
            bps = cost_per_trade(capped_notional, a, params)
            cost_dollars += capped_notional * bps / 1e4
        turnover_cost.loc[date] = cost_dollars / book_capital

        borrow_dollars = 0.0
        for s in w.index:
            if w[s] >= 0:
                continue
            a = float(adv_t[s]) if pd.notna(adv_t[s]) else 0.0
            borrow_dollars += abs(w[s]) * book_capital * borrow_bps_daily(a, params) / 1e4
        borrow_cost.loc[date] = borrow_dollars / book_capital

    total = turnover_cost + borrow_cost
    return {"turnover_cost": turnover_cost, "borrow_cost": borrow_cost,
            "total": total}


# ── Metrics ───────────────────────────────────────────────────────────────────

def _max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def _sharpe(returns: pd.Series, periods: int = 252) -> float:
    r = returns.dropna()
    if len(r) < 2 or r.std(ddof=0) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=0) * np.sqrt(periods))


def _avg_hold(positions: pd.DataFrame) -> float:
    """Average consecutive run length of a non-zero position per symbol."""
    runs = []
    for s in positions.columns:
        pos = positions[s].to_numpy()
        run = 0
        for v in pos:
            if v != 0:
                run += 1
            else:
                if run > 0:
                    runs.append(run)
                run = 0
        if run > 0:
            runs.append(run)
    return float(np.mean(runs)) if runs else float("nan")


def portfolio_metrics(
    gross: pd.Series,
    net: pd.Series,
    net_2x: pd.Series,
    turnover: pd.Series,
    positions: Optional[pd.DataFrame] = None,
    n_trials: int = 1,
    capacity_cap_frac: float = float("nan"),
) -> Dict[str, float]:
    """Annualised return, Sharpe, drawdown, hit rate, turnover, avg hold,
    capacity and deflated Sharpe (Bailey/Lopez de Prado, using ``n_trials``)."""
    from ml.evaluate import deflated_sharpe_ratio

    out: Dict[str, float] = {}
    for tag, s in (("gross", gross), ("net", net), ("net_2x", net_2x)):
        out[f"{tag}_ann_return"] = float(s.mean() * 252)
        out[f"{tag}_sharpe"] = _sharpe(s)
        out[f"{tag}_max_drawdown"] = _max_drawdown(s)
    out["hit_rate"] = float((net > 0).mean())
    out["turnover_avg_daily"] = float(turnover.mean())
    out["avg_hold_days"] = _avg_hold(positions) if positions is not None else float("nan")
    out["capacity_adv_cap_frac"] = capacity_cap_frac
    out["deflated_sharpe_ratio"] = deflated_sharpe_ratio(
        net.to_numpy(), n_trials=n_trials, periods_per_year=252,
    )
    return out


# ── Full run ──────────────────────────────────────────────────────────────────

def run_backtest(
    desired_positions: pd.DataFrame,
    returns: pd.DataFrame,
    universe: pd.DataFrame,
    adv: pd.DataFrame,
    beta: Optional[pd.DataFrame] = None,
    industry: Optional[pd.Series] = None,
    book_capital: float = 10_000_000.0,
    target_gross: float = 1.0,
    cost_params: Optional[CostParams] = None,
    n_trials: int = 1,
    execution_lag_bars: int = 1,
) -> Dict:
    """Run the residual mean-reversion backtest over the given date range.

    Args:
        desired_positions: wide [date x symbol] desired +1/-1/0 per signal bar.
        returns: wide [date x symbol] close-to-close returns (same index/columns).
        universe: long ``[trade_date, symbol]`` from ``gold_tradable_universe``.
        adv: wide [date x symbol] trailing dollar volume (for cost/capacity).
        beta: optional wide [date x symbol] market beta (for neutralisation).
        industry: optional Series symbol -> industry (for neutralisation).
        book_capital: notional capital of the book (default $10M).
        target_gross: total gross leverage ``sum |w|`` (default 1.0).
        cost_params: transaction cost parameters.
        n_trials: number of configurations tried (deflated-Sharpe penalty).

    Returns a dict with ``fills``, ``weights``, ``gross``/``net``/``net_2x``
    daily series, the ``costs`` breakdown, ``turnover``, and ``metrics``.
    """
    fills = enforce_execution_lag(desired_positions, bars=execution_lag_bars)
    fills = filter_to_universe(fills, universe)
    weights = neutralize_daily(fills, beta=beta, industry=industry,
                               target_gross=target_gross)

    # Cap weight changes at ADV participation limit *after* neutralisation.
    # The capped positions are what the portfolio actually holds; P&L and
    # borrow are computed on these, not the uncapped neutralised weights.
    # Zero-ADV names can never accumulate a position.
    adv_aligned = adv.reindex(index=weights.index, columns=weights.columns).fillna(0.0)
    weights = cap_weight_changes_by_adv(weights, adv_aligned, book_capital, params=cost_params)

    # Book return on day t is earned by the weights established at t-1.
    gross = (weights.shift(1).fillna(0.0) * returns).sum(axis=1)

    adv_aligned = adv.reindex(index=returns.index, columns=returns.columns)
    adv_aligned = adv_aligned.fillna(0.0)

    costs = compute_costs(weights, adv_aligned, book_capital, cost_params,
                          cost_multiplier=1.0)
    costs_2x = compute_costs(weights, adv_aligned, book_capital, cost_params,
                             cost_multiplier=2.0)
    net = gross - costs["total"]
    net_2x = gross - costs_2x["total"]

    one_way = (weights.diff().abs().sum(axis=1) / 2.0)
    one_way.iloc[0] = (weights.iloc[0].abs().sum() / 2.0)
    turnover = one_way / max(target_gross, 1e-9)

    metrics = portfolio_metrics(
        gross, net, net_2x, turnover, positions=weights,
        n_trials=n_trials,
    )

    return {
        "fills": fills,
        "weights": weights,
        "gross": gross,
        "net": net,
        "net_2x": net_2x,
        "costs": costs,
        "turnover": turnover,
        "metrics": metrics,
    }
