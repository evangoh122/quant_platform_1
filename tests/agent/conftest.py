"""tests/agent/conftest.py — shared fixtures for agent ordering tests."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


class _FakeCol:
    """Stub Column whose str includes column name and direction marker."""

    def __init__(self, name: str = "", _desc: bool = False):
        self._name = name
        self._desc = _desc

    def desc(self):
        return _FakeCol(self._name, _desc=True)

    def asc(self):
        return _FakeCol(self._name, _desc=False)

    def alias(self, alias):
        return _FakeCol(alias, self._desc)

    def between(self, low, high):
        return _FakeCol(self._name, self._desc)

    def __eq__(self, other):
        return _FakeCol(self._name, self._desc)

    def __gt__(self, other):
        return _FakeCol(self._name, self._desc)

    def __lt__(self, other):
        return _FakeCol(self._name, self._desc)

    def __ge__(self, other):
        return _FakeCol(self._name, self._desc)

    def __le__(self, other):
        return _FakeCol(self._name, self._desc)

    def __and__(self, other):
        return _FakeCol(f"{self._name} & {other}", self._desc)

    def __or__(self, other):
        return _FakeCol(f"{self._name} | {other}", self._desc)

    def __str__(self):
        direction = " DESC" if self._desc else " ASC"
        return f"Column<{self._name}{direction}>"

    def __repr__(self):
        return self.__str__()


def _fake_col(name: str):
    return _FakeCol(name)


@pytest.fixture
def fake_pyspark(monkeypatch):
    """Inject stub pyspark modules so ordering tests work without real pyspark.

    Creates ``pyspark``, ``pyspark.sql``, and ``pyspark.sql.functions`` in
    ``sys.modules`` with a ``col()`` that returns a chainable stub whose
    ``str`` includes the column name and direction marker (DESC/ASC).
    Patches ``db.delta_adapter._has_pyspark`` and ``db.delta_adapter.F`` so
    the PySpark branches execute.
    """
    pyspark_mod = ModuleType("pyspark")
    pyspark_sql_mod = ModuleType("pyspark.sql")
    pyspark_sql_mod.SparkSession = MagicMock()
    pyspark_sql_mod.DataFrame = MagicMock()

    functions_mod = ModuleType("pyspark.sql.functions")
    functions_mod.col = _fake_col
    functions_mod.lit = lambda v: v
    functions_mod.lower = lambda col: col
    functions_mod.unix_timestamp = lambda col=None: col

    pyspark_mod.sql = pyspark_sql_mod
    pyspark_sql_mod.functions = functions_mod

    monkeypatch.setitem(sys.modules, "pyspark", pyspark_mod)
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql_mod)
    monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_mod)

    import db.delta_adapter as _da

    monkeypatch.setattr(_da, "_has_pyspark", True, raising=False)
    monkeypatch.setattr(_da, "F", functions_mod, raising=False)

    return pyspark_mod, pyspark_sql_mod, functions_mod