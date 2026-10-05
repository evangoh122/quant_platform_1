"""Tests for scripts/check_schema_contract.py sys.path and LIMIT fixes."""
from __future__ import annotations

import subprocess
import sys


def test_script_importable_from_repo_root():
    """Running as ``python3 scripts/check_schema_contract.py --help`` must not
    raise ModuleNotFoundError for ``db``.

    MUTATION: remove sys.path insert → subprocess exits with ImportError.
    """
    result = subprocess.run(
        [sys.executable, "scripts/check_schema_contract.py", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "Check schema contract drift" in result.stdout