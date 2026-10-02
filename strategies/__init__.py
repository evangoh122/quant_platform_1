"""MFT Strategy Framework — strategies package.

Modules:
    config       – YAML-driven parameter management
    cost_model   – Parameterized transaction cost model
    neutralize   – dollar_neutral, sector_neutral, unit_gross
    data_layer   – Bar loaders from Delta, sector map, liquidity filter
    backtest     – Event-driven / vectorized backtest engine
    report       – Sharpe, drawdown, turnover, per-signal attribution

Signal sub-packages:
    signals.cross_sectional  – Strategy 2: Formulaic alpha basket
    signals.pairs            – Strategy 1: Intraday cointegration pairs
    signals.ml_spread        – Strategy 3: ML-enhanced spread model
"""