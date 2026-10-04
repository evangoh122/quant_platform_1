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
]

mock_if_missing(problematic_modules)

# We don't globally mock api.config.Config here as it breaks Config tests.
# If a specific test needs it mocked, it should do so itself.


@pytest.fixture(autouse=True)
def _reset_retriever_singletons():
    """Reset embedding and retriever singletons before and after each test.

    Earlier tests that monkeypatch EMBEDDING_PROVIDER and then importlib.reload
    leave a cached _embeddings object in the *old* module reference.  Subsequent
    tests hit that stale singleton and fail with EmbeddingConfigError.
    Clearing the cache forces get_embeddings() to re-evaluate on every test.
    """
    import api.services.embeddings as emb_mod
    import api.services.hybrid_retriever as hr

    # --- before ---
    emb_mod._embeddings = None

    hr._corpus_loaded = False
    hr._corpus.clear()
    hr._bm25_docs = None
    hr._bm25_tokenised = None
    hr._bm25_index = None
    hr._embeddings_map.clear()
    hr._stored_index_dim = None
    hr._stored_embedding_model = None

    yield

    # --- after ---
    emb_mod._embeddings = None

    hr._corpus_loaded = False
    hr._corpus.clear()
    hr._bm25_docs = None
    hr._bm25_tokenised = None
    hr._bm25_index = None
    hr._embeddings_map.clear()
    hr._stored_index_dim = None
    hr._stored_embedding_model = None


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """Prevent any test from accidentally hitting the network or running slow models.

    HuggingFace model downloads, cross-encoder loads, and other network
    calls must be mocked at a higher level.  This guard makes accidental
    network access fail fast with a clear error instead of stalling.
    Also disables the cross-encoder reranker to keep tests fast — tests
    that need reranking should mock it explicitly.
    """
    import socket

    _real_create_connection = socket.create_connection

    def _fail_create_connection(address, *args, **kwargs):
        host, port = address
        raise ConnectionRefusedError(
            f"Network access blocked in tests (attempted {host}:{port}). "
            f"Mock the call or use monkeypatch to allow."
        )

    monkeypatch.setattr(socket, "create_connection", _fail_create_connection)

    # Disable cross-encoder reranker in all tests for speed.
    # _get_model returning None makes rerank() return docs[:top_k] unchanged.
    import api.services.reranker as reranker_mod
    monkeypatch.setattr(reranker_mod, "_get_model", lambda *a, **kw: None)


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
