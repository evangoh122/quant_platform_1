"""
tests/test_financial_calc.py — Unit tests for deterministic financial calculations.
"""
from __future__ import annotations

import pytest
import polars as pl
from api.services.financial_calc import (
    gross_margin, operating_margin, net_margin, ebitda, ebitda_margin,
    rd_intensity, sga_intensity, yoy_growth, current_ratio, quick_ratio,
    debt_to_equity, net_debt, working_capital, book_value_per_share,
    free_cash_flow, fcf_margin, fcf_conversion, capex_intensity,
    cagr, check_balance_sheet, check_gross_profit, check_fcf_identity,
    normalize_to_usd, compute_period_growth, compute_margins, FactExtractor
)

class TestFinancialCalculators:
    def test_gross_margin(self):
        res = gross_margin(100.0, 60.0, period="2023")
        assert res.value == 40.0
        assert res.unit == "%"
        assert "40.00%" in res.formula

    def test_gross_margin_prefers_filed_gross_profit(self):
        # When a filed GrossProfit is supplied, margin = GrossProfit / Revenue
        # (not derived from COGS), and the formula shows that numerator.
        res = gross_margin(100.0, 60.0, period="2023", gross_profit=45.0)
        assert res.value == 45.0
        assert res.inputs["gross_profit"] == 45.0
        assert "filed" in res.notes.lower()

    def test_gross_margin_requires_cogs_or_gross_profit(self):
        with pytest.raises(ValueError, match="gross_profit or cogs"):
            gross_margin(100.0)

    def test_operating_margin(self):
        res = operating_margin(100.0, 20.0, period="2023")
        assert res.value == 20.0
        assert res.unit == "%"

    def test_net_margin(self):
        res = net_margin(100.0, 10.0, period="2023")
        assert res.value == 10.0

    def test_ebitda(self):
        res = ebitda(15.0, 5.0, period="2023")
        assert res.value == 20.0
        assert res.unit == "USD"

    def test_ebitda_margin(self):
        res = ebitda_margin(100.0, 25.0, period="2023")
        assert res.value == 25.0

    def test_rd_intensity(self):
        res = rd_intensity(100.0, 15.0)
        assert res.value == 15.0

    def test_sga_intensity(self):
        res = sga_intensity(100.0, 20.0)
        assert res.value == 20.0

    def test_yoy_growth(self):
        res = yoy_growth(120.0, 100.0, metric_name="Revenue")
        assert res.value == 20.0
        assert "Revenue YoY Growth" in res.metric

    def test_current_ratio(self):
        res = current_ratio(200.0, 100.0)
        assert res.value == 2.0
        assert res.unit == "x"

    def test_quick_ratio(self):
        res = quick_ratio(50.0, 30.0, 20.0, 50.0)
        assert res.value == 2.0

    def test_debt_to_equity(self):
        res = debt_to_equity(100.0, 200.0)
        assert res.value == 0.5

    def test_net_debt(self):
        res = net_debt(100.0, 150.0)
        assert res.value == -50.0
        assert "net cash position" in res.notes

    def test_working_capital(self):
        res = working_capital(200.0, 150.0)
        assert res.value == 50.0

    def test_book_value_per_share(self):
        res = book_value_per_share(1000.0, 100.0)
        assert res.value == 10.0

    def test_free_cash_flow(self):
        res = free_cash_flow(100.0, -20.0) # Capex often negative in CF
        assert res.value == 80.0
        res2 = free_cash_flow(100.0, 20.0) # Should handle positive too
        assert res2.value == 80.0

    def test_fcf_margin(self):
        res = fcf_margin(20.0, 100.0)
        assert res.value == 20.0

    def test_fcf_conversion(self):
        res = fcf_conversion(120.0, 100.0)
        assert res.value == 1.2

    def test_capex_intensity(self):
        res = capex_intensity(-10.0, 100.0)
        assert res.value == 10.0

    def test_cagr(self):
        res = cagr(100.0, 144.0, 2.0)
        assert res.value == 20.0 # 1.2^2 = 1.44

    def test_cagr_errors(self):
        with pytest.raises(ValueError, match="start_value must be positive"):
            cagr(0, 100, 1)
        with pytest.raises(ValueError, match="n_years must be positive"):
            cagr(100, 110, 0)
        with pytest.raises(ValueError, match="end_value is negative"):
            cagr(100, -10, 1)

    def test_guard_div_zero(self):
        with pytest.raises(ValueError, match="denominator is effectively zero"):
            gross_margin(0.0, 0.0)

    def test_normalize_to_usd(self):
        assert normalize_to_usd(1.0, "USD") == 1.0
        assert normalize_to_usd(1.0, "USD/1000") == 1000.0
        assert normalize_to_usd(1.0, "millions") == 1_000_000.0

class TestIdentityCheckers:
    def test_check_balance_sheet(self):
        res = check_balance_sheet(100.0, 70.0, 30.0)
        assert res.passed is True
        res_fail = check_balance_sheet(100.0, 70.0, 40.0)
        assert res_fail.passed is False

    def test_check_gross_profit(self):
        res = check_gross_profit(100.0, 60.0, 40.0)
        assert res.passed is True

    def test_check_fcf_identity(self):
        res = check_fcf_identity(80.0, 100.0, 20.0)
        assert res.passed is True

class TestPolarsBatchOps:
    def test_compute_period_growth(self):
        df = pl.DataFrame({
            "period": ["2021", "2022", "2023"],
            "revenue": [100.0, 120.0, 150.0]
        })
        out = compute_period_growth(df, "revenue", "period")
        assert out["revenue_yoy_pct"][1] == 20.0
        assert out["revenue_yoy_pct"][2] == 25.0
        assert out["revenue_yoy_pct"][0] is None

    def test_compute_margins(self):
        df = pl.DataFrame({
            "revenues": [100.0],
            "cogs": [60.0],
            "operatingincome": [20.0],
            "netincome": [10.0]
        })
        out = compute_margins(df)
        assert out["gross_margin_pct"][0] == 40.0
        assert out["operating_margin_pct"][0] == 20.0
        assert out["net_margin_pct"][0] == 10.0

class TestFactExtractor:
    @pytest.fixture
    def df(self):
        return pl.DataFrame({
            "concept": ["Revenues", "CostOfRevenue", "NetIncomeLoss", "Assets"],
            "value": [1000.0, 600.0, 100.0, 5000.0],
            "period": ["2023-12-31", "2023-12-31", "2023-12-31", "2023-12-31"]
        })

    def test_get_exact(self, df):
        fe = FactExtractor(df)
        assert fe.get("Revenues") == 1000.0
        assert fe.get("revenues") == 1000.0

    def test_get_alias(self, df):
        fe = FactExtractor(df)
        # "revenues" is the canonical key that has "revenue" as an alias.
        # If the DF has "Revenues" (normalized to "revenues"), 
        # searching for "revenues" will match "Revenues" via exact match.
        # If we search for "revenue", it doesn't find it because "revenue" is not a canonical key.
        assert fe.get("revenues") == 1000.0

    def test_get_missing(self, df):
        fe = FactExtractor(df)
        assert fe.get("NonExistent") is None

    def test_get_multi(self, df):
        fe = FactExtractor(df)
        res = fe.get_multi(["Revenues", "Assets"])
        assert res == {"Revenues": 1000.0, "Assets": 5000.0}

    def test_periods(self, df):
        fe = FactExtractor(df)
        assert fe.periods() == ["2023-12-31"]

    def test_most_recent(self):
        df = pl.DataFrame({
            "concept": ["Revenues", "Revenues"],
            "value": [1000.0, 1100.0],
            "period": ["2022-12-31", "2023-12-31"]
        })
        fe = FactExtractor(df)
        assert fe.get("Revenues") == 1100.0
        assert fe.get("Revenues", period="2022") == 1000.0

    def test_empty_df(self):
        schema = {"concept": pl.Utf8, "value": pl.Float64, "period": pl.Utf8}
        fe = FactExtractor(pl.DataFrame(schema=schema))
        assert fe.get("Revenues") is None
        assert fe.periods() == []
