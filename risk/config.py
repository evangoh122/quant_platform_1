"""Typed configuration for the volatility and risk-sizing layer.

Every numeric or naming knob used by ``risk/`` is read from
``risk/config.yaml``; the dataclasses below are the typed view of that file.
Tests override individual fields with ``dataclasses.replace`` rather than
editing the YAML.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PairColumns:
    """Column names of the long-format pair panel (prices must be adjusted)."""

    date: str
    open_a: str
    close_a: str
    open_b: str
    close_b: str


@dataclass(frozen=True)
class EstimatorParams:
    annualization: int
    return_type: str
    ewma_span: int
    ewma_min_samples: int
    ewma_adjust: bool
    rolling_windows: tuple[int, ...]
    rolling_min_samples: int
    vol_floor: float
    percentile_window: int
    percentile_min_history: int
    overnight_window: int
    intraday_window: int
    epsilon: float


@dataclass(frozen=True)
class SizingParams:
    method: str
    target_vol: float
    max_gross: float
    hedge_clip_low: float
    hedge_clip_high: float
    spread_var_floor: float
    vol_floor: float
    equal_dollar_gross: float
    inverse_vol_gross: float
    signal_cap: float
    default_signal: float
    epsilon: float


@dataclass(frozen=True)
class SignalParams:
    mode: str
    lookback: int


@dataclass(frozen=True)
class CostConfig:
    bps_per_side: tuple[float, ...]
    baseline_bps: float


@dataclass(frozen=True)
class BacktestParams:
    annualization: int
    return_type: str
    sharpe_ddof: int
    borrow_bucket: str
    cost_mode: str
    cost_bps_per_side: float
    book_capital: float
    epsilon: float


@dataclass(frozen=True)
class RegimeParams:
    percentile_window: int
    percentile_min_history: int
    low_threshold: float
    high_threshold: float
    unknown_label: str


@dataclass(frozen=True)
class CompareParams:
    methods: tuple[str, ...]
    oos_fraction: float


@dataclass(frozen=True)
class GarchParams:
    omega: float
    alpha: float
    beta: float
    long_run_vol: float


@dataclass(frozen=True)
class ExperimentParams:
    seed: int
    n_days: int
    start_date: str
    rho: float
    overnight_share: float
    gap_idio_vol: float
    garch_a: GarchParams
    garch_b: GarchParams
    output: str


@dataclass(frozen=True)
class RiskConfig:
    columns: PairColumns
    estimators: EstimatorParams
    sizing: SizingParams
    signals: SignalParams
    costs: CostConfig
    backtest: BacktestParams
    regimes: RegimeParams
    compare: CompareParams
    experiment: ExperimentParams


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise KeyError(f"risk config: missing required key {where}.{key}")
    return mapping[key]


def _garch(raw: dict[str, Any], where: str) -> GarchParams:
    return GarchParams(
        omega=float(_require(raw, "omega", where)),
        alpha=float(_require(raw, "alpha", where)),
        beta=float(_require(raw, "beta", where)),
        long_run_vol=float(_require(raw, "long_run_vol", where)),
    )


def _parse(raw: dict[str, Any]) -> RiskConfig:
    epsilon = float(_require(raw, "epsilon", "risk"))
    columns_raw = _require(raw, "columns", "risk")
    est_raw = _require(raw, "estimators", "risk")
    size_raw = _require(raw, "sizing", "risk")
    signals_raw = _require(raw, "signals", "risk")
    costs_raw = _require(raw, "costs", "risk")
    bt_raw = _require(raw, "backtest", "risk")
    regime_raw = _require(raw, "regimes", "risk")
    compare_raw = _require(raw, "compare", "risk")
    exp_raw = _require(raw, "experiment", "risk")

    columns = PairColumns(
        date=str(_require(columns_raw, "date", "columns")),
        open_a=str(_require(columns_raw, "open_a", "columns")),
        close_a=str(_require(columns_raw, "close_a", "columns")),
        open_b=str(_require(columns_raw, "open_b", "columns")),
        close_b=str(_require(columns_raw, "close_b", "columns")),
    )
    estimators = EstimatorParams(
        annualization=int(_require(raw, "annualization", "risk")),
        return_type=str(_require(est_raw, "return_type", "estimators")),
        ewma_span=int(_require(est_raw, "ewma_span", "estimators")),
        ewma_min_samples=int(_require(est_raw, "ewma_min_samples", "estimators")),
        ewma_adjust=bool(_require(est_raw, "ewma_adjust", "estimators")),
        rolling_windows=tuple(
            int(w) for w in _require(est_raw, "rolling_windows", "estimators")
        ),
        rolling_min_samples=int(_require(est_raw, "rolling_min_samples", "estimators")),
        vol_floor=float(_require(est_raw, "vol_floor", "estimators")),
        percentile_window=int(_require(est_raw, "percentile_window", "estimators")),
        percentile_min_history=int(
            _require(est_raw, "percentile_min_history", "estimators")
        ),
        overnight_window=int(_require(est_raw, "overnight_window", "estimators")),
        intraday_window=int(_require(est_raw, "intraday_window", "estimators")),
        epsilon=epsilon,
    )
    sizing = SizingParams(
        method=str(_require(size_raw, "method", "sizing")),
        target_vol=float(_require(size_raw, "target_vol", "sizing")),
        max_gross=float(_require(size_raw, "max_gross", "sizing")),
        hedge_clip_low=float(_require(size_raw, "hedge_clip_low", "sizing")),
        hedge_clip_high=float(_require(size_raw, "hedge_clip_high", "sizing")),
        spread_var_floor=float(_require(size_raw, "spread_var_floor", "sizing")),
        vol_floor=float(_require(size_raw, "vol_floor", "sizing")),
        equal_dollar_gross=float(_require(size_raw, "equal_dollar_gross", "sizing")),
        inverse_vol_gross=float(_require(size_raw, "inverse_vol_gross", "sizing")),
        signal_cap=float(_require(size_raw, "signal_cap", "sizing")),
        default_signal=float(_require(size_raw, "default_signal", "sizing")),
        epsilon=epsilon,
    )
    signals = SignalParams(
        mode=str(_require(signals_raw, "mode", "signals")),
        lookback=int(_require(signals_raw, "lookback", "signals")),
    )
    costs = CostConfig(
        bps_per_side=tuple(
            float(b) for b in _require(costs_raw, "bps_per_side", "costs")
        ),
        baseline_bps=float(_require(costs_raw, "baseline_bps", "costs")),
    )
    backtest = BacktestParams(
        annualization=int(_require(bt_raw, "annualization", "backtest")),
        return_type=str(_require(bt_raw, "return_type", "backtest")),
        sharpe_ddof=int(_require(bt_raw, "sharpe_ddof", "backtest")),
        borrow_bucket=str(_require(bt_raw, "borrow_bucket", "backtest")),
        cost_mode=str(_require(bt_raw, "cost_mode", "backtest")),
        cost_bps_per_side=float(_require(costs_raw, "baseline_bps", "costs")),
        book_capital=float(_require(bt_raw, "book_capital", "backtest")),
        epsilon=epsilon,
    )
    regimes = RegimeParams(
        percentile_window=int(_require(regime_raw, "percentile_window", "regimes")),
        percentile_min_history=int(
            _require(regime_raw, "percentile_min_history", "regimes")
        ),
        low_threshold=float(_require(regime_raw, "low_threshold", "regimes")),
        high_threshold=float(_require(regime_raw, "high_threshold", "regimes")),
        unknown_label=str(_require(regime_raw, "unknown_label", "regimes")),
    )
    compare = CompareParams(
        methods=tuple(
            str(m) for m in _require(compare_raw, "methods", "compare")
        ),
        oos_fraction=float(_require(compare_raw, "oos_fraction", "compare")),
    )
    experiment = ExperimentParams(
        seed=int(_require(exp_raw, "seed", "experiment")),
        n_days=int(_require(exp_raw, "n_days", "experiment")),
        start_date=str(_require(exp_raw, "start_date", "experiment")),
        rho=float(_require(exp_raw, "rho", "experiment")),
        overnight_share=float(_require(exp_raw, "overnight_share", "experiment")),
        gap_idio_vol=float(_require(exp_raw, "gap_idio_vol", "experiment")),
        garch_a=_garch(_require(exp_raw, "garch_a", "experiment"), "experiment.garch_a"),
        garch_b=_garch(_require(exp_raw, "garch_b", "experiment"), "experiment.garch_b"),
        output=str(_require(exp_raw, "output", "experiment")),
    )
    return RiskConfig(
        columns=columns,
        estimators=estimators,
        sizing=sizing,
        signals=signals,
        costs=costs,
        backtest=backtest,
        regimes=regimes,
        compare=compare,
        experiment=experiment,
    )


@lru_cache(maxsize=8)
def _load_cached(path: str) -> RiskConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"risk config {path}: top level must be a mapping")
    return _parse(raw)


def load_config(path: str | Path | None = None) -> RiskConfig:
    """Load and cache ``risk/config.yaml`` (or an explicit path)."""
    config_path = Path(path) if path is not None else Path(__file__).with_name("config.yaml")
    return _load_cached(str(config_path.resolve()))
