"""tests/rag/test_zz_isolation.py - Guard against sys.modules pollution.

This test runs after other tests in tests/rag/ (zz prefix ensures ordering).
It verifies that module-scoped mocking in test_sec_rag_ingest.py and
test_sec_retrieval_tool.py does not leak MagicMock into sys.modules
for other test suites.
"""
import sys


def test_databricks_connect_not_polluted():
    """databricks.connect must not be a MagicMock after rag tests finish."""
    mod = sys.modules.get("databricks.connect")
    assert mod is None or not isinstance(mod, type(__import__("unittest.mock").MagicMock())), (
        "databricks.connect is still a MagicMock in sys.modules after rag tests. "
        "This pollutes downstream test suites (e.g. tests/bronze/)."
    )


def test_pyspark_not_polluted():
    """pyspark must not be a MagicMock after rag tests finish."""
    from unittest.mock import MagicMock
    mod = sys.modules.get("pyspark")
    assert mod is None or not isinstance(mod, MagicMock), (
        "pyspark is still a MagicMock in sys.modules after rag tests."
    )