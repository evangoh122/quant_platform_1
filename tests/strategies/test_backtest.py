"""Backtester invariants: the one-bar execution lag is structural, trades
outside the point-in-time universe are prevented, and the neutralised book is
dollar/beta/industry neutral."""

import numpy as np
import pandas as pd
import pytest

from strategies.backtest import (
    _max_drawdown,
    cap_weight_changes_by_adv,
    compute_costs,
    enforce_execution_lag,
    filter_to_universe,
    neutralize_daily,
    one_way_turnover,
    run_backtest,
)
from strategies.cost_model import CostParams


@pytest.fixture
def dates():
    return pd.date_range("2024-01-01", periods=20, freq="B")


@pytest.fixture
def symbols():
    return ["A", "B", "C", "D"]


def test_signal_on_day_t_cannot_fill_on_day_t(dates, symbols):
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[3], "A"] = 1.0  # a single signal at day 3's close

    fills = enforce_execution_lag(desired)

    # No same-bar fill: day 3 must still be flat.
    assert fills.loc[dates[3], "A"] == 0.0
    # The fill lands on day 4.
    assert fills.loc[dates[4], "A"] == 1.0
    # And it never leaks backwards.
    assert (fills.loc[:dates[3], "A"] == 0.0).all()


def test_full_backtest_signal_earns_no_return_on_signal_day(dates, symbols):
    returns = pd.DataFrame(0.0, index=dates, columns=symbols)
    returns.loc[dates[5], "A"] = 0.10  # big return on day 5

    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[4], "A"] = 1.0  # signal at day 4 close -> fill day 5

    universe = pd.DataFrame({"trade_date": dates, "symbol": ["A"] * len(dates)})
    universe = pd.concat([universe] * len(symbols), ignore_index=True)
    universe = universe.drop_duplicates()
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)

    res = run_backtest(desired, returns, universe, adv, target_gross=1.0)

    # The position from day 4's signal is filled on day 5, so it earns day 6's
    # return, not day 5's. Gross PnL on day 5 must be 0.
    assert res["gross"].loc[dates[5]] == pytest.approx(0.0)


def test_trade_outside_universe_is_zeroed(dates, symbols):
    fills = pd.DataFrame(1.0, index=dates, columns=symbols)
    # Universe only ever contains A; B/C/D are never tradable.
    universe = pd.DataFrame({"trade_date": dates, "symbol": ["A"] * len(dates)})

    filtered = filter_to_universe(fills, universe)

    assert (filtered["A"] == 1.0).all()
    assert (filtered[["B", "C", "D"]] == 0.0).all().all()


def test_neutralized_book_is_dollar_beta_industry_neutral(dates, symbols):
    # Asymmetric weights so the book has an idiosyncratic component that survives
    # neutralisation (a pure [1,-1,1,-1] book is exactly a systematic bet and
    # neutralising it correctly yields zero).
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    for d in dates:
        weights.loc[d] = {"A": 0.5, "B": -1.0, "C": 0.3, "D": -0.8}

    beta = pd.DataFrame(1.0, index=dates, columns=symbols)
    beta[["A", "C"]] = 1.2
    beta[["B", "D"]] = 0.8
    industry = pd.Series({"A": "tech", "B": "tech", "C": "fin", "D": "fin"})

    out = neutralize_daily(weights, beta=beta, industry=industry, target_gross=1.0)

    for d in dates:
        w = out.loc[d]
        assert abs(w.sum()) < 1e-9                      # dollar neutral
        assert abs((w * beta.loc[d]).sum()) < 1e-9      # beta neutral
        assert abs(w["A"] + w["B"]) < 1e-9              # industry neutral (tech)
        assert abs(w["C"] + w["D"]) < 1e-9              # industry neutral (fin)


def test_compute_costs_charges_borrow_on_shorts(dates, symbols):
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    weights["A"] = 0.6   # long
    weights["B"] = -0.6  # short (pays borrow)
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)  # liquid bucket
    params = CostParams()
    costs = compute_costs(weights, adv, book_capital=10_000_000.0, params=params)
    # Borrow is charged for the short leg only.
    assert (costs["borrow_cost"] > 0).all()


def test_run_backtest_reports_gross_net_and_net_2x(dates, symbols):
    returns = pd.DataFrame(np.random.default_rng(0).normal(0.001, 0.01, (20, 4)),
                           index=dates, columns=symbols)
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[2], "A"] = 1.0
    desired.loc[dates[2], "C"] = -1.0

    universe = pd.DataFrame(
        [(d, s) for d in dates for s in symbols],
        columns=["trade_date", "symbol"],
    )
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)

    res = run_backtest(desired, returns, universe, adv, target_gross=1.0)
    m = res["metrics"]
    for k in ("gross_ann_return", "net_ann_return", "net_2x_ann_return",
              "gross_sharpe", "net_sharpe", "net_2x_sharpe", "turnover_avg_daily"):
        assert k in m


def test_adv_cap_constrains_execution(dates, symbols):
    """An order over the ADV cap yields a capped position, and P&L is on the
    capped size.  Zero-ADV names cannot be traded."""
    returns = pd.DataFrame(0.01, index=dates, columns=symbols)
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[1], "A"] = 1.0  # want full long
    desired.loc[dates[1], "B"] = -1.0  # want full short
    # C and D stay at 0 (no signal).

    universe = pd.DataFrame(
        [(d, s) for d in dates for s in symbols],
        columns=["trade_date", "symbol"],
    )
    # All symbols have tiny ADV: 1% cap = $100 on a $10M book → max weight = 0.00001.
    # D has zero ADV.
    adv = pd.DataFrame(10_000.0, index=dates, columns=symbols)
    adv["D"] = 0.0  # zero ADV

    from strategies.cost_model import CostParams
    params = CostParams(adv_participation_cap=0.01)

    res = run_backtest(desired, returns, universe, adv, target_gross=1.0,
                       cost_params=params)
    weights = res["weights"]

    # A's position should be capped well below 1.0 (tiny ADV).
    max_a = weights["A"].abs().max()
    assert max_a < 0.01, f"A's max weight {max_a} should be far below 1.0 (tiny ADV)"

    # D has zero ADV → must never trade.
    assert (weights["D"] == 0.0).all(), "zero-ADV name D must never have a position"

    # P&L should be computed on the capped positions (not on the desired 1.0).
    # With tiny ADV on all names, the resulting book is minuscule.
    assert res["gross"].abs().max() < 0.001


def test_position_liquidates_when_adv_becomes_nan(dates, symbols):
    """A held position must liquidate when the name leaves the universe, even
    when ADV becomes NaN.  The cap must never block a reduction toward 0.

    CodeRabbit finding #2: ADV is pivoted only for universe members then
    fillna(0).  When a held name leaves the universe, its target becomes 0 but
    cap = 0.01 * 0 = 0, so the exit is capped to zero change and the position
    is held forever.
    """
    returns = pd.DataFrame(0.001, index=dates, columns=symbols)
    # Signal: hold long A from day 1 through the end (never exits on its own).
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[1]:, "A"] = 1.0

    # A is in the universe for days 0-9, then drops out.
    universe = pd.DataFrame(
        [(d, "A") for d in dates[:10]],
        columns=["trade_date", "symbol"],
    )

    # ADV is 1e8 for A in-universe, NaN after it drops out.
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)
    adv.loc[dates[10]:, "A"] = np.nan

    res = run_backtest(desired, returns, universe, adv, target_gross=1.0)
    weights = res["weights"]

    # After A drops out of universe on day 10, its weight should go to 0
    # within a bounded number of days (not frozen forever).
    last_day = dates[-1]
    assert weights.loc[last_day, "A"] == 0.0, (
        f"A's weight is {weights.loc[last_day, 'A']} on last day — should be 0 "
        f"(position frozen due to NaN ADV)"
    )


# ── Sign-flip ADV cap tests ──────────────────────────────────────────────────

def _make_cap_inputs(n_days, symbols, target_series, adv_val, book_capital, cap_frac):
    """Helper: build weight/adv frames for cap_weight_changes_by_adv tests."""
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    for i, w in enumerate(target_series):
        weights.iloc[i, 0] = w  # only first symbol gets the target
    adv = pd.DataFrame(adv_val, index=dates, columns=symbols)
    params = CostParams(adv_participation_cap=cap_frac)
    return dates, weights, adv, params


def test_sign_flip_equal_magnitude_capped():
    """+0.4 → -0.4 with cap 0.02/day: the new short leg must be capped.

    Day 0: target +0.4, prev=0 → open +0.4, capped to +0.02.
    Day 1: target -0.4, prev=+0.02 → close +0.02 (free), open -0.4 (capped to -0.02).
    So day 1 weight = +0.02 + (-0.02) + (-0.02) = -0.02.
    Day 2: target -0.4, prev=-0.02 → same-side increase, open -0.38, capped to -0.02.
    So day 2 weight = -0.02 + 0 + (-0.02) = -0.04. Converges toward -0.4.
    """
    n_days = 10
    symbols = ["A", "B"]
    target = [0.4] + [-0.4] * (n_days - 1)
    book_capital = 1e6
    cap_frac = 0.01
    adv_val = 0.02 * book_capital / cap_frac  # cap weight = 0.02

    dates, weights, adv, params = _make_cap_inputs(
        n_days, symbols, target, adv_val, book_capital, cap_frac,
    )
    result = cap_weight_changes_by_adv(weights, adv, book_capital, params)
    a = result["A"].to_numpy()

    # Day 0: prev=0, target=+0.4 → open +0.4, capped to +0.02
    assert a[0] == pytest.approx(0.02), f"day 0: expected +0.02, got {a[0]}"

    # Day 1: prev=+0.02, target=-0.4 (sign flip)
    # close = -0.02 (free, toward 0); open = -0.4 (capped to -0.02)
    # new = +0.02 + (-0.02) + (-0.02) = -0.02
    assert a[1] == pytest.approx(-0.02), f"day 1: expected -0.02, got {a[1]}"

    # Day 2: prev=-0.02, target=-0.4 (same-side increase)
    # close = 0; open = -0.38, capped to -0.02
    # new = -0.02 + 0 + (-0.02) = -0.04
    assert a[2] == pytest.approx(-0.04), f"day 2: expected -0.04, got {a[2]}"

    # Convergence: each day adds another -0.02.
    assert a[3] == pytest.approx(-0.06)
    assert a[4] == pytest.approx(-0.08)


def test_sign_flip_close_out_not_capped():
    """+0.06 → -0.4 with cap 0.02/day: the long is fully closed on the flip day.

    Day 0: target +0.06, prev=0 → open +0.06, capped to +0.02.
    Day 1: target +0.06, prev=+0.02 → open +0.04, capped to +0.02. Weight=+0.04.
    Day 2: target +0.06, prev=+0.04 → open +0.02, capped to +0.02. Weight=+0.06.
    Day 3: target -0.4, prev=+0.06 → close -0.06 (free), open -0.4 (capped to -0.02).
    Weight = +0.06 + (-0.06) + (-0.02) = -0.02.
    The long IS fully closed on the flip day (close leg = -0.06 is not capped).
    """
    n_days = 6
    symbols = ["A", "B"]
    target = [0.06, 0.06, 0.06, -0.4, -0.4, -0.4]
    book_capital = 1e6
    cap_frac = 0.01
    adv_val = 0.02 * book_capital / cap_frac  # cap weight = 0.02

    dates, weights, adv, params = _make_cap_inputs(
        n_days, symbols, target, adv_val, book_capital, cap_frac,
    )
    result = cap_weight_changes_by_adv(weights, adv, book_capital, params)
    a = result["A"].to_numpy()

    # Day 0: prev=0, target=+0.06 → open +0.06, capped to +0.02
    assert a[0] == pytest.approx(0.02), f"day 0: expected +0.02, got {a[0]}"
    # Day 1: prev=+0.02, target=+0.06 → same-side increase, open +0.04, capped to +0.02 → +0.04
    assert a[1] == pytest.approx(0.04), f"day 1: expected +0.04, got {a[1]}"
    # Day 2: prev=+0.04, target=+0.06 → same-side increase, open +0.02, capped to +0.02 → +0.06
    assert a[2] == pytest.approx(0.06), f"day 2: expected +0.06, got {a[2]}"
    # Day 3: prev=+0.06, target=-0.4 → close -0.06 (free), open -0.4 (capped to -0.02)
    # new = +0.06 + (-0.06) + (-0.02) = -0.02
    assert a[3] == pytest.approx(-0.02), f"day 3: expected -0.02, got {a[3]}"


def test_existing_dropped_name_exits():
    """Dropped name (target=0) still exits uncapped — the close leg is free."""
    n_days = 5
    symbols = ["A", "B"]
    target = [0.3, 0.3, 0.0, 0.0, 0.0]  # A drops out at day 2
    book_capital = 1e6
    cap_frac = 0.01
    adv_val = 0.02 * book_capital / cap_frac

    dates, weights, adv, params = _make_cap_inputs(
        n_days, symbols, target, adv_val, book_capital, cap_frac,
    )
    result = cap_weight_changes_by_adv(weights, adv, book_capital, params)
    a = result["A"].to_numpy()

    # Day 2: prev=+0.06, target=0 → close=-0.06 (free), open=0 → weight=0
    assert a[2] == pytest.approx(0.0), f"day 2: expected 0.0, got {a[2]}"
    assert a[3] == pytest.approx(0.0), f"day 3: expected 0.0, got {a[3]}"


def test_existing_same_side_increase_capped():
    """Same-side increase: open leg only, capped at +0.02/day."""
    n_days = 4
    symbols = ["A", "B"]
    target = [0.1, 0.3, 0.5, 0.5]
    book_capital = 1e6
    cap_frac = 0.01
    adv_val = 0.02 * book_capital / cap_frac  # cap weight = 0.02

    dates, weights, adv, params = _make_cap_inputs(
        n_days, symbols, target, adv_val, book_capital, cap_frac,
    )
    result = cap_weight_changes_by_adv(weights, adv, book_capital, params)
    a = result["A"].to_numpy()

    # Day 0: prev=0, target=+0.1 → open +0.1, capped to +0.02
    assert a[0] == pytest.approx(0.02)
    # Day 1: prev=+0.02, target=+0.3 → same-side increase, open +0.28, capped to +0.02 → +0.04
    assert a[1] == pytest.approx(0.04)
    # Day 2: prev=+0.04, target=+0.5 → same-side increase, open +0.46, capped to +0.02 → +0.06
    assert a[2] == pytest.approx(0.06)
    # Day 3: prev=+0.06, target=+0.5 → same-side increase, open +0.44, capped to +0.02 → +0.08
    assert a[3] == pytest.approx(0.08)


# ── Same-side partial reduction test ─────────────────────────────────────────

def test_same_side_partial_reduction_not_capped():
    """Same-side reduction from +0.4 to +0.2 must land in one day (free close leg).

    With cap 0.02/day (well below 0.2), the reduction is a close leg (toward 0)
    and is never ADV-capped.  This is the regression DeepSeek check4 found:
    round-6 code treated the reduction as an open leg, throttling it at 0.02/day.
    """
    n_days = 28
    symbols = ["A", "B"]
    target = [0.4] * 20 + [0.2] * 8
    book_capital = 1e6
    cap_frac = 0.01
    adv_val = 0.02 * book_capital / cap_frac  # cap weight = 0.02

    dates, weights, adv, params = _make_cap_inputs(
        n_days, symbols, target, adv_val, book_capital, cap_frac,
    )
    result = cap_weight_changes_by_adv(weights, adv, book_capital, params)
    a = result["A"].to_numpy()

    # Days 0-18: building up from 0 to +0.4 at +0.02/day
    # Day 19: target still 0.4, prev=0.38 → +0.04 (same-side increase capped to 0.02) → 0.40
    assert a[19] == pytest.approx(0.4), f"day 19: expected 0.4, got {a[19]}"

    # Day 20: target drops to 0.2, prev=0.4 → close leg = -0.2 (free), lands at 0.2
    assert a[20] == pytest.approx(0.2), (
        f"day 20 (first reduction): expected 0.2, got {a[20]}"
    )

    # Days 21-27: target stays 0.2, no change needed
    for d in range(21, 28):
        assert a[d] == pytest.approx(0.2), f"day {d}: expected 0.2, got {a[d]}"


# ── Property test: ADV cap invariants ────────────────────────────────────────

def test_adv_cap_property_invariants():
    """Property test over 500 random target sequences (seeded).

    For every name and day, with ``out`` the realised weight:
    (a) Never overshoot: out[t] lies between out[t-1] and target[t], inclusive.
    (b) Free moves toward zero: if target[t] is between 0 and out[t-1], inclusive,
        then out[t] == target[t].
    (c) Flips close fully: if the sign flips, out[t] has the new sign or is 0,
        and |out[t]| <= cap.
    (d) Increases are capped: |out[t]| - |out[t-1]| <= cap + 1e-12 whenever
        sign(out[t]) == sign(out[t-1]), or out[t-1] == 0.
    """
    rng = np.random.default_rng(42)
    n_names = 3
    n_days = 30
    n_trials = 500
    book_capital = 1e6
    cap_frac = 0.01
    adv_val = 0.02 * book_capital / cap_frac  # cap weight = 0.02
    cap = cap_frac * adv_val / book_capital  # 0.02
    symbols = [f"S{i}" for i in range(n_names)]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    adv = pd.DataFrame(adv_val, index=dates, columns=symbols)
    params = CostParams(adv_participation_cap=cap_frac)

    violations = []

    for trial in range(n_trials):
        # Generate random target: mix of signs, magnitudes, zeros
        targets = rng.uniform(-1.0, 1.0, size=(n_days, n_names))
        # Sprinkle some zeros (20%)
        zero_mask = rng.random((n_days, n_names)) < 0.2
        targets[zero_mask] = 0.0

        # Randomly inject NaN ADV then forward-fill (simulate gaps)
        adv_with_nan = np.full((n_days, n_names), adv_val)
        nan_mask = rng.random((n_days, n_names)) < 0.05
        adv_with_nan[nan_mask] = np.nan
        adv_df = pd.DataFrame(adv_with_nan, index=dates, columns=symbols).ffill().fillna(0.0)

        weights_df = pd.DataFrame(targets, index=dates, columns=symbols)
        result = cap_weight_changes_by_adv(weights_df, adv_df, book_capital, params)

        for name_idx in range(n_names):
            col = symbols[name_idx]
            out = result[col].to_numpy()
            tgt = targets[:, name_idx]

            for t in range(n_days):
                prev_w = out[t - 1] if t > 0 else 0.0
                cur_w = out[t]
                cur_tgt = tgt[t]

                # (a) Never overshoot: out[t] between out[t-1] and target[t]
                lo = min(prev_w, cur_tgt)
                hi = max(prev_w, cur_tgt)
                if not (lo - 1e-12 <= cur_w <= hi + 1e-12):
                    violations.append(
                        f"trial={trial} {col} day={t}: overshoot "
                        f"prev={prev_w:.6f} tgt={cur_tgt:.6f} out={cur_w:.6f}"
                    )

                # (b) Free moves toward zero: target between 0 and prev → out == target
                if (min(0.0, prev_w) - 1e-12 <= cur_tgt <= max(0.0, prev_w) + 1e-12):
                    if abs(cur_w - cur_tgt) > 1e-9:
                        violations.append(
                            f"trial={trial} {col} day={t}: reduction not free "
                            f"prev={prev_w:.6f} tgt={cur_tgt:.6f} out={cur_w:.6f}"
                        )

                # (c) Flips close fully: sign flip → out has new sign or 0, |out| <= cap
                if t > 0 and prev_w != 0.0 and cur_tgt != 0.0:
                    if np.sign(prev_w) != np.sign(cur_tgt):
                        # Sign flip: out should have new sign or be 0
                        if cur_w != 0.0 and np.sign(cur_w) != np.sign(cur_tgt):
                            violations.append(
                                f"trial={trial} {col} day={t}: flip not closed "
                                f"prev={prev_w:.6f} tgt={cur_tgt:.6f} out={cur_w:.6f}"
                            )
                        if abs(cur_w) > cap + 1e-12:
                            violations.append(
                                f"trial={trial} {col} day={t}: flip exceeds cap "
                                f"|out|={abs(cur_w):.6f} cap={cap:.6f}"
                            )

                # (d) Increases are capped: same-side increase
                if t > 0 and prev_w != 0.0 and cur_w != 0.0:
                    if np.sign(cur_w) == np.sign(prev_w):
                        increase = abs(cur_w) - abs(prev_w)
                        if increase > cap + 1e-12:
                            violations.append(
                                f"trial={trial} {col} day={t}: increase exceeds cap "
                                f"increase={increase:.6f} cap={cap:.6f}"
                            )
                # From zero: increase is capped
                if t > 0 and prev_w == 0.0 and cur_w != 0.0:
                    if abs(cur_w) > cap + 1e-12:
                        violations.append(
                            f"trial={trial} {col} day={t}: from-zero exceeds cap "
                            f"|out|={abs(cur_w):.6f} cap={cap:.6f}"
                        )

    assert not violations, "Property test violations:\n" + "\n".join(violations[:20])


# ── Cost-on-executed-notional tests (round 8) ────────────────────────────────

def test_exit_costs_charged_on_full_executed_notional():
    """A large exit (executed notional = 5% of ADV) must be charged on the
    full executed notional, not the 1%-of-ADV cap.

    Before the fix, compute_costs re-capped through scale_order_to_adv_cap,
    charging costs on at most 1% of ADV even for a $5M exit on a $10M ADV name.
    """
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    symbols = ["A", "B"]

    # A goes from 0.5 to 0 (exit). Executed notional = 0.5 * $10M = $5M.
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    weights.loc[dates[0], "A"] = 0.5
    weights.loc[dates[1], "A"] = 0.0

    book_capital = 10_000_000.0
    # ADV = $10M → 1% cap = $100k. Executed $5M = 50x the cap.
    adv = pd.DataFrame(10_000_000.0, index=dates, columns=symbols)
    params = CostParams()

    costs = compute_costs(weights, adv, book_capital, params)

    # Cost on day 1 (the exit bar) with the fix:
    #   notional = $5M, participation = 5M/10M = 0.5
    #   bps = 0.5 + 0.5*3 + 2*(0.5/0.01) = 102
    #   cost_dollars = 5M * 102 / 1e4 = $51,000
    #   cost_frac = 51,000 / 10M = 0.0051
    exit_cost = costs["turnover_cost"].loc[dates[1]]
    expected = 5_000_000.0 * (0.5 + 0.5 * 3.0 + 2.0 * (0.5 / 0.01)) / 1e4 / book_capital

    assert exit_cost == pytest.approx(expected), (
        f"Exit cost should be charged on $5M notional (expected {expected:.6f}), "
        f"got {exit_cost:.6f}"
    )


def test_costs_never_below_minimum_bps_times_executed_notional():
    """Costs are never below (commission + 0.5*spread) bps * executed notional.

    The slippage term is participation-dependent and >= 0, so the floor is
    the fixed component only.
    """
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    symbols = ["A", "B"]

    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    weights.loc[dates[1], "A"] = 0.5  # entry

    book_capital = 10_000_000.0
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)
    params = CostParams()

    costs = compute_costs(weights, adv, book_capital, params)
    entry_cost = costs["turnover_cost"].loc[dates[1]]

    executed_notional = 0.5 * book_capital
    min_cost_frac = executed_notional * (params.commission_bps + 0.5 * params.spread_bps) / 1e4 / book_capital

    assert entry_cost >= min_cost_frac - 1e-15, (
        f"Entry cost {entry_cost:.8f} < minimum {min_cost_frac:.8f}"
    )


def test_cap_weight_changes_with_read_only_input():
    """cap_weight_changes_by_adv must work when input arrays are read-only.

    Reproduces pandas 3 copy-on-write behaviour on pandas 2: .to_numpy() can
    return a read-only view, and writing into the output array raises
    ValueError.  The fix (to_numpy(copy=True)) guarantees a writeable copy.
    """
    n_days = 5
    symbols = ["A", "B"]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")

    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    weights.iloc[0, 0] = 0.1
    weights.iloc[1, 0] = 0.2

    adv = pd.DataFrame(1e8, index=dates, columns=symbols)
    book_capital = 1e6
    params = CostParams(adv_participation_cap=0.01)

    # Make the underlying numpy arrays read-only (simulates pandas 3 CoW).
    w_arr = weights.to_numpy()
    a_arr = adv.to_numpy()
    w_arr.setflags(write=False)
    a_arr.setflags(write=False)

    # Build new frames from the read-only arrays — .to_numpy() on these
    # frames may return read-only views under pandas 3.
    weights_ro = pd.DataFrame(w_arr, index=dates, columns=symbols)
    adv_ro = pd.DataFrame(a_arr, index=dates, columns=symbols)

    # Must not raise ValueError: assignment destination is read-only
    result = cap_weight_changes_by_adv(weights_ro, adv_ro, book_capital, params)
    assert result.iloc[0, 0] == pytest.approx(0.1)


# ── ADV cost forward-fill tests (round 10) ──────────────────────────────────

def test_exit_cost_uses_last_known_adv_not_100pct_participation():
    """A name held, then dropped from the universe with NaN ADV after the drop.
    The exit-day cost must equal the cost computed with its LAST KNOWN ADV,
    not 100% participation (which would be ~200 bps).

    Before the fix, run_backtest rebuilt adv_aligned with fillna(0.0) before
    compute_costs, so a dropped name's ADV was 0 → participation = 1.0 →
    ~200 bps on exit instead of the correct ~12 bps.
    """
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    symbols = ["A", "B"]

    # Signal: hold long A from day 1 through end.  A drops out of universe on day 10.
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[1]:, "A"] = 1.0

    # A is in universe for days 0-9, then drops out.
    universe = pd.DataFrame(
        [(d, "A") for d in dates[:10]],
        columns=["trade_date", "symbol"],
    )

    returns = pd.DataFrame(0.001, index=dates, columns=symbols)

    # ADV = 1e8 for A in-universe, NaN after it drops out.
    adv = pd.DataFrame(1e8, index=dates, columns=symbols)
    adv.loc[dates[10]:, "A"] = np.nan

    book_capital = 10_000_000.0
    params = CostParams()

    res = run_backtest(desired, returns, universe, adv,
                       book_capital=book_capital, cost_params=params)
    weights = res["weights"]

    # A must have exited by the end (position liquidated).
    assert weights.loc[dates[-1], "A"] == 0.0, (
        f"A's weight is {weights.loc[dates[-1], 'A']} on last day — should be 0"
    )

    # Find the exit day: first day after day 10 where A's weight drops to 0.
    exit_day = None
    for d in dates[10:]:
        if weights.loc[d, "A"] == 0.0 and weights.loc[dates[dates.get_loc(d) - 1], "A"] != 0.0:
            exit_day = d
            break
    assert exit_day is not None, "A should have exited on a specific day"

    # The exit-day cost should use LAST KNOWN ADV (1e8), not 100% participation.
    # With ADV=1e8, book_capital=10M, exit weight ~0.5 (capped accumulation):
    #   notional = |Δweight| * book_capital
    #   participation = notional / 1e8
    #   bps = 0.5 + 0.5*3 + 2*(participation/0.01)
    # This should be << 202 bps (which is what 100% participation gives).
    exit_cost_frac = res["costs"]["turnover_cost"].loc[exit_day]

    # Compute expected cost using last known ADV.
    exit_weight_change = abs(weights.loc[exit_day, "A"] - weights.loc[dates[dates.get_loc(exit_day) - 1], "A"])
    exit_notional = exit_weight_change * book_capital
    last_known_adv = 1e8
    participation = exit_notional / last_known_adv
    expected_bps = (
        params.commission_bps
        + 0.5 * params.spread_bps
        + params.slippage_bps * (participation / params.adv_participation_cap)
    )
    expected_cost_frac = exit_notional * expected_bps / 1e4 / book_capital

    assert exit_cost_frac == pytest.approx(expected_cost_frac, rel=1e-6), (
        f"Exit cost {exit_cost_frac:.8f} should use last known ADV "
        f"(expected {expected_cost_frac:.8f}), not 100% participation"
    )

    # Sanity: the cost should be MUCH less than 100% participation (202 bps).
    cost_100pct = exit_notional * (
        params.commission_bps + 0.5 * params.spread_bps
        + params.slippage_bps * (1.0 / params.adv_participation_cap)
    ) / 1e4 / book_capital
    assert exit_cost_frac < cost_100pct * 0.1, (
        f"Exit cost {exit_cost_frac:.8f} should be < 10% of 100% participation cost "
        f"{cost_100pct:.8f}"
    )


def test_never_held_adv_name_charged_100pct_participation():
    """A name with ADV=0 (never had a value) is charged at 100% participation
    in compute_costs.  Through run_backtest, such a name cannot accumulate a
    position (cap blocks it), so we test compute_costs directly."""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    symbols = ["A", "B"]

    # Simulate a position that somehow exists (e.g., from a prior period).
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    weights.loc[dates[0], "A"] = 0.5  # entry
    weights.loc[dates[1], "A"] = 0.0  # exit

    book_capital = 10_000_000.0

    # A has ADV=0 on all days (never had a value → fillna(0) in run_backtest).
    adv = pd.DataFrame(0.0, index=dates, columns=symbols)
    params = CostParams()

    costs = compute_costs(weights, adv, book_capital, params)

    # Exit day: ADV=0 → participation = 1.0 (100%), bps = 0.5 + 1.5 + 200 = 202.
    exit_cost_frac = costs["turnover_cost"].loc[dates[1]]
    exit_notional = 0.5 * book_capital  # |0.5 - 0.0| * book_capital
    expected_bps = (
        params.commission_bps
        + 0.5 * params.spread_bps
        + params.slippage_bps * (1.0 / params.adv_participation_cap)  # 100% participation
    )
    expected_cost_frac = exit_notional * expected_bps / 1e4 / book_capital

    assert exit_cost_frac == pytest.approx(expected_cost_frac, rel=1e-6), (
        f"Exit cost {exit_cost_frac:.8f} should be 100% participation "
        f"(expected {expected_cost_frac:.8f}) for never-ADV name"
    )


def test_one_way_turnover_long_flat_short():
    """Pin the turnover convention on hand-computed weights.

    one-way turnover = sum_s |w_t - w_{t-1}| / (2 * target_gross): the
    numerator is the two-way traded notional and the /2 keeps one side
    (strategies/backtest.py::one_way_turnover; same convention as
    ml/evaluate.py::build_backtest's |Δposition|/2).
    """
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    weights = pd.DataFrame({"A": [1.0, 0.0, -1.0]}, index=dates)

    turnover = one_way_turnover(weights, target_gross=1.0)

    # Hand computation — unit weights long -> flat -> short:
    #   t0: entering the book trades 1.0 two-way -> |1.0| / 2      = 0.5
    #   t1: 1.0 -> 0.0 trades 1.0 two-way        -> |0 - 1| / 2    = 0.5
    #   t2: 0.0 -> -1.0 trades 1.0 two-way       -> |-1 - 0| / 2   = 0.5
    assert turnover.tolist() == pytest.approx([0.5, 0.5, 0.5], abs=1e-12)

    # Same trades against a 2.0-gross book are half the turnover.
    assert one_way_turnover(weights, target_gross=2.0).tolist() == pytest.approx(
        [0.25, 0.25, 0.25], abs=1e-12
    )


# ── R3: initial-equity drawdown fix for _max_drawdown ───────────────────────


def test_max_drawdown_initial_loss_from_starting_equity():
    """_max_drawdown must include initial equity 1.0 in the running peak.

    Returns [-0.10, 0, 0]: equity 0.9, 0.9, 0.9; peak 1.0;
    dd = 0.9/1.0 - 1 = -0.10; _max_drawdown returns the raw min = -0.10.
    """
    r = pd.Series([-0.10, 0.0, 0.0])
    assert _max_drawdown(r) == pytest.approx(-0.10, abs=1e-12)


def test_max_drawdown_later_peak():
    """When equity exceeds 1.0, the post-peak drawdown dominates.

    Returns [0.05, 0.03, -0.10]:
      equity 1.05, 1.0815, 0.97335; peak 1.0815;
      dd = 0.97335/1.0815 - 1 = -0.10; _max_drawdown returns raw min = -0.10.
    """
    r = pd.Series([0.05, 0.03, -0.10])
    assert _max_drawdown(r) == pytest.approx(-0.10, abs=1e-12)
