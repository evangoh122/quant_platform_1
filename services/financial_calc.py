"""
api/services/financial_calc.py
Deterministic financial statement calculations using Polars.

Design contract:
  - AI retrieves raw XBRL values (context retrieval — AI strength).
  - THIS module calculates (arithmetic — AI weakness, Python strength).
  - Every function returns a CalcResult with a full audit trail so the
    AI can cite the formula and inputs without recalculating.
  - All monetary inputs are expected in raw USD (not millions or billions).
    Use normalize_to_usd() first if the XBRL unit is "USD/shares" or scaled.

Public surface:
  Scalar calculators   — income statement, balance sheet, cash flow, valuation
  Identity checkers    — verify accounting relationships hold (for XBRL QA)
  Polars batch ops     — period-over-period growth, trailing metrics, fact extraction
  FactExtractor        — fuzzy lookup of XBRL concepts from a Polars DataFrame
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional
import polars as pl

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CalcResult:
    """Full audit record for a single financial calculation."""
    metric: str
    value: float
    formula: str          # human-readable, e.g. "GrossMargin = (383.3B - 210.6B) / 383.3B"
    inputs: dict[str, float]
    unit: str             # "%" | "USD" | "ratio" | "x" | "USD/share" | "shares"
    period: str
    notes: str = ""

    def display(self) -> str:
        """One-line display string for the AI to cite verbatim."""
        val = f"{self.value:.1f}%" if self.unit == "%" else (
              f"{self.value:+.1f}pp" if self.unit == "pp" else
              f"${self.value:,.0f}" if self.unit == "USD" else
              f"{self.value:.2f}x" if self.unit == "x" else
              f"{self.value:.4f}" )
        return f"{self.metric} ({self.period}): {val} | formula: {self.formula}"


@dataclass
class IdentityResult:
    """Result of an accounting identity check."""
    identity: str
    passed: bool
    lhs: float
    rhs: float
    delta_pct: float
    tolerance_pct: float
    note: str = ""

    @property
    def verdict(self) -> str:
        return "PASS" if self.passed else "FAIL"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BILLION = 1_000_000_000.0
_MILLION = 1_000_000.0


def _fmt(v: float) -> str:
    """Format a raw USD value as a compact string for formula display."""
    abs_v = abs(v)
    if abs_v >= _BILLION:
        return f"{v / _BILLION:.3f}B"
    if abs_v >= _MILLION:
        return f"{v / _MILLION:.1f}M"
    return f"{v:,.0f}"


def _guard_div(numerator: float, denominator: float, metric: str) -> float:
    # abs_tol=1.0: catches near-zero USD values (< $1) as well as exact zero
    if math.isclose(denominator, 0.0, abs_tol=1.0):
        raise ValueError(f"{metric}: denominator is effectively zero ({denominator}) — cannot divide.")
    return numerator / denominator


def normalize_to_usd(value: float, unit: str) -> float:
    """
    Normalize XBRL unit-scaled values to raw USD.

    XBRL sometimes reports in thousands ('USD/1000') or as millions.
    Pass the raw value and its unit string; get back raw USD.
    """
    unit_lower = unit.lower()
    if "1000" in unit_lower or unit_lower in ("usd/1000", "thousands"):
        return value * 1_000.0
    if "1000000" in unit_lower or unit_lower in ("usd/1000000", "millions"):
        return value * 1_000_000.0
    return value  # already raw USD

# ---------------------------------------------------------------------------
# Income Statement Calculators
# ---------------------------------------------------------------------------

def gross_margin(
    revenue: float,
    cogs: Optional[float] = None,
    period: str = "",
    *,
    gross_profit: Optional[float] = None,
) -> CalcResult:
    """Gross Margin % = Gross Profit / Revenue * 100.

    Prefers a directly-filed ``gross_profit`` (the company's own XBRL GrossProfit
    tag) when provided — most faithful to the filing. Otherwise derives gross
    profit as Revenue - COGS. Exactly one of ``cogs`` or ``gross_profit`` is
    required; the formula string reflects which path was taken so the audit
    trail shows the real numerator and denominator.
    """
    if gross_profit is None:
        if cogs is None:
            raise ValueError("gross_margin: provide either gross_profit or cogs")
        gross_profit = revenue - cogs
        pct = _guard_div(gross_profit, revenue, "gross_margin") * 100
        formula = f"({_fmt(revenue)} - {_fmt(cogs)}) / {_fmt(revenue)} = {pct:.2f}%"
        notes = ""
    else:
        pct = _guard_div(gross_profit, revenue, "gross_margin") * 100
        formula = f"{_fmt(gross_profit)} / {_fmt(revenue)} = {pct:.2f}%"
        notes = "Gross profit taken directly from the filed XBRL GrossProfit tag"

    inputs: dict[str, float] = {"revenue": revenue, "gross_profit": gross_profit}
    if cogs is not None:
        inputs["cogs"] = cogs

    return CalcResult(
        metric="Gross Margin",
        value=round(pct, 4),
        formula=formula,
        inputs=inputs,
        unit="%",
        period=period,
        notes=notes,
    )


def gross_margin_growth(
    current_revenue: float,
    current_cogs: float,
    prior_revenue: float,
    prior_cogs: float,
    current_period: str = "",
    prior_period: str = "",
) -> CalcResult:
    """Gross Margin Growth (percentage points) = Current Gross Margin - Prior Gross Margin."""
    current_gm = _guard_div(current_revenue - current_cogs, current_revenue, "gross_margin_growth_current") * 100
    prior_gm = _guard_div(prior_revenue - prior_cogs, prior_revenue, "gross_margin_growth_prior") * 100
    delta = round(current_gm - prior_gm, 4)
    period = f"{prior_period} -> {current_period}" if prior_period else current_period
    return CalcResult(
        metric="Gross Margin Growth",
        value=delta,
        formula=(
            f"[({_fmt(current_revenue)} - {_fmt(current_cogs)}) / {_fmt(current_revenue)}] "
            f"- [({_fmt(prior_revenue)} - {_fmt(prior_cogs)}) / {_fmt(prior_revenue)}] "
            f"= {current_gm:.2f}% - {prior_gm:.2f}% = {delta:+.2f}pp"
        ),
        inputs={
            "current_revenue": current_revenue, "current_cogs": current_cogs,
            "prior_revenue": prior_revenue, "prior_cogs": prior_cogs,
            "current_gross_margin_pct": current_gm, "prior_gross_margin_pct": prior_gm,
        },
        unit="pp",
        period=period,
        notes="Change in gross margin percentage points year-over-year",
    )


def operating_margin(revenue: float, operating_income: float, period: str = "") -> CalcResult:
    """Operating Margin % = Operating Income / Revenue * 100"""
    pct = _guard_div(operating_income, revenue, "operating_margin") * 100
    return CalcResult(
        metric="Operating Margin",
        value=round(pct, 4),
        formula=f"{_fmt(operating_income)} / {_fmt(revenue)} = {pct:.2f}%",
        inputs={"revenue": revenue, "operating_income": operating_income},
        unit="%",
        period=period,
    )


def net_margin(revenue: float, net_income: float, period: str = "") -> CalcResult:
    """Net Margin % = Net Income / Revenue * 100"""
    pct = _guard_div(net_income, revenue, "net_margin") * 100
    return CalcResult(
        metric="Net Margin",
        value=round(pct, 4),
        formula=f"{_fmt(net_income)} / {_fmt(revenue)} = {pct:.2f}%",
        inputs={"revenue": revenue, "net_income": net_income},
        unit="%",
        period=period,
    )


def ebitda(
    operating_income: float,
    depreciation_amortization: float,
    period: str = "",
) -> CalcResult:
    """EBITDA = Operating Income + D&A  (approximation from GAAP components)"""
    val = operating_income + depreciation_amortization
    return CalcResult(
        metric="EBITDA (approx.)",
        value=round(val, 2),
        formula=f"{_fmt(operating_income)} + {_fmt(depreciation_amortization)} = {_fmt(val)}",
        inputs={"operating_income": operating_income, "da": depreciation_amortization},
        unit="USD",
        period=period,
        notes="GAAP approximation; excludes stock-based comp and one-time items",
    )


def ebitda_margin(revenue: float, ebitda_value: float, period: str = "") -> CalcResult:
    """EBITDA Margin % = EBITDA / Revenue * 100"""
    pct = _guard_div(ebitda_value, revenue, "ebitda_margin") * 100
    return CalcResult(
        metric="EBITDA Margin",
        value=round(pct, 4),
        formula=f"{_fmt(ebitda_value)} / {_fmt(revenue)} = {pct:.2f}%",
        inputs={"revenue": revenue, "ebitda": ebitda_value},
        unit="%",
        period=period,
    )


def rd_intensity(revenue: float, rd_expense: float, period: str = "") -> CalcResult:
    """R&D Intensity % = R&D Expense / Revenue * 100"""
    pct = _guard_div(rd_expense, revenue, "rd_intensity") * 100
    return CalcResult(
        metric="R&D Intensity",
        value=round(pct, 4),
        formula=f"{_fmt(rd_expense)} / {_fmt(revenue)} = {pct:.2f}%",
        inputs={"revenue": revenue, "rd_expense": rd_expense},
        unit="%",
        period=period,
    )


def sga_intensity(revenue: float, sga: float, period: str = "") -> CalcResult:
    """SG&A Intensity % = SG&A / Revenue * 100"""
    pct = _guard_div(sga, revenue, "sga_intensity") * 100
    return CalcResult(
        metric="SG&A Intensity",
        value=round(pct, 4),
        formula=f"{_fmt(sga)} / {_fmt(revenue)} = {pct:.2f}%",
        inputs={"revenue": revenue, "sga": sga},
        unit="%",
        period=period,
    )


def yoy_growth(
    current: float,
    prior: float,
    metric_name: str = "Revenue",
    current_period: str = "",
    prior_period: str = "",
) -> CalcResult:
    """Year-over-Year Growth % = (Current - Prior) / |Prior| * 100"""
    pct = _guard_div(current - prior, abs(prior), "yoy_growth") * 100
    period = f"{prior_period} -> {current_period}" if prior_period else current_period
    return CalcResult(
        metric=f"{metric_name} YoY Growth",
        value=round(pct, 4),
        formula=f"({_fmt(current)} - {_fmt(prior)}) / |{_fmt(prior)}| = {pct:.2f}%",
        inputs={"current": current, "prior": prior},
        unit="%",
        period=period,
    )

# ---------------------------------------------------------------------------
# Balance Sheet Calculators
# ---------------------------------------------------------------------------

def current_ratio(
    current_assets: float, current_liabilities: float, period: str = ""
) -> CalcResult:
    """Current Ratio = Current Assets / Current Liabilities"""
    val = _guard_div(current_assets, current_liabilities, "current_ratio")
    return CalcResult(
        metric="Current Ratio",
        value=round(val, 4),
        formula=f"{_fmt(current_assets)} / {_fmt(current_liabilities)} = {val:.2f}x",
        inputs={"current_assets": current_assets, "current_liabilities": current_liabilities},
        unit="x",
        period=period,
        notes=">1.0 generally healthy; <1.0 may signal liquidity pressure",
    )


def quick_ratio(
    cash: float,
    short_term_investments: float,
    receivables: float,
    current_liabilities: float,
    period: str = "",
) -> CalcResult:
    """Quick Ratio = (Cash + ST Investments + Receivables) / Current Liabilities"""
    liquid = cash + short_term_investments + receivables
    val = _guard_div(liquid, current_liabilities, "quick_ratio")
    return CalcResult(
        metric="Quick Ratio",
        value=round(val, 4),
        formula=(f"({_fmt(cash)} + {_fmt(short_term_investments)} + {_fmt(receivables)}) "
                 f"/ {_fmt(current_liabilities)} = {val:.2f}x"),
        inputs={"cash": cash, "st_investments": short_term_investments,
                "receivables": receivables, "current_liabilities": current_liabilities},
        unit="x",
        period=period,
        notes="Excludes inventory from current assets",
    )


def debt_to_equity(
    total_debt: float, shareholders_equity: float, period: str = ""
) -> CalcResult:
    """Debt-to-Equity = Total Debt / Shareholders' Equity"""
    val = _guard_div(total_debt, shareholders_equity, "debt_to_equity")
    return CalcResult(
        metric="Debt / Equity",
        value=round(val, 4),
        formula=f"{_fmt(total_debt)} / {_fmt(shareholders_equity)} = {val:.2f}x",
        inputs={"total_debt": total_debt, "shareholders_equity": shareholders_equity},
        unit="x",
        period=period,
        notes="Total debt = short-term + long-term debt (excludes operating liabilities)",
    )


def net_debt(
    total_debt: float, cash_and_equivalents: float, period: str = ""
) -> CalcResult:
    """Net Debt = Total Debt - Cash & Equivalents"""
    val = total_debt - cash_and_equivalents
    sign = "net cash position" if val < 0 else "net debt"
    return CalcResult(
        metric="Net Debt",
        value=round(val, 2),
        formula=f"{_fmt(total_debt)} - {_fmt(cash_and_equivalents)} = {_fmt(val)}",
        inputs={"total_debt": total_debt, "cash": cash_and_equivalents},
        unit="USD",
        period=period,
        notes=f"Negative = {sign}",
    )


def net_debt_to_ebitda(
    net_debt_value: float, ebitda_value: float, period: str = ""
) -> CalcResult:
    """Net Debt / EBITDA leverage ratio"""
    val = _guard_div(net_debt_value, ebitda_value, "net_debt_to_ebitda")
    return CalcResult(
        metric="Net Debt / EBITDA",
        value=round(val, 4),
        formula=f"{_fmt(net_debt_value)} / {_fmt(ebitda_value)} = {val:.2f}x",
        inputs={"net_debt": net_debt_value, "ebitda": ebitda_value},
        unit="x",
        period=period,
        notes="<2x typically conservative; >4x elevated leverage",
    )


def working_capital(
    current_assets: float, current_liabilities: float, period: str = ""
) -> CalcResult:
    """Working Capital = Current Assets - Current Liabilities"""
    val = current_assets - current_liabilities
    return CalcResult(
        metric="Working Capital",
        value=round(val, 2),
        formula=f"{_fmt(current_assets)} - {_fmt(current_liabilities)} = {_fmt(val)}",
        inputs={"current_assets": current_assets, "current_liabilities": current_liabilities},
        unit="USD",
        period=period,
    )


def book_value_per_share(
    equity: float, shares_outstanding: float, period: str = ""
) -> CalcResult:
    """Book Value Per Share = Equity / Shares Outstanding"""
    val = _guard_div(equity, shares_outstanding, "book_value_per_share")
    return CalcResult(
        metric="Book Value Per Share",
        value=round(val, 4),
        formula=f"{_fmt(equity)} / {shares_outstanding:,.0f} shares = ${val:.2f}",
        inputs={"equity": equity, "shares_outstanding": shares_outstanding},
        unit="USD/share",
        period=period,
    )

# ---------------------------------------------------------------------------
# Cash Flow Calculators
# ---------------------------------------------------------------------------

def free_cash_flow(
    operating_cash_flow: float, capital_expenditures: float, period: str = ""
) -> CalcResult:
    """Free Cash Flow = Operating Cash Flow - Capital Expenditures"""
    # capex is typically reported as negative in cash flow statements
    capex_abs = abs(capital_expenditures)
    val = operating_cash_flow - capex_abs
    return CalcResult(
        metric="Free Cash Flow",
        value=round(val, 2),
        formula=f"{_fmt(operating_cash_flow)} - {_fmt(capex_abs)} = {_fmt(val)}",
        inputs={"operating_cf": operating_cash_flow, "capex": capex_abs},
        unit="USD",
        period=period,
        notes="Capex sign normalized to positive (subtracted from operating CF)",
    )


def fcf_margin(
    fcf_value: float, revenue: float, period: str = ""
) -> CalcResult:
    """FCF Margin % = Free Cash Flow / Revenue * 100"""
    pct = _guard_div(fcf_value, revenue, "fcf_margin") * 100
    return CalcResult(
        metric="FCF Margin",
        value=round(pct, 4),
        formula=f"{_fmt(fcf_value)} / {_fmt(revenue)} = {pct:.2f}%",
        inputs={"fcf": fcf_value, "revenue": revenue},
        unit="%",
        period=period,
    )


def fcf_conversion(
    fcf_value: float, net_income: float, period: str = ""
) -> CalcResult:
    """FCF Conversion = Free Cash Flow / Net Income (quality signal)"""
    val = _guard_div(fcf_value, net_income, "fcf_conversion")
    return CalcResult(
        metric="FCF Conversion",
        value=round(val, 4),
        formula=f"{_fmt(fcf_value)} / {_fmt(net_income)} = {val:.2f}x",
        inputs={"fcf": fcf_value, "net_income": net_income},
        unit="x",
        period=period,
        notes=">1.0 means cash earnings exceed accounting earnings (quality signal)",
    )


def capex_intensity(
    capital_expenditures: float, revenue: float, period: str = ""
) -> CalcResult:
    """Capex Intensity % = Capex / Revenue * 100"""
    capex_abs = abs(capital_expenditures)
    pct = _guard_div(capex_abs, revenue, "capex_intensity") * 100
    return CalcResult(
        metric="Capex Intensity",
        value=round(pct, 4),
        formula=f"{_fmt(capex_abs)} / {_fmt(revenue)} = {pct:.2f}%",
        inputs={"capex": capex_abs, "revenue": revenue},
        unit="%",
        period=period,
    )

# ---------------------------------------------------------------------------
# Multi-period / CAGR
# ---------------------------------------------------------------------------

def cagr(
    start_value: float,
    end_value: float,
    n_years: float,
    metric_name: str = "Revenue",
    start_period: str = "",
    end_period: str = "",
) -> CalcResult:
    """Compound Annual Growth Rate = (end/start)^(1/n) - 1"""
    if start_value <= 0:
        raise ValueError("cagr: start_value must be positive")
    if n_years <= 0:
        raise ValueError("cagr: n_years must be positive")
    if end_value < 0:
        raise ValueError(
            "cagr: end_value is negative — CAGR is undefined when the terminal value crosses zero. "
            "Use yoy_growth() for single-period changes that cross zero instead."
        )
    val = (end_value / start_value) ** (1 / n_years) - 1
    pct = val * 100
    period = f"{start_period} to {end_period}" if start_period else ""
    return CalcResult(
        metric=f"{metric_name} CAGR ({n_years:.0f}yr)",
        value=round(pct, 4),
        formula=(f"({_fmt(end_value)} / {_fmt(start_value)})^(1/{n_years:.0f}) - 1 "
                 f"= {pct:.2f}%"),
        inputs={"start": start_value, "end": end_value, "n_years": n_years},
        unit="%",
        period=period,
    )

# ---------------------------------------------------------------------------
# Accounting Identity Checkers (for XBRL verification)
# ---------------------------------------------------------------------------

def check_balance_sheet(
    assets: float,
    liabilities: float,
    equity: float,
    tolerance_pct: float = 1.0,
    period: str = "",
) -> IdentityResult:
    """Assets = Liabilities + Equity"""
    lhs = assets
    rhs = liabilities + equity
    delta_pct = abs(lhs - rhs) / max(abs(lhs), 1.0) * 100
    return IdentityResult(
        identity="Assets = Liabilities + Equity",
        passed=delta_pct <= tolerance_pct,
        lhs=lhs,
        rhs=rhs,
        delta_pct=round(delta_pct, 4),
        tolerance_pct=tolerance_pct,
        note=f"delta={_fmt(lhs - rhs)} ({delta_pct:.2f}%)  period={period}",
    )


def check_gross_profit(
    revenue: float,
    cogs: float,
    stated_gross_profit: float,
    tolerance_pct: float = 1.0,
    period: str = "",
) -> IdentityResult:
    """Gross Profit = Revenue - COGS"""
    derived = revenue - cogs
    delta_pct = abs(derived - stated_gross_profit) / max(abs(stated_gross_profit), 1.0) * 100
    return IdentityResult(
        identity="Gross Profit = Revenue - COGS",
        passed=delta_pct <= tolerance_pct,
        lhs=derived,
        rhs=stated_gross_profit,
        delta_pct=round(delta_pct, 4),
        tolerance_pct=tolerance_pct,
        note=f"derived={_fmt(derived)} stated={_fmt(stated_gross_profit)}  period={period}",
    )


def check_fcf_identity(
    stated_fcf: float,
    operating_cf: float,
    capex: float,
    tolerance_pct: float = 1.0,
    period: str = "",
) -> IdentityResult:
    """FCF = Operating CF - |Capex|"""
    derived = operating_cf - abs(capex)
    delta_pct = abs(derived - stated_fcf) / max(abs(stated_fcf), 1.0) * 100
    return IdentityResult(
        identity="FCF = Operating CF - Capex",
        passed=delta_pct <= tolerance_pct,
        lhs=derived,
        rhs=stated_fcf,
        delta_pct=round(delta_pct, 4),
        tolerance_pct=tolerance_pct,
        note=f"derived={_fmt(derived)} stated={_fmt(stated_fcf)}  period={period}",
    )

# ---------------------------------------------------------------------------
# Polars Batch Operations
# ---------------------------------------------------------------------------

def compute_period_growth(
    df: pl.DataFrame,
    value_col: str,
    period_col: str,
    group_col: Optional[str] = None,
) -> pl.DataFrame:
    """
    Add a `{value_col}_yoy_pct` column containing YoY % change.
    Sorts by period_col before computing shift.
    """
    sort_cols = ([group_col, period_col] if group_col else [period_col])
    out = df.sort(sort_cols)
    shift_expr = (
        pl.col(value_col).shift(1).over(group_col)
        if group_col
        else pl.col(value_col).shift(1)
    )
    prior_col = f"_prior_{value_col}"
    out = out.with_columns(shift_expr.alias(prior_col))
    out = out.with_columns(
        # Replace zero prior values with null so division yields null (not inf)
        ((pl.col(value_col) - pl.col(prior_col))
         / pl.col(prior_col).abs().replace(0.0, None) * 100)
        .round(4)
        .alias(f"{value_col}_yoy_pct")
    ).drop(prior_col)
    return out


def compute_margins(df: pl.DataFrame) -> pl.DataFrame:
    """
    Given a DataFrame with columns [Revenue, CostOfRevenue, OperatingIncome,
    NetIncome], add margin percentage columns.
    Expected column names (case-insensitive match attempted):
      revenue, cost_of_revenue / cogs, operating_income, net_income
    """
    col_map: dict[str, str] = {}
    lower_cols = {c.lower().replace(" ", "_"): c for c in df.columns}
    for alias, candidates in {
        "revenue":          ["revenues", "revenue", "netsales", "totalrevenue"],
        "cogs":             ["costofrevenue", "costofgoodsandservices", "cogs", "cost_of_revenue"],
        "operating_income": ["operatingincome", "operatingincomeloss", "operating_income"],
        "net_income":       ["netincomeloss", "netincome", "net_income"],
    }.items():
        for cand in candidates:
            if cand in lower_cols:
                col_map[alias] = lower_cols[cand]
                break

    exprs = []
    if "revenue" in col_map and "cogs" in col_map:
        r, c = col_map["revenue"], col_map["cogs"]
        exprs.append(
            ((pl.col(r) - pl.col(c)) / pl.col(r) * 100).round(4).alias("gross_margin_pct")
        )
    if "revenue" in col_map and "operating_income" in col_map:
        r, o = col_map["revenue"], col_map["operating_income"]
        exprs.append(
            (pl.col(o) / pl.col(r) * 100).round(4).alias("operating_margin_pct")
        )
    if "revenue" in col_map and "net_income" in col_map:
        r, n = col_map["revenue"], col_map["net_income"]
        exprs.append(
            (pl.col(n) / pl.col(r) * 100).round(4).alias("net_margin_pct")
        )

    return df.with_columns(exprs) if exprs else df

# ---------------------------------------------------------------------------
# FactExtractor — pulls specific XBRL concepts from a Polars DataFrame
# ---------------------------------------------------------------------------

# Canonical XBRL concept → common aliases (all lower-case, no hyphens)
_CONCEPT_ALIASES: dict[str, list[str]] = {
    "revenues":                  ["revenues", "revenue", "netsales", "totalrevenues",
                                  "revenuesfromcontractswithcustomers", "salesrevenuenet",
                                  "revenuefromcontractwithcustomerexcludingassessedtax",
                                  "revenuefromcontractwithcustomerincludingassessedtax"],
    "costofrevenue":             ["costofrevenue", "costofgoodsandservices", "costofgoodsandservicessold", "costofsales"],
    "grossprofit":               ["grossprofit"],
    "operatingincomeloss":       ["operatingincomeloss", "operatingincome",
                                  "incomefromoperations"],
    "netincomeloss":             ["netincomeloss", "netincome"],
    "researchanddevelopment":    ["researchanddevelopment", "researchanddevelopmentexpense"],
    "sellinggeneralandadmin":    ["sellinggeneralandadministrativeexpense", "sgaexpense",
                                  "operatingexpenses"],
    "assets":                    ["assets"],
    "liabilities":               ["liabilities"],
    "stockholdersequity":        ["stockholdersequity", "stockholdersequityattributable",
                                  "totalequity", "equity"],
    "cashandequivalents":        ["cashandcashequivalents", "cashcashequivalents",
                                  "cashcashequivalentsandshortterminvestments"],
    "currentassets":             ["assetscurrent", "currentassets"],
    "currentliabilities":        ["liabilitiescurrent", "currentliabilities"],
    "longtermdebt":              ["longtermdebtandcapitalleaseobligations", "longtermdebt",
                                  "longtermnotes"],
    "netcashoperating":          ["netcashprovidedbyusedinoperatingactivities",
                                  "netcashfromoperating"],
    "capitalexpenditures":       ["paymentstoacquirepropertyplantandequipment",
                                  "capitalexpenditures", "purchaseofpropertyplantequipment"],
    "depreciationamortization":  ["depreciationdepletionandamortization",
                                  "depreciationandamortization"],
    "sharesoutstanding":         ["commonstocksharesoutstanding", "sharesoutstanding",
                                  "weightedaveragenumberofsharesoutstandingbasic"],
    "earningspershare":          ["earningspersharebasic", "eps", "earningspershare"],
}


class FactExtractor:
    """
    Wraps a Polars DataFrame of XBRL facts and provides fuzzy concept lookups.

    Expected DataFrame columns (flexible, case-insensitive):
      Concept | Value | Unit | Period  (standard output of sec_client.get_latest_10k_facts)
    """

    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df
        concept_col = next(
            (c for c in df.columns if c.lower() in ("concept", "label", "name")),
            df.columns[0] if df.columns else "concept",
        )
        value_col = next(
            (c for c in df.columns if c.lower() in ("value", "amount")),
            df.columns[1] if len(df.columns) > 1 else "value",
        )
        period_col = next(
            (c for c in df.columns if c.lower() in ("period", "period_end", "date", "year")),
            None,
        )
        self._concept_col = concept_col
        self._value_col = value_col
        self._period_col = period_col

        # Fix #9: pre-build a normalised concept index for O(1) lookups.
        # Maps normalised_concept_string -> list of row indices.
        self._index: dict[str, list[int]] = {}
        for i, raw in enumerate(df[concept_col].to_list()):
            if raw is None:
                continue
            normed = str(raw).lower().replace("-", "").replace("_", "").replace(" ", "")
            self._index.setdefault(normed, []).append(i)

    def get(
        self,
        concept: str,
        period: Optional[str] = None,
        most_recent: bool = True,
    ) -> Optional[float]:
        """
        Look up a financial concept. Returns the raw float value or None.

        concept: canonical name or any alias (see _CONCEPT_ALIASES).
        period:  ISO date string, e.g. "2023-09-30". If None, uses most recent.
        """
        if self._df.is_empty():
            return None

        canon_key = concept.lower().replace("-", "").replace("_", "").replace(" ", "")
        aliases = _CONCEPT_ALIASES.get(canon_key, [canon_key])

        # Fix #1: use O(1) index with corrected matching — exact equality first,
        # then alias-contains-concept only (not bidirectional), with length guard.
        row_indices: list[int] = []
        for normed_concept, idxs in self._index.items():
            if any(
                normed_concept == a                              # exact match
                or (len(normed_concept) > 4 and normed_concept in a)  # concept is substring of alias
                for a in aliases
            ):
                row_indices.extend(idxs)

        if not row_indices:
            return None

        matched = self._df[row_indices]

        # Filter by period
        if period and self._period_col:
            period_filtered = matched.filter(
                pl.col(self._period_col).cast(pl.Utf8).str.contains(period)
            )
            if not period_filtered.is_empty():
                matched = period_filtered

        # Most recent first
        if most_recent and self._period_col:
            matched = matched.sort(self._period_col, descending=True)

        # Fix #8: use index access instead of .item(0) to avoid strict-mode crash
        val = matched[self._value_col][0]
        return float(val) if val is not None else None

    def get_multi(self, concepts: list[str], period: Optional[str] = None) -> dict[str, Optional[float]]:
        """Look up multiple concepts at once."""
        return {c: self.get(c, period=period) for c in concepts}

    def periods(self) -> list[str]:
        """Return sorted list of available period values."""
        if not self._period_col:
            return []
        return sorted(self._df[self._period_col].drop_nulls().unique().to_list())
