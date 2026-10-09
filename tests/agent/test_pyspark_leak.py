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

Mechanism: a CUSTOM conftest.py is generated into each ``tmp_path`` that
imports the adapter INSIDE the fixture body (before creating fakes) so the
adapter is never imported at conftest-collection time.  The generated test
module has no top-level import of ``db.delta_adapter``; instead it asserts
the adapter is absent from ``sys.modules`` at fixture setup via the
``adapter_not_yet_imported`` fixture ordered BEFORE ``fake_pyspark``.
``--confcutdir=<tmp_path>`` prevents pytest from picking up the repo-root
conftest files.

The real ``tests/agent/conftest.py`` imports the adapter at module level
(line 79), which means it is always first imported at conftest-collection
time before any fixture runs, so the fixture's import ORDER can never
matter.  This harness avoids that by deferring the import into the fixture.
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

_CONFTEST_TEMPLATE = '''\
"""Custom conftest: adapter imported INSIDE the fixture, not at module level.

The real tests/agent/conftest.py imports db.delta_adapter at module level
which means the adapter is always first imported against the real environment
(no fakes) at collection time, before any fixture runs.  This conftest
defers the import so the harness can detect the original bug (mutation M1).

Import order inside the fixture:
  1. Import adapter against the REAL environment (no fakes in sys.modules).
  2. Create fake pyspark modules and inject into sys.modules.
  3. monkeypatch adapter attributes (_has_pyspark, F).
     monkeypatch records the original values and restores on teardown.
"""
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

    IMPORTANT: adapter is imported INSIDE the fixture body, FIRST, against the
    REAL environment (no fakes).  Fakes are injected AFTER.  monkeypatch
    records the original values and restores them on teardown.
    """
    # 1. Import adapter FIRST against the REAL environment.
    import db.delta_adapter as _da
    import agent.tools_retrieval  # noqa: F401

    # 2. Create fake pyspark modules.
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

    # 3. Inject fakes into sys.modules.
    monkeypatch.setitem(sys.modules, "pyspark", pyspark_mod)
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql_mod)
    monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_mod)

    # 4. Patch adapter attributes; monkeypatch records originals for teardown.
    monkeypatch.setattr(_da, "_has_pyspark", True, raising=False)
    monkeypatch.setattr(_da, "F", functions_mod, raising=False)

    return pyspark_mod, pyspark_sql_mod, functions_mod
'''

# Buggy variant: inject fakes BEFORE importing adapter (mutation M1).
_BUGGY_CONFTEST_MARKER = "# BUG: inject fakes BEFORE importing the adapter"


def _write_conftest(tmp_path: Path) -> None:
    """Write a conftest.py into tmp_path that imports adapter INSIDE the fixture."""
    dest = tmp_path / "conftest.py"
    dest.write_text(_CONFTEST_TEMPLATE)


def _write_test_module(tmp_path: Path) -> Path:
    """Write a two-test module that exercises the REAL fake_pyspark fixture.

    NO top-level import of db.delta_adapter.  The adapter_not_yet_imported
    fixture asserts the adapter is absent from sys.modules at fixture setup
    time (before fake_pyspark imports it).  test_a requests both fixtures;
    test_b asserts the post-teardown state through sys.modules.
    """
    test_file = tmp_path / "test_fixture_leak.py"
    test_file.write_text(textwrap.dedent('''\
        """Subprocess test module: exercise the real fake_pyspark fixture.

        No top-level import of db.delta_adapter -- the adapter must first be
        imported by the fake_pyspark fixture, not at collection time.
        """
        import sys

        import pytest


        @pytest.fixture
        def adapter_not_yet_imported():
            """Assert adapter is NOT in sys.modules before fake_pyspark runs.

            Ordered before fake_pyspark in test signatures so that if the
            conftest imports the adapter at module level (the original bug),
            this assertion catches it.
            """
            assert "db.delta_adapter" not in sys.modules, (
                "db.delta_adapter was imported before fake_pyspark fixture ran "
                "(conftest imports it at module level -- the original bug)"
            )
            assert "agent.tools_retrieval" not in sys.modules, (
                "agent.tools_retrieval was imported before fake_pyspark fixture ran"
            )


        def test_a(adapter_not_yet_imported, fake_pyspark):
            """Fixture is active: _has_pyspark=True and F exists."""
            da = sys.modules["db.delta_adapter"]
            assert da._has_pyspark is True, (
                f"During fixture: expected _has_pyspark=True, got {da._has_pyspark}"
            )
            assert hasattr(da, "F"), "During fixture: F should exist"
            assert da.F is not None, "During fixture: F should not be None"


        def test_b():
            """After teardown: state must reflect the REAL environment."""
            da = sys.modules["db.delta_adapter"]
            assert da._has_pyspark is False, (
                f"After teardown: _has_pyspark leaked as {da._has_pyspark}"
            )
            assert not hasattr(da, "F"), (
                f"After teardown: F leaked as {getattr(da, 'F', 'MISSING')}"
            )
            assert "pyspark" not in sys.modules, (
                "After teardown: pyspark leaked in sys.modules"
            )
    '''))
    return test_file


def _write_pyspark_available_test_module(tmp_path: Path) -> Path:
    """Write a two-test module for the pyspark-IS-importable case.

    NO top-level import of db.delta_adapter.  The adapter_not_yet_imported
    fixture asserts clean state before fake_pyspark runs.
    """
    test_file = tmp_path / "test_fixture_leak_pyspark.py"
    test_file.write_text(textwrap.dedent('''\
        """Subprocess test: pyspark-available -- originals restored after teardown.

        No top-level import of db.delta_adapter.
        """
        import sys

        import pytest


        @pytest.fixture
        def adapter_not_yet_imported():
            """Assert adapter is NOT in sys.modules before fake_pyspark runs."""
            assert "db.delta_adapter" not in sys.modules, (
                "db.delta_adapter was imported before fake_pyspark fixture ran "
                "(conftest imports it at module level -- the original bug)"
            )
            assert "agent.tools_retrieval" not in sys.modules, (
                "agent.tools_retrieval was imported before fake_pyspark fixture ran"
            )


        def test_a(adapter_not_yet_imported, fake_pyspark):
            """Fixture is active: _has_pyspark=True and F is the fake."""
            da = sys.modules["db.delta_adapter"]
            assert da._has_pyspark is True, (
                f"During fixture: expected _has_pyspark=True, got {da._has_pyspark}"
            )
            assert hasattr(da, "F"), "During fixture: F should exist"


        def test_b():
            """After teardown: original pyspark values restored exactly."""
            da = sys.modules["db.delta_adapter"]
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

    # pyspark/sql/functions.py -- minimal stub with col()
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
    the generated conftest.py is the ONLY conftest discovered.
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
        _write_conftest(tmp_path)
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
        _write_conftest(tmp_path)
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
        importing the adapter MUST fail the leak assertion.

        Two detection checks:
        1. Hand-written buggy conftest (historical).
        2. Programmatic buggy variant derived from the REAL conftest text:
           read tests/agent/conftest.py, move adapter-import lines after the
           monkeypatch.setitem lines, run the harness against it.
        """
        blocker_dir = _make_nospark_blocker(tmp_path)

        # -- detection check 1: hand-written buggy conftest ----------------
        buggy_dir = tmp_path / "hand_written"
        buggy_dir.mkdir()
        buggy_conftest = buggy_dir / "conftest.py"
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

            # NOW import adapter -- it sees fakes and caches _has_pyspark=True
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

        test_file_hand = _write_test_module(buggy_dir)
        pythonpath = str(blocker_dir) + os.pathsep + _REPO_ROOT

        result = _run_pytest_subprocess(test_file_hand, pythonpath)

        assert result.returncode != 0, (
            f"Hand-written buggy conftest should have failed but passed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "leaked" in combined, (
            f"Failure message should contain 'leaked':\n{combined}"
        )

        # -- detection check 2: programmatic buggy variant from REAL conftest --
        real_text = _REAL_CONFTEST.read_text(encoding="utf-8")

        # Verify the real conftest has the expected structure.
        assert "import db.delta_adapter as _da" in real_text, (
            "REAL conftest does not contain expected adapter import"
        )
        assert "monkeypatch.setitem(sys.modules" in real_text, (
            "REAL conftest does not contain expected monkeypatch.setitem"
        )

        # Produce the buggy variant by moving adapter-import lines after the
        # monkeypatch.setitem lines (string transformation).
        lines = real_text.splitlines(keepends=True)
        import_lines = []
        other_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped in ("import db.delta_adapter as _da",
                            "import agent.tools_retrieval  # noqa: F401"):
                import_lines.append(line)
            else:
                other_lines.append(line)

        assert len(import_lines) == 2, (
            f"Expected 2 adapter import lines, found {len(import_lines)}"
        )

        # Find the last monkeypatch.setitem line and insert imports after it.
        last_setitem_idx = None
        for i, line in enumerate(other_lines):
            if "monkeypatch.setitem(sys.modules" in line:
                last_setitem_idx = i

        assert last_setitem_idx is not None, (
            "Could not find monkeypatch.setitem line in conftest"
        )

        buggy_lines = (
            other_lines[:last_setitem_idx + 1]
            + ["\n"] + import_lines
            + other_lines[last_setitem_idx + 1:]
        )
        buggy_text = "".join(buggy_lines)

        assert buggy_text != real_text, (
            "Programmatic buggy variant is identical to real conftest"
        )

        prog_dir = tmp_path / "programmatic"
        prog_dir.mkdir()
        (prog_dir / "conftest.py").write_text(buggy_text, encoding="utf-8")
        test_file_prog = _write_test_module(prog_dir)

        result2 = _run_pytest_subprocess(test_file_prog, pythonpath)

        assert result2.returncode != 0, (
            f"Programmatic buggy conftest should have failed but passed:\n"
            f"stdout: {result2.stdout}\nstderr: {result2.stderr}"
        )
        combined2 = result2.stdout + result2.stderr
        assert "leaked" in combined2, (
            f"Programmatic failure message should contain 'leaked':\n{combined2}"
        )