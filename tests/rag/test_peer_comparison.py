"""Tests for the multi-company peer-comparison path (pure logic, no DB)."""
from api.services.peer_comparison import (
    detect_comparison,
    _metric_for_query,
    _tickers_named_in_query,
    _name_to_ticker,
    _format_value,
    _parse_year_horizon,
    _wants_multiyear,
    _MULTIYEAR_CHARTABLE,
    _MAX_TREND_YEARS,
    _filing_sources,
    _shaped_response,
)


class TestComparisonEnrichment:
    """The comparison result must carry sources + the 3-layer fields a single-
    company answer has, or the UI shows no graph context / sources / 'what it means'."""

    def test_filing_sources_one_per_ticker_with_edgar_url(self):
        docs = _filing_sources(["NVDA", "AMD"])
        assert len(docs) == 2
        assert [d["metadata"]["ticker"] for d in docs] == ["NVDA", "AMD"]
        for d in docs:
            assert d["metadata"]["edgar_url"].startswith("https://www.sec.gov/")
            assert "10-K" in d["metadata"]["edgar_url"]
            assert d.get("chunk_text")

    def test_filing_sources_empty(self):
        assert _filing_sources([]) == []

    def test_shaped_response_carries_optional_fields(self):
        r = _shaped_response(
            "ans", "why", chart={"type": "line"},
            what_it_means="wim", how_to_interpret="hti",
            follow_ups=["a", "b"], retrieved_docs=[{"chunk_text": "x", "metadata": {}}],
        )
        assert r["what_it_means"] == "wim"
        assert r["how_to_interpret"] == "hti"
        assert r["follow_ups"] == ["a", "b"]
        assert len(r["retrieved_docs"]) == 1
        assert r["status"]["retrieval"] == "success"  # docs present → retrieval ran

    def test_shaped_response_defaults_are_empty(self):
        r = _shaped_response("ans", "why")
        assert r["what_it_means"] == "" and r["follow_ups"] == []
        assert r["retrieved_docs"] == []
        assert r["status"]["retrieval"] == "skipped"


class TestComparisonDetection:
    def test_competitor_intent_is_peer_mode(self):
        d = detect_comparison(
            "How does NVIDIA's revenue growth compare to its competitors?", "NVDA")
        assert d is not None
        assert d["mode"] == "peer"
        assert d["subject"] == "NVDA"

    def test_industry_phrasing_is_peer_mode(self):
        d = detect_comparison("How does AMD stack up against the industry?", "AMD")
        assert d is not None and d["mode"] == "peer" and d["subject"] == "AMD"

    def test_two_named_companies_is_explicit_mode(self):
        d = detect_comparison("Compare NVDA and Intel gross margins", "NVDA")
        assert d is not None
        assert d["mode"] == "explicit"
        assert set(d["explicit"]) == {"NVDA", "INTC"}

    def test_three_named_companies_preserves_all(self):
        d = detect_comparison("NVDA vs QCOM vs TXN revenue", "NVDA")
        assert d is not None and d["mode"] == "explicit"
        assert set(d["explicit"]) == {"NVDA", "QCOM", "TXN"}

    def test_plain_single_company_question_is_not_a_comparison(self):
        assert detect_comparison("What is NVDA's gross margin?", "NVDA") is None

    def test_peer_intent_uses_caller_ticker_when_query_names_none(self):
        d = detect_comparison("How does it compare to competitors?", "MU")
        assert d is not None and d["mode"] == "peer" and d["subject"] == "MU"


class TestNameResolution:
    def test_company_names_map_to_tickers(self):
        assert _name_to_ticker("NVIDIA Corporation") == "NVDA"
        assert _name_to_ticker("Texas Instruments") == "TXN"
        assert _name_to_ticker("Broadcom Inc.") == "AVGO"

    def test_unknown_name_returns_none(self):
        assert _name_to_ticker("MediaTek") is None
        assert _name_to_ticker("") is None

    def test_named_tickers_in_query_order(self):
        assert _tickers_named_in_query("TXN then NVDA") == ["TXN", "NVDA"]

    def test_substring_company_names_ignored(self):
        # 'on' is a name for ON Semiconductor, but shouldn't match inside 'micron'
        assert _tickers_named_in_query("What is Micron's gross margin?") == ["MU"]
        # 'on' as a common English word should be ignored as a false positive
        assert _tickers_named_in_query("Based on the filing, did Micron's gross margin improve?") == ["MU"]
        # Uppercase 'ON' or other specific ON Semiconductor names should match
        assert "ON" in _tickers_named_in_query("Compare ON and MU")
        assert "ON" in _tickers_named_in_query("What about onsemi's margin?")


class TestMetricMapping:
    def test_growth_phrasing(self):
        assert _metric_for_query("revenue growth rate vs peers")[0] == "revenue_yoy_growth"

    def test_gross_margin_phrasing(self):
        assert _metric_for_query("compare gross margins")[0] == "gross_margin"

    def test_default_is_revenue(self):
        assert _metric_for_query("how do they compare")[0] == "revenue"


class TestYearHorizon:
    def test_parses_digit_horizon(self):
        assert _parse_year_horizon("compare nvidia and amd revenue over 5 years") == 5
        assert _parse_year_horizon("3-year revenue trend") == 3
        assert _parse_year_horizon("revenue over the last 4 years") == 4

    def test_parses_written_number(self):
        assert _parse_year_horizon("revenue over the last three years") == 3

    def test_clamps_to_bounds(self):
        assert _parse_year_horizon("revenue over 20 years") == _MAX_TREND_YEARS
        assert _parse_year_horizon("revenue over 1 year") == 2

    def test_no_horizon_when_unstated(self):
        assert _parse_year_horizon("compare nvidia and amd revenue") is None
        assert _parse_year_horizon("") is None


class TestMultiyearDetection:
    def test_explicit_horizon_wants_multiyear(self):
        assert _wants_multiyear("compare nvidia and amd revenue over 5 years")

    def test_trend_signal_wants_multiyear(self):
        assert _wants_multiyear("nvidia vs amd revenue trend")
        assert _wants_multiyear("amd revenue history vs nvidia")

    def test_snapshot_query_does_not_want_multiyear(self):
        assert not _wants_multiyear("compare nvidia and amd revenue")

    def test_revenue_is_chartable_for_multiyear(self):
        assert "revenue" in _MULTIYEAR_CHARTABLE
        # Growth / ratio metrics are not tabulated year-by-year (snapshot only).
        assert "revenue_yoy_growth" not in _MULTIYEAR_CHARTABLE
        assert "current_ratio" not in _MULTIYEAR_CHARTABLE


class TestValueFormatting:
    def test_percent_metric(self):
        assert _format_value("gross_margin", 71.14) == "71.1%"

    def test_usd_billions(self):
        assert _format_value("revenue", 130_497_000_000.0) == "$130.50B"

    def test_ratio(self):
        assert _format_value("debt_to_equity", 0.42) == "0.42"

    def test_missing_value_is_na(self):
        assert _format_value("revenue", None) == "n/a"
