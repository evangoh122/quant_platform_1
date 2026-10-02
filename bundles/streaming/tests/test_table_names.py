"""Static guard: every table the streaming pipeline declares is prefixed ``dlt_``
and none of them equals a real (production) table name.

This is the offline counterpart of the build request's "your pipeline must never own
or write a real table" rule. It parses the transformation source files and asserts
exactly the five expected ``dlt_`` tables are declared, and that none collides with a
production table.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from pipelines.streaming import helpers

_TRANSFORMATIONS_DIR = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "pipelines" / "streaming" / "transformations"
)

_EXPECTED_TABLES = {
    "dlt_bronze_ohlcv_stream",
    "dlt_silver_ohlcv",
    "dlt_silver_ohlcv_quarantine",
    "dlt_gold_ohlcv_features",
    "dlt_latency_metrics",
}

# Matches the ``name="..."`` / ``name='...'`` argument of a ``@dp.table`` /
# ``@dp.materialized_view`` / ``@dp.view`` decorator.
_NAME_RE = re.compile(r"name\s*=\s*[\"']([^\"']+)[\"']")


def _declared_table_names() -> set[str]:
    names: set[str] = set()
    files = sorted(_TRANSFORMATIONS_DIR.glob("*.py"))
    assert files, f"no transformation files found under {_TRANSFORMATIONS_DIR}"
    for path in files:
        text = path.read_text(encoding="utf-8")
        names.update(_NAME_RE.findall(text))
    return names


def test_every_declared_table_is_prefixed_dlt():
    names = _declared_table_names()
    assert names, "no @dp.table/@dp.materialized_view declarations found"
    for name in names:
        assert name.startswith("dlt_"), f"table {name!r} is not prefixed dlt_"


def test_declared_tables_match_the_expected_five():
    assert _declared_table_names() == _EXPECTED_TABLES


def test_no_declared_table_collides_with_a_real_table():
    real = set(helpers.REAL_TABLE_NAMES)
    for name in _declared_table_names():
        assert name not in real, f"table {name!r} would write a real production table"


def test_real_table_names_are_not_prefixed_dlt():
    # If a real table ever gained a dlt_ prefix the static guard would miss it.
    for name in helpers.REAL_TABLE_NAMES:
        assert not name.startswith("dlt_")
