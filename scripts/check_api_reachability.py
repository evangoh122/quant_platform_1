"""Derive which ``api.*`` modules no live entry point can reach.

This is the tested helper behind ``tests/test_no_dead_api_modules.py``.  It
answers one question: *given the modules that production code actually starts
from, which ``api.*`` modules are unreachable?*  The module list is derived by
parsing the tree every run — nothing is hard-coded, so a newly added module is
covered automatically.

Live entry points are the things the application and its jobs really execute:

* ``api.main`` — the FastAPI app (``app.yaml`` / ``uvicorn`` target).
* every module under the pipeline/script packages below — they are invoked as
  Databricks job tasks, notebooks or CLIs, so each is a root by definition.
* every ``.py`` path declared as a job task in ``resources/*.yml``.  The spec is
  parsed as YAML, so a commented-out task is not a task.
* the package ``__init__`` files Python executes before importing a seed
  (``api.main`` cannot be imported without running ``api/__init__.py``).

``tests/`` and any ``archive`` directory are excluded from the source scan: a
module that only a test imports is dead production code, and archived code is
not shipped.

Edges come from real ``import`` statements (including deferred, function-local
imports) plus dotted module names that appear as non-docstring string literals
(uvicorn targets, ``importlib`` lookups).  Comments and docstrings are ignored so
prose about a retired module cannot keep it "alive".  Imports under a
``if TYPE_CHECKING:`` guard never run, so they create no edge; the ``else``
branch of the same guard does run and is scanned normally.  Importing a submodule
also executes every parent package ``__init__``, so those edges are followed as
well.  A *package* ``__init__`` is exempt when at least one of its submodules is
reachable: ``import api.services.x`` makes the package usable without ever
naming ``api.services`` itself.

Known limits, accepted deliberately so the guard stays cheap and stable:

* Every module in ``ENTRY_PACKAGES`` is a root by definition.  This is lenient:
  an ``api.*`` module imported only by a retired pipeline still counts as
  reachable, because the scan cannot tell a live job from a dead one.
* Computed dynamic imports are invisible: ``importlib.import_module(f"api.{n}")``
  has no literal module name to read, so the scan cannot follow that edge.
* Task paths are read only from the ``python_file`` / ``notebook_path`` keys of
  the parsed spec; a templated path (``${var}``, glob) is skipped because it is
  not resolvable before deployment.

Usage::

    python scripts/check_api_reachability.py [repo_root]

Exit codes: 0 when every ``api.*`` module is reachable, 1 when some are not,
2 when no ``api.*`` module was found at all (an empty or wrong root, which must
not be mistaken for a clean scan).
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from collections.abc import Iterator

import yaml

# Packages whose modules are executable roots (job tasks, notebooks, CLIs).
ENTRY_PACKAGES = (
    "agent",
    "pipelines",
    "gold",
    "silver",
    "etl",
    "bronze",
    "ml",
    "strategies",
    "scripts",
    "notebooks",
    "sec_kg",
    "analytics_nl",
    "config",
    "evals",
)

# Never scanned: test-only code and vendored dependencies.
_EXCLUDED_TOP_LEVEL = frozenset({"tests", "node_modules"})

# Never descend into these at any depth: virtualenvs, installed node packages
# and every dot-directory (``.venv``, ``.cache``, tool state) hold vendored or
# generated copies, never production modules.
_EXCLUDED_ANY_DEPTH = frozenset({"node_modules", ".venv", "venv"})

# Only dotted names starting with one of these roots can be a local module.
_LOCAL_ROOTS = frozenset(
    {"api", "agent", "pipelines", "gold", "silver", "etl", "bronze", "ml",
     "strategies", "scripts", "notebooks", "sec_kg", "analytics_nl", "config",
     "evals", "db", "security", "execution", "ontology"}
)

# A dotted local module name inside a string literal, e.g. ``"api.main:app"`` or
# ``importlib.import_module("api.live")``.  The lookbehind stops ``myapi.main``
# from matching ``api.main``.
_STRING_REF_RE = re.compile(
    r"""(?<![\w.])(""" + "|".join(sorted(_LOCAL_ROOTS)) + r""")(?:\.[A-Za-z_][A-Za-z0-9_]*)+"""
)

# Bundle-spec keys whose value is the path of the code a task runs:
# ``spark_python_task.python_file: ../pipelines/x.py`` and
# ``notebook_task.notebook_path: ../notebooks/x.py``.
_TASK_PATH_KEYS = frozenset({"python_file", "notebook_path"})

# Markers that make a declared task path unresolvable from the repository alone:
# bundle template variables (``${var}``, ``$(var)``) and glob wildcards are only
# expanded after deployment, so no file can be named before that.
_UNRESOLVABLE_PATH_MARKERS = ("${", "$(", "*", "?")


def is_resolvable_task_path(ref: str) -> bool:
    """Return whether a declared task path names a file before deployment.

    ``python_file: ${workspace.file_path}/pipelines/x.py`` or a glob such as
    ``../notebooks/task_*.py`` cannot be mapped to a module name by reading the
    repository, so every consumer of ``python_file`` / ``notebook_path`` skips
    it.  The predicate lives here — used by the scanner and by the test oracle —
    so the two can never drift apart on what counts as resolvable.
    """
    return not any(marker in ref for marker in _UNRESOLVABLE_PATH_MARKERS)


def _module_name(path: pathlib.Path, root: pathlib.Path) -> str:
    rel = path.relative_to(root)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _iter_sources(root: pathlib.Path):
    """Yield ``(module_name, path)`` for production source files under *root*."""
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.parts[0] in _EXCLUDED_TOP_LEVEL:
            continue
        if "archive" in rel.parts:
            continue
        if any(
            part in _EXCLUDED_ANY_DEPTH or part.startswith(".")
            for part in rel.parts[:-1]
        ):
            continue
        name = _module_name(path, root)
        if not name:
            continue
        yield name, path


def _resolve_relative(module: str, is_package_init: bool, level: int, base: str) -> str:
    """Resolve a relative import base to an absolute dotted module name."""
    package_parts = module.split(".") if is_package_init else module.split(".")[:-1]
    keep = len(package_parts) - (level - 1)
    if keep < 0:
        return ""
    parts = package_parts[:keep]
    if base:
        parts = parts + base.split(".")
    return ".".join(parts)


def _docstring_ids(tree: ast.AST) -> set[int]:
    """Return the ``id()`` of every docstring ``Constant`` node in *tree*.

    Only the first statement of a module, class or function can be a docstring;
    comments never reach the AST, so documentation-only text cannot create a
    module edge.
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _type_checking_guard(test: ast.expr) -> bool | None:
    """Classify an ``if`` test as a ``TYPE_CHECKING`` guard.

    ``True`` means the body only exists for type checkers; ``False`` means the
    guard is negated, so the body runs and the ``else`` branch does not;
    ``None`` means the test is not such a guard at all.
    """
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _type_checking_guard(test.operand)
        return None if inner is None else not inner
    if isinstance(test, ast.Name):
        return True if test.id == "TYPE_CHECKING" else None
    if isinstance(test, ast.Attribute):
        return True if test.attr == "TYPE_CHECKING" else None
    return None


def _runtime_nodes(tree: ast.AST) -> Iterator[ast.AST]:
    """Yield the nodes of *tree* that really execute at runtime.

    A ``if TYPE_CHECKING:`` body is skipped entirely: it never executes, so an
    import inside it cannot keep a module alive.
    """
    yield tree
    if isinstance(tree, ast.If):
        guard = _type_checking_guard(tree.test)
        if guard is not None:
            branch = tree.orelse if guard else tree.body
            for child in branch:
                yield from _runtime_nodes(child)
            return
    for child in ast.iter_child_nodes(tree):
        yield from _runtime_nodes(child)


def _imports_of(module: str, path: pathlib.Path, known: dict[str, bool]) -> set[str]:
    """Return local module names imported by *path* (static + string refs)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    is_package_init = path.name == "__init__.py"
    docstring_ids = _docstring_ids(tree)
    raw: set[str] = set()

    for node in _runtime_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                raw.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                resolved_base = _resolve_relative(module, is_package_init, node.level, base)
                if resolved_base:
                    raw.add(resolved_base)
                    for alias in node.names:
                        raw.add(f"{resolved_base}.{alias.name}")
            elif base:
                raw.add(base)
                for alias in node.names:
                    raw.add(f"{base}.{alias.name}")
            else:
                for alias in node.names:
                    raw.add(alias.name)

    # Dotted module names only count where they are executable string literals.
    for node in _runtime_nodes(tree):
        if id(node) in docstring_ids:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            raw.update(
                match.group(0) for match in _STRING_REF_RE.finditer(node.value)
            )

    resolved: set[str] = set()
    for name in raw:
        if name in known:
            resolved.add(name)
        # Importing ``a.b.c`` executes every parent package ``__init__`` whether
        # or not ``a.b.c`` is itself a scanned module, so add the ancestors.
        parts = name.split(".")
        for i in range(1, len(parts)):
            prefix = ".".join(parts[:i])
            if prefix in known:
                resolved.add(prefix)
    return resolved


def scan_repository(root: pathlib.Path):
    """Return ``(known, graph)`` for the production tree under *root*.

    ``known`` maps module name -> ``is_package_init``; ``graph`` maps module
    name -> set of local modules it imports.
    """
    root = pathlib.Path(root).resolve()
    known: dict[str, bool] = {}
    paths: dict[str, pathlib.Path] = {}
    for name, path in _iter_sources(root):
        known[name] = path.name == "__init__.py"
        paths[name] = path
    graph = {name: _imports_of(name, path, known) for name, path in paths.items()}
    return known, graph


def _task_paths(node: object) -> Iterator[str]:
    """Yield every ``python_file`` / ``notebook_path`` value in a parsed spec.

    Walking the *parsed* document is what makes a commented-out task inert: the
    YAML parser drops comments before they can look like a declaration.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _TASK_PATH_KEYS and isinstance(value, str):
                yield value
            yield from _task_paths(value)
    elif isinstance(node, list):
        for item in node:
            yield from _task_paths(item)


def _resource_modules(spec: pathlib.Path, root: pathlib.Path) -> set[str]:
    """Resolve the task paths declared in one bundle spec to module names.

    Databricks resolves task ``python_file`` / ``notebook_path`` values relative
    to the bundle root of the spec, i.e. ``resources/jobs.yml`` declaring
    ``python_file: ../pipelines/x.py`` runs ``<repo>/pipelines/x.py``.  The path
    therefore has to be joined to ``spec.parent`` (not to the repository root)
    and must lose its ``.py`` suffix before it can match a scanned module.
    """
    try:
        text = spec.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return set()
    modules: set[str] = set()
    for ref in _task_paths(document):
        if not is_resolvable_task_path(ref):
            continue  # templated / glob path: not resolvable before deployment
        try:
            rel = (spec.parent / ref).resolve().relative_to(root)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        if parts:
            modules.add(".".join(parts))
    return modules


def _with_parent_package_inits(names: set[str], known: dict[str, bool]) -> set[str]:
    """Add the package initializers Python runs before importing *names*.

    ``import api.main`` executes ``api/__init__.py`` first, so a module imported
    by that initializer is live even though no source statement names it.
    """
    expanded = set(names)
    for name in names:
        parts = name.split(".")
        for i in range(1, len(parts)):
            prefix = ".".join(parts[:i])
            if known.get(prefix, False):
                expanded.add(prefix)
    return expanded


def entry_points(root: pathlib.Path, known: dict[str, bool]) -> set[str]:
    """Return the modules production code starts from."""
    root = pathlib.Path(root).resolve()
    seeds = {"api.main"}
    resources = root / "resources"
    if resources.is_dir():
        for spec in sorted(resources.glob("*.yml")):
            seeds |= _resource_modules(spec, root)
    # Importing a seed runs its packages' ``__init__`` files first.
    entries = _with_parent_package_inits(seeds, known)
    for name in known:
        if name.split(".")[0] in ENTRY_PACKAGES:
            entries.add(name)
    return {name for name in entries if name in known}


def _reachable(graph: dict[str, set[str]], entries: set[str]) -> set[str]:
    seen: set[str] = set()
    stack = list(entries)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(graph.get(name, ()))
    return seen


def _is_init_with_live_submodules(name: str, known: dict[str, bool], seen: set[str]) -> bool:
    if not known.get(name, False):
        return False
    prefix = name + "."
    return any(other.startswith(prefix) for other in seen)


def analyse(root: pathlib.Path):
    """Return ``(inventory, reachable, dead)`` for the ``api.*`` package.

    ``inventory`` is every ``api.*`` module derived from the tree;
    ``reachable`` are those reachable from live entry points; ``dead`` is the
    remainder, excluding package ``__init__`` modules that have live
    submodules.
    """
    root = pathlib.Path(root).resolve()
    known, graph = scan_repository(root)
    seen = _reachable(graph, entry_points(root, known))
    inventory = sorted(name for name in known if name.startswith("api."))
    dead = [
        name
        for name in inventory
        if name not in seen and not _is_init_with_live_submodules(name, known, seen)
    ]
    return inventory, sorted(seen), dead


def unreachable_api_modules(root: pathlib.Path) -> list[str]:
    """Return the ``api.*`` modules no live entry point can reach."""
    return analyse(root)[2]


def main(argv: list[str]) -> int:
    """CLI entry point; returns 0 clean, 1 dead modules, 2 nothing scanned.

    Exit code 2 means the inventory of ``api.*`` modules was empty, i.e. *root*
    is empty or is not the repository root.  Returning 0 there would report a
    vacuous "nothing is dead" result for a scan that read no code at all.
    """
    root = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
    inventory, seen, dead = analyse(root)
    if not inventory:
        print(
            f"error: no api.* modules found under {root}; pass the repository root",
            file=sys.stderr,
        )
        return 2
    live_api = [name for name in seen if name.startswith("api.")]
    print(f"api modules: {len(inventory)} | reachable: {len(live_api)} | unreachable: {len(dead)}")
    for name in dead:
        print(f"  DEAD {name}")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
