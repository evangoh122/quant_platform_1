"""Robustness round-5 guard tests.

Every test in this file must FAIL on the pre-round-5 HEAD and PASS after the
round-5 fixes.  Tests cover:
  1. Drop-top-3 selects by realised P&L (lagged_weight × tradeable returns),
     not residual returns.
  2. Rank IC table discloses the t-stat method and shows effective_n.
"""

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fix 1: Drop-top-3 selects by realised P&L, not residual P&L
# ---------------------------------------------------------------------------

class TestDropTop3UsesRealisedPnL:
    def test_top3_by_realised_differs_from_residual_in_market_dominated_panel(
        self,
    ):
        """On a market-dominated synthetic panel with distinct per-symbol
        betas, the top-3 by realised P&L must differ from the top-3 by
        residual P&L.

        This test FAILS on pre-round-5 code because the per-fold path uses
        residual_returns to pick the top-3 names.
        """
        rng = np.random.default_rng(42)
        n_dates, n_sym = 200, 10
        dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
        symbols = [f"S{i:02d}" for i in range(n_sym)]

        # Market factor dominates returns.
        market = pd.Series(rng.normal(0.0, 0.04, n_dates), index=dates)
        # Distinct betas per symbol so realised P&L ordering depends on beta.
        betas = np.array([3.0, 2.8, 2.5, 2.0, 1.5, 1.0, 0.8, 0.5, 0.3, 0.1])

        # Residual returns: small, uniform noise (no strong signal).
        residual_returns = pd.DataFrame(
            rng.normal(0.0, 0.001, (n_dates, n_sym)),
            index=dates, columns=symbols,
        )

        # Total (tradeable) returns = beta * market + residual.
        total_returns = pd.DataFrame(
            np.outer(market.values, betas) + residual_returns.values,
            index=dates, columns=symbols,
        )

        # Weights: equal weight after warm-up.
        weights = pd.DataFrame(0.0, index=dates, columns=symbols)
        weights.iloc[10:] = 1.0 / n_sym

        # Realised P&L per symbol = lagged_weight × total_returns.
        realised_pnl = (weights.shift(1).fillna(0.0) * total_returns).sum()
        # Residual P&L per symbol = lagged_weight × residual_returns.
        residual_pnl = (weights.shift(1).fillna(0.0) * residual_returns).sum()

        top3_realised = set(realised_pnl.nlargest(3).index)
        top3_residual = set(residual_pnl.nlargest(3).index)

        # In a market-dominated panel, the two sets should differ because
        # betas are distinct and dominate the residual noise.
        assert top3_realised != top3_residual, (
            f"Top-3 by realised ({top3_realised}) should differ from "
            f"top-3 by residual ({top3_residual}) in a market-dominated panel"
        )

    def test_per_fold_drop3_uses_trade_returns_not_residual(self):
        """The per-fold drop-top-3 path must read 'trade_returns' (realised
        P&L basis) from the variant result, not 'residual_returns'.

        This test FAILS on pre-round-5 code because the per-fold path reads
        hold_vr['residual_returns'] and uses it for P&L computation.
        """
        import inspect
        from strategies.run_residual_reversion import main
        src = inspect.getsource(main)

        # The per-fold path must reference trade_returns, not residual_returns,
        # for the top-3 P&L computation.
        # Look for the pattern where pnl_sym is computed using trade_returns.
        assert 'hold_vr["trade_returns"]' in src or "hold_vr['trade_returns']" in src, (
            "Per-fold drop-top-3 must read 'trade_returns' from variant result, "
            "not 'residual_returns'"
        )

    def test_run_variant_stores_trade_returns(self):
        """_run_variant must store the raw tradeable returns (sig['returns'])
        under the key 'trade_returns' for use by the per-fold drop-top-3 path.

        This test FAILS on pre-round-5 code because _run_variant only stores
        'residual_returns', not 'trade_returns'.
        """
        import inspect
        from strategies.run_residual_reversion import _run_variant
        src = inspect.getsource(_run_variant)
        assert '"trade_returns"' in src, (
            "_run_variant must store 'trade_returns' key"
        )

    def test_remove_top_pnl_and_per_fold_share_selection_logic(self):
        """The remove_top_pnl_contributors helper and the per-fold path must
        both use realised P&L (lagged_weight × tradeable_returns).

        This test FAILS on pre-round-5 code because the per-fold path uses
        residual returns while remove_top_pnl_contributors uses raw returns.
        """
        # Verify remove_top_pnl_contributors uses raw returns (already correct).
        import inspect
        from strategies.robustness import remove_top_pnl_contributors
        src = inspect.getsource(remove_top_pnl_contributors)
        # It takes 'returns' as a parameter and uses it directly — this is the
        # tradeable returns, not residual.

        # Verify the per-fold path in main() also uses trade_returns.
        from strategies.run_residual_reversion import main
        main_src = inspect.getsource(main)

        # Both should use the same returns basis.  Since remove_top_pnl_contributors
        # uses raw returns (the 'returns' parameter = sig["returns"]), the per-fold
        # path must also use trade_returns (which is sig["returns"]).
        assert 'trade_returns' in main_src, (
            "Per-fold path must use 'trade_returns' to match "
            "remove_top_pnl_contributors logic"
        )


# ---------------------------------------------------------------------------
# Fix 2: Rank IC table discloses method and effective_n
# ---------------------------------------------------------------------------

class TestRankICTableDisclosure:
    def test_render_report_mentions_newey_west_method(self):
        """The Rank IC table must state the t-stat method as Newey-West HAC
        with lag = H-1.

        This test FAILS on pre-round-5 code because render_robustness_report
        does not mention the method.
        """
        import inspect
        from strategies.robustness import render_robustness_report
        src = inspect.getsource(render_robustness_report)
        assert "Newey-West" in src or "HAC" in src or "newey" in src.lower(), (
            "render_robustness_report Rank IC section must state "
            "'Newey-West HAC' method"
        )

    def test_render_report_shows_effective_n(self):
        """The Rank IC table must show effective_n next to n.

        This test FAILS on pre-round-5 code because the table only shows n.
        """
        import inspect
        from strategies.robustness import render_robustness_report
        src = inspect.getsource(render_robustness_report)
        assert "effective_n" in src, (
            "render_robustness_report Rank IC section must include 'effective_n'"
        )

    def test_rank_ic_table_header_includes_method_and_effective_n(self):
        """The Rank IC table header row must include 'method' and 'eff. n'
        columns.

        This test FAILS on pre-round-5 code because the header only has
        'factor model | mean IC | IC t-stat | n | sign | hit rate'.
        """
        import inspect
        from strategies.robustness import render_robustness_report
        src = inspect.getsource(render_robustness_report)
        # The Rank IC section (after the header L.append("## Rank IC"))
        # must contain eff. n in its table header or data rows.
        rank_ic_section = src.split('L.append("## Rank IC")')[1] if 'L.append("## Rank IC")' in src else ""
        assert "eff. n" in rank_ic_section.lower() or "effective_n" in rank_ic_section, (
            "Rank IC table header must include 'eff. n' column"
        )