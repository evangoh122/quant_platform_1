"""Guard: no ``api.*`` module may be unreachable from a live entry point.

The repository inherited a large Rag_workbench RAG/DuckDB stack that nothing
started from production code — not the FastAPI app, not a job task, not a
notebook, not a script.  That dead weight was deleted; this test keeps it from
coming back, because an unreachable module is indistinguishable from the
"exists as legacy code" problem it caused (tests kept it alive, docs pointed at
it, reviewers treated presence as evidence it was wired up).

The module list is **derived** on every run by
``scripts/check_api_reachability.py`` — nothing here is a hard-coded inventory.
The test fails if any ``api.*`` module cannot be reached from:

* ``api.main`` (the FastAPI app),
* every module in the executable packages (``agent/``, ``pipelines/``,
  ``gold/``, ``silver/``, ``etl/``, ``bronze/``, ``ml/``, ``strategies/``,
  ``scripts/``, ``notebooks/``, ``sec_kg/``, ``analytics_nl/``, ``config/``,
  ``evals/``),
* every ``.py`` named in ``resources/*.yml``.

Package ``__init__`` modules are exempt only when a live submodule keeps the
package importable (``import api.services.x`` never names ``api.services``).
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.check_api_reachability import (
    ENTRY_PACKAGES,
    analyse,
    entry_points,
    scan_repository,
    unreachable_api_modules,
)

REPO = Path(__file__).resolve().parent.parent


def _write(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_every_api_module_is_reachable_from_a_live_entry_point():
    """The real tree: no unreachable ``api.*`` module may remain."""
    dead = unreachable_api_modules(REPO)
    assert dead == [], (
        "Unreachable api modules found (no live entry point imports them):\n  "
        + "\n  ".join(dead)
        + "\nDelete them, wire them up, or — if they are a genuine job/CLI entry "
        "point — add the call site so the reachability scan can see it."
    )


def test_scan_sees_the_live_api_surface():
    """Non-vacuity: a broken scan that reports nothing dead must not pass.

    The derivation must actually find the app and its deep dependencies, and it
    must enumerate a non-trivial ``api.*`` inventory.
    """
    inventory, reachable, _dead = analyse(REPO)

    assert len(inventory) >= 10, f"api inventory suspiciously small: {inventory}"
    # Anchors: the FastAPI entrypoint and two modules it only reaches through
    # imports (routes and services).  If the graph walk were broken, these
    # would fall out of the reachable set.
    for anchor in ("api.main", "api.deps", "api.services.hybrid_retriever"):
        assert anchor in reachable, f"{anchor} is not reachable — scan is broken"
    assert "api.main" in inventory

    known, graph = scan_repository(REPO)
    assert ENTRY_PACKAGES, "entry packages must not be empty"
    # Every executable package must contribute at least one root when present.
    for package in ENTRY_PACKAGES:
        if any(name.startswith(package + ".") for name in known):
            assert any(name.startswith(package + ".") for name in graph), package


def test_helper_detects_dead_modules_and_exempts_live_package_inits(tmp_path: Path):
    """Synthetic tree: the derivation must flag dead modules, not live ones."""
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py", "import api.live\nimport api.sub.live\n")
    _write(tmp_path, "api/live.py", "import api.live_dep\n")
    _write(tmp_path, "api/live_dep.py")
    _write(tmp_path, "api/dead.py")
    _write(tmp_path, "api/sub/__init__.py")
    _write(tmp_path, "api/sub/live.py")
    _write(tmp_path, "api/orphan/__init__.py")
    _write(tmp_path, "api/orphan/gone.py")

    _inventory, reachable, dead = analyse(tmp_path)

    # Reached: the app, its import graph, and package inits with live submodules.
    assert "api.main" in reachable
    assert "api.live" in reachable
    assert "api.live_dep" in reachable
    assert "api.sub.live" in reachable
    assert "api" not in dead, "package init with live submodules must be exempt"
    assert "api.sub" not in dead, "package init with live submodules must be exempt"

    # Not reached: an unimported module and a package nothing imports.
    assert dead == ["api.dead", "api.orphan", "api.orphan.gone"]


def test_resources_yaml_job_tasks_are_entry_points(tmp_path: Path):
    """A task named only in ``resources/*.yml`` is a live root.

    Databricks resolves ``python_file`` / ``notebook_path`` relative to the
    spec's own directory, so ``../db/job_task.py`` in ``resources/jobs.yml``
    means ``<root>/db/job_task.py``.  ``db`` and ``jobs`` are deliberately not
    in ``ENTRY_PACKAGES``: only the YAML registration can keep the ``api``
    modules those tasks import out of the dead list.
    """
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py")
    _write(tmp_path, "api/via_spark_task.py")
    _write(tmp_path, "api/via_notebook_task.py")
    _write(tmp_path, "db/job_task.py", "import api.via_spark_task\n")
    _write(tmp_path, "jobs/notebook_task.py", "import api.via_notebook_task\n")
    _write(
        tmp_path,
        "resources/jobs.yml",
        "resources:\n"
        "  jobs:\n"
        "    job:\n"
        "      tasks:\n"
        "        - task_key: spark\n"
        "          spark_python_task:\n"
        "            python_file: ../db/job_task.py\n"
        "        - task_key: notebook\n"
        "          notebook_task:\n"
        "            notebook_path: ../jobs/notebook_task.py\n",
    )

    _inventory, reachable, dead = analyse(tmp_path)

    assert "db.job_task" in reachable, "spark_python_task path was not registered"
    assert "jobs.notebook_task" in reachable, "notebook_task path was not registered"
    assert "api.via_spark_task" in reachable
    assert "api.via_notebook_task" in reachable
    assert dead == []


def test_real_bundle_specs_resolve_to_scanned_modules():
    """Non-vacuity: every job task in ``resources/*.yml`` is a live root."""
    known, _graph = scan_repository(REPO)
    entries = entry_points(REPO, known)
    specs = sorted((REPO / "resources").glob("*.yml"))
    assert specs, "no resources/*.yml found"

    # Independent, minimal resolution of the declared task paths: Databricks
    # resolves them against the spec's own directory.
    expected: set[str] = set()
    for spec in specs:
        text = spec.read_text(encoding="utf-8")
        for raw in re.findall(
            r"(?:python_file|notebook_path):\s*['\"]?([^'\"\s]+\.py)", text
        ):
            rel = (spec.parent / raw).resolve().relative_to(REPO)
            expected.add(".".join(rel.with_suffix("").parts))

    assert expected, "no job task paths declared in resources/*.yml"
    assert expected <= set(known), f"declared modules are not scanned: {expected - set(known)}"
    assert expected <= entries, f"declared job tasks are not entry points: {expected - entries}"


def test_tests_and_archives_are_not_scan_roots(tmp_path: Path):
    """A module only tests import is dead production code, so it must be flagged."""
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py")
    _write(tmp_path, "api/only_tests_import.py")
    _write(tmp_path, "tests/test_only.py", "import api.only_tests_import\n")
    _write(tmp_path, "docs/archive/old.py", "import api.only_tests_import\n")

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.only_tests_import" in dead
    assert "tests.test_only" not in reachable
