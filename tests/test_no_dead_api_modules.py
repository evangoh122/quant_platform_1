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

* ``api.main`` (the FastAPI app) and the package initializers it executes,
* every module in the executable packages (``agent/``, ``pipelines/``,
  ``gold/``, ``silver/``, ``etl/``, ``bronze/``, ``ml/``, ``strategies/``,
  ``scripts/``, ``notebooks/``, ``sec_kg/``, ``analytics_nl/``, ``config/``,
  ``evals/``),
* every job task declared in ``resources/*.yml``.

Imports under ``if TYPE_CHECKING:`` never execute, so they are not edges; the
``else`` branch of such a guard does run.  Job tasks are read from the parsed
YAML, so a commented-out task is not a task.

Package ``__init__`` modules are exempt only when a live submodule keeps the
package importable (``import api.services.x`` never names ``api.services``).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts import check_api_reachability as reachability
from scripts.check_api_reachability import (
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


def _yaml_task_paths(node: object):
    """Collect task paths from a **parsed** bundle spec.

    Deliberately independent of ``check_api_reachability``: this is the oracle
    the helper is checked against.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("python_file", "notebook_path") and isinstance(value, str):
                yield value
            yield from _yaml_task_paths(value)
    elif isinstance(node, list):
        for item in node:
            yield from _yaml_task_paths(item)


def _oracle_task_modules(root: Path, specs) -> set[str]:
    """Resolve declared task paths to modules, independently of the scanner.

    The walk over the parsed YAML is this oracle's own; only the *skip* rule is
    shared, because both sides must agree that a templated or glob path names no
    file.  A path that resolves outside *root* names no scanned module either,
    so it is dropped here exactly as the scanner drops it.
    """
    expected: set[str] = set()
    for spec in specs:
        document = yaml.safe_load(spec.read_text(encoding="utf-8"))
        for raw in _yaml_task_paths(document):
            if not reachability.is_resolvable_task_path(raw):
                continue
            try:
                rel = (spec.parent / raw).resolve().relative_to(root.resolve())
            except ValueError:
                continue
            parts = list(rel.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts.pop()
            if parts:
                expected.add(".".join(parts))
    return expected


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

    # Entry-package leniency itself is covered by a fail-able synthetic tree in
    # ``test_entry_package_modules_are_live_roots``; a real-repo loop over
    # ENTRY_PACKAGES could only ever pass.


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


def test_commented_out_task_paths_are_not_entry_points(tmp_path: Path):
    """A commented-out task declares nothing, so its module must stay dead.

    ``db`` is deliberately not an entry package: only a real YAML task can make
    ``db.commented_task`` live, and its declaration is commented out.
    """
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py")
    _write(tmp_path, "api/only_commented.py")
    _write(tmp_path, "api/live_task_import.py")
    _write(tmp_path, "db/commented_task.py", "import api.only_commented\n")
    _write(tmp_path, "db/live_task.py", "import api.live_task_import\n")
    _write(
        tmp_path,
        "resources/jobs.yml",
        "resources:\n"
        "  jobs:\n"
        "    job:\n"
        "      tasks:\n"
        "        # - task_key: disabled\n"
        "        #   spark_python_task:\n"
        "        #     python_file: ../db/commented_task.py\n"
        "        - task_key: live\n"
        "          notebook_task:\n"
        "            notebook_path: ../db/live_task.py\n",
    )

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.live_task_import" in reachable, "the live task stopped being a root"
    assert "db.commented_task" not in reachable, "a YAML comment became a task"
    assert dead == ["api.only_commented"]


def test_real_bundle_specs_resolve_to_scanned_modules():
    """Non-vacuity: every job task in ``resources/*.yml`` is a live root."""
    known, _graph = scan_repository(REPO)
    entries = entry_points(REPO, known)
    specs = sorted((REPO / "resources").glob("*.yml"))
    assert specs, "no resources/*.yml found"

    # Independent, minimal resolution of the declared task paths: the spec is
    # parsed so comments cannot contribute, and Databricks resolves the paths
    # against the spec's own directory.
    expected = _oracle_task_modules(REPO, specs)

    assert expected, "no job task paths declared in resources/*.yml"
    assert expected <= set(known), f"declared modules are not scanned: {expected - set(known)}"
    assert expected <= entries, f"declared job tasks are not entry points: {expected - entries}"


def test_templated_glob_and_out_of_repo_task_paths_are_skipped(tmp_path: Path):
    """Unresolvable task paths are no roots — for the scanner and the oracle.

    ``python_file`` values may be bundle templates, globs, or point outside the
    repository; none of those names a file at scan time.  Only the genuinely
    registered task may become an entry point, and the shared skip predicate
    must make both sides reach that conclusion.
    """
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py")
    _write(tmp_path, "api/via_registered_task.py")
    _write(tmp_path, "db/registered_task.py", "import api.via_registered_task\n")
    _write(tmp_path, "db/templated_task.py", "import api.via_registered_task\n")
    _write(tmp_path, "jobs/glob_task.py", "import api.via_registered_task\n")
    _write(
        tmp_path,
        "resources/jobs.yml",
        "resources:\n"
        "  jobs:\n"
        "    job:\n"
        "      tasks:\n"
        "        - task_key: registered\n"
        "          spark_python_task:\n"
        "            python_file: ../db/registered_task.py\n"
        "        - task_key: templated\n"
        "          spark_python_task:\n"
        "            python_file: ${workspace.file_path}/db/templated_task.py\n"
        "        - task_key: glob\n"
        "          notebook_task:\n"
        "            notebook_path: ../jobs/glob_*.py\n"
        "        - task_key: outside\n"
        "          spark_python_task:\n"
        "            python_file: ../../outside/escape.py\n",
    )

    spec = tmp_path / "resources" / "jobs.yml"
    scanner_modules = reachability._resource_modules(spec, tmp_path)
    oracle_modules = _oracle_task_modules(tmp_path, [spec])
    _inventory, reachable, dead = analyse(tmp_path)

    assert reachability.is_resolvable_task_path("../db/registered_task.py")
    assert not reachability.is_resolvable_task_path("${workspace.file_path}/x.py")
    assert not reachability.is_resolvable_task_path("$(var)/x.py")
    assert not reachability.is_resolvable_task_path("../jobs/glob_*.py")

    assert scanner_modules == {"db.registered_task"}
    assert oracle_modules == {"db.registered_task"}

    assert "db.registered_task" in reachable
    assert "api.via_registered_task" in reachable
    assert "db.templated_task" not in reachable, "a templated path became a root"
    assert "jobs.glob_task" not in reachable, "a glob path became a root"
    assert dead == []


def test_tests_and_archives_are_not_scan_roots(tmp_path: Path, monkeypatch):
    """A module only tests or archives import is dead production code.

    Both fixtures sit inside an entry package so that this fails when either
    exclusion is removed: ``tests`` is patched into ``ENTRY_PACKAGES`` and the
    archive lives under the real entry package ``pipelines``.  Without the
    ``tests/`` skip, ``tests/test_only.py`` becomes a live root; without the
    ``archive`` skip, ``pipelines/archive/old.py`` does — each keeping its own
    ``api`` module out of the dead list.
    """
    monkeypatch.setattr(reachability, "ENTRY_PACKAGES", ("tests", "pipelines"))
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py")
    _write(tmp_path, "api/only_tests_import.py")
    _write(tmp_path, "api/only_in_archive.py")
    _write(tmp_path, "tests/test_only.py", "import api.only_tests_import\n")
    _write(tmp_path, "pipelines/archive/old.py", "import api.only_in_archive\n")

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.only_tests_import" in dead, "a test-only import kept a module alive"
    assert "api.only_in_archive" in dead, "an archived import kept a module alive"
    assert "tests.test_only" not in reachable
    assert "pipelines.archive.old" not in reachable

    known, _graph = scan_repository(tmp_path)
    assert "tests.test_only" not in known, "tests/ was scanned as production code"
    assert "pipelines.archive.old" not in known, (
        "archive/ was scanned as production code"
    )


def test_parent_package_initializers_are_followed(tmp_path: Path):
    """Importing a submodule runs every parent ``__init__``, so follow it.

    ``api.main`` imports only ``api.sub.live``; the ``api.sub`` package
    initializer imports ``api.required``.  Python executes that initializer, so
    ``api.required`` is live even though no source statement names ``api.sub``.
    """
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py", "import api.sub.live\n")
    _write(tmp_path, "api/sub/__init__.py", "import api.required\n")
    _write(tmp_path, "api/sub/live.py")
    _write(tmp_path, "api/required.py")

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.sub.live" in reachable
    assert "api.required" in reachable, "parent package __init__ edge was dropped"
    assert dead == []


def test_api_package_init_is_a_live_root(tmp_path: Path):
    """``import api.main`` runs ``api/__init__.py`` first, so its imports are live.

    ``api.main`` imports nothing from ``api``; only seeding the app's package
    initializer can keep ``api.helper`` alive.
    """
    _write(tmp_path, "api/__init__.py", "import api.helper\n")
    _write(tmp_path, "api/main.py")
    _write(tmp_path, "api/helper.py")

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.helper" in reachable, "api/__init__ was not seeded as a root"
    assert dead == []


def test_string_references_ignore_comments_and_docstrings(tmp_path: Path):
    """Only executable string literals are module references.

    A comment, or a module/class/function docstring that mentions a retired
    module, must not keep that module alive; a real ``importlib`` argument or a
    plain string literal in code must.
    """
    _write(tmp_path, "api/__init__.py")
    _write(
        tmp_path,
        "api/main.py",
        '"""Module note: "api.module_doc" was retired."""\n'
        "import importlib\n"
        "\n"
        "\n"
        "class Widget:\n"
        '    """Class note: "api.class_doc" was retired."""\n'
        "\n"
        "\n"
        "def load():\n"
        '    """Function note: "api.func_doc" was retired."""\n'
        '    importlib.import_module("api.live")\n'
        '    return "api.live_call"\n'
        "\n"
        "\n"
        '# Comment: "api.comment_only" was retired.\n',
    )
    for name in (
        "api/live.py",
        "api/live_call.py",
        "api/module_doc.py",
        "api/class_doc.py",
        "api/func_doc.py",
        "api/comment_only.py",
    ):
        _write(tmp_path, name)

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.live" in reachable, "importlib string argument must create an edge"
    assert "api.live_call" in reachable, "plain string literal must create an edge"
    assert dead == [
        "api.class_doc",
        "api.comment_only",
        "api.func_doc",
        "api.module_doc",
    ]


def test_type_checking_imports_are_not_runtime_edges(tmp_path: Path):
    """An import under ``if TYPE_CHECKING:`` never runs, so it is not an edge.

    The ``else`` branch of the same guard *does* run and must still count.
    """
    _write(tmp_path, "api/__init__.py")
    _write(
        tmp_path,
        "api/main.py",
        "import typing\n"
        "from typing import TYPE_CHECKING\n"
        "\n"
        "if TYPE_CHECKING:\n"
        "    import api.retired_import\n"
        "    from api import retired_from\n"
        '    LOADER = "api.retired_string"\n'
        "else:\n"
        "    import api.runtime_else\n"
        "\n"
        "if typing.TYPE_CHECKING:\n"
        "    import api.retired_attribute\n"
        "\n"
        "if not SOME_FLAG:\n"
        "    import api.negated_non_guard\n",
    )
    for name in (
        "api/runtime_else.py",
        "api/retired_import.py",
        "api/retired_from.py",
        "api/retired_string.py",
        "api/retired_attribute.py",
        "api/negated_non_guard.py",
    ):
        _write(tmp_path, name)

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.runtime_else" in reachable, "the else branch runs at runtime"
    assert "api.negated_non_guard" in reachable, "`if not X:` is not a guard"
    assert dead == [
        "api.retired_attribute",
        "api.retired_from",
        "api.retired_import",
        "api.retired_string",
    ]


def test_negated_type_checking_guard_runs_its_body(tmp_path: Path):
    """``if not TYPE_CHECKING:`` is the runtime branch; its ``else`` never runs.

    This pins the inversion in ``_type_checking_guard``.  Treating the negated
    guard like a plain ``TYPE_CHECKING`` guard would mark ``api.live`` dead and
    ``api.typing_only`` live — the exact opposite of what Python does.
    """
    _write(tmp_path, "api/__init__.py")
    _write(
        tmp_path,
        "api/main.py",
        "from typing import TYPE_CHECKING\n"
        "\n"
        "if not TYPE_CHECKING:\n"
        "    import api.live\n"
        "else:\n"
        "    import api.typing_only\n",
    )
    _write(tmp_path, "api/live.py")
    _write(tmp_path, "api/typing_only.py")

    _inventory, reachable, dead = analyse(tmp_path)

    assert "api.live" in reachable, "the body of `if not TYPE_CHECKING:` must run"
    assert "api.typing_only" in dead, "the else branch of a negated guard never runs"


def test_entry_package_modules_are_live_roots(tmp_path: Path, monkeypatch):
    """A module in an entry package is a root; drop the package and it dies.

    This is the fail-able version of "entry packages contribute roots", and it
    documents the deliberate leniency: any module under an entry package is
    assumed live, so an ``api`` module imported only by a retired pipeline still
    passes the guard.
    """
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py")
    _write(tmp_path, "api/used_by_task.py")
    _write(tmp_path, "taskpkg/__init__.py")
    _write(tmp_path, "taskpkg/run.py", "import api.used_by_task\n")

    monkeypatch.setattr(reachability, "ENTRY_PACKAGES", ("taskpkg",))
    _inventory, reachable, _dead = analyse(tmp_path)
    assert "taskpkg.run" in reachable, "module in an entry package is not a root"
    assert "api.used_by_task" in reachable

    monkeypatch.setattr(reachability, "ENTRY_PACKAGES", ())
    _inventory, reachable, dead = analyse(tmp_path)
    assert "taskpkg.run" not in reachable, "entry package still treated as a root"
    assert "api.used_by_task" in dead


def test_vendor_and_hidden_directories_are_skipped_at_any_depth(
    tmp_path: Path, monkeypatch
):
    """``node_modules``, ``venv`` and dot-directories never contribute modules.

    Every fixture lives under the entry package ``pipelines`` and imports its own
    ``api`` module, so removing the vendor/dot-directory skip turns that fixture
    into a live root and revives the ``api`` module it names.
    """
    monkeypatch.setattr(reachability, "ENTRY_PACKAGES", ("pipelines",))
    _write(tmp_path, "api/__init__.py")
    _write(tmp_path, "api/main.py")
    fixtures = {
        "pipelines/.venv/lib/vendored_dot_venv.py": "api.only_in_dot_venv",
        "pipelines/venv/lib/vendored_venv.py": "api.only_in_venv",
        "pipelines/node_modules/pkg/vendored_node_modules.py": (
            "api.only_in_node_modules"
        ),
        "pipelines/.cache/vendored_dot_cache.py": "api.only_in_dot_cache",
    }
    for rel, imported in fixtures.items():
        _write(tmp_path, f"api/{imported.split('.')[-1]}.py")
        _write(tmp_path, rel, f"import {imported}\n")

    _inventory, _reachable, dead = analyse(tmp_path)

    for imported in fixtures.values():
        assert imported in dead, f"{imported} stayed alive through a vendor/hidden copy"

    known, _graph = scan_repository(tmp_path)
    excluded_modules = {".".join(Path(rel).with_suffix("").parts) for rel in fixtures}
    assert not excluded_modules & set(known), (
        "vendor/hidden files were scanned as production modules: "
        f"{sorted(excluded_modules & set(known))}"
    )


def test_cli_distinguishes_clean_dead_and_empty_inventory(tmp_path: Path, capsys):
    """Exit codes: 0 clean, 1 dead modules found, 2 nothing scanned.

    An empty or wrong root yields no ``api.*`` inventory at all.  Reporting that
    as 0 would make the CLI look green without having read any code, so it is a
    distinct failure (2) with a clear message.
    """
    clean = tmp_path / "clean"
    _write(clean, "api/__init__.py")
    _write(clean, "api/main.py")
    assert reachability.main(["check_api_reachability.py", str(clean)]) == 0
    assert capsys.readouterr().out.startswith("api modules: ")

    dead = tmp_path / "dead"
    _write(dead, "api/__init__.py")
    _write(dead, "api/main.py")
    _write(dead, "api/orphan.py")
    assert reachability.main(["check_api_reachability.py", str(dead)]) == 1
    assert "DEAD api.orphan" in capsys.readouterr().out

    empty = tmp_path / "not_a_repo"
    empty.mkdir()
    assert reachability.main(["check_api_reachability.py", str(empty)]) == 2
    captured = capsys.readouterr()
    assert "no api.* modules found" in captured.err
    assert captured.out == "", "the empty-inventory case must not print a summary"
