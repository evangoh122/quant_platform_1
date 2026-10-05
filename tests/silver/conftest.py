"""tests/silver/conftest.py — Fixtures for silver layer tests."""
import socket

import pytest


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """Fail any test that attempts a real network connection.

    This guard ensures all tests in tests/silver are hermetic — no DNS
    resolution, no TCP connects. Tests must use in-memory fixtures
    (DuckDB, mock DataFrames, etc.).
    """
    _orig_connect = socket.socket.connect

    def _guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) else str(address)
        # Allow loopback connections (some tests may use localhost)
        if host in ("127.0.0.1", "::1", "localhost"):
            return _orig_connect(self, address, *args, **kwargs)
        raise RuntimeError(
            f"Network access blocked in tests/silver: attempted connect to {host}. "
            "Use in-memory fixtures (DuckDB, mock DataFrames, etc.)."
        )

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    yield