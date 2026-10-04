import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


def mock_if_missing(module_names):
    for name in module_names:
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = MagicMock()

# Only mock modules that are truly problematic or missing in the test environment
# to allow real unit testing of installed packages.
problematic_modules = [
    'langgraph',
    'langgraph.graph',
    'edgartools', # Can be heavy/network dependent
    'langfuse',
    'langfuse.decorators',
    'sec_edgar_downloader',
    'langchain_text_splitters',
    'bs4',
    'psycopg', # Not available in test environment
    'psycopg_pool', # Not available in test environment
]

mock_if_missing(problematic_modules)

# We don't globally mock api.config.Config here as it breaks Config tests.
# If a specific test needs it mocked, it should do so itself.


@pytest.fixture()
def fake_pyspark(monkeypatch):
    """Install lightweight pyspark stubs so tests that exercise code paths
    importing ``pyspark.sql.functions`` can run on CI runners without pyspark.

    The stubs return MagicMock objects for column-expression helpers (col,
    lit, lower, unix_timestamp, desc) which are sufficient for mocked
    DataFrame chains used in the offline tests.
    """
    class _ColExpr:
        """Lightweight pyspark Column expression stub. Supports comparison
        operators (returns self) and attribute access (returns self) so that
        chained expressions like
        ``F.unix_timestamp(F.col("x")).alias("y") <= F.lit(n)``
        produce a passable object for mocked DataFrame.where() calls."""
        def __le__(self, other): return self
        def __lt__(self, other): return self
        def __ge__(self, other): return self
        def __gt__(self, other): return self
        def __eq__(self, other): return self  # noqa: E712
        def __ne__(self, other): return self  # noqa: E712
        def __getattr__(self, name): return self
        def __call__(self, *a, **kw): return self

    pyspark = ModuleType("pyspark")
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql_functions = ModuleType("pyspark.sql.functions")
    pyspark_sql_types = ModuleType("pyspark.sql.types")

    pyspark.sql = pyspark_sql
    pyspark_sql.functions = pyspark_sql_functions
    pyspark_sql.types = pyspark_sql_types

    for name, obj in [
        ("pyspark", pyspark),
        ("pyspark.sql", pyspark_sql),
        ("pyspark.sql.functions", pyspark_sql_functions),
        ("pyspark.sql.types", pyspark_sql_types),
    ]:
        monkeypatch.setitem(sys.modules, name, obj)

    pyspark_sql_functions.col = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.lit = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.lower = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.unix_timestamp = lambda *a, **kw: _ColExpr()
    pyspark_sql_functions.desc = lambda *a, **kw: _ColExpr()

    pyspark_sql.SparkSession = MagicMock(name="SparkSession")
    pyspark_sql.DataFrame = MagicMock(name="DataFrame")
