from __future__ import annotations

import math

import pytest

from strategies.report import performance_metrics


# ---------------------------------------------------------------------------
# Hardening fixture: alternating +0.01 / -0.005 repeated 126x => T = 252
# observations.  Every expected value below is a hand-computed literal; the
# arithmetic is shown in the comments and evaluated once here in full double
# precision.
#
#   mu          = (0.01 - 0.005) / 2                    = 0.0025
#   devs        = +-0.0075 (126 each)
#   sum sq dev  = 252 * 0.0075**2                       = 0.014175
#   std (ddof=1)= sqrt(0.014175 / 251)                  = 0.0075149253878969
#   std (ddof=0)= sqrt(0.014175 / 252)                  = 0.0075 (exact)
#   SR_p        = 0.0025 / 0.0075149253878969           = 0.3326713002402331
#   Sharpe      = SR_p * sqrt(252)                      = 5.280993172584953
#   Sharpe(ddof=0) = 0.0025 / 0.0075 * sqrt(252)        = 5.291502622129182
#
#   downside RMS over ALL 252 periods
#     = sqrt(126 * 0.005**2 / 252)                      = 0.0035355339059327377
#   Sortino     = 0.0025 / 0.0035355339059327377 * sqrt(252)
#               = 11.224972160321826
#   (RMS over the 126 negatives only would be 0.005 and give
#    0.0025 / 0.005 * sqrt(252) = 7.937253933193772 — wrong.)
#
#   equity      = (1.01 * 0.995)**126 = 1.00495**126    = 1.862950307211549
#   CAGR        = equity**(1/1) - 1                     = 0.862950307211549
#   max DD      = 0.005 (each -0.005 leg is a new trough after a new peak)
#   Calmar      = 0.862950307211549 / 0.005             = 172.5900614423098
#   (annualized arithmetic return = 0.0025 * 252 = 0.63 would give
#    0.63 / 0.005 = 126.0 — wrong, that is mutation M3.)
#
#   CI (T = 252 = periods_per_year):
#     SE_ann    = sqrt((1 + 0.5 * SR_p**2) / 252) * sqrt(252)
#               = sqrt(1 + 0.5 * 0.3326713002402331**2) = 1.0272950389258988
#     z_0.975   = Phi^-1(0.975)                         = 1.9599639845400536
#     half-wid  = z * SE_ann                            = 2.0134612777914342
# ---------------------------------------------------------------------------
ALT = [0.01, -0.005] * 126

SHARPE = 5.280993172584953
SHARPE_DDOF0 = 5.291502622129182
SORTINO = 11.224972160321826
SORTINO_NEGATIVES_ONLY = 7.937253933193772
CALMAR = 172.5900614423098
CALMAR_ARITHMETIC_ANNUALIZED = 126.0
CI_HALF_WIDTH = 2.0134612777914342


def test_performance_ratios_have_expected_trade_math():
    # min_observations_for_ratios=1: this test pins the trade math on a tiny
    # sample; the sample-sufficiency gate itself is pinned by the tests below.
    returns = [0.02, -0.01, 0.03, -0.01]
    result = performance_metrics(
        returns, periods_per_year=252, min_observations_for_ratios=1
    )

    assert result["profit_factor"] == pytest.approx(2.5)
    assert result["win_rate"] == pytest.approx(0.5)
    assert result["average_win"] == pytest.approx(0.025)
    assert result["average_loss"] == pytest.approx(0.01)
    assert result["payoff_ratio"] == pytest.approx(2.5)
    assert result["max_drawdown"] == pytest.approx(0.01)
    assert result["sharpe_ratio"] > 0
    assert result["sortino_ratio"] > 0
    assert result["calmar_ratio"] > 0


def test_trade_pnls_control_profit_factor_and_win_rate():
    result = performance_metrics(
        [0.001, 0.002, -0.001],
        periods_per_year=252,
        trade_pnls=[100.0, -50.0, 25.0, -25.0],
    )
    assert result["profit_factor"] == pytest.approx(125 / 75)
    assert result["win_rate"] == pytest.approx(0.5)
    assert result["trade_count"] == 4


def test_all_winners_have_infinite_profit_factor():
    result = performance_metrics([0.01, 0.02], periods_per_year=252)
    assert math.isinf(result["profit_factor"])
    assert result["win_rate"] == 1.0


def test_empty_returns_are_reported_as_nan():
    result = performance_metrics([], periods_per_year=252)
    assert math.isnan(result["sharpe_ratio"])
    assert math.isnan(result["profit_factor"])
    assert result["observation_count"] == 0
    assert result["sample_state"] == "insufficient_sample"


def test_invalid_annualization_is_rejected():
    with pytest.raises(ValueError, match="periods_per_year"):
        performance_metrics([0.01], periods_per_year=0)


# ── Hardening: sample gate, CI, annualization transparency ──────────────────


def test_ratio_literals_on_252_observation_fixture():
    result = performance_metrics(ALT, periods_per_year=252)

    assert result["observation_count"] == 252
    assert result["sample_state"] == "ok"
    assert result["periods_per_year"] == 252

    # Sharpe = 0.0025 / sqrt(0.014175/251) * sqrt(252)
    assert result["sharpe_ratio"] == pytest.approx(SHARPE, abs=1e-9)
    # Sortino = 0.0025 / sqrt(126*0.000025/252) * sqrt(252)
    assert result["sortino_ratio"] == pytest.approx(SORTINO, abs=1e-9)
    # Calmar = (1.00495**126 - 1) / 0.005
    assert result["calmar_ratio"] == pytest.approx(CALMAR, abs=1e-9)

    # Non-ratio metrics stay numeric and match the hand math.
    assert result["total_return"] == pytest.approx(0.862950307211549, abs=1e-9)
    assert result["cagr"] == pytest.approx(0.862950307211549, abs=1e-9)
    assert result["max_drawdown"] == pytest.approx(0.005, abs=1e-12)
    assert result["win_rate"] == pytest.approx(0.5)
    assert result["profit_factor"] == pytest.approx(2.0)
    assert result["payoff_ratio"] == pytest.approx(2.0)


def test_short_sample_gates_ratios_but_keeps_other_metrics_numeric():
    short = [0.01, -0.005] * 50  # T = 100 < 252
    result = performance_metrics(short, periods_per_year=252)

    assert result["observation_count"] == 100
    assert result["sample_state"] == "insufficient_sample"

    # The three annualized ratios are NaN below the gate.
    assert math.isnan(result["sharpe_ratio"])
    assert math.isnan(result["sortino_ratio"])
    assert math.isnan(result["calmar_ratio"])
    # CI bounds are NaN when the state is insufficient.
    assert math.isnan(result["sharpe_ci_95_low"])
    assert math.isnan(result["sharpe_ci_95_high"])

    # Everything else stays numeric.
    for key in (
        "total_return",
        "cagr",
        "annualized_volatility",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "payoff_ratio",
    ):
        assert math.isfinite(result[key]), key


def test_sharpe_uses_sample_std_ddof_one():
    result = performance_metrics(ALT, periods_per_year=252)
    sharpe = result["sharpe_ratio"]

    # ddof=1 literal (sqrt(0.014175/251) in the denominator).
    assert sharpe == pytest.approx(SHARPE, abs=1e-9)
    # ddof=0 would use sqrt(0.014175/252) = 0.0075 exactly -> 5.2915...,
    # clearly different from the reported value (mutation M1).
    assert abs(sharpe - SHARPE_DDOF0) > 1e-6


def test_sortino_downside_deviation_is_rms_over_all_periods():
    result = performance_metrics(ALT, periods_per_year=252)
    sortino = result["sortino_ratio"]

    # RMS of min(excess, 0) over ALL 252 periods: sqrt(126*0.000025/252).
    assert sortino == pytest.approx(SORTINO, abs=1e-9)
    # RMS over the negatives only would use sqrt(mean over 126 obs) = 0.005
    # and land on 7.937... — the reported value pins the "over ALL periods"
    # denominator (mutation M2: plain std of the negatives -> 0 -> NaN).
    assert abs(sortino - SORTINO_NEGATIVES_ONLY) > 1e-6


def test_calmar_uses_cagr_not_annualized_arithmetic_return():
    result = performance_metrics(ALT, periods_per_year=252)
    calmar = result["calmar_ratio"]

    # CAGR / maxDD = (1.00495**126 - 1) / 0.005.
    assert calmar == pytest.approx(CALMAR, abs=1e-9)
    # Annualized arithmetic return / maxDD = 0.63 / 0.005 = 126 (mutation M3).
    assert abs(calmar - CALMAR_ARITHMETIC_ANNUALIZED) > 1e-6


def test_sharpe_ci_95_matches_iid_normal_approx_half_width():
    result = performance_metrics(ALT, periods_per_year=252)

    assert result["sharpe_ci_method"] == "iid_normal_approx"
    low = result["sharpe_ci_95_low"]
    high = result["sharpe_ci_95_high"]
    sharpe = result["sharpe_ratio"]
    assert low < sharpe < high

    # half-width = z_0.975 * sqrt((1 + 0.5*SR_p**2)/252) * sqrt(252)
    #            = 1.9599639845400536 * 1.0272950389258988
    #            = 2.0134612777914342
    assert (high - low) / 2.0 == pytest.approx(CI_HALF_WIDTH, abs=1e-12)
    assert high - sharpe == pytest.approx(CI_HALF_WIDTH, abs=1e-12)
    assert sharpe - low == pytest.approx(CI_HALF_WIDTH, abs=1e-12)
