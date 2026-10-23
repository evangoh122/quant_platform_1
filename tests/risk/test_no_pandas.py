"""Guard: the risk layer is Polars-only.

The forbidden module name is assembled at runtime so this file is not its own
first match, and the check only inspects Python sources (README prose may name
the forbidden bridge when explaining that it is absent).
"""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_IMPORT = "pan" + "das"
FORBIDDEN_BRIDGE = "to_" + "pan" + "das"


def _sources() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    package = sorted((root / "risk").rglob("*.py"))
    package_tests = sorted((root / "tests" / "risk").rglob("*.py"))
    own_file = Path(__file__).resolve()
    return [
        path
        for path in package + package_tests
        if path.resolve() != own_file
    ]


def test_no_dataframe_bridge_in_risk_sources() -> None:
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN_IMPORT in text or FORBIDDEN_BRIDGE in text:
            offenders.append(path.name)
    assert offenders == []


def test_guard_actually_scans_sources() -> None:
    # A vacuous guard (empty glob) would pass the test above.
    names = {path.name for path in _sources()}
    assert "estimators.py" in names
    assert Path(__file__).name not in names
