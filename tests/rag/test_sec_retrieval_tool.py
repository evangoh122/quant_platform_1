"""tests/rag/test_sec_retrieval_tool.py — Tests for search_sec_filings tool.

Verifies distinct error types: no_coverage, ticker_required, retrieval_unavailable.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


# Hide pyspark/databricks
_pyspark_mock = MagicMock()
sys.modules.setdefault("pyspark", _pyspark_mock)
sys.modules.setdefault("pyspark.sql", _pyspark_mock.sql)
sys.modules.setdefault("pyspark.sql.functions", _pyspark_mock.sql.functions)
sys.modules.setdefault("databricks", MagicMock())
sys.modules.setdefault("databricks.connect", MagicMock())


class TestSearchSecFilingsErrors:
    """Verify search_sec_filings returns exactly the right error structure."""

    def test_no_coverage_returns_exact_structure(self, monkeypatch):
        """NoCoverageError -> [{"error": "no_coverage", "ticker": symbol}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import NoCoverageError

        def raise_no_coverage(*args, **kwargs):
            raise NoCoverageError("XYZ")

        monkeypatch.setattr(
            "api.services.hybrid_retriever.HybridRetriever.retrieve",
            raise_no_coverage,
        )

        result = search_sec_filings("XYZ", query="test query")
        assert result == [{"error": "no_coverage", "ticker": "XYZ"}]

    def test_no_coverage_does_not_invoke_substring_fallback(self, monkeypatch):
        """NoCoverageError must not trigger the substring fallback path."""
        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import NoCoverageError

        def raise_no_coverage(*args, **kwargs):
            raise NoCoverageError("XYZ")

        monkeypatch.setattr(
            "api.services.hybrid_retriever.HybridRetriever.retrieve",
            raise_no_coverage,
        )

        result = search_sec_filings("XYZ", query="test")
        assert result[0]["error"] == "no_coverage"
        assert "retrieval_mode" not in result[0]

    def test_ticker_required_returns_exact_structure(self, monkeypatch):
        """TickerRequiredError -> [{"error": "ticker_required"}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import TickerRequiredError

        def raise_ticker_required(*args, **kwargs):
            raise TickerRequiredError()

        monkeypatch.setattr(
            "api.services.hybrid_retriever.HybridRetriever.retrieve",
            raise_ticker_required,
        )

        result = search_sec_filings("XYZ", query="test")
        assert result == [{"error": "ticker_required"}]

    def test_retrieval_unavailable_preserved(self, monkeypatch):
        """CorpusUnavailableError -> [{"error": "retrieval_unavailable", ...}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import CorpusUnavailableError

        def raise_unavailable(*args, **kwargs):
            raise CorpusUnavailableError("table not found")

        monkeypatch.setattr(
            "api.services.hybrid_retriever.HybridRetriever.retrieve",
            raise_unavailable,
        )

        result = search_sec_filings("NVDA", query="test")
        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert "ticker" in result[0]

    def test_embedding_config_error_returns_structured(self, monkeypatch):
        """EmbeddingConfigError -> [{"error": "retrieval_unavailable", "reason": "embedding_config"}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import EmbeddingConfigError

        def raise_config(*args, **kwargs):
            raise EmbeddingConfigError("dim mismatch", user_safe=True)

        monkeypatch.setattr(
            "api.services.hybrid_retriever.HybridRetriever.retrieve",
            raise_config,
        )

        result = search_sec_filings("NVDA", query="test")
        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["reason"] == "embedding_config"