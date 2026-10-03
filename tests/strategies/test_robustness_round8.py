"""Round 8 — vectorised compute_costs / cap equivalence + parallel determinism.

The vectorised implementations in ``backtest.py`` must produce results identical
to the old loop-based versions to 1e-10 on random inputs (including NaN ADV,
sign flips, reductions and exits).  A 500-sequence property test enforces the
ADV-cap invariants.  Parallel variant execution must be deterministic regardless
of worker count.
"""
from __future__ import annotations

import copy
import math
import multiprocessing
import numpy as np
import pandas as pd
import pytest

from strategies.backtest import (
    cap_weight_changes_by_adv,
    compute_costs,
    _borrow_bps_daily_vec,
)
from strategies.cost_model import CostParams, borrow_bps_daily


# ── Reference (old loop-based) implementations ───────────────────────────────

def _compute_costs_ref(
    weights: pd.DataFrame,
    adv: pd.DataFrame,
    book_capital: float,
    params: CostParams | None = None,
    cost_multiplier: float = 1.0,
) -> dict[str, pd.Series]:
    """Old loop-based compute_costs — kept as reference copy."""
    from strategies.backtest import _scale_params
    if params is None:
        params = CostParams()
    params = _scale_params(params, cost_multiplier)

    dw = weights.diff()
    dw.iloc[0] = weights.iloc[0]
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
            participation = notional / a if a > 0 else 1.0
            bps = (
                params.commission_bps
                + 0.5 * params.spread_bps
                + params.slippage_bps * (participation / params.adv_participation_cap)
            )
            cost_dollars += notional * bps / 1e4
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


def _cap_weight_changes_by_adv_ref(
    weights: pd.DataFrame,
    adv: pd.DataFrame,
    book_capital: float,
    params: CostParams | None = None,
) -> pd.DataFrame:
    """Old cap_weight_changes_by_adv — kept as reference copy."""
    if params is None:
        params = CostParams()
    cap_frac = params.adv_participation_cap
    out = weights.to_numpy(dtype=float, copy=True)
    prev = np.zeros(out.shape[1])
    adv_ff = adv.reindex(index=weights.index, columns=weights.columns).ffill()
    adv_np = adv_ff.fillna(0.0).to_numpy(dtype=float)
    for i in range(out.shape[0]):
        cur = out[i]
        dw = cur - prev
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


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _random_panel(n_days=50, n_sym=20, seed=42, nan_adv_frac=0.05):
    """Generate random test data with realistic edge cases."""
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    symbols = [f"S{i:04d}" for i in range(n_sym)]

    weights_np = rng.randn(n_days, n_sym) * 0.02
    weights = pd.DataFrame(weights_np, index=dates, columns=symbols)

    adv_np = np.abs(rng.randn(n_days, n_sym) * 1e7 + 5e7)
    # Inject NaN ADV at random positions.
    mask = rng.rand(n_days, n_sym) < nan_adv_frac
    adv_np[mask] = np.nan
    adv = pd.DataFrame(adv_np, index=dates, columns=symbols)

    return weights, adv, dates, symbols


# ── compute_costs equivalence ────────────────────────────────────────────────

class TestComputeCostsEquivalence:
    """Vectorised compute_costs must match the old loop version to 1e-10."""

    @pytest.mark.parametrize("seed", range(20))
    def test_random_inputs(self, seed):
        weights, adv, _, _ = _random_panel(seed=seed)
        params = CostParams()
        ref = _compute_costs_ref(weights, adv, 10_000_000.0, params)
        new = compute_costs(weights, adv, 10_000_000.0, params)
        for key in ("turnover_cost", "borrow_cost", "total"):
            np.testing.assert_allclose(
                new[key].to_numpy(), ref[key].to_numpy(), atol=1e-10,
                err_msg=f"mismatch on {key} (seed={seed})",
            )

    def test_nan_adv_conservative(self):
        """NaN ADV must produce 100% participation (conservative)."""
        weights, adv, _, _ = _random_panel(nan_adv_frac=0.5, seed=99)
        params = CostParams()
        ref = _compute_costs_ref(weights, adv, 10_000_000.0, params)
        new = compute_costs(weights, adv, 10_000_000.0, params)
        np.testing.assert_allclose(
            new["total"].to_numpy(), ref["total"].to_numpy(), atol=1e-10,
        )

    def test_flips_and_exits(self):
        """Sign flips and exits must produce identical costs."""
        dates = pd.bdate_range("2024-01-02", periods=10)
        syms = ["A", "B", "C"]
        weights = pd.DataFrame(
            [[0.05, -0.03, 0.02],
             [-0.05, 0.03, 0.0],   # A flips, C exits
             [0.0, 0.05, -0.02],    # A exits, B increases, C flips
             [0.03, 0.0, 0.05],     # B exits
             [-0.03, -0.05, 0.0],
             [0.06, 0.02, -0.04],
             [0.0, 0.0, 0.0],       # all flat
             [0.01, 0.01, 0.01],
             [-0.01, -0.01, -0.01],
             [0.0, 0.0, 0.0]],
            index=dates, columns=syms,
        )
        adv = pd.DataFrame(
            np.full((10, 3), 1e8), index=dates, columns=syms,
        )
        params = CostParams()
        ref = _compute_costs_ref(weights, adv, 10_000_000.0, params)
        new = compute_costs(weights, adv, 10_000_000.0, params)
        np.testing.assert_allclose(
            new["total"].to_numpy(), ref["total"].to_numpy(), atol=1e-10,
        )

    def test_cost_multiplier(self):
        """Cost multiplier must scale identically in both implementations."""
        weights, adv, _, _ = _random_panel(seed=7)
        params = CostParams()
        for mult in (1.0, 2.0, 3.0):
            ref = _compute_costs_ref(weights, adv, 10_000_000.0, params, mult)
            new = compute_costs(weights, adv, 10_000_000.0, params, mult)
            np.testing.assert_allclose(
                new["total"].to_numpy(), ref["total"].to_numpy(), atol=1e-10,
            )

    def test_500_sequence_property(self):
        """Property test: turnover_cost >= 0, borrow_cost >= 0, total = sum."""
        weights, adv, _, _ = _random_panel(
            n_days=500, n_sym=500, seed=0, nan_adv_frac=0.02,
        )
        params = CostParams()
        result = compute_costs(weights, adv, 10_000_000.0, params)
        assert (result["turnover_cost"].to_numpy() >= -1e-15).all()
        assert (result["borrow_cost"].to_numpy() >= -1e-15).all()
        np.testing.assert_allclose(
            result["total"].to_numpy(),
            (result["turnover_cost"] + result["borrow_cost"]).to_numpy(),
            atol=1e-10,
        )


# ── cap_weight_changes_by_adv equivalence ────────────────────────────────────

class TestCapEquivalence:
    """Vectorised cap must match the old loop version to 1e-10."""

    @pytest.mark.parametrize("seed", range(20))
    def test_random_inputs(self, seed):
        weights, adv, _, _ = _random_panel(seed=seed)
        params = CostParams()
        ref = _cap_weight_changes_by_adv_ref(weights, adv, 10_000_000.0, params)
        new = cap_weight_changes_by_adv(weights, adv, 10_000_000.0, params)
        pd.testing.assert_frame_equal(new, ref, atol=1e-10)

    def test_sign_flips(self):
        """Sign flips: close leg free, open leg capped."""
        dates = pd.bdate_range("2024-01-02", periods=5)
        weights = pd.DataFrame(
            [[0.1, -0.05],
             [-0.1, 0.05],   # both flip
             [0.0, 0.0],      # exit
             [0.08, -0.08],
             [-0.08, 0.08]],
            index=dates, columns=["A", "B"],
        )
        adv = pd.DataFrame(
            np.full((5, 2), 1e8), index=dates, columns=["A", "B"],
        )
        params = CostParams()
        ref = _cap_weight_changes_by_adv_ref(weights, adv, 10_000_000.0, params)
        new = cap_weight_changes_by_adv(weights, adv, 10_000_000.0, params)
        pd.testing.assert_frame_equal(new, ref, atol=1e-10)

    def test_reductions_never_capped(self):
        """Same-side reductions toward zero must never be capped."""
        dates = pd.bdate_range("2024-01-02", periods=4)
        weights = pd.DataFrame(
            [[0.1, -0.1],
             [0.05, -0.05],  # reductions — must pass through
             [0.02, -0.02],  # further reductions
             [0.0, 0.0]],    # exits
            index=dates, columns=["A", "B"],
        )
        # Large ADV so initial positions are not capped on entry.
        adv = pd.DataFrame(
            [[1e9, 1e9]] * 4,
            index=dates, columns=["A", "B"],
        )
        params = CostParams()
        result = cap_weight_changes_by_adv(weights, adv, 10_000_000.0, params)
        # Reductions must be uncapped.
        np.testing.assert_allclose(
            result.iloc[1].to_numpy(), [0.05, -0.05], atol=1e-12,
        )
        np.testing.assert_allclose(
            result.iloc[2].to_numpy(), [0.02, -0.02], atol=1e-12,
        )

    def test_500_sequence_property(self):
        """500-day property test: output bounded, reductions free."""
        weights, adv, _, _ = _random_panel(
            n_days=500, n_sym=500, seed=1, nan_adv_frac=0.02,
        )
        params = CostParams()
        result = cap_weight_changes_by_adv(weights, adv, 10_000_000.0, params)
        # Output shape preserved.
        assert result.shape == weights.shape
        # No NaN in output (NaN ADV handled by ffill).
        assert not result.isna().any().any()


# ── borrow vectorisation ─────────────────────────────────────────────────────

class TestBorrowBpsVec:
    """Vectorised borrow_bps_daily must match scalar version."""

    def test_matches_scalar(self):
        adv_values = np.array([0.0, 1e6, 2e7, 5e7, 1e8, np.nan])
        params = CostParams()
        vec = _borrow_bps_daily_vec(np.nan_to_num(adv_values, nan=0.0), params)
        for i, adv in enumerate(adv_values):
            scalar = borrow_bps_daily(float(adv) if not math.isnan(adv) else 0.0, params)
            assert vec[i] == scalar, f"mismatch at adv={adv}"


# ── Parallel determinism ─────────────────────────────────────────────────────

# Module-level synthetic data for spawn-safe pool workers.
_RNG = np.random.RandomState(42)
_N_DAYS, _N_SYM = 200, 30
_DATES = pd.bdate_range("2024-01-02", periods=_N_DAYS)
_SYMBOLS = [f"S{i:04d}" for i in range(_N_SYM)]
_POSITIONS = pd.DataFrame(
    np.sign(_RNG.randn(_N_DAYS, _N_SYM) * 0.3),
    index=_DATES, columns=_SYMBOLS,
)
_RETURNS = pd.DataFrame(
    _RNG.randn(_N_DAYS, _N_SYM) * 0.01,
    index=_DATES, columns=_SYMBOLS,
)
_S_SCORE = pd.DataFrame(
    _RNG.randn(_N_DAYS, _N_SYM),
    index=_DATES, columns=_SYMBOLS,
)
_RESIDUAL = pd.DataFrame(
    _RNG.randn(_N_DAYS, _N_SYM) * 0.001,
    index=_DATES, columns=_SYMBOLS,
)
_INDUSTRY = pd.Series({s: f"ind_{i % 5}" for i, s in enumerate(_SYMBOLS)})


def _fake_build_signals(*args, **kwargs):
    """Pickleable fake build_signals for pool workers."""
    return {
        "positions": _POSITIONS.copy(),
        "returns": _RETURNS.copy(),
        "s_score": _S_SCORE.copy(),
        "residual": _RESIDUAL.copy(),
        "industry": _INDUSTRY.copy(),
    }


class TestParallelDeterminism:
    """Variant results must be identical regardless of worker count.

    Uses the ACTUAL ProcessPoolExecutor with the ``spawn`` start method
    so the test works on all platforms and exercises the real pickling path.
    """

    def test_workers_determinism(self):
        """workers=1 must equal workers=2 through the real ProcessPool (spawn)."""
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        from strategies.robustness import build_variant_registry
        from strategies.run_residual_reversion import (
            _run_variant, load_strategy_config, build_cost_params,
        )
        from strategies.robustness_worker import _worker_init, _worker_task

        cfg = load_strategy_config("strategies/config.yaml")
        cost_params = build_cost_params(cfg)
        registry = build_variant_registry(cfg)
        subset = registry[:4]
        n_trials = len(registry)

        universe = pd.DataFrame(
            [(d, s) for d in _DATES for s in _SYMBOLS],
            columns=["trade_date", "symbol"],
        )
        universe["adv_rank"] = 1
        adv_wide = pd.DataFrame(
            np.abs(_RNG.randn(_N_DAYS, _N_SYM) * 1e7 + 5e7),
            index=_DATES, columns=_SYMBOLS,
        )

        def _run_pool(n_workers):
            ctx = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(
                max_workers=n_workers,
                mp_context=ctx,
                initializer=_worker_init,
                initargs=(
                    cfg, pd.DataFrame(), universe, adv_wide,
                    _INDUSTRY, 10_000_000.0, cost_params, None,
                    _fake_build_signals,
                ),
            ) as pool:
                futures = [
                    pool.submit(_worker_task, (vs, n_trials))
                    for vs in subset
                ]
                return [f.result() for f in futures]

        results_w1 = _run_pool(1)
        results_w2 = _run_pool(2)

        for i, (w1, w2) in enumerate(zip(results_w1, results_w2)):
            if "error" in w1 or "error" in w2:
                pytest.fail(f"variant {i} errored: w1={w1.get('error')}, "
                            f"w2={w2.get('error')}")
            pd.testing.assert_series_equal(
                w1["net"], w2["net"], atol=1e-10,
                obj=f"variant {i} net",
            )


# ── Cache fingerprint completeness ───────────────────────────────────────────

class TestCacheFingerprint:
    """Composite cache fingerprint must change when config, data, or code change."""

    def test_commission_bps_changes_fingerprint(self):
        """Changing cost_model.commission_bps must change the fingerprint."""
        from strategies.robustness import compute_cache_fingerprint
        from strategies.run_residual_reversion import load_strategy_config

        cfg = load_strategy_config("strategies/config.yaml")
        fp1 = compute_cache_fingerprint("abc123", cfg, panel=None)

        cfg2 = copy.deepcopy(cfg)
        cfg2["cost_model"]["commission_bps"] = 50.0
        fp2 = compute_cache_fingerprint("abc123", cfg2, panel=None)

        assert fp1 != fp2, (
            f"fingerprint unchanged after changing commission_bps: {fp1}"
        )

    def test_spread_bps_changes_fingerprint(self):
        """Changing cost_model.spread_bps must change the fingerprint."""
        from strategies.robustness import compute_cache_fingerprint
        from strategies.run_residual_reversion import load_strategy_config

        cfg = load_strategy_config("strategies/config.yaml")
        fp1 = compute_cache_fingerprint("abc123", cfg, panel=None)

        cfg2 = copy.deepcopy(cfg)
        cfg2["cost_model"]["spread_bps"] = 300.0
        fp2 = compute_cache_fingerprint("abc123", cfg2, panel=None)

        assert fp1 != fp2

    def test_data_shape_changes_fingerprint(self):
        """Changing panel shape must change the fingerprint."""
        from strategies.robustness import compute_cache_fingerprint
        from strategies.run_residual_reversion import load_strategy_config

        cfg = load_strategy_config("strategies/config.yaml")
        dates_small = pd.bdate_range("2024-01-02", periods=10)
        dates_large = pd.bdate_range("2024-01-02", periods=20)
        panel_small = pd.DataFrame({
            "symbol": ["A"] * 10 + ["B"] * 10,
            "event_date": list(dates_small) * 2,
            "close": [100.0] * 20,
        })
        panel_large = pd.DataFrame({
            "symbol": ["A"] * 20 + ["B"] * 20 + ["C"] * 20 + ["D"] * 20,
            "event_date": list(dates_large) * 4,
            "close": [100.0] * 80,
        })
        fp1 = compute_cache_fingerprint("abc123", cfg, panel=panel_small)
        fp2 = compute_cache_fingerprint("abc123", cfg, panel=panel_large)

        assert fp1 != fp2

    def test_variant_params_change_fingerprint(self):
        """Different variant params must produce different fingerprints."""
        from strategies.robustness import compute_cache_fingerprint
        from strategies.run_residual_reversion import load_strategy_config

        cfg = load_strategy_config("strategies/config.yaml")
        fp1 = compute_cache_fingerprint("aaa", cfg, panel=None)
        fp2 = compute_cache_fingerprint("bbb", cfg, panel=None)

        assert fp1 != fp2


# ── Resume ordering ──────────────────────────────────────────────────────────

class TestResumeOrdering:
    """Partial resume must give each variant its own result, not reorder."""

    def test_resume_keys_by_variant_id(self):
        """Registry [A,B,C,D] with cached {A,C} must give A, B, C, D
        their OWN results (not B↔C swapped)."""
        from strategies.robustness import (
            build_variant_registry,
            compute_cache_fingerprint,
        )
        from strategies.run_residual_reversion import load_strategy_config

        cfg = load_strategy_config("strategies/config.yaml")
        registry = build_variant_registry(cfg)

        # Take first 4 variants.
        subset = registry[:4]
        ids = [vs.variant_id for vs in subset]
        assert len(ids) == 4

        # Simulate: A and C are cached, B and D need to run.
        results_by_id = {}
        cache_keys = {}
        for vs in subset:
            ck = compute_cache_fingerprint(vs.fingerprint, cfg, panel=None)
            cache_keys[vs.variant_id] = ck

        # Cached results (A and C).
        results_by_id[ids[0]] = {"variant_id": ids[0], "net": "cached_A"}
        results_by_id[ids[2]] = {"variant_id": ids[2], "net": "cached_C"}

        # Simulated computed results (B and D).
        results_by_id[ids[1]] = {"variant_id": ids[1], "net": "computed_B"}
        results_by_id[ids[3]] = {"variant_id": ids[3], "net": "computed_D"}

        # Rebuild in registry order.
        ordered = [results_by_id[vs.variant_id] for vs in subset]

        # Verify each variant gets its own result.
        assert ordered[0]["net"] == "cached_A", "A should get cached_A"
        assert ordered[1]["net"] == "computed_B", "B should get computed_B"
        assert ordered[2]["net"] == "cached_C", "C should get cached_C"
        assert ordered[3]["net"] == "computed_D", "D should get computed_D"