"""
Regression tests for api/services/xbrl_relevance.py.

Focus: zero-valued XBRL facts must be treated as real values, not dropped.
A legitimate 0 (zero long-term debt, zero R&D, etc.) previously became None via
truthiness fallback (`fact.get("value") or fact.get("val")`), rendering as "—"
and being marked unverified, and getting demoted in ranking.
"""
from api.services.xbrl_relevance import (
    filter_facts_for_query,
    get_fact_period,
    _pick_value,
    _rank_facts,
    format_fact_for_display,
    get_relevant_facts,
)


# ── _pick_value ────────────────────────────────────────────────────────────────

def test_pick_value_keeps_zero():
    """A value of 0 must be returned as 0, not fall through to 'val' or None."""
    assert _pick_value({"value": 0}) == 0
    assert _pick_value({"value": 0.0}) == 0.0


def test_pick_value_falls_back_to_val_only_when_value_missing():
    """Value selection uses val only when the primary value is absent."""
    assert _pick_value({"val": 123}) == 123
    # 'value' present (even as 0) wins over 'val'
    assert _pick_value({"value": 0, "val": 999}) == 0


def test_pick_value_none_when_both_absent():
    """Value selection returns None when neither numeric key exists."""
    assert _pick_value({"concept": "X"}) is None


# ── format_fact_for_display ─────────────────────────────────────────────────────

def test_format_zero_value_is_verified_and_not_dropped():
    """Formatting preserves a legitimate zero as a verified SEC value."""
    out = format_fact_for_display({
        "concept": "LongTermDebt", "value": 0, "unit": "USD", "period_end": "2024-09-28",
    })
    assert out["value"] == 0.0          # not None
    assert out["is_verified"] is True   # zero is a real, verified value
    assert out["label"] == "Long-Term Debt"
    assert out["period"] == "2024-09-28"  # period_end mapped to period


def test_format_maps_period_and_label():
    """Formatting maps canonical display labels and reporting periods."""
    out = format_fact_for_display({
        "concept": "Revenues", "value": 30391000000, "unit": "USD", "period_end": "2024-09-28",
    })
    assert out["label"] == "Revenue"
    assert out["period"] == "2024-09-28"
    assert out["is_verified"] is True


def test_format_missing_value_is_unverified():
    """Formatting marks a missing numeric value as unverified."""
    out = format_fact_for_display({"concept": "Revenues", "unit": "USD", "period_end": "2024-09-28"})
    assert out["value"] is None
    assert out["is_verified"] is False


def test_format_preserves_exact_sec_fact_provenance():
    """Formatting retains provenance and constructs exact SEC source URLs."""
    out = format_fact_for_display({
        "ticker": "NVDA",
        "cik": "1045810",
        "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "value": 130497000000,
        "unit": "USD",
        "period_start": "2024-01-29",
        "period_end": "2025-01-26",
        "form_type": "10-K",
        "accession": "0001045810-25-000023",
        "filed": "2025-02-26",
        "frame": "CY2024",
    })
    assert out["cik"] == "0001045810"
    assert out["accession"] == "0001045810-25-000023"
    assert out["period_start"] == "2024-01-29"
    assert out["frame"] == "CY2024"
    assert out["raw_fact_url"].endswith(
        "/CIK0001045810/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json"
    )
    assert out["filing_url"].endswith(
        "/1045810/000104581025000023/0001045810-25-000023-index.htm"
    )
    assert out["raw_frame_url"].endswith(
        "/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax/USD/CY2024.json"
    )


def test_period_falls_back_to_fiscal_year_when_period_end_is_empty():
    """Period display falls back to fiscal year when no end date exists."""
    fact = {"fiscal_year": 2025, "fiscal_period": "FY"}
    assert get_fact_period(fact) == "FY2025"
    assert format_fact_for_display(fact)["period"] == "FY2025"


def test_period_prefers_period_end_over_filing_date_and_fiscal_year():
    """Period display prefers the fact end date over filing metadata."""
    fact = {
        "period_end": "2025-01-31",
        "filed": "2025-03-10",
        "fiscal_year": 2025,
    }
    assert get_fact_period(fact) == "2025-01-31"


def test_period_prefers_fiscal_year_over_later_filing_date():
    """Fiscal year outranks filing date when the fact end date is absent."""
    fact = {"period_end": None, "fiscal_year": 2025, "fiscal_period": "FY", "filed": "2026-02-01"}
    assert get_fact_period(fact) == "FY2025"


def test_period_normalises_datetime_to_date_for_stable_deduplication():
    """Period normalization removes time components for stable identities."""
    assert get_fact_period({"period_end": "2025-01-31T00:00:00"}) == "2025-01-31"


# ── _rank_facts / get_relevant_facts ───────────────────────────────────────────

def test_rank_does_not_demote_zero_valued_fact_below_missing():
    """A zero-valued fact in the primary group must outrank a value-less fact."""
    facts = [
        {"concept": "GrossProfit", "value": None, "period_end": "2024-09-28"},   # missing → demoted
        {"concept": "GrossProfit", "value": 0, "period_end": "2024-09-28"},      # zero → real value
    ]
    ranked = _rank_facts(facts, "profitability", top_n=2)
    assert ranked[0]["value"] == 0       # zero-valued fact ranks first
    assert ranked[1]["value"] is None


def test_get_relevant_facts_includes_zero_value():
    """Relevance filtering retains zero-valued facts."""
    facts = [{"concept": "LongTermDebt", "value": 0, "unit": "USD", "period_end": "2024-09-28"}]
    result = get_relevant_facts("What is the company's long-term debt?", facts)
    assert result["total"] == 1
    assert len(result["relevant"]) == 1
    assert result["relevant"][0]["value"] == 0


def test_get_relevant_facts_empty():
    """Relevance filtering returns an empty result for an empty corpus."""
    result = get_relevant_facts("anything", [])
    assert result["relevant"] == []
    assert result["total"] == 0
    assert result["group"] == "none"


def test_latest_query_keeps_only_facts_from_latest_fiscal_year():
    """Latest intent restricts facts to the newest fiscal year."""
    facts = [
        {"concept": "Revenues", "value": 100, "period_end": "2023-12-31", "fiscal_year": 2023},
        {"concept": "Revenues", "value": 120, "period_end": "2024-12-31", "fiscal_year": 2024},
        {"concept": "NetIncomeLoss", "value": 20, "period_end": "2024-12-31", "fiscal_year": 2024},
    ]
    filtered = filter_facts_for_query("What is the latest revenue?", facts)
    assert len(filtered) == 2
    assert {fact["fiscal_year"] for fact in filtered} == {2024}


def test_latest_query_uses_period_year_when_fiscal_year_is_missing():
    """Latest intent derives the year from period when fiscal year is absent."""
    facts = [
        {"concept": "Revenues", "value": 100, "period_end": "2023-12-31"},
        {"concept": "Revenues", "value": 120, "period_end": "2024-12-31"},
    ]
    result = get_relevant_facts("most recent revenue", facts)
    assert len(result["relevant"]) == 1
    assert result["relevant"][0]["period_end"] == "2024-12-31"


def test_general_query_preserves_multiple_years():
    """General intent keeps multi-year facts for trend analysis."""
    facts = [
        {"concept": "Revenues", "value": 100, "period_end": "2023-12-31"},
        {"concept": "Revenues", "value": 120, "period_end": "2024-12-31"},
    ]
    assert filter_facts_for_query("Show revenue history", facts) == facts


def test_current_requires_a_complete_word():
    """Latest-intent keywords match complete words rather than substrings."""
    facts = [
        {"concept": "Revenues", "value": 100, "period_end": "2023-12-31"},
        {"concept": "Revenues", "value": 120, "period_end": "2024-12-31"},
    ]
    assert filter_facts_for_query("What currency is revenue reported in?", facts) == facts
    assert len(filter_facts_for_query("What is current revenue?", facts)) == 1


def test_relevance_can_skip_period_filter_when_caller_already_applied_it():
    """Callers can bypass redundant latest-period filtering."""
    facts = [
        {"concept": "Revenues", "value": 100, "period_end": "2023-12-31"},
        {"concept": "Revenues", "value": 120, "period_end": "2024-12-31"},
    ]
    result = get_relevant_facts(
        "latest revenue",
        facts,
        filter_by_period=False,
    )
    assert len(result["relevant"]) == 2


def test_default_caps_relevant_facts_at_three():
    """The contextual display should stay terse — at most 3 facts, not 8."""
    facts = [
        {"concept": c, "value": v, "period_end": "2024-12-31"}
        for c, v in [
            ("Revenues", 100), ("GrossProfit", 40), ("OperatingIncomeLoss", 30),
            ("NetIncomeLoss", 20), ("ResearchAndDevelopmentExpense", 10),
            ("OperatingExpenses", 15), ("InterestExpense", 5),
        ]
    ]
    result = get_relevant_facts("How profitable is the company?", facts)
    assert len(result["relevant"]) <= 3


def test_gross_margin_surfaces_revenue_and_gross_profit():
    """A gross-margin question should show its components (revenue + gross
    profit), not a broad dump of profitability facts."""
    facts = [
        {"concept": "Revenues", "value": 100, "period_end": "2024-12-31", "fiscal_year": 2024},
        {"concept": "GrossProfit", "value": 40, "period_end": "2024-12-31", "fiscal_year": 2024},
        {"concept": "NetIncomeLoss", "value": 20, "period_end": "2024-12-31", "fiscal_year": 2024},
        {"concept": "OperatingExpenses", "value": 15, "period_end": "2024-12-31", "fiscal_year": 2024},
        {"concept": "ResearchAndDevelopmentExpense", "value": 10, "period_end": "2024-12-31", "fiscal_year": 2024},
    ]
    result = get_relevant_facts("What is the gross margin?", facts, filter_by_period=False)
    concepts = {f["concept"] for f in result["relevant"]}
    assert concepts == {"Revenues", "GrossProfit"}


def test_gross_margin_collapses_repeated_concepts_to_latest():
    """With multiple years present, the metric components dedupe to one each."""
    facts = [
        {"concept": "Revenues", "value": 90, "period_end": "2023-12-31", "fiscal_year": 2023},
        {"concept": "Revenues", "value": 100, "period_end": "2024-12-31", "fiscal_year": 2024},
        {"concept": "GrossProfit", "value": 35, "period_end": "2023-12-31", "fiscal_year": 2023},
        {"concept": "GrossProfit", "value": 40, "period_end": "2024-12-31", "fiscal_year": 2024},
    ]
    result = get_relevant_facts("gross margin", facts, filter_by_period=False)
    assert len(result["relevant"]) == 2
    by_concept = {f["concept"]: f["value"] for f in result["relevant"]}
    assert by_concept == {"Revenues": 100, "GrossProfit": 40}
