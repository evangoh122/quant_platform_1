"""
tests/test_sentiment.py

Unit tests for Loughran-McDonald sentiment analysis.
Run with: python -m pytest tests/test_sentiment.py -v
"""
import pytest
from api.services.sentiment import (
    load_lm_dictionary,
    tokenize,
    count_sentiment,
    analyze_section,
    analyze_filing_sections,
    SentimentCounts,
    SentimentDictionary,
)


# ── Dictionary loading ───────────────────────────────────────────────────────

class TestDictionaryLoading:
    def test_load_returns_frozen_dict(self):
        d = load_lm_dictionary()
        assert isinstance(d, SentimentDictionary)
        assert isinstance(d.positive, frozenset)
        assert isinstance(d.negative, frozenset)

    def test_positive_words_not_empty(self):
        d = load_lm_dictionary()
        assert len(d.positive) > 50, "Positive word list should have 50+ words"

    def test_negative_words_not_empty(self):
        d = load_lm_dictionary()
        assert len(d.negative) > 50, "Negative word list should have 50+ words"

    def test_uncertainty_words_not_empty(self):
        d = load_lm_dictionary()
        assert len(d.uncertainty) > 30, "Uncertainty word list should have 30+ words"

    def test_all_categories_present(self):
        d = load_lm_dictionary()
        for cat in ("positive", "negative", "uncertainty", "litigious",
                     "constraining", "strong_modal", "weak_modal"):
            words = getattr(d, cat)
            assert isinstance(words, frozenset), f"{cat} should be a frozenset"

    def test_words_are_lowercase(self):
        d = load_lm_dictionary()
        for word in list(d.positive)[:20]:
            assert word == word.lower(), f"Dictionary word should be lowercase: {word}"

    def test_known_positive_words_present(self):
        d = load_lm_dictionary()
        for word in ("growth", "strong", "improve", "achievement", "advantage"):
            assert word in d.positive, f"Expected '{word}' in positive words"

    def test_known_negative_words_present(self):
        d = load_lm_dictionary()
        for word in ("loss", "decline", "failure", "impair", "weakness"):
            assert word in d.negative, f"Expected '{word}' in negative words"

    def test_known_uncertainty_words_present(self):
        d = load_lm_dictionary()
        for word in ("believe", "estimate", "approximately", "assume", "assume"):
            assert word in d.uncertainty, f"Expected '{word}' in uncertainty words"


# ── Tokenizer ────────────────────────────────────────────────────────────────

class TestTokenizer:
    def test_basic_tokenization(self):
        tokens = tokenize("The company reported strong growth")
        assert tokens == ["the", "company", "reported", "strong", "growth"]

    def test_hyphenated_words(self):
        tokens = tokenize("well-known and year-over-year growth")
        assert "well-known" in tokens
        assert "year-over-year" in tokens

    def test_numbers_stripped(self):
        tokens = tokenize("Revenue was $1,234,567 in 2024")
        assert "1234567" not in tokens
        assert "2024" not in tokens
        assert "revenue" in tokens

    def test_empty_text(self):
        tokens = tokenize("")
        assert tokens == []

    def test_punctuation_stripped(self):
        tokens = tokenize("growth, loss; and: improvement!")
        assert "growth" in tokens
        assert "loss" in tokens
        assert "improvement" in tokens


# ── Counting ─────────────────────────────────────────────────────────────────

class TestCountSentiment:
    def test_positive_text(self):
        d = load_lm_dictionary()
        text = "The company achieved strong growth and improvement with excellent results"
        counts = count_sentiment(text, d)
        assert counts.positive >= 3

    def test_negative_text(self):
        d = load_lm_dictionary()
        text = "The company faces decline, loss, failure, and impairment charges"
        counts = count_sentiment(text, d)
        assert counts.negative >= 3
        assert counts.positive == 0

    def test_mixed_text(self):
        d = load_lm_dictionary()
        text = "Despite strong growth, the company faces declining revenue and impairment"
        counts = count_sentiment(text, d)
        assert counts.positive >= 1
        assert counts.negative >= 1

    def test_empty_text(self):
        d = load_lm_dictionary()
        counts = count_sentiment("", d)
        assert counts.total_words == 0
        assert counts.positive == 0
        assert counts.net_sentiment == 0.0

    def test_net_sentiment_formula(self):
        d = load_lm_dictionary()
        text = "growth profit loss decline"
        counts = count_sentiment(text, d)
        # net_sentiment = (positive - negative) / total_words
        expected = (counts.positive - counts.negative) / max(counts.total_words, 1)
        assert counts.net_sentiment == pytest.approx(expected, abs=1e-6)

    def test_tone_score_formula(self):
        d = load_lm_dictionary()
        text = "growth profit loss uncertainty risk"
        counts = count_sentiment(text, d)
        expected = (counts.positive - counts.negative - counts.uncertainty) / max(counts.total_words, 1)
        assert counts.tone_score == pytest.approx(expected, abs=1e-6)

    def test_to_dict_round_trip(self):
        d = load_lm_dictionary()
        text = "The company achieved strong growth"
        counts = count_sentiment(text, d)
        result = counts.to_dict()
        assert "positive" in result
        assert "net_sentiment" in result
        assert "tone_score" in result
        assert isinstance(result["positive"], int)

    def test_uncertainty_words_counted(self):
        d = load_lm_dictionary()
        text = "The company may could possibly achieve growth"
        counts = count_sentiment(text, d)
        assert counts.uncertainty >= 2

    def test_strong_vs_weak_modal(self):
        d = load_lm_dictionary()
        text_strong = "We will definitely achieve our goals"
        text_weak = "We might possibly achieve our goals"
        c_strong = count_sentiment(text_strong, d)
        c_weak = count_sentiment(text_weak, d)
        assert c_strong.strong_modal >= 1
        assert c_weak.weak_modal >= 1


# ── Section analysis ─────────────────────────────────────────────────────────

class TestAnalyzeSection:
    def test_returns_dict_with_section_type(self):
        result = analyze_section("growth profit improvement", "md_and_a")
        assert result["section_type"] == "md_and_a"
        assert "positive" in result
        assert "net_sentiment" in result

    def test_risk_factors_more_negative(self):
        risk_text = "We face litigation risk, regulatory investigation, and potential loss from impairment"
        mdna_text = "We achieved strong growth, profitable results, and improvement in margins"
        risk = analyze_section(risk_text, "risk_factors")
        mdna = analyze_section(mdna_text, "md_and_a")
        assert risk["negative"] >= mdna["negative"]
        assert mdna["positive"] >= risk["positive"]


# ── Filing-level aggregation ─────────────────────────────────────────────────

class TestAnalyzeFilingSections:
    def test_aggregates_multiple_sections(self):
        sections = {
            "Item 1A": "litigation risk loss impairment decline",
            "Item 7": "strong growth profit improvement success",
        }
        result = analyze_filing_sections(sections)
        assert "sections" in result
        assert "totals" in result
        assert "overall_net_sentiment" in result
        assert len(result["sections"]) == 2

    def test_totals_sum_correctly(self):
        sections = {
            "Item 1A": "loss decline failure",
            "Item 7": "growth strong improvement",
        }
        result = analyze_filing_sections(sections)
        assert result["totals"]["negative"] >= 2
        assert result["totals"]["positive"] >= 2

    def test_empty_sections(self):
        result = analyze_filing_sections({})
        assert result["total_words"] == 0
        assert result["overall_net_sentiment"] == 0.0

    def test_overall_net_sentiment_range(self):
        sections = {"Item 7": "strong growth profit improvement"}
        result = analyze_filing_sections(sections)
        assert -1.0 <= result["overall_net_sentiment"] <= 1.0


# ── SentimentCounts dataclass ────────────────────────────────────────────────

class TestSentimentCounts:
    def test_default_values(self):
        c = SentimentCounts()
        assert c.positive == 0
        assert c.total_words == 0

    def test_net_sentiment_zero_words(self):
        c = SentimentCounts()
        assert c.net_sentiment == 0.0

    def test_tone_score_zero_words(self):
        c = SentimentCounts()
        assert c.tone_score == 0.0

    def test_positive_bias(self):
        c = SentimentCounts(positive=10, negative=2, total_words=100)
        assert c.net_sentiment > 0
        assert c.tone_score > 0

    def test_negative_bias(self):
        c = SentimentCounts(positive=2, negative=10, total_words=100)
        assert c.net_sentiment < 0
        assert c.tone_score < 0
