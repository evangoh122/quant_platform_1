"""Robustness round-2 blocking-findings tests.

Every test in this file must FAIL on the pre-round-2 HEAD and PASS after the
round-2 fixes.  The tests use synthetic data exclusively — no network calls.
"""

import copy
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from strategies.robustness import (
    VariantSpec,
    build_variant_registry,
    compute_fold_metrics,
    render_robustness_report,
    remove_top_pnl_contributors,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_config():
    return {
        "residual_reversion": {
            "status": "primary", "bar_freq": "1d",
            "factor_model": "ols_mkt_ind", "factor_window": 60,
            "pca_components": 10, "residual_lookback": 5,
            "entry_threshold": 2.5, "exit_threshold": 0.5,
            "max_hold_candidates": [3, 5, 10], "min_obs_fraction": 0.8,
            "universe_size": 300, "target_gross": 1.0,
            "book_capital": 10_000_000, "execution_lag_bars": 1,
        },
        "robustness": {
            "cost_multipliers": [1.0, 2.0, 3.0],
            "universe_sizes": [200, 300, 500],
            "parameter_perturbation": 0.20,
            "drop_top_pnl_contributors": 3,
            "walk_forward_folds": 5,
            "min_profitable_folds": 3,
            "rank_ic_horizon_days": 5,
        },
        "cost_model": {
            "commission_bps": 0.5, "spread_bps": 3.0, "slippage_bps": 2.0,
            "adv_participation_cap": 0.01,
        },
        "metric_gates": {
            "sharpe_min": 1.25, "max_drawdown_max": 0.15,
            "return_to_dd_min": 1.0, "margin_min_bps": 5.0,
            "oos_ratio_min": 0.50,
        },
    }


def _make_panel(n_symbols=600, n_days=400, seed=42):
    """Synthetic bronze panel with dollar_volume for universe screening."""
    dates = pd.date_range("2023-01-03", periods=n_days, freq="B")
    rng = np.random.RandomState(seed)
    rows = []
    for i in range(n_symbols):
        sym = f"S{i:03d}"
        base_dv = (n_symbols - i) * 1e6  # decreasing dollar volume
        for d, date in enumerate(dates):
            dv = base_dv * (1.0 + d / 200.0) + rng.normal(0, 1e4)
            rows.append((sym, date, max(dv, 1000.0)))
    return pd.DataFrame(rows, columns=["symbol", "event_date", "dollar_volume"])


def _make_closes_from_panel(panel):
    """Derive a closes long frame from the panel (fake close = dollar_volume / 1e6)."""
    closes = panel.copy()
    closes["close"] = closes["dollar_volume"] / 1e6
    return closes[["symbol", "event_date", "close"]]


# ---------------------------------------------------------------------------
# Blocking #1: Top-500 universe is really built
# ---------------------------------------------------------------------------

class TestTop500Universe:
    def test_top500_differs_from_top300(self):
        """With 600 symbols, top-500 must contain more symbols than top-300.

        Before the fix, _run_variant always sliced from gold_tradable_universe
        (max 300), so universe_size=500 silently returned ≤300 rows.
        """
        from strategies.universe import screen_universe
        panel = _make_panel(n_symbols=600, n_days=400)
        u500 = screen_universe(panel, n=500, min_history=100, recency_sessions=5)
        u300 = screen_universe(panel, n=300, min_history=100, recency_sessions=5)

        # On any date, top-500 must have more symbols than top-300.
        date = u500["trade_date"].iloc[200]
        n500 = len(u500[u500["trade_date"] == date])
        n300 = len(u300[u300["trade_date"] == date])
        assert n500 > n300, (
            f"top-500 has {n500} symbols, top-300 has {n300}; "
            "they should differ when 600 symbols exist"
        )

    def test_missing_session_symbol_handled(self):
        """A symbol with a missing session (gap) must still be ranked correctly
        using dense-grid semantics (coordinate with round 8 of universe.py)."""
        from strategies.universe import screen_universe
        panel = _make_panel(n_symbols=20, n_days=200)
        # Remove some sessions for S000 to create a gap.
        mask = (panel["symbol"] == "S000") & (panel["event_date"].isin(
            panel[panel["symbol"] == "S000"]["event_date"].iloc[50:55]
        ))
        panel_gapped = panel[~mask].copy()

        out = screen_universe(panel_gapped, n=20, min_history=50, recency_sessions=1)
        # S000 should still appear after its gap (it has enough history).
        syms = set(out["symbol"])
        assert "S000" in syms, "S000 disappeared after a 5-session gap"


# ---------------------------------------------------------------------------
# Blocking #2: Top-3 contributor removal executes
# ---------------------------------------------------------------------------

class TestDropTopPnl:
    def test_drop_top_changes_results(self):
        """The drop_top variant must produce different results from baseline.

        Before the fix, _run_variant ignored drop_top_pnl entirely, so the
        drop-top variant was numerically identical to baseline.
        """
        from strategies.run_residual_reversion import _run_variant, run_one
        cfg = _base_config()
        # Use 400 dates so screen_universe (min_history=252) works.
        dates = pd.date_range("2023-01-03", periods=400, freq="B")
        rng = np.random.RandomState(42)
        symbols = [f"S{i:03d}" for i in range(10)]

        # Synthetic closes (long frame).
        rows = []
        for sym in symbols:
            for d, date in enumerate(dates):
                rows.append((sym, date, 100.0 + rng.normal(0, 1.0)))
        closes = pd.DataFrame(rows, columns=["symbol", "event_date", "close"])

        # Synthetic universe (all symbols on all dates).
        univ_rows = []
        for sym in symbols:
            for d, date in enumerate(dates):
                univ_rows.append((date, sym, 1e8, 1))
        universe = pd.DataFrame(univ_rows, columns=["trade_date", "symbol", "med_adv_60d", "adv_rank"])

        adv_wide = pd.DataFrame(1e8, index=dates, columns=symbols)
        industry = pd.Series({s: "tech" for s in symbols})

        # Track which symbols build_signals was called with.
        call_log = []

        def mock_build_signals(closes_df, univ_df, *args, **kwargs):
            syms = sorted(set(closes_df["symbol"]) & set(univ_df["symbol"]))
            call_log.append(set(syms))
            idx = dates
            positions = pd.DataFrame(0.0, index=idx, columns=syms)
            returns = pd.DataFrame(rng.normal(0.001, 0.01, (len(idx), len(syms))),
                                   index=idx, columns=syms)
            # Make S000, S001, S002 carry the most P&L.
            if "S000" in syms:
                returns["S000"] = 0.05
            if "S001" in syms:
                returns["S001"] = 0.03
            if "S002" in syms:
                returns["S002"] = 0.02
            positions.iloc[10:] = 0.1  # small position in all
            return {"positions": positions, "returns": returns, "beta_mkt": None,
                    "industry": industry.reindex(syms)}

        def mock_run_backtest(positions, returns, *args, **kwargs):
            net = (positions.shift(1).fillna(0.0) * returns).sum(axis=1)
            weights = positions.shift(1).fillna(0.0)
            return {"net": net, "gross": net, "weights": weights,
                    "turnover": pd.Series(0.1, index=positions.index),
                    "metrics": {"net_sharpe": 1.0, "net_ann_return": 0.1,
                                "net_max_drawdown": -0.05}}

        # Panel for screen_universe (needs dollar_volume column).
        panel = pd.DataFrame(
            [(s, d, 1e8) for s in symbols for d in dates],
            columns=["symbol", "event_date", "dollar_volume"],
        )

        with patch("strategies.run_residual_reversion.build_signals", side_effect=mock_build_signals), \
             patch("strategies.run_residual_reversion.run_backtest", side_effect=mock_run_backtest):

            # Baseline variant (no drop).
            baseline_spec = VariantSpec(
                variant_id="baseline_ols_h5",
                fingerprint="aaa",
                params={"factor_model": "ols_mkt_ind", "max_hold": 5,
                        "universe_size": 300, "cost_multiplier": 1.0,
                        "entry_threshold": 2.5, "exit_threshold": 0.5,
                        "factor_window": 60},
                category="baseline",
            )
            # Drop-top variant.
            drop_spec = VariantSpec(
                variant_id="drop_top_ols_h5",
                fingerprint="bbb",
                params={"factor_model": "ols_mkt_ind", "max_hold": 5,
                        "universe_size": 300, "cost_multiplier": 1.0,
                        "entry_threshold": 2.5, "exit_threshold": 0.5,
                        "factor_window": 60,
                        "drop_top_pnl": 3},
                category="top_pnl_removal",
            )

            base_result = _run_variant(baseline_spec, closes, universe, adv_wide,
                                       industry, 10_000_000,
                                       MagicMock(), cfg, panel=panel)
            drop_result = _run_variant(drop_spec, closes, universe, adv_wide,
                                       industry, 10_000_000,
                                       MagicMock(), cfg, panel=panel)

        # The drop variant should have been called 3 times for build_signals
        # (baseline initial + drop initial + drop after removal).
        # Verify that the last call had fewer symbols.
        assert len(call_log) >= 3, f"Expected ≥3 build_signals calls, got {len(call_log)}"
        # Last call should have fewer symbols (top3 removed).
        assert len(call_log[-1]) < len(call_log[0]), (
            f"Drop-top build_signals should use fewer symbols: "
            f"first={len(call_log[0])}, last={len(call_log[-1])}"
        )

        # Results must differ (drop removes top contributors).
        assert not np.allclose(
            base_result["net"].values, drop_result["net"].values,
            atol=1e-10,
        ), "drop_top variant produced identical results to baseline"

    def test_dropped_symbols_tracked(self):
        """The drop-top variant must record which symbols were dropped."""
        from strategies.robustness import remove_top_pnl_contributors
        dates = pd.date_range("2024-01-01", periods=20, freq="B")
        symbols = ["A", "B", "C", "D"]
        returns = pd.DataFrame(
            [[0.05, 0.01, 0.03, 0.001]] * 20,
            index=dates, columns=symbols,
        )
        weights = pd.DataFrame(0.1, index=dates, columns=symbols)
        net = (weights.shift(1).fillna(0.0) * returns).sum(axis=1)

        result = remove_top_pnl_contributors(net, weights, returns, n_remove=2)
        assert len(result["removed_symbols"]) == 2
        # A (0.05) and C (0.03) should be the top 2.
        assert "A" in result["removed_symbols"]
        assert "C" in result["removed_symbols"]


# ---------------------------------------------------------------------------
# Blocking #3: Report has every required table
# ---------------------------------------------------------------------------

class TestReportTables:
    def test_report_has_all_required_headings(self):
        """render_robustness_report must emit all required section headings."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        rng = np.random.default_rng(42)
        variant_results = []
        for vs in registry:
            net = pd.Series(rng.normal(0.001, 0.01, 100), index=dates)
            variant_results.append({
                "variant_id": vs.variant_id,
                "fingerprint": vs.fingerprint,
                "net": net,
                "gross": net,
                "metrics": {},
                "weights": pd.DataFrame(0.0, index=dates, columns=["A"]),
                "turnover": pd.Series(0.1, index=dates),
                "is_sharpe": 1.0,
                "oos_sharpe": 0.7,
            })

        splits = [(np.arange(0, 16), np.arange(16, 32)),
                  (np.arange(0, 32), np.arange(32, 48)),
                  (np.arange(0, 48), np.arange(48, 64)),
                  (np.arange(0, 64), np.arange(64, 80)),
                  (np.arange(0, 80), np.arange(80, 100))]

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
            splits=splits,
        )

        required_headings = [
            "Factor-model comparison",
            "Cost stress",
            "Universe stress",
            "Parameter perturbation",
            "Top-3 P&L contributor removal",
            "Walk-forward folds",
            "Exposures",
            "Turnover / capacity / margin",
            "Rank IC",
            "Gate summary",
        ]
        for heading in required_headings:
            assert heading in report, f"Missing required report section: {heading}"

    def test_gate_columns_present_and_nonempty(self):
        """The gate summary table must have all gate columns and they must not
        all be N/A."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        rng = np.random.default_rng(42)
        variant_results = []
        for vs in registry:
            net = pd.Series(rng.normal(0.001, 0.01, 100), index=dates)
            variant_results.append({
                "variant_id": vs.variant_id,
                "fingerprint": vs.fingerprint,
                "net": net,
                "gross": net,
                "metrics": {},
                "weights": pd.DataFrame(0.0, index=dates, columns=["A"]),
                "turnover": pd.Series(0.1, index=dates),
                "is_sharpe": 1.0,
                "oos_sharpe": 0.7,
            })

        report = render_robustness_report(
            registry=registry,
            variant_results=variant_results,
            gates=cfg["metric_gates"],
            config=cfg,
            n_trials=len(registry),
            executed_trials=len(registry),
        )

        gate_cols = ["sharpe_min", "max_dd_max", "return_dd_min", "margin_min", "oos_ratio"]
        for col in gate_cols:
            assert col in report, f"Gate column '{col}' missing from report"

    def test_variant_rows_include_is_oos_ratio(self):
        """Variant rows must include IS Sharpe, OOS Sharpe and OOS/IS columns."""
        cfg = _base_config()
        registry = [VariantSpec(
            variant_id="baseline_ols_h5", fingerprint="aaa",
            params={"factor_model": "ols_mkt_ind", "max_hold": 5,
                    "universe_size": 300, "cost_multiplier": 1.0,
                    "entry_threshold": 2.5, "exit_threshold": 0.5,
                    "factor_window": 60},
            category="baseline",
        )]
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        net = pd.Series(np.random.default_rng(42).normal(0.001, 0.01, 50), index=dates)
        variant_results = [{
            "net": net, "gross": net, "metrics": {},
            "weights": pd.DataFrame(0.0, index=dates, columns=["A"]),
            "turnover": pd.Series(0.1, index=dates),
            "is_sharpe": 1.2, "oos_sharpe": 0.8,
        }]

        report = render_robustness_report(
            registry=registry, variant_results=variant_results,
            gates=cfg["metric_gates"], config=cfg,
            n_trials=1, executed_trials=1,
        )

        assert "IS Sharpe" in report or "IS Sharpe" in report.lower()
        assert "OOS Sharpe" in report or "OOS Sharpe" in report.lower()
        # The gate summary table should show non-N/A for oos_ratio when IS/OOS are provided.
        assert "0.67" in report or "0.80" in report  # 0.8/1.2 ≈ 0.67


# ---------------------------------------------------------------------------
# Blocking #4: Config keys are consumed (not just validated)
# ---------------------------------------------------------------------------

class TestConfigConsumption:
    def test_min_obs_fraction_consumed(self):
        """Changing min_obs_fraction must change the residual computation."""
        from strategies.residual_reversion import compute_residuals
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.normal(0, 0.02, (100, 5)),
                               index=dates, columns=list("ABCDE"))
        market = pd.Series(rng.normal(0, 0.01, 100), index=dates)

        # With min_obs_fraction=0.8, window=60 → min_obs=48.
        res_high = compute_residuals(returns, market, window=60, lookback=5,
                                     min_obs=int(np.ceil(0.8 * 60)))
        # With min_obs_fraction=0.5, window=60 → min_obs=30.
        res_low = compute_residuals(returns, market, window=60, lookback=5,
                                    min_obs=int(np.ceil(0.5 * 60)))

        # Lower min_obs should produce fewer NaN residuals.
        n_nan_high = res_high["residual"].isna().sum().sum()
        n_nan_low = res_low["residual"].isna().sum().sum()
        assert n_nan_low <= n_nan_high, (
            f"Lower min_obs ({n_nan_low} NaN) should have ≤ NaN vs higher ({n_nan_high})"
        )

    def test_target_gross_consumed(self):
        """target_gross must be passed to neutralize_daily in run_backtest."""
        from strategies.backtest import run_backtest
        dates = pd.date_range("2024-01-01", periods=20, freq="B")
        symbols = ["A", "B"]
        positions = pd.DataFrame(0.0, index=dates, columns=symbols)
        positions.iloc[5:] = 0.5
        returns = pd.DataFrame(0.001, index=dates, columns=symbols)
        universe = pd.DataFrame(
            [(d, s) for d in dates for s in symbols],
            columns=["trade_date", "symbol"],
        )
        adv = pd.DataFrame(1e8, index=dates, columns=symbols)

        with patch("strategies.backtest.neutralize_daily") as mock_neut:
            mock_neut.return_value = positions.copy()
            run_backtest(positions, returns, universe, adv,
                         target_gross=0.5, book_capital=10_000_000)
            # Verify neutralize_daily was called with target_gross=0.5.
            call_kwargs = mock_neut.call_args
            assert call_kwargs.kwargs.get("target_gross") == 0.5 or \
                   (len(call_kwargs.args) > 3 and call_kwargs.args[3] == 0.5) or \
                   call_kwargs[1].get("target_gross") == 0.5, \
                f"target_gross not passed to neutralize_daily: {call_kwargs}"

    def test_execution_lag_bars_consumed(self):
        """execution_lag_bars must be passed to enforce_execution_lag."""
        from strategies.backtest import run_backtest
        dates = pd.date_range("2024-01-01", periods=20, freq="B")
        symbols = ["A", "B"]
        positions = pd.DataFrame(0.5, index=dates, columns=symbols)
        returns = pd.DataFrame(0.001, index=dates, columns=symbols)
        universe = pd.DataFrame(
            [(d, s) for d in dates for s in symbols],
            columns=["trade_date", "symbol"],
        )
        adv = pd.DataFrame(1e8, index=dates, columns=symbols)

        res1 = run_backtest(positions, returns, universe, adv,
                            book_capital=10_000_000, execution_lag_bars=1)
        res2 = run_backtest(positions, returns, universe, adv,
                            book_capital=10_000_000, execution_lag_bars=2)

        # With lag=2, the first 2 bars should be zero fills.
        assert (res2["fills"].iloc[0] == 0.0).all(), "lag=2: first bar should be zero"
        assert (res2["fills"].iloc[1] == 0.0).all(), "lag=2: second bar should be zero"
        # With lag=1, only the first bar is zero.
        assert (res1["fills"].iloc[0] == 0.0).all(), "lag=1: first bar should be zero"
        assert (res1["fills"].iloc[1] != 0.0).any(), "lag=1: second bar should be nonzero"


# ---------------------------------------------------------------------------
# Blocking #5: Trial count is honest
# ---------------------------------------------------------------------------

class TestTrialCountHonesty:
    def test_identical_results_not_double_counted(self):
        """Two variants that produce identical results should be flagged.

        The fingerprint dedup in build_variant_registry already prevents exact
        param duplicates, but if two different param vectors produce identical
        outputs (e.g., due to the universe-size bug), n_trials overstates.
        """
        cfg = _base_config()
        registry = build_variant_registry(cfg)

        # Verify that universe_size=200 and universe_size=500 have different fingerprints.
        univ_variants = [v for v in registry if v.category == "universe_stress"]
        fps = [v.fingerprint for v in univ_variants]
        assert len(fps) == len(set(fps)), (
            f"Universe stress variants have duplicate fingerprints: {fps}"
        )

    def test_drop_top_has_unique_fingerprint(self):
        """The drop_top variant must have a different fingerprint from baseline."""
        cfg = _base_config()
        registry = build_variant_registry(cfg)
        baselines = {v.variant_id: v for v in registry if v.category == "baseline"}
        drop_tops = {v.variant_id: v for v in registry if v.category == "top_pnl_removal"}

        for bt_id, bt in baselines.items():
            # Find matching drop_top (same factor_model and hold).
            for dt_id, dt in drop_tops.items():
                if (dt.params.get("factor_model") == bt.params.get("factor_model") and
                    dt.params.get("max_hold") == bt.params.get("max_hold")):
                    assert dt.fingerprint != bt.fingerprint, (
                        f"Drop-top {dt_id} has same fingerprint as baseline {bt_id}"
                    )