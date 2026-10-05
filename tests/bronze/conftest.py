"""tests/bronze/conftest.py — Fixtures for bronze layer tests."""
import os
import tempfile
from unittest.mock import patch

import pytest


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