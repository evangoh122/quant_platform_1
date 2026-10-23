"""The installed Polars must provide the keywords the estimators rely on.

The layer passes ``min_samples`` to ``ewm_mean``, ``ewm_var``, ``rolling_std``
and ``rolling_map``; those keywords exist from Polars 1.21.0.  On an older
release every estimator would fail deep inside the expression, so these guards
fail first with a message naming the required version.

The floor declared in ``pyproject.toml`` must cover the version ``risk/README.md``
documents for this layer.  Both floors are parsed from those files rather than
copied here, so moving one without the other fails the suite instead of shipping
a lock that installs a Polars the layer cannot use.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import polars as pl

MINIMUM_POLARS = "1.21.0"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_RISK_README = _REPO_ROOT / "risk" / "README.md"

# A ``polars`` entry in ``[project].dependencies``: ``polars>=1.21.0`` (an extra
# such as ``polars[rt64]>=1.21.0`` is accepted too).
_DEPENDENCY_FLOOR = re.compile(
    r"^polars\s*(?:\[[^\]]*\])?\s*>=\s*(?P<version>\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
# The documented requirement in ``risk/README.md``: ``polars >= 1.21.0``.
_README_FLOOR = re.compile(
    r"polars\s*>=\s*(?P<version>\d+(?:\.\d+)*)", re.IGNORECASE
)


def _version(text: str) -> tuple[int, ...]:
    """Numeric release parts, padded so that ``1.21`` == ``1.21.0``."""
    parts = [int(part) for part in text.split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


def _pyproject_polars_floor() -> str:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    matches = [
        match.group("version")
        for spec in data["project"]["dependencies"]
        if (match := _DEPENDENCY_FLOOR.match(spec.strip()))
    ]
    assert matches, (
        "pyproject.toml [project].dependencies declares no 'polars>=<floor>'"
    )
    assert len(set(matches)) == 1, (
        f"ambiguous polars floors in pyproject.toml: {matches}"
    )
    return matches[0]


def _readme_polars_floor() -> str:
    matches = _README_FLOOR.findall(_RISK_README.read_text(encoding="utf-8"))
    assert matches, (
        "risk/README.md must document the layer's floor, "
        "e.g. 'Requires `polars >= 1.21.0`'"
    )
    assert len(set(matches)) == 1, (
        f"ambiguous polars floors in risk/README.md: {matches}"
    )
    return matches[0]


def test_pyproject_polars_floor_covers_the_risk_readme_requirement() -> None:
    declared = _pyproject_polars_floor()
    documented = _readme_polars_floor()
    assert _version(declared) >= _version(documented), (
        f"pyproject.toml declares polars>={declared} but risk/README.md documents "
        f"polars>={documented}: uv sync could install a Polars without min_samples"
    )


def test_guard_message_names_the_documented_floor() -> None:
    documented = _readme_polars_floor()
    assert _version(MINIMUM_POLARS) == _version(documented), (
        f"MINIMUM_POLARS is {MINIMUM_POLARS} but risk/README.md documents "
        f"{documented}"
    )


def test_installed_polars_supports_min_samples_on_ewm_and_rolling() -> None:
    frame = pl.DataFrame({"x": [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0, 8.0]})
    try:
        out = frame.select(
            pl.col("x").ewm_mean(span=3, adjust=False, min_samples=3).alias("m"),
            pl.col("x")
            .ewm_var(bias=False, span=3, adjust=False, min_samples=3)
            .alias("v"),
            pl.col("x")
            .rolling_std(window_size=3, min_samples=3, ddof=1)
            .alias("r"),
        )
    except TypeError as exc:  # pragma: no cover - only on an old Polars
        raise AssertionError(
            f"risk/ requires polars >= {MINIMUM_POLARS}: ewm_mean/ewm_var/"
            f"rolling_std must accept min_samples (installed polars "
            f"{pl.__version__}): {exc}"
        ) from exc
    assert out.height == frame.height
    # min_samples really gates the output: the first rows stay null.
    assert out["m"].null_count() > 0
    assert out["r"].null_count() > 0


def test_installed_polars_supports_min_samples_on_rolling_map() -> None:
    frame = pl.DataFrame({"x": [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0, 8.0]})
    try:
        out = frame.select(
            pl.col("x")
            .rolling_map(
                lambda window: window.mean(), window_size=3, min_samples=3
            )
            .alias("p")
        )
    except TypeError as exc:  # pragma: no cover - only on an old Polars
        raise AssertionError(
            f"risk/ requires polars >= {MINIMUM_POLARS}: rolling_map must "
            f"accept min_samples (installed polars {pl.__version__}): {exc}"
        ) from exc
    assert out.height == frame.height
    assert out["p"].null_count() > 0
