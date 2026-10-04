import sys
import hashlib
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pytest

from tests.rag._netguard import _is_loopback, install_default_timeout


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

    Also installs a deterministic fake embedding provider so no HuggingFace
    download or sentence-transformers model load occurs in tests/rag.
    """
    import api.services.embeddings as emb_mod
    import api.services.hybrid_retriever as hr

    class _FakeEmbeddingProvider:
        """Hash-seeded deterministic vectors of the correct dimension (384)."""
        _dim = 384

        def _vec_for(self, text: str) -> list[float]:
            seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
            rng = np.random.RandomState(seed)
            v = rng.randn(self._dim).astype(np.float32)
            norm = np.linalg.norm(v)
            if norm > 0:
                v = v / norm
            return v.tolist()

        def embed_query(self, text: str) -> list[float]:
            return self._vec_for(text)

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [self._vec_for(t) for t in texts]

    # --- before ---
    emb_mod._embeddings = _FakeEmbeddingProvider()

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
def _block_network(monkeypatch, request):
    """Prevent any test from accidentally hitting the network or running slow models.

    HuggingFace model downloads, cross-encoder loads, and other network
    calls must be mocked at a higher level.  This guard makes accidental
    network access fail fast with a clear error instead of stalling.
    Also disables the cross-encoder reranker to keep tests fast — tests
    that need reranking should mock it explicitly.
    """
    import socket

    # Socket-level safety timeout so a broken guard fails fast instead of
    # hanging indefinitely (defense-in-depth alongside pytest-timeout).
    # Scoped: restore the previous value on teardown so it doesn't leak
    # to tests outside this module.
    install_default_timeout(request.addfinalizer, 10)

    _real_create_connection = socket.create_connection
    _real_socket_connect = socket.socket.connect
    _real_socket_connect_ex = socket.socket.connect_ex
    _real_getaddrinfo = socket.getaddrinfo

    def _fail_create_connection(address, *args, **kwargs):
        host, port = address
        if _is_loopback(host):
            return _real_create_connection(address, *args, **kwargs)
        raise ConnectionRefusedError(
            f"Network access blocked in tests (attempted {host}:{port}). "
            f"Mock the call or use monkeypatch to allow."
        )

    _has_af_unix = hasattr(socket, "AF_UNIX")

    def _extract_host_port(address, sock_family):
        """Extract host and port from address tuple by socket family."""
        if _has_af_unix and sock_family == socket.AF_UNIX:
            # AF_UNIX: address is a str or bytes path
            return None, None
        if sock_family == socket.AF_INET6:
            # AF_INET6: (host, port, flow, scope)
            return address[0], address[1] if len(address) > 1 else 0
        # AF_INET (default): (host, port)
        return address[0], address[1] if len(address) > 1 else 0

    def _fail_socket_connect(self, address, *args, **kwargs):
        # AF_UNIX sockets are always allowed (local IPC, no network)
        if _has_af_unix and self.family == socket.AF_UNIX:
            return _real_socket_connect(self, address, *args, **kwargs)
        host, port = _extract_host_port(address, self.family)
        if _is_loopback(host):
            return _real_socket_connect(self, address, *args, **kwargs)
        raise ConnectionRefusedError(
            f"Network access blocked in tests (socket.connect to {host}:{port}). "
            f"Mock the call or use monkeypatch to allow."
        )

    def _fail_socket_connect_ex(self, address, *args, **kwargs):
        # AF_UNIX sockets are always allowed (local IPC, no network)
        if _has_af_unix and self.family == socket.AF_UNIX:
            return _real_socket_connect_ex(self, address, *args, **kwargs)
        host, port = _extract_host_port(address, self.family)
        if _is_loopback(host):
            return _real_socket_connect_ex(self, address, *args, **kwargs)
        raise ConnectionRefusedError(
            f"Network access blocked in tests (socket.connect_ex to {host}:{port}). "
            f"Mock the call or use monkeypatch to allow."
        )

    def _fail_getaddrinfo(host, port, *args, **kwargs):
        # getaddrinfo(None, ...) is passive (used for bind) — always allow
        if host is None or _is_loopback(host):
            return _real_getaddrinfo(host, port, *args, **kwargs)
        raise ConnectionRefusedError(
            f"Network access blocked in tests (getaddrinfo for {host}:{port}). "
            f"Mock the call or use monkeypatch to allow."
        )

    monkeypatch.setattr(socket, "create_connection", _fail_create_connection)
    monkeypatch.setattr(socket.socket, "connect", _fail_socket_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _fail_socket_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", _fail_getaddrinfo)

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
