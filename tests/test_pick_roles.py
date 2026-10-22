"""Role-routing contract for .agents/pick-roles.sh (see AGENTS.md "Role routing")."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / ".agents" / "pick-roles.sh"
MIMO_CODES = "mimo deepseek"
DEEPSEEK_CODES = "dsbuild mimoval"


def _pick(hour: int, **env: str) -> str:
    e = {k: v for k, v in os.environ.items() if k != "QP1_CODER"}
    e.update(env)
    out = subprocess.run(
        ["bash", str(SCRIPT), str(hour)], capture_output=True, text=True, env=e, check=True
    )
    return out.stdout.strip()


@pytest.mark.parametrize("hour", [1, 2, 3, 6, 7, 8, 9])
def test_mimo_codes_while_deepseek_is_in_peak(hour):
    assert _pick(hour) == MIMO_CODES


@pytest.mark.parametrize("hour", [0, 4, 5, 10, 12, 15, 16, 20, 23])
def test_deepseek_codes_while_deepseek_is_off_peak(hour):
    assert _pick(hour) == DEEPSEEK_CODES


@pytest.mark.parametrize("hour", [3, 20])
def test_owner_override_wins(hour):
    assert _pick(hour, QP1_CODER="mimo") == MIMO_CODES
    assert _pick(hour, QP1_CODER="deepseek") == DEEPSEEK_CODES


def test_leading_zero_hours_are_not_octal():
    assert _pick("08") == MIMO_CODES and _pick("09") == MIMO_CODES


@pytest.mark.parametrize("bad_hour", ["abc", "24", "-1", "7x", "", "1.5"])
def test_invalid_hour_is_a_usage_error(bad_hour):
    """Only an integer 0-23 is a UTC hour; everything else exits 2 with no role line."""
    e = {k: v for k, v in os.environ.items() if k != "QP1_CODER"}
    out = subprocess.run(
        ["bash", str(SCRIPT), bad_hour], capture_output=True, text=True, env=e
    )
    assert out.returncode == 2
    assert out.stdout.strip() == ""
    assert out.stderr.strip() != ""
