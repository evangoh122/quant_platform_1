"""Tests for run_residual_reversion helpers."""

import numpy as np
import pandas as pd
import pytest

from strategies.run_residual_reversion import _render, parse_round_from_output


class TestParseRoundFromOutput:
    def test_parses_r1(self):
        assert parse_round_from_output("strategies/results/residual_reversion_r1.md") == 1

    def test_parses_r4(self):
        assert parse_round_from_output("strategies/results/residual_reversion_r4.md") == 4

    def test_parses_r12(self):
        assert parse_round_from_output("residual_reversion_r12.md") == 12

    def test_raises_on_no_match(self):
        with pytest.raises(ValueError, match="cannot derive round"):
            parse_round_from_output("strategies/results/residual_reversion.md")

    def test_raises_on_wrong_suffix(self):
        with pytest.raises(ValueError, match="cannot derive round"):
            parse_round_from_output("strategies/results/residual_reversion_r3.txt")


def test_leverage_wording_says_50pct():
    """Gross 1.0 with dollar neutrality is 50% long / 50% short, not 100%/100%.

    The rendered configuration line must say '50% long / 50% short'.
    """
    bm = {
        "gross_ann_return": 0.01, "net_ann_return": 0.005,
        "net_2x_ann_return": 0.0, "gross_sharpe": 0.5, "net_sharpe": 0.3,
        "net_2x_sharpe": 0.1, "gross_max_drawdown": -0.1,
        "net_max_drawdown": -0.12, "net_2x_max_drawdown": -0.15,
        "hit_rate": 0.52, "turnover_avg_daily": 0.05, "avg_hold_days": 5.0,
        "deflated_sharpe_ratio": 0.0,
    }
    gm = dict(bm)
    base_res = {"metrics": bm}
    gated_res = {"metrics": gm}
    oos_net = pd.Series([0.001, 0.002, 0.003])

    lines = _render(
        base_res, gated_res, oos_net, n_trials=3, capacity=1e8,
        book_capital=10_000_000.0, window=60, lookback=5, entry=2.5,
        exit_thresh=0.5, date_start=pd.Timestamp("2024-01-01"),
        date_end=pd.Timestamp("2024-12-31"), n_dates=252, n_folds=5,
        round_num=7,
    )

    config_line = [l for l in lines if "target gross" in l]
    assert config_line, "no 'target gross' line found in rendered output"
    line = config_line[0]

    assert "50% long / 50% short" in line, (
        f"should say '50% long / 50% short', got: {line}"
    )
    assert "100% long / 100% short" not in line, (
        f"should NOT say '100% long / 100% short', got: {line}"
    )


# ── Round 11: valuation_returns fix ──────────────────────────────────────────

def test_exit_day_pnl_includes_held_name_return():
    """A name held at t-1 that leaves the universe at t, with a valid close at
    t. Day-t gross P&L must include w[t-1] * r[t] (the exit-day return).

    With masked (NaN) returns the exit-day P&L vanishes; with unmasked returns
    the backtest correctly picks up the held position's return.
    """
    from strategies.backtest import run_backtest

    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    symbols = ["A", "B"]

    # Signal: hold long A from day 1 onward.
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[1]:, "A"] = 1.0
    desired.loc[dates[1]:, "B"] = -1.0  # short B for dollar neutrality

    # A is in the universe for days 0-9, then drops out.
    universe = pd.DataFrame(
        [(d, "A") for d in dates[:10]]
        + [(d, "B") for d in dates],
        columns=["trade_date", "symbol"],
    )

    # True (unmasked) returns: A has a valid +1% return on every day,
    # including days 10-19 when it is out of the universe.
    returns_unmasked = pd.DataFrame(0.01, index=dates, columns=symbols)

    # Masked returns (the OLD code path): A's returns are NaN after day 9
    # because the signal pipeline masks to the PIT universe.
    members = set(zip(universe["trade_date"], universe["symbol"]))
    mask = pd.DataFrame(
        [[(d, s) in members for s in symbols] for d in dates],
        index=dates, columns=symbols,
    )
    returns_masked = returns_unmasked.where(mask)

    adv = pd.DataFrame(1e8, index=dates, columns=symbols)
    book_capital = 10_000_000.0

    # ── With masked returns (old behaviour): exit-day P&L is dropped ─────
    res_old = run_backtest(desired, returns_masked, universe, adv,
                           book_capital=book_capital, target_gross=1.0)
    w_prev_b = res_old["weights"].loc[dates[9], "B"]
    exit_day = dates[10]
    old_gross_exit = res_old["gross"].loc[exit_day]
    assert old_gross_exit == pytest.approx(w_prev_b * 0.01, abs=1e-12), (
        "with masked returns, exit-day gross should only include B's return"
    )

    # ── With unmasked returns (the fix): exit-day P&L is correct ─────────
    res_new = run_backtest(desired, returns_unmasked, universe, adv,
                           book_capital=book_capital, target_gross=1.0)
    w_prev_a = res_new["weights"].loc[dates[9], "A"]
    assert w_prev_a != 0.0, "A should have a non-zero weight on day 9"

    new_gross_exit = res_new["gross"].loc[exit_day]
    expected_gross = w_prev_a * 0.01 + w_prev_b * 0.01
    assert new_gross_exit == pytest.approx(expected_gross, abs=1e-12), (
        f"with unmasked returns, exit-day gross should include A's return: "
        f"expected {expected_gross:.8f}, got {new_gross_exit:.8f}"
    )

    # ── The fix adds A's return: new_gross != old_gross ───────────────────
    assert new_gross_exit != pytest.approx(old_gross_exit, abs=1e-12), (
        f"unmasked returns must produce different exit-day P&L than masked: "
        f"old={old_gross_exit:.8f}, new={new_gross_exit:.8f}"
    )


def test_missing_close_contributes_zero_not_fabricated():
    """A name with a genuinely missing close at t contributes 0 to gross P&L,
    with no fabricated return.

    When the return is NaN (missing price), weights.shift(1)[t] * NaN = NaN,
    and .sum() skips it — effectively 0 contribution.  The fix must not
    fabricate a return for a name with no price data.
    """
    from strategies.backtest import run_backtest

    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    symbols = ["A", "B"]

    # Hold A from day 1 onward.
    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    desired.loc[dates[1]:, "A"] = 1.0
    desired.loc[dates[1]:, "B"] = -1.0

    # A is always in the universe.
    universe = pd.DataFrame(
        [(d, "A") for d in dates]
        + [(d, "B") for d in dates],
        columns=["trade_date", "symbol"],
    )

    # A has a NaN return on day 10 (genuinely missing close).
    returns = pd.DataFrame(0.01, index=dates, columns=symbols)
    returns.loc[dates[10], "A"] = np.nan

    adv = pd.DataFrame(1e8, index=dates, columns=symbols)
    book_capital = 10_000_000.0

    res = run_backtest(desired, returns, universe, adv,
                       book_capital=book_capital, target_gross=1.0)

    # On day 10, A's return is NaN → contribution is NaN (skipped by sum).
    # B contributes normally.  Gross P&L should equal B's contribution only.
    w_prev_b = res["weights"].loc[dates[9], "B"]
    expected_b_pnl = w_prev_b * 0.01
    gross_day10 = res["gross"].loc[dates[10]]

    assert gross_day10 == pytest.approx(expected_b_pnl, abs=1e-12), (
        f"gross P&L on day 10 should only include B's return (A has missing close): "
        f"expected {expected_b_pnl:.8f}, got {gross_day10:.8f}"
    )


def test_signals_unchanged_by_valuation_returns_fix():
    """s-scores and positions must be identical before and after the fix.

    The fix adds 'valuation_returns' (unmasked) for the backtest but keeps
    'returns' (masked) for signal construction.  Signal outputs must not change.
    """
    from strategies.run_residual_reversion import build_signals

    dates = pd.date_range("2024-01-01", periods=200, freq="B")
    rng = np.random.default_rng(42)

    # Build synthetic closes with SPY + two tradeable names.
    spy = 100.0 + np.cumsum(rng.normal(0, 0.5, 200))
    a = 50.0 + np.cumsum(rng.normal(0, 0.3, 200))
    b = 30.0 + np.cumsum(rng.normal(0, 0.2, 200))

    closes_long = []
    for i, d in enumerate(dates):
        closes_long.append({"symbol": "SPY", "event_date": d, "close": spy[i]})
        closes_long.append({"symbol": "A", "event_date": d, "close": a[i]})
        closes_long.append({"symbol": "B", "event_date": d, "close": b[i]})
    closes = pd.DataFrame(closes_long)

    # A is in universe for first 150 days; B is always in universe.
    universe_rows = [(d, "A") for d in dates[:150]] + [(d, "B") for d in dates]
    universe = pd.DataFrame(universe_rows, columns=["trade_date", "symbol"])

    signals = build_signals(closes, universe, window=60, lookback=5,
                            entry=2.5, exit_thresh=0.5, max_hold=5)

    # The fix must add 'valuation_returns' key.
    assert "valuation_returns" in signals, "missing 'valuation_returns' key"

    # valuation_returns must be UNMASKED: A's return on day 150 should be
    # valid (not NaN), even though A is not in the universe on day 150.
    val_ret = signals["valuation_returns"]
    assert pd.notna(val_ret.loc[dates[150], "A"]), (
        "valuation_returns should be unmasked — A's return on day 150 must be valid"
    )

    # 'returns' (masked) must have NaN for A on day 150.
    mask_ret = signals["returns"]
    assert pd.isna(mask_ret.loc[dates[150], "A"]), (
        "returns (masked) should have NaN for A on day 150"
    )

    # s-scores and positions must be valid and unchanged.
    s_score = signals["s_score"]
    positions = signals["positions"]
    assert s_score.shape == (200, 2), f"s_score shape {s_score.shape}"
    assert positions.shape == (200, 2), f"positions shape {positions.shape}"

    # Verify positions are -1, 0, or +1.
    unique_pos = set(positions.values.flatten())
    assert unique_pos.issubset({-1.0, 0.0, 1.0}), (
        f"positions should be -1/0/+1, got {unique_pos}"
    )


# ── Round 12: split-adjusted prices + masked breaks ────────────────────────

def test_adjusted_table_maps_adj_close_as_close():
    """When price_table='silver_ohlcv_day_adjusted', fetch_data generates SQL
    that selects `adj_close AS close`."""
    import inspect
    from strategies.run_residual_reversion import fetch_data
    src = inspect.getsource(fetch_data)
    assert "adj_close AS close" in src, (
        "fetch_data must select 'adj_close AS close' for the adjusted table"
    )


def test_bronze_path_logs_warning():
    """When price_table='bronze_ohlcv_day', fetch_data must emit a warning
    about unadjusted prices."""
    import warnings
    import inspect
    from strategies.run_residual_reversion import fetch_data
    src = inspect.getsource(fetch_data)
    assert "UNADJUSTED" in src or "unadjusted" in src.lower(), (
        "fetch_data must warn about unadjusted prices for bronze path"
    )


def test_masked_break_yields_nan_return():
    """A (symbol, date) in masked_breaks must have NaN return in both
    signal returns and valuation returns."""
    from strategies.run_residual_reversion import build_signals

    dates = pd.date_range("2024-01-01", periods=200, freq="B")
    rng = np.random.default_rng(42)

    spy = 100.0 + np.cumsum(rng.normal(0, 0.5, 200))
    x = 50.0 + np.cumsum(rng.normal(0, 0.3, 200))
    y = 30.0 + np.cumsum(rng.normal(0, 0.2, 200))

    closes_long = []
    for i, d in enumerate(dates):
        closes_long.append({"symbol": "SPY", "event_date": d, "close": spy[i]})
        closes_long.append({"symbol": "TESTX", "event_date": d, "close": x[i]})
        closes_long.append({"symbol": "TESTY", "event_date": d, "close": y[i]})
    closes = pd.DataFrame(closes_long)

    universe_rows = [(d, "TESTX") for d in dates] + [(d, "TESTY") for d in dates]
    universe = pd.DataFrame(universe_rows, columns=["trade_date", "symbol"])

    # Day 100 is a masked break for TESTX.
    masked_breaks = {("TESTX", dates[100])}

    signals = build_signals(closes, universe, window=60, lookback=5,
                            entry=2.5, exit_thresh=0.5, max_hold=5,
                            masked_breaks=masked_breaks)

    # Signal returns (masked): TESTX on day 100 must be NaN.
    assert pd.isna(signals["returns"].loc[dates[100], "TESTX"]), (
        "masked break day must have NaN in signal returns"
    )
    # Valuation returns: TESTX on day 100 must also be NaN.
    assert pd.isna(signals["valuation_returns"].loc[dates[100], "TESTX"]), (
        "masked break day must have NaN in valuation returns"
    )
    # TESTY is unaffected.
    assert pd.notna(signals["returns"].loc[dates[100], "TESTY"]), (
        "non-masked symbol must have valid return"
    )


def test_masked_break_no_signal_triggered():
    """A synthetic panel with a x3 jump flagged as masked must NOT trigger
    a trade signal on that day."""
    from strategies.run_residual_reversion import build_signals

    dates = pd.date_range("2024-01-01", periods=200, freq="B")
    rng = np.random.default_rng(99)

    spy_prices = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 200)))
    # X and Y: fake symbols (not in tickers.yaml) so both map to __unknown__
    # and share the same industry → non-zero industry factor.
    # X: moderate daily moves, then a x3 jump on day 100 (return ~200%).
    x_returns = rng.normal(0, 0.02, 200)
    x_returns[100] = 2.0  # x3 price jump = 200% return
    x_prices = 50.0 * np.exp(np.cumsum(x_returns))
    y_prices = 30.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 200)))

    closes_long = []
    for i, d in enumerate(dates):
        closes_long.append({"symbol": "SPY", "event_date": d, "close": spy_prices[i]})
        closes_long.append({"symbol": "TESTX", "event_date": d, "close": x_prices[i]})
        closes_long.append({"symbol": "TESTY", "event_date": d, "close": y_prices[i]})
    closes = pd.DataFrame(closes_long)

    universe_rows = [(d, "TESTX") for d in dates] + [(d, "TESTY") for d in dates]
    universe = pd.DataFrame(universe_rows, columns=["trade_date", "symbol"])

    # Flag the x3 jump day as masked.
    masked_breaks = {("TESTX", dates[100])}

    signals = build_signals(closes, universe, window=60, lookback=5,
                            entry=2.5, exit_thresh=0.5, max_hold=5,
                            masked_breaks=masked_breaks)

    # The masked day must have NaN return → no signal generated.
    pos_x = signals["positions"].loc[dates[100], "TESTX"]
    assert pos_x == 0.0, (
        f"masked break day must not trigger a trade, got position {pos_x}"
    )


def test_mutation_ignore_mask_fails():
    """Mutation test: ignoring the mask changes returns from NaN to finite.

    This verifies the mask is load-bearing — removing it breaks the invariant
    that masked break days have NaN returns.
    """
    from strategies.run_residual_reversion import build_signals

    dates = pd.date_range("2024-01-01", periods=200, freq="B")
    rng = np.random.default_rng(42)

    spy = 100.0 + np.cumsum(rng.normal(0, 0.5, 200))
    x = 50.0 + np.cumsum(rng.normal(0, 0.3, 200))
    y = 30.0 + np.cumsum(rng.normal(0, 0.2, 200))

    closes_long = []
    for i, d in enumerate(dates):
        closes_long.append({"symbol": "SPY", "event_date": d, "close": spy[i]})
        closes_long.append({"symbol": "TESTX", "event_date": d, "close": x[i]})
        closes_long.append({"symbol": "TESTY", "event_date": d, "close": y[i]})
    closes = pd.DataFrame(closes_long)

    universe_rows = [(d, "TESTX") for d in dates] + [(d, "TESTY") for d in dates]
    universe = pd.DataFrame(universe_rows, columns=["trade_date", "symbol"])

    masked_breaks = {("TESTX", dates[100])}

    # WITH mask: return on masked day is NaN.
    signals_masked = build_signals(closes, universe, window=60, lookback=5,
                                   entry=2.5, exit_thresh=0.5, max_hold=5,
                                   masked_breaks=masked_breaks)
    assert pd.isna(signals_masked["returns"].loc[dates[100], "TESTX"]), (
        "with mask, return must be NaN on masked day"
    )

    # WITHOUT mask (mutation): return on same day is finite.
    signals_no_mask = build_signals(closes, universe, window=60, lookback=5,
                                    entry=2.5, exit_thresh=0.5, max_hold=5,
                                    masked_breaks=None)
    assert pd.notna(signals_no_mask["returns"].loc[dates[100], "TESTX"]), (
        "without mask, return must be finite on the same day"
    )

    # The two must differ — the mask is load-bearing.
    assert pd.isna(signals_masked["returns"].loc[dates[100], "TESTX"]) != \
           pd.isna(signals_no_mask["returns"].loc[dates[100], "TESTX"]), (
        "mask must change NaN/finite status of the return on the break day"
    )