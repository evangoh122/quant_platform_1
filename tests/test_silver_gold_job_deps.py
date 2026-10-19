"""tests/test_silver_gold_job_deps.py — silver_gold_refresh serverless dependencies.

The ``silver_gold_refresh`` job runs ``pipelines/run_silver_gold.py`` in a
serverless ``spark_python_task`` environment.  Serverless environments install
nothing unless it is declared under ``environments[].spec.dependencies``; on
2026-10-13 the gold step failed with ``ModuleNotFoundError: No module named
'loguru'`` and then ``'dotenv'`` because the job declared no packages.

This test statically AST-traces the third-party imports reachable from the job's
entry point — module-scope imports of ``pipelines/run_silver_gold.py``, every
repo-local module it imports (including parent-package ``__init__`` modules),
and every Python transform listed in the entry point's ``STEPS`` table — and
asserts that each import's distribution is declared in ``resources/jobs.yml``
for ``silver_gold_refresh`` after normalizing names
(``python-dotenv`` -> ``dotenv``, ``pyyaml`` -> ``yaml``).

Only module-scope imports are traced: lazy imports inside function bodies are
optional and not executed on this path (e.g. ``openai`` inside
``api/services/sentiment.generate_tone_analysis``), so they must NOT force a
declaration.  ``pyspark`` / ``databricks*`` are provided by the Databricks
serverless runtime and must NOT be declared.

Fails on ``main``, where the job's serverless environment declares no
dependencies.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JOBS_YML = _REPO_ROOT / "resources" / "jobs.yml"
_JOB_NAME = "silver_gold_refresh"
_ENTRY_REL = "pipelines/run_silver_gold.py"
_ENTRY_POINT = _REPO_ROOT / _ENTRY_REL

# Distribution name -> import name, for packages whose PyPI name and import
# name differ (mirrors tests/test_requirements_completeness.py).
_DIST_TO_IMPORT = {
    "python-dotenv": "dotenv",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "edgartools": "edgar",
    "psycopg-pool": "psycopg_pool",
    "langchain-openai": "langchain_openai",
    "langchain-core": "langchain_core",
    "sentence-transformers": "sentence_transformers",
    "rank-bm25": "rank_bm25",
    "huggingface-hub": "huggingface_hub",
}

# Provided by the Databricks serverless runtime; must never be declared in the
# job environment (they are not pip-installable dependencies of this job).
_RUNTIME_PROVIDED = {"pyspark", "databricks"}

_STDLIB = set(sys.stdlib_module_names) | {"__future__"}


# ── YAML helpers (same pattern as tests/test_bundle_sync.py) ─────────────────

def _load_jobs() -> dict:
    with open(_JOBS_YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _job_environment_dependencies() -> list[str]:
    """Return spec.dependencies strings of every environment of the job."""
    jobs = _load_jobs().get("resources", {}).get("jobs", {})
    job = jobs.get(_JOB_NAME)
    assert job is not None, f"job {_JOB_NAME!r} missing from {_JOBS_YML}"
    deps: list[str] = []
    for env in job.get("environments", []):
        deps.extend((env.get("spec") or {}).get("dependencies") or [])
    return deps


def _dep_dist_name(dep: str) -> str:
    """Strip extras/version specifiers: 'psycopg[binary]>=3.1' -> 'psycopg'."""
    return re.split(r"[><=\[;!\s]", dep.strip(), maxsplit=1)[0].lower()


def _dep_to_import_name(dep: str) -> str:
    """Normalize a requirement string to its import name: 'python-dotenv>=1.0.0'
    -> 'dotenv'."""
    name = _dep_dist_name(dep)
    return _DIST_TO_IMPORT.get(name, name.replace("-", "_"))


# ── AST import tracing ───────────────────────────────────────────────────────

def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and any(
            isinstance(c, ast.Constant) and c.value == "__main__"
            for c in test.comparators
        )
    )


def _is_type_checking_guard(node: ast.If) -> bool:
    return isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"


def _module_scope_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """Absolute module names imported at module scope.

    Skips imports inside function/method bodies and inside ``if __name__ ==
    '__main__'`` / ``if TYPE_CHECKING:`` guards: those are lazy/optional and are
    not executed when the module is imported on this job path.
    """
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def lazy(node: ast.AST) -> bool:
        p = parents.get(node)
        while p is not None:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return True
            if isinstance(p, ast.If) and (_is_main_guard(p) or _is_type_checking_guard(p)):
                return True
            p = parents.get(p)
        return False

    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if lazy(node):
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0 or not node.module:
                continue  # relative imports cannot name a third-party distribution
            out.append((node.lineno, node.module))
    return out


def _local_module_path(dotted: str) -> Path | None:
    """Resolve a dotted module name to a repo-local file, else None."""
    parts = dotted.split(".")
    if not (_REPO_ROOT / parts[0]).exists():
        return None
    candidate = _REPO_ROOT.joinpath(*parts)
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    init = candidate / "__init__.py"
    if init.is_file():
        return init
    return None


def _parent_package_inits(dotted: str) -> list[Path]:
    parts = dotted.split(".")
    out = []
    for i in range(1, len(parts)):
        init = _REPO_ROOT.joinpath(*parts[:i]) / "__init__.py"
        if init.is_file():
            out.append(init)
    return out


def _read_steps(entry: Path) -> list[tuple[str, str, str]]:
    """Read the (name, path, kind) transform table from the entry point's AST."""
    for node in _parse(entry).body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "STEPS":
                    return [tuple(step) for step in ast.literal_eval(node.value)]
    raise AssertionError(f"STEPS transform table not found in {entry}")


def _reachable_files() -> list[Path]:
    """Entry point plus every Python transform the script executes (kind 'py')."""
    files = [_ENTRY_POINT]
    for _name, rel, kind in _read_steps(_ENTRY_POINT):
        if kind == "py":
            path = (_REPO_ROOT / rel).resolve()
            assert path.is_file(), f"STEPS transform {rel!r} does not exist"
            files.append(path)
    return files


def _trace_third_party(start_files: list[Path]) -> tuple[set[str], set[str]]:
    """Follow repo-local imports (incl. parent package inits) and return
    (third-party top-level import names, repo-relative files visited)."""
    seen: set[Path] = set()
    third_party: set[str] = set()
    queue = [p.resolve() for p in start_files]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for _lineno, mod in _module_scope_imports(_parse(path)):
            top = mod.split(".")[0]
            if top in _STDLIB or top in _RUNTIME_PROVIDED:
                continue
            local = _local_module_path(mod)
            if local is not None:
                queue.append(local.resolve())
                for init in _parent_package_inits(mod):
                    queue.append(init.resolve())
                continue
            third_party.add(top)
    visited = {str(p.relative_to(_REPO_ROOT)) for p in seen}
    return third_party, visited


# ── Tracer sanity (guards against a vacuous trace) ───────────────────────────

def test_steps_python_transforms_are_discovered():
    """The STEPS table must yield the gold Python transform (read from the
    script, not hardcoded in the tracer)."""
    py_transforms = [rel for _n, rel, kind in _read_steps(_ENTRY_POINT) if kind == "py"]
    assert "gold/gold_sec_features.py" in py_transforms, (
        f"expected gold/gold_sec_features.py among STEPS 'py' transforms; got {py_transforms}"
    )


def test_trace_reaches_the_gold_sentiment_chain():
    """The trace must cross into api.services.sentiment via gold_sec_features
    and follow every parent-package __init__ on the import path."""
    _third_party, visited = _trace_third_party(_reachable_files())
    for expected in (
        "pipelines/run_silver_gold.py",
        "pipelines/_runtime.py",
        "pipelines/__init__.py",
        "config/universe.py",
        "config/__init__.py",
        "gold/gold_sec_features.py",
        "api/__init__.py",
        "api/services/__init__.py",
        "api/services/sentiment.py",
        "api/config.py",
    ):
        assert expected in visited, (
            f"tracer did not visit {expected}; visited={sorted(visited)}"
        )


def test_trace_finds_the_live_failure_packages():
    """The live 2026-10-13 failure packages must be in the traced set
    (loguru and dotenv raised ModuleNotFoundError; yaml is imported by
    config/universe.py on the same path)."""
    third_party, _ = _trace_third_party(_reachable_files())
    expected = {"loguru", "dotenv", "yaml"}
    assert expected <= third_party, (
        f"tracer missed {sorted(expected - third_party)}; traced={sorted(third_party)}"
    )


# ── The actual dependency contract ───────────────────────────────────────────

def _missing_declared(third_party: set[str], deps: list[str]) -> list[str]:
    """Traced imports with no matching declared dependency (shared by the
    contract test and its named mutations)."""
    declared = {_dep_to_import_name(d) for d in deps}
    return sorted(third_party - declared)


def test_traced_third_party_imports_are_declared():
    """Every third-party import reachable at module scope from the job entry
    point must be declared in the job's serverless environment dependencies,
    after normalizing distribution names to import names."""
    third_party, _ = _trace_third_party(_reachable_files())
    assert third_party, "vacuous trace: no third-party imports found"
    missing = _missing_declared(third_party, _job_environment_dependencies())
    assert not missing, (
        f"{_JOB_NAME} serverless environment is missing dependencies for "
        f"imports reachable from {_ENTRY_REL}: {missing}\n"
        f"Declare them under resources/jobs.yml environments[].spec.dependencies "
        f"(currently declared: {sorted(_job_environment_dependencies()) or 'NONE'})"
    )


def test_declared_dependencies_match_requirements_specifiers():
    """Declared dependencies must reuse the 'name>=lower' specifiers from
    pyproject.toml [project].dependencies (no divergent pinning in the job spec)."""
    import tomllib

    deps = _job_environment_dependencies()
    assert deps, (
        f"{_JOB_NAME} declares no dependencies; the entry point needs at least "
        f"the traced third-party imports declared"
    )
    with (_REPO_ROOT / "pyproject.toml").open("rb") as f:
        req_lines = {
            line.strip()
            for line in tomllib.load(f).get("project", {}).get("dependencies", [])
        }
    assert req_lines, "pyproject.toml declares no [project].dependencies"
    mismatched = [d for d in deps if d.strip() not in req_lines]
    assert not mismatched, (
        f"job dependencies {mismatched} do not match dependency specifiers in "
        f"pyproject.toml; use the same 'name>=lower' specifier"
    )


def test_runtime_provided_packages_are_not_declared():
    """pyspark / databricks* come from the serverless runtime and must not be
    pip-declared in the job environment."""
    offenders = [
        d for d in _job_environment_dependencies()
        if _dep_dist_name(d).split("-")[0] in _RUNTIME_PROVIDED
    ]
    assert not offenders, (
        f"{_JOB_NAME} must not declare runtime-provided packages: {offenders}"
    )


# ── Named mutations (self-contained; archive-level proofs live in evidence) ──

def test_mutation_drop_dependency_is_detected():
    """Mutation: removing a needed dependency from the declared list must make
    the declaration check fail."""
    third_party, _ = _trace_third_party(_reachable_files())
    assert "loguru" in third_party, "precondition: loguru is on the traced path"
    mutated = [
        d for d in _job_environment_dependencies()
        if _dep_to_import_name(d) != "loguru"
    ]
    assert "loguru" not in {_dep_to_import_name(d) for d in mutated}, (
        "precondition: mutation removed loguru"
    )
    missing = _missing_declared(third_party, mutated)
    assert "loguru" in missing, (
        f"mutation (drop loguru) was NOT detected; missing={missing}"
    )


def test_mutation_undeclared_on_main_is_detected():
    """Mutation: a jobs.yml without any dependencies (as on main) must fail the
    declaration check."""
    third_party, _ = _trace_third_party(_reachable_files())
    assert _missing_declared(third_party, []), (
        "mutation (main: no dependencies declared) was NOT detected — "
        "the declaration check would pass vacuously"
    )
