import re
from pathlib import Path

PLAN = Path(__file__).resolve().parents[2] / "docs" / "MFT_STRATEGY_PLAN.md"


def _plan_text() -> str:
    return PLAN.read_text(encoding="utf-8")


def _decision_row(label: str) -> str:
    for line in _plan_text().splitlines():
        if line.startswith(f"| **{label}** |"):
            return line
    raise AssertionError(f"missing decision row: {label}")


def _section(heading: str) -> str:
    text = _plan_text()
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = re.search(r"\n#{2,4} ", rest)
    return rest[: end.start()] if end else rest


def test_risk_budget_is_not_worded_as_a_guarantee():
    text = _plan_text()

    assert "built in through stops" not in text.lower()

    cap_row = _decision_row("Per-trade risk cap: 0.5% of portfolio equity")
    assert "modelled loss budget" in cap_row.lower()
    assert "not a guaranteed realised-loss ceiling" in cap_row.lower()
    assert "$1,000" in cap_row
    assert "0.5%" in cap_row
    assert "Defined-risk options spreads now fit" in cap_row
    assert "paper-eligible" in cap_row
    assert not re.search(r"worst-case loss[^|]{0,120}may exceed 0\.5%", cap_row, re.I)

    stop_row = _decision_row("Mandatory stop-loss on every trade")
    assert "sized into every trade" in stop_row.lower()
    assert "cannot guarantee execution through gaps, halts or liquidity failures" in stop_row.lower()

    section = " ".join(_section("### 10.1a Per-trade risk cap").split()).lower()
    assert "modelled loss budget" in section
    assert "not a guaranteed realised-loss ceiling" in section
    assert "stops cannot guarantee execution through gaps, halts or liquidity failures" in section

    heading = next(
        line for line in text.splitlines() if line.startswith("### 10.1b Mandatory stop-losses")
    )
    assert "built in" not in heading.lower()
    assert "sized into trades through stops" in heading.lower()
