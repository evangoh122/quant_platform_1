"""tests/rag/test_sec_retrieval_tool.py - Tests for search_sec_filings tool.

Verifies distinct error types: no_coverage, ticker_required, retrieval_unavailable.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


# pyspark/databricks/psycopg fakes installed via module-scoped fixture below.
# psycopg/psycopg.rows/psycopg_pool are also handled by tests/rag/conftest.py mock_if_missing.

import pytest as _pytest


@_pytest.fixture(autouse=True, scope="module")
def _mock_pyspark():
    """Install pyspark/databricks/psycopg fakes for this module only."""
    _pyspark_mock = MagicMock()
    _originals = {}
    _patches = {
        "pyspark": _pyspark_mock,
        "pyspark.sql": _pyspark_mock.sql,
        "pyspark.sql.functions": _pyspark_mock.sql.functions,
        "databricks": MagicMock(),
        "databricks.connect": MagicMock(),
        "psycopg": MagicMock(),
        "psycopg.rows": MagicMock(),
        "psycopg_pool": MagicMock(),
    }
    for name, mock in _patches.items():
        _originals[name] = sys.modules.get(name)
        sys.modules[name] = mock

    yield

    for name in _patches:
        if _originals[name] is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = _originals[name]


class TestSearchSecFilingsErrors:
    """Verify search_sec_filings returns exactly the right error structure."""

    def test_no_coverage_returns_exact_structure(self):
        """NoCoverageError -> [{"error": "no_coverage", "ticker": symbol}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import NoCoverageError

        def raise_no_coverage(*args, **kwargs):
            raise NoCoverageError("XYZ")

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever:
            MockRetriever.return_value.retrieve.side_effect = raise_no_coverage
            result = search_sec_filings("XYZ", query="test query")

        assert result == [{"error": "no_coverage", "ticker": "XYZ"}]

    def test_no_coverage_does_not_invoke_substring_fallback(self):
        """NoCoverageError must not trigger the substring fallback path."""
        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import NoCoverageError

        def raise_no_coverage(*args, **kwargs):
            raise NoCoverageError("XYZ")

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever:
            MockRetriever.return_value.retrieve.side_effect = raise_no_coverage
            result = search_sec_filings("XYZ", query="test")

        assert result[0]["error"] == "no_coverage"
        assert "retrieval_mode" not in result[0]

    def test_ticker_required_returns_exact_structure(self):
        """TickerRequiredError -> [{"error": "ticker_required"}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.hybrid_retriever import TickerRequiredError

        def raise_ticker_required(*args, **kwargs):
            raise TickerRequiredError()

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever:
            MockRetriever.return_value.retrieve.side_effect = raise_ticker_required
            result = search_sec_filings("XYZ", query="test")

        assert result == [{"error": "ticker_required"}]

    def test_retrieval_unavailable_preserved(self):
        """CorpusUnavailableError -> [{"error": "retrieval_unavailable", ...}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import CorpusUnavailableError

        def raise_unavailable(*args, **kwargs):
            raise CorpusUnavailableError("table not found")

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever:
            MockRetriever.return_value.retrieve.side_effect = raise_unavailable
            result = search_sec_filings("NVDA", query="test")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert "ticker" in result[0]

    def test_embedding_config_error_returns_structured(self):
        """EmbeddingConfigError -> [{"error": "retrieval_unavailable", "reason": "embedding_config"}]"""
        from agent.tools_retrieval import search_sec_filings
        from api.services.exceptions import EmbeddingConfigError

        def raise_config(*args, **kwargs):
            raise EmbeddingConfigError("dim mismatch", user_safe=True)

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever:
            MockRetriever.return_value.retrieve.side_effect = raise_config
            result = search_sec_filings("NVDA", query="test")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["reason"] == "embedding_config"

    def test_spark_table_error_returns_retrieval_unavailable(self):
        """Spark/table errors must return retrieval_unavailable, not fall through to substring."""
        from agent.tools_retrieval import search_sec_filings

        def raise_spark_error(*args, **kwargs):
            raise RuntimeError("Table not found: silver_sec_sections")

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever:
            MockRetriever.return_value.retrieve.side_effect = raise_spark_error
            result = search_sec_filings("NVDA", query="test")

        assert len(result) == 1
        assert result[0]["error"] == "retrieval_unavailable"
        assert result[0]["ticker"] == "NVDA"
        # Must NOT have retrieval_mode (no substring fallback)
        assert "retrieval_mode" not in result[0]

    def test_table_error_does_not_invoke_substring_path(self):
        """Spark/table errors must not trigger substring fallback path."""
        from agent.tools_retrieval import search_sec_filings

        def raise_spark_error(*args, **kwargs):
            raise RuntimeError("Connection refused")

        mock_spark = MagicMock()

        with patch("agent.tools_retrieval.normalize_symbol", side_effect=lambda s: s), \
             patch("api.services.hybrid_retriever.HybridRetriever") as MockRetriever, \
             patch("agent.tools_retrieval._spark", return_value=mock_spark):
            MockRetriever.return_value.retrieve.side_effect = raise_spark_error
            result = search_sec_filings("NVDA", query="test")

        # The Spark session must NOT have been called (no substring fallback)
        mock_spark.table.assert_not_called()
        assert result[0]["error"] == "retrieval_unavailable"