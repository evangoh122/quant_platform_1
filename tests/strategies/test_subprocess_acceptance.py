"""Subprocess acceptance test using a temporary sitecustomize.py that mocks
pyspark.  Verifies that strategies.residual_reversion, strategies.robustness,
strategies.universe, strategies.backtest, and the runner helpers can all be
imported and executed without pyspark."""

import os
import subprocess
import sys
import tempfile
import textwrap

import pytest


def test_subprocess_acceptance():
    """Run a small synthetic OLS/PCA robustness run in a subprocess with
    pyspark mocked out."""
    # Create a temporary sitecustomize.py that mocks pyspark.
    with tempfile.TemporaryDirectory() as tmpdir:
        sitecustomize = os.path.join(tmpdir, "sitecustomize.py")
        with open(sitecustomize, "w") as f:
            f.write(textwrap.dedent("""\
                import sys
                for m in ("pyspark", "pyspark.sql", "pyspark.sql.functions",
                          "pyspark.sql.types"):
                    sys.modules[m] = None
            """))

        # Create the test script.
        test_script = os.path.join(tmpdir, "run_test.py")
        with open(test_script, "w") as f:
            f.write(textwrap.dedent("""\
                import sys
                import os
                # Ensure our sitecustomize.py is found.
                sys.path.insert(0, os.environ["TEST_SITECUSTOMIZE_DIR"])

                import numpy as np
                import pandas as pd

                # Import all required modules.
                from strategies.residual_reversion import (
                    compute_residuals, compute_pca_residuals,
                    generate_signals, compute_daily_returns,
                    compute_industry_factor, load_industry_map,
                )
                from strategies.robustness import (
                    build_variant_registry, evaluate_gates,
                    compute_fold_metrics, compute_margin_bps,
                    compute_rank_ic, compute_exposures,
                    compute_capacity, render_robustness_report,
                )
                from strategies.universe import screen_universe
                from strategies.backtest import run_backtest, compute_costs
                from strategies.cost_model import CostParams

                # Run a small synthetic OLS robustness test.
                dates = pd.date_range("2024-01-01", periods=120, freq="B")
                rng = np.random.default_rng(42)
                n_sym = 20
                symbols = [f"S{i:02d}" for i in range(n_sym)]
                market = pd.Series(rng.normal(0, 0.01, 120), index=dates)
                data = {}
                for s in symbols:
                    data[s] = 1.0 * market.to_numpy() + rng.normal(0, 0.01, 120)
                returns = pd.DataFrame(data, index=dates)

                industry_map = {s: "tech" for s in symbols}
                ind = compute_industry_factor(returns, industry_map)
                res = compute_residuals(returns, market, ind, window=60, lookback=5)
                positions = generate_signals(res["s_score"], entry=2.5,
                                             exit_thresh=0.5, max_hold=5)

                # Run PCA.
                pca_res = compute_pca_residuals(returns, window=60, lookback=5,
                                                n_components=10)
                pca_pos = generate_signals(pca_res["s_score"], entry=2.5,
                                           exit_thresh=0.5, max_hold=5)

                # Verify shapes.
                assert res["s_score"].shape == (120, n_sym)
                assert pca_res["s_score"].shape == (120, n_sym)
                assert positions.shape == (120, n_sym)
                assert pca_pos.shape == (120, n_sym)

                # Verify gate evaluation.
                gates = {"sharpe_min": 1.25, "max_drawdown_max": 0.15,
                         "return_to_dd_min": 1.0, "margin_min_bps": 5.0,
                         "oos_ratio_min": 0.50}
                result = evaluate_gates({"net_sharpe": 1.5, "net_max_drawdown": -0.10,
                                         "net_ann_return": 0.20, "margin_bps": 10.0,
                                         "oos_sharpe": 0.8, "is_sharpe": 1.0}, gates)
                assert result["sharpe_min"] == "PASS"

                print("ALL ACCEPTANCE CHECKS PASSED")
            """))

        env = os.environ.copy()
        env["TEST_SITECUSTOMIZE_DIR"] = tmpdir
        env["PYTHONPATH"] = os.getcwd()

        result = subprocess.run(
            [sys.executable, test_script],
            capture_output=True, text=True, timeout=60, env=env,
        )

        assert result.returncode == 0, (
            f"Subprocess failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "ALL ACCEPTANCE CHECKS PASSED" in result.stdout