"""tests/agent/test_pyspark_leak.py — prove fake_pyspark fixture does not leak.

Each test drives the REAL conftest ``fake_pyspark`` fixture in a FRESH
subprocess interpreter so module-level state cannot bleed across tests.

Two scenarios are covered:
  * **nospark** — pyspark is blocked by a stub; after teardown
    ``_has_pyspark`` must be ``False`` and ``F`` must not exist.
  * **pyspark-available** — a minimal pyspark stub is importable; after
    teardown the ORIGINAL values are restored (``_has_pyspark is True``,
    ``F`` is the real stub, not the fixture's fake).

A final test proves the harness is real: a buggy conftest (inject fakes
BEFORE importing the adapter) MUST fail, making mutation M1 detectable.

Mechanism: the real ``tests/agent/conftest.py`` is symlinked into each
``tmp_path/conftest.py`` so pytest auto-discovers it alongside the
subprocess test module.  ``--confcutdir=<tmp_path>`` prevents pytest
from also picking up the repo-root conftest files.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


_REPO_ROOT = str(Path(__file__).resolve().parents[2])
_REAL_CONFTEST = Path(__file__).resolve().parent / "conftest.py"


# ── helpers ───────────────────────────────────────────────────────────────────


def _link_conftest(tmp_path: Path) -> None:
    """Symlink the real conftest.py into tmp_path."""
    dest = tmp_path / "conftest.py"
    if not dest.exists():
        dest.symlink_to(_REAL_CONFTEST)


def _write_test_module(tmp_path: Path) -> Path:
    """Write a two-test module that exercises the REAL fake_pyspark fixture.

    test_a requests the fixture and asserts fakes are active.
    test_b (no fixture) asserts clean state after teardown.
    """
    test_file = tmp_path / "test_fixture_leak.py"
    test_file.write_text(textwrap.dedent('''\
        """Subprocess test module: exercise the real fake_pyspark fixture."""
        import db.delta_adapter as da


        def test_a(fake_pyspark):
            """Fixture is active: _has_pyspark=True and F exists."""
            assert da._has_pyspark is True, (
                f"During fixture: expected _has_pyspark=True, got {da._has_pyspark}"
            )
            assert hasattr(da, "F"), "During fixture: F should exist"
            assert da.F is not None, "During fixture: F should not be None"


        def test_b():
            """After teardown: state must reflect the REAL environment."""
            assert da._has_pyspark is False, (
                f"After teardown: _has_pyspark leaked as {da._has_pyspark}"
            )
            assert not hasattr(da, "F"), (
                f"After teardown: F leaked as {getattr(da, 'F', 'MISSING')}"
            )
            import sys
            assert "pyspark" not in sys.modules, (
                "After teardown: pyspark leaked in sys.modules"
            )
    '''))
    return test_file


def _write_pyspark_available_test_module(tmp_path: Path) -> Path:
    """Write a two-test module for the pyspark-IS-importable case.

    test_a requests the fixture and asserts fakes are active.
    test_b asserts the ORIGINAL pyspark values are restored after teardown.
    """
    test_file = tmp_path / "test_fixture_leak_pyspark.py"
    test_file.write_text(textwrap.dedent('''\
        """Subprocess test: pyspark-available — originals restored after teardown."""
        import db.delta_adapter as da
        import sys


        def test_a(fake_pyspark):
            """Fixture is active: _has_pyspark=True and F is the fake."""
            assert da._has_pyspark is True, (
                f"During fixture: expected _has_pyspark=True, got {da._has_pyspark}"
            )
            assert hasattr(da, "F"), "During fixture: F should exist"


        def test_b():
            """After teardown: original pyspark values restored exactly."""
            assert da._has_pyspark is True, (
                f"After teardown: _has_pyspark should be True (pyspark available), "
                f"got {da._has_pyspark}"
            )
            assert hasattr(da, "F"), "After teardown: F should exist (pyspark available)"
            # F must be the REAL pyspark.sql.functions, not the fixture fake.
            # The real stub exposes a col() function; the fake's col returns _FakeCol.
            real_F = sys.modules.get("pyspark.sql.functions")
            assert real_F is not None, "pyspark.sql.functions should be in sys.modules"
            assert da.F is real_F, (
                "After teardown: F should be the original pyspark.sql.functions, "
                "not the fixture fake"
            )
    '''))
    return test_file


def _make_nospark_blocker(tmp_path: Path) -> Path:
    """Create a pyspark-blocking stub package under tmp_path/blocker."""
    blocker_dir = tmp_path / "blocker"
    blocker_dir.mkdir(exist_ok=True)
    pyspark_pkg = blocker_dir / "pyspark"
    pyspark_pkg.mkdir(exist_ok=True)
    (pyspark_pkg / "__init__.py").write_text(
        'raise ModuleNotFoundError("No module named \'pyspark\'", name="pyspark")\n'
    )
    return blocker_dir


def _make_pyspark_stub(tmp_path: Path) -> Path:
    """Create a minimal pyspark stub package under tmp_path/pyspark_stub.

    Provides pyspark, pyspark.sql (with SparkSession, DataFrame stubs), and
    pyspark.sql.functions (with a real col() that returns a simple object).
    """
    stub_dir = tmp_path / "pyspark_stub"
    stub_dir.mkdir(exist_ok=True)

    # pyspark/__init__.py
    pyspark_pkg = stub_dir / "pyspark"
    pyspark_pkg.mkdir(exist_ok=True)
    (pyspark_pkg / "__init__.py").write_text("")

    # pyspark/sql/__init__.py
    sql_pkg = pyspark_pkg / "sql"
    sql_pkg.mkdir(exist_ok=True)
    (sql_pkg / "__init__.py").write_text(
        "class SparkSession: pass\n"
        "class DataFrame: pass\n"
    )

    # pyspark/sql/functions.py — minimal stub with col()
    functions_py = textwrap.dedent("""\
        class _StubCol:
            def __init__(self, name=""):
                self._name = name
            def desc(self):
                return _StubCol(self._name)
            def asc(self):
                return _StubCol(self._name)
            def alias(self, a):
                return _StubCol(a)
            def __str__(self):
                return f"StubCol<{self._name}>"

        def col(name):
            return _StubCol(name)

        def lit(v):
            return v

        def lower(c):
            return c

        def unix_timestamp(c=None):
            return c
    """)
    (sql_pkg / "functions.py").write_text(functions_py)

    return stub_dir


def _run_pytest_subprocess(
    test_file: Path,
    pythonpath: str,
    *,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Run pytest in a subprocess against *test_file*.

    ``--confcutdir`` is set to the test file's parent (tmp_path) so that
    the symlinked conftest.py is the ONLY conftest discovered.
    """
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "--confcutdir", str(test_file.parent),
        "-p", "no:cacheprovider",
        "-q",
    ]
    if extra_args:
        cmd.extend(extra_args)

    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath
    env.pop("PYSPARK_PYTHON", None)
    env.pop("PYSPARK_DRIVER_PYTHON", None)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=_REPO_ROOT,
        timeout=60,
    )


# ── tests ─────────────────────────────────────────────────────────────────────


class TestRealFixtureNospark:
    """Subprocess tests: pyspark is blocked; fixture must restore _has_pyspark=False."""

    def test_fixture_restores_clean_state_nospark(self, tmp_path):
        """After fixture teardown in a nospark env, _has_pyspark must be False
        and F must not exist.  This is the primary leak detection test."""
        _link_conftest(tmp_path)
        test_file = _write_test_module(tmp_path)
        blocker_dir = _make_nospark_blocker(tmp_path)
        pythonpath = str(blocker_dir) + os.pathsep + _REPO_ROOT

        result = _run_pytest_subprocess(test_file, pythonpath)

        assert result.returncode == 0, (
            f"Subprocess pytest failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "2 passed" in result.stdout, (
            f"Expected '2 passed' in output:\n{result.stdout}"
        )


class TestRealFixturePysparkAvailable:
    """Subprocess tests: pyspark stub is importable; fixture must restore originals."""

    def test_fixture_restores_originals_pyspark_available(self, tmp_path):
        """After fixture teardown when pyspark IS available, the original
        _has_pyspark=True and the real F (not the fake) must be restored."""
        _link_conftest(tmp_path)
        test_file = _write_pyspark_available_test_module(tmp_path)
        pyspark_stub = _make_pyspark_stub(tmp_path)
        pythonpath = str(pyspark_stub) + os.pathsep + _REPO_ROOT

        result = _run_pytest_subprocess(test_file, pythonpath)

        assert result.returncode == 0, (
            f"Subprocess pytest failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "2 passed" in result.stdout, (
            f"Expected '2 passed' in output:\n{result.stdout}"
        )


class TestHarnessIsReal:
    """Prove the subprocess harness actually uses the real conftest fixture.

    A buggy conftest (inject fakes BEFORE importing the adapter) must FAIL
    because monkeypatch saves the wrong old value (_has_pyspark=True) and
    restores it after teardown, leaving a leak.
    """

    def test_buggy_conftest_must_fail(self, tmp_path):
        """Mutation M1 proof: a buggy conftest that injects fakes before
        importing the adapter MUST fail the leak assertion."""
        blocker_dir = _make_nospark_blocker(tmp_path)

        # Write a buggy conftest that injects fakes BEFORE importing adapter.
        buggy_conftest = tmp_path / "conftest.py"
        buggy_conftest.write_text(textwrap.dedent('''\
            """Buggy conftest: inject fakes BEFORE importing adapter (mutation M1)."""
            import sys
            from types import ModuleType
            from unittest.mock import MagicMock
            import pytest

            class _FakeCol:
                def __init__(self, name="", _desc=False):
                    self._name = name
                    self._desc = _desc
                def desc(self):
                    return _FakeCol(self._name, _desc=True)
                def asc(self):
                    return _FakeCol(self._name, _desc=False)
                def alias(self, a):
                    return _FakeCol(a, self._desc)
                def __str__(self):
                    d = "DESC" if self._desc else "ASC"
                    return f"Column<{self._name} {d}>"

            # BUG: inject fakes BEFORE importing the adapter
            pyspark_mod = ModuleType("pyspark")
            pyspark_sql_mod = ModuleType("pyspark.sql")
            pyspark_sql_mod.SparkSession = MagicMock()
            pyspark_sql_mod.DataFrame = MagicMock()
            functions_mod = ModuleType("pyspark.sql.functions")
            functions_mod.col = lambda name: _FakeCol(name)
            functions_mod.lit = lambda v: v
            functions_mod.lower = lambda col: col
            functions_mod.unix_timestamp = lambda col=None: col
            pyspark_mod.sql = pyspark_sql_mod
            pyspark_sql_mod.functions = functions_mod

            sys.modules["pyspark"] = pyspark_mod
            sys.modules["pyspark.sql"] = pyspark_sql_mod
            sys.modules["pyspark.sql.functions"] = functions_mod

            # NOW import adapter — it sees fakes and caches _has_pyspark=True
            import db.delta_adapter as _da
            import agent.tools_retrieval  # noqa: F401

            @pytest.fixture
            def fake_pyspark(monkeypatch):
                monkeypatch.setitem(sys.modules, "pyspark", pyspark_mod)
                monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql_mod)
                monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_mod)
                monkeypatch.setattr(_da, "_has_pyspark", True, raising=False)
                monkeypatch.setattr(_da, "F", functions_mod, raising=False)
                return pyspark_mod, pyspark_sql_mod, functions_mod
        '''))

        test_file = _write_test_module(tmp_path)
        pythonpath = str(blocker_dir) + os.pathsep + _REPO_ROOT

        result = _run_pytest_subprocess(test_file, pythonpath)

        # The buggy conftest must FAIL because _has_pyspark leaks as True.
        assert result.returncode != 0, (
            f"Buggy conftest should have failed but passed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "_has_pyspark" in combined, (
            f"Failure message should mention _has_pyspark:\n{combined}"
        )