"""tests/bronze/conftest.py — Fixtures for bronze layer tests."""
import os
import socket
import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """Fail any test that attempts a real network connection.

    This guard ensures all tests in tests/bronze are hermetic — no DNS
    resolution, no TCP connects.  Tests must use FakeHttpClient or
    monkeypatch the HTTP layer.
    """
    _orig_connect = socket.socket.connect

    def _guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) else str(address)
        # Allow loopback connections (some tests may use localhost)
        if host in ("127.0.0.1", "::1", "localhost"):
            return _orig_connect(self, address, *args, **kwargs)
        raise RuntimeError(
            f"Network access blocked in tests/bronze: attempted connect to {host}. "
            "Use FakeHttpClient or monkeypatch the HTTP layer."
        )

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    yield


@pytest.fixture(autouse=True)
def _isolate_sec_cache(tmp_path, monkeypatch):
    """Prevent tests from polluting the real /tmp/sec_cache fallback path.

    Every test that touches the CIK cache gets its own tmp_path-based cache
    directory, so no test can accidentally write a small company_tickers.json
    into the production fallback path.
    """
    # Create a test-specific cache directory
    test_cache_dir = str(tmp_path / "sec_cache")
    os.makedirs(test_cache_dir, exist_ok=True)

    # Patch tempfile.gettempdir to return tmp_path so the fallback path
    # in ingest_sec_companyfacts.py uses the test's isolated directory
    original_gettempdir = tempfile.gettempdir

    def mock_gettempdir():
        return str(tmp_path)

    monkeypatch.setattr(tempfile, "gettempdir", mock_gettempdir)
    yield