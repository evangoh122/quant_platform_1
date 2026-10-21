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
* every ``.py`` path named in ``resources/*.yml`` — declared job tasks.

``tests/`` and any ``archive`` directory are excluded from the source scan: a
module that only a test imports is dead production code, and archived code is
not shipped.

Edges come from real ``import`` statements (including deferred, function-local
imports) plus dotted module names that appear as strings (uvicorn targets,
``importlib`` lookups).  A *package* ``__init__`` is exempt when at least one of
its submodules is reachable: ``import api.services.x`` makes the package usable
without ever naming ``api.services`` itself.

Usage::

    python scripts/check_api_reachability.py [repo_root]

Exit code 0 when every ``api.*`` module is reachable, 1 when some are not.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

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

# Only dotted names starting with one of these roots can be a local module.
_LOCAL_ROOTS = frozenset(
    {"api", "agent", "pipelines", "gold", "silver", "etl", "bronze", "ml",
     "strategies", "scripts", "notebooks", "sec_kg", "analytics_nl", "config",
     "evals", "db", "security", "execution", "ontology"}
)

_STRING_REF_RE = re.compile(
    r"""['"](""" + "|".join(sorted(_LOCAL_ROOTS)) + r""")(?:\.[A-Za-z_][A-Za-z0-9_]*)+"""
)

# A ``.py`` path in a bundle spec: ``python_file: ../pipelines/x.py``,
# ``notebook_path: ../notebooks/x.py``.  Templated paths are skipped later.
_RESOURCE_PATH_RE = re.compile(r"""([\w${}./~-]+\.py)\b""")


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


def _imports_of(module: str, path: pathlib.Path, known: dict[str, bool]) -> set[str]:
    """Return local module names imported by *path* (static + string refs)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    is_package_init = path.name == "__init__.py"
    raw: set[str] = set()

    for node in ast.walk(tree):
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

    for match in _STRING_REF_RE.finditer(text):
        raw.add(match.group(0).strip("'\""))

    resolved: set[str] = set()
    for name in raw:
        if name in known:
            resolved.add(name)
            continue
        # ``import a.b.c`` also makes a.b and a live when they are modules here.
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


def _resource_modules(spec: pathlib.Path, root: pathlib.Path) -> set[str]:
    """Resolve the ``.py`` paths named in one bundle spec to module names.

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
    modules: set[str] = set()
    for ref in _RESOURCE_PATH_RE.findall(text):
        if any(marker in ref for marker in ("${", "$(", "*", "?")):
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


def entry_points(root: pathlib.Path, known: dict[str, bool]) -> set[str]:
    """Return the modules production code starts from."""
    root = pathlib.Path(root).resolve()
    entries = {"api.main"}
    for name in known:
        if name.split(".")[0] in ENTRY_PACKAGES:
            entries.add(name)
    resources = root / "resources"
    if resources.is_dir():
        for spec in sorted(resources.glob("*.yml")):
            entries |= _resource_modules(spec, root)
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
    root = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
    inventory, seen, dead = analyse(root)
    live_api = [name for name in seen if name.startswith("api.")]
    print(f"api modules: {len(inventory)} | reachable: {len(live_api)} | unreachable: {len(dead)}")
    for name in dead:
        print(f"  DEAD {name}")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
