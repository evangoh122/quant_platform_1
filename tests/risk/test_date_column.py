"""A configured date column name other than ``date`` must work end to end.

CR-1 of the fix-4 request: every frame entry point either honours
``columns.date`` (``estimate_pair``, ``build_signal``, ``label_regimes``,
``backtest_vol_pair``, ``performance_metrics``, ``compare_sizers``, the
synthetic generator and the CLI) or rejects another name with one clear error
naming that column (``size``, whose public contract is the fixed
``date, w_a, w_b`` frame).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from risk.compare import build_signal, compare_sizers
from risk.config import RiskConfig, load_config
from risk.estimators import estimate_pair
from risk.pair_backtest import backtest_vol_pair, performance_metrics
from risk.regimes import label_regimes
from risk.run_compare import main as run_compare_main
from risk.sizing import size
from risk.synthetic import synthetic_pair_panel

CUSTOM_DATE = "session"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _panel(config: RiskConfig) -> pl.DataFrame:
    return synthetic_pair_panel(
        replace(config.experiment, n_days=320, seed=17),
        config.estimators.annualization,
        config.columns,
    )


def _custom_config() -> RiskConfig:
    cfg = load_config()
    return replace(cfg, columns=replace(cfg.columns, date=CUSTOM_DATE))


def _default_frames(config: RiskConfig):
    panel = _panel(config)
    estimates = estimate_pair(panel, config.estimators, config.columns)
    signal = build_signal(panel, config.signals, config.columns)
    weights = size(signal, estimates, config.sizing)
    result = backtest_vol_pair(
        panel, weights, config.backtest, columns=config.columns
    )
    return panel, estimates, signal, result


def _custom_frames(config: RiskConfig, custom: RiskConfig):
    panel = _panel(custom)
    estimates = estimate_pair(panel, custom.estimators, custom.columns)
    signal = build_signal(panel, custom.signals, custom.columns)
    # ``size`` keeps its fixed date contract: rename only at that boundary.
    weights = size(
        signal.rename({CUSTOM_DATE: "date"}),
        estimates.rename({CUSTOM_DATE: "date"}),
        custom.sizing,
    ).rename({"date": CUSTOM_DATE})
    result = backtest_vol_pair(
        panel, weights, custom.backtest, columns=custom.columns
    )
    return panel, estimates, signal, result


def _back_to_default(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.rename({CUSTOM_DATE: "date"})


@pytest.mark.parametrize(
    "entry",
    [
        "estimate_pair",
        "build_signal",
        "label_regimes",
        "backtest_vol_pair",
        "performance_metrics",
        "compare_sizers",
    ],
)
def test_custom_date_column_matches_the_default_run(entry: str) -> None:
    cfg = load_config()
    custom = _custom_config()
    d_panel, d_est, d_sig, d_result = _default_frames(cfg)
    c_panel, c_est, c_sig, c_result = _custom_frames(cfg, custom)
    assert c_panel.columns[0] == CUSTOM_DATE

    if entry == "estimate_pair":
        assert_frame_equal(_back_to_default(c_est), d_est, check_exact=True)
    elif entry == "build_signal":
        assert_frame_equal(_back_to_default(c_sig), d_sig, check_exact=True)
    elif entry == "label_regimes":
        c_reg = label_regimes(c_est, custom.regimes)
        d_reg = label_regimes(d_est, cfg.regimes)
        assert_frame_equal(_back_to_default(c_reg), d_reg, check_exact=True)
        assert set(c_reg["regime"].unique().to_list()) <= {
            "low",
            "mid",
            "high",
            "unknown",
        }
    elif entry == "backtest_vol_pair":
        assert_frame_equal(
            _back_to_default(c_result.daily), d_result.daily, check_exact=True
        )
        assert c_result.metrics == d_result.metrics
    elif entry == "performance_metrics":
        assert performance_metrics(
            c_result.daily, custom.backtest
        ) == performance_metrics(d_result.daily, cfg.backtest)
    else:
        assert_frame_equal(
            compare_sizers(c_panel, custom, cost_levels=(10.0,)),
            compare_sizers(d_panel, cfg, cost_levels=(10.0,)),
            check_exact=True,
        )


def test_compare_sizers_accepts_a_custom_named_signal_frame() -> None:
    cfg = load_config()
    custom = _custom_config()
    d_panel, _, d_sig, _ = _default_frames(cfg)
    c_panel, _, c_sig, _ = _custom_frames(cfg, custom)
    assert_frame_equal(
        compare_sizers(c_panel, custom, signals=c_sig, cost_levels=(5.0,)),
        compare_sizers(d_panel, cfg, signals=d_sig, cost_levels=(5.0,)),
        check_exact=True,
    )


def test_fully_renamed_columns_match_the_default_run() -> None:
    """Every price column takes its name from the config, not from literals."""
    cfg = load_config()
    renamed = replace(
        cfg,
        columns=replace(
            cfg.columns,
            date=CUSTOM_DATE,
            open_a="oa",
            close_a="ca",
            open_b="ob",
            close_b="cb",
        ),
    )
    assert_frame_equal(
        compare_sizers(_panel(renamed), renamed, cost_levels=(10.0,)),
        compare_sizers(_panel(cfg), cfg, cost_levels=(10.0,)),
        check_exact=True,
    )


def test_size_rejects_a_custom_date_column_with_a_clear_error() -> None:
    cfg = load_config()
    custom = _custom_config()
    _, c_est, c_sig, _ = _custom_frames(cfg, custom)

    with pytest.raises(KeyError) as estimates_error:
        size(c_sig, c_est, custom.sizing)
    message = str(estimates_error.value)
    assert "estimates missing columns: ['date']" in message
    assert CUSTOM_DATE in message
    assert "rename it to 'date'" in message

    _, d_est, _, _ = _default_frames(cfg)
    with pytest.raises(KeyError) as signal_error:
        size(c_sig, d_est, custom.sizing)
    message = str(signal_error.value)
    assert "signal_or_pair missing columns: ['date']" in message
    assert CUSTOM_DATE in message


def test_synthetic_panel_uses_the_configured_column_names() -> None:
    cfg = load_config()
    renamed = replace(
        cfg,
        columns=replace(
            cfg.columns,
            date=CUSTOM_DATE,
            open_a="oa",
            close_a="ca",
            open_b="ob",
            close_b="cb",
        ),
    )
    panel = _panel(renamed)
    assert panel.columns == [CUSTOM_DATE, "oa", "ca", "ob", "cb"]
    assert panel.schema[CUSTOM_DATE] == pl.Date


def test_run_compare_honours_a_custom_date_column(tmp_path: Path) -> None:
    source = REPO_ROOT / "risk" / "config.yaml"
    text = source.read_text(encoding="utf-8")
    assert "  date: date\n" in text
    candidate = tmp_path / "config_session.yaml"
    candidate.write_text(
        text.replace("  date: date\n", f"  date: {CUSTOM_DATE}\n"),
        encoding="utf-8",
    )
    output = tmp_path / "p1_compare.md"
    assert run_compare_main(["--config", str(candidate), "--out", str(output)]) == 0
    committed = (
        REPO_ROOT / "risk" / "results" / "p1_compare.md"
    ).read_text(encoding="utf-8")
    assert output.read_text(encoding="utf-8") == committed
