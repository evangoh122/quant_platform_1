"""Round 10 — cache round-trip, CLI override fingerprint, data fingerprint, determinism.

The checkpoint cache must preserve DatetimeIndex on Series and DataFrames.
CLI overrides (book_capital, factor_model, pca_components) must enter the
cache fingerprint.  The data fingerprint must cover close AND dollar_volume.
Parallel determinism must hold for ALL result fields at workers 1/2/4.
"""
from __future__ import annotations

import copy
import multiprocessing
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategies.robustness import (
    build_variant_registry,
    compute_cache_fingerprint,
    load_variant_cache,
    save_variant_cache,
)
from strategies.run_residual_reversion import (
    _run_variant,
    build_cost_params,
    load_strategy_config,
)


# ── Shared synthetic data (module-level for spawn-safe pickling) ─────────────

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


# ── Cache round-trip preserves indexes ───────────────────────────────────────

class TestCacheRoundTrip:
    """save_variant_cache / load_variant_cache must preserve all index types."""

    def test_round_trip_preserves_datetime_index(self):
        """A real _run_variant result round-trips with equal index and values."""
        cfg = load_strategy_config("strategies/config.yaml")
        cost_params = build_cost_params(cfg)
        registry = build_variant_registry(cfg)
        vs = registry[0]  # first baseline variant
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

        fresh = _run_variant(
            vs, pd.DataFrame(), universe, adv_wide,
            _INDUSTRY, 10_000_000.0, cost_params, cfg,
            n_trials=n_trials, build_signals_fn=_fake_build_signals,
        )
        assert "error" not in fresh, fresh.get("error")

        with tempfile.TemporaryDirectory() as tmp:
            save_variant_cache(tmp, "test_key", fresh)
            loaded = load_variant_cache(tmp, "test_key")

        assert loaded is not None, "cache miss after save"

        # Compare every Series/DataFrame field.
        for key in ("net", "gross", "turnover"):
            if key in fresh and isinstance(fresh[key], pd.Series):
                assert key in loaded, f"{key} missing from loaded cache"
                pd.testing.assert_series_equal(
                    loaded[key], fresh[key],
                    check_names=True,
                    obj=f"round-trip {key}",
                )
                assert isinstance(loaded[key].index, type(fresh[key].index)), (
                    f"{key} index type changed: {type(loaded[key].index)} vs "
                    f"{type(fresh[key].index)}"
                )

        for key in ("weights", "s_score", "trade_returns", "residual_returns"):
            if key in fresh and isinstance(fresh[key], pd.DataFrame):
                assert key in loaded, f"{key} missing from loaded cache"
                pd.testing.assert_frame_equal(
                    loaded[key], fresh[key],
                    check_names=True,
                    obj=f"round-trip {key}",
                )

    def test_round_trip_preserves_metrics(self):
        """Scalar metrics survive the round-trip exactly."""
        cfg = load_strategy_config("strategies/config.yaml")
        cost_params = build_cost_params(cfg)
        registry = build_variant_registry(cfg)
        vs = registry[0]
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

        fresh = _run_variant(
            vs, pd.DataFrame(), universe, adv_wide,
            _INDUSTRY, 10_000_000.0, cost_params, cfg,
            n_trials=n_trials, build_signals_fn=_fake_build_signals,
        )

        with tempfile.TemporaryDirectory() as tmp:
            save_variant_cache(tmp, "test_key", fresh)
            loaded = load_variant_cache(tmp, "test_key")

        assert loaded["variant_id"] == fresh["variant_id"]
        assert loaded["fingerprint"] == fresh["fingerprint"]
        assert loaded["is_sharpe"] == fresh["is_sharpe"]
        assert loaded["oos_sharpe"] == fresh["oos_sharpe"]

    def test_input_only_fields_dropped(self):
        """adv_wide and industry are not persisted (they are inputs)."""
        cfg = load_strategy_config("strategies/config.yaml")
        cost_params = build_cost_params(cfg)
        registry = build_variant_registry(cfg)
        vs = registry[0]
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

        fresh = _run_variant(
            vs, pd.DataFrame(), universe, adv_wide,
            _INDUSTRY, 10_000_000.0, cost_params, cfg,
            n_trials=n_trials, build_signals_fn=_fake_build_signals,
        )

        with tempfile.TemporaryDirectory() as tmp:
            save_variant_cache(tmp, "test_key", fresh)
            loaded = load_variant_cache(tmp, "test_key")

        assert "adv_wide" not in loaded, "adv_wide should be dropped from cache"
        assert "industry" not in loaded, "industry should be dropped from cache"

    def test_resume_report_identical_to_fresh(self):
        """A run that resumes fully from cache produces identical results to fresh."""
        cfg = load_strategy_config("strategies/config.yaml")
        cost_params = build_cost_params(cfg)
        registry = build_variant_registry(cfg)
        vs = registry[0]
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

        fresh = _run_variant(
            vs, pd.DataFrame(), universe, adv_wide,
            _INDUSTRY, 10_000_000.0, cost_params, cfg,
            n_trials=n_trials, build_signals_fn=_fake_build_signals,
        )

        with tempfile.TemporaryDirectory() as tmp:
            save_variant_cache(tmp, "test_key", fresh)
            loaded = load_variant_cache(tmp, "test_key")

            # Simulate the drop-top-3 loop: net_full.reindex(train_dates)
            train_dates = _DATES[:50]
            fresh_net = fresh["net"].reindex(train_dates).dropna()
            loaded_net = loaded["net"].reindex(train_dates).dropna()
            assert len(fresh_net) == len(loaded_net), (
                f"reindex lost dates: fresh={len(fresh_net)}, loaded={len(loaded_net)}"
            )
            pd.testing.assert_series_equal(fresh_net, loaded_net)


# ── CLI overrides in fingerprint ─────────────────────────────────────────────

class TestCLIOverrideFingerprint:
    """compute_cache_fingerprint must change when CLI overrides change."""

    def test_book_capital_changes_fingerprint(self):
        cfg = load_strategy_config("strategies/config.yaml")
        fp1 = compute_cache_fingerprint(
            "abc123", cfg, panel=None,
            effective_overrides={"book_capital": 10_000_000, "factor_model": "ols_mkt_ind", "pca_components": 10},
        )
        fp2 = compute_cache_fingerprint(
            "abc123", cfg, panel=None,
            effective_overrides={"book_capital": 5_000_000, "factor_model": "ols_mkt_ind", "pca_components": 10},
        )
        assert fp1 != fp2, (
            f"fingerprint unchanged after changing book_capital: {fp1}"
        )

    def test_factor_model_changes_fingerprint(self):
        cfg = load_strategy_config("strategies/config.yaml")
        fp1 = compute_cache_fingerprint(
            "abc123", cfg, panel=None,
            effective_overrides={"book_capital": 10_000_000, "factor_model": "ols_mkt_ind", "pca_components": 10},
        )
        fp2 = compute_cache_fingerprint(
            "abc123", cfg, panel=None,
            effective_overrides={"book_capital": 10_000_000, "factor_model": "pca", "pca_components": 10},
        )
        assert fp1 != fp2

    def test_pca_components_changes_fingerprint(self):
        cfg = load_strategy_config("strategies/config.yaml")
        fp1 = compute_cache_fingerprint(
            "abc123", cfg, panel=None,
            effective_overrides={"book_capital": 10_000_000, "factor_model": "pca", "pca_components": 10},
        )
        fp2 = compute_cache_fingerprint(
            "abc123", cfg, panel=None,
            effective_overrides={"book_capital": 10_000_000, "factor_model": "pca", "pca_components": 15},
        )
        assert fp1 != fp2

    def test_no_overrides_unchanged(self):
        """Without effective_overrides, fingerprint is the same as before."""
        cfg = load_strategy_config("strategies/config.yaml")
        fp1 = compute_cache_fingerprint("abc123", cfg, panel=None)
        fp2 = compute_cache_fingerprint("abc123", cfg, panel=None, effective_overrides=None)
        assert fp1 == fp2


# ── Data fingerprint covers dollar_volume ────────────────────────────────────

class TestDataFingerprint:
    """_data_fingerprint must change when dollar_volume changes."""

    def test_dollar_volume_changes_fingerprint(self):
        from strategies.robustness import _data_fingerprint

        dates = pd.bdate_range("2024-01-02", periods=10)
        panel1 = pd.DataFrame({
            "symbol": ["A"] * 10,
            "event_date": dates,
            "close": [100.0] * 10,
            "dollar_volume": [1e6] * 10,
        })
        panel2 = panel1.copy()
        panel2["dollar_volume"] = [2e6] * 10  # doubled

        fp1 = _data_fingerprint(panel1)
        fp2 = _data_fingerprint(panel2)
        assert fp1 != fp2, (
            f"fingerprint unchanged after doubling dollar_volume: {fp1}"
        )

    def test_close_value_change_fingerprint(self):
        from strategies.robustness import _data_fingerprint

        dates = pd.bdate_range("2024-01-02", periods=10)
        panel1 = pd.DataFrame({
            "symbol": ["A"] * 10,
            "event_date": dates,
            "close": [100.0] * 10,
            "dollar_volume": [1e6] * 10,
        })
        panel2 = panel1.copy()
        panel2.loc[0, "close"] = 101.0  # +1
        panel2.loc[1, "close"] = 99.0   # -1 (sum preserved)

        fp1 = _data_fingerprint(panel1)
        fp2 = _data_fingerprint(panel2)
        assert fp1 != fp2, (
            f"fingerprint unchanged after sum-preserving close edit: {fp1}"
        )


# ── Parallel determinism: ALL fields at workers 1/2/4 ────────────────────────

# Module-level shared test data for spawn-safe pool workers (must be created
# once, not inside _run_pool, because _RNG state advances on each call).
_UNIVERSE = pd.DataFrame(
    [(d, s) for d in _DATES for s in _SYMBOLS],
    columns=["trade_date", "symbol"],
)
_UNIVERSE["adv_rank"] = 1
_ADV_WIDE = pd.DataFrame(
    np.abs(np.random.RandomState(99).randn(_N_DAYS, _N_SYM) * 1e7 + 5e7),
    index=_DATES, columns=_SYMBOLS,
)


class TestParallelDeterminismAllFields:
    """Variant results must be identical for ALL fields regardless of worker count.

    Uses the ACTUAL ProcessPoolExecutor with the ``spawn`` start method.
    Tests workers 1, 2, and 4.
    """

    def _run_pool(self, n_workers, subset, cfg, cost_params, n_trials):
        from strategies.robustness_worker import _worker_init, _worker_task

        ctx = multiprocessing.get_context("spawn")
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(
            max_workers=n_workers,
            mp_context=ctx,
            initializer=_worker_init,
            initargs=(
                cfg, pd.DataFrame(), _UNIVERSE, _ADV_WIDE,
                _INDUSTRY, 10_000_000.0, cost_params, None,
                _fake_build_signals,
            ),
        ) as pool:
            futures = [
                pool.submit(_worker_task, (vs, n_trials))
                for vs in subset
            ]
            return [f.result() for f in futures]

    def _assert_results_equal(self, baseline, other, label):
        """Deep-compare two variant results across all fields."""
        for i, (base, comp) in enumerate(zip(baseline, other)):
            if "error" in base or "error" in comp:
                pytest.fail(f"variant {i} errored: base={base.get('error')}, "
                            f"{label}={comp.get('error')}")

            # Compare Series fields.
            for key in ("net", "gross", "turnover"):
                if key in base and isinstance(base[key], pd.Series):
                    pd.testing.assert_series_equal(
                        base[key], comp[key], atol=1e-10,
                        obj=f"variant {i} {key} ({label})",
                    )

            # Compare DataFrame fields.
            for key in ("weights", "s_score", "trade_returns", "residual_returns"):
                if key in base and isinstance(base[key], pd.DataFrame):
                    pd.testing.assert_frame_equal(
                        base[key], comp[key], atol=1e-10,
                        obj=f"variant {i} {key} ({label})",
                    )

            # Compare scalar fields.
            for key in ("variant_id", "fingerprint", "is_sharpe", "oos_sharpe"):
                if key in base:
                    assert base[key] == comp[key], (
                        f"variant {i} {key} mismatch: {base[key]} vs {comp[key]} ({label})"
                    )

    def test_workers_1_2_4(self):
        """Results identical at workers=1, workers=2, and workers=4."""
        cfg = load_strategy_config("strategies/config.yaml")
        cost_params = build_cost_params(cfg)
        registry = build_variant_registry(cfg)
        subset = registry[:4]
        n_trials = len(registry)

        results_w1 = self._run_pool(1, subset, cfg, cost_params, n_trials)
        results_w2 = self._run_pool(2, subset, cfg, cost_params, n_trials)
        results_w4 = self._run_pool(4, subset, cfg, cost_params, n_trials)

        self._assert_results_equal(results_w1, results_w2, "w2")
        self._assert_results_equal(results_w1, results_w4, "w4")