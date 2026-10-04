"""tests/rag/test_zz_isolation.py - Guard against sys.modules pollution.

This test runs after other tests in tests/rag/ (zz prefix ensures ordering).
It verifies that module-scoped mocking in test_sec_rag_ingest.py and
test_sec_retrieval_tool.py does not leak MagicMock into sys.modules
for other test suites.
"""
import os
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


def test_pyspark_connect_mode_not_leaked():
    """pyspark.sql.functions must not be a MagicMock or stub after rag tests.

    With databricks-connect installed, pyspark.sql.functions delegates to
    pyspark.sql.connect.functions via try_remote_functions.  If the module-
    scoped _mock_pyspark fixtures replace pyspark.sql.functions with a
    MagicMock and fail to restore it, downstream tests (e.g. tests/bronze/)
    will get MagicMock Columns instead of real Connect Columns, causing
    isinstance failures in pyspark.sql.connect.functions.builtin._invoke_function.
    """
    from unittest.mock import MagicMock

    # pyspark.sql.functions must be a real module, not a MagicMock
    mod = sys.modules.get("pyspark.sql.functions")
    assert mod is None or not isinstance(mod, MagicMock), (
        "pyspark.sql.functions is still a MagicMock in sys.modules after rag tests. "
        "This causes isinstance failures in downstream Connect functions."
    )

    # pyspark.sql must be a real module, not a MagicMock
    sql_mod = sys.modules.get("pyspark.sql")
    assert sql_mod is None or not isinstance(sql_mod, MagicMock), (
        "pyspark.sql is still a MagicMock in sys.modules after rag tests."
    )

    # Environment variables that force Connect mode must not be leaked
    assert "SPARK_CONNECT_MODE_ENABLED" not in os.environ, (
        "SPARK_CONNECT_MODE_ENABLED was set by a rag test and not cleaned up."
    )
    assert "SPARK_REMOTE" not in os.environ, (
        "SPARK_REMOTE was set by a rag test and not cleaned up."
    )