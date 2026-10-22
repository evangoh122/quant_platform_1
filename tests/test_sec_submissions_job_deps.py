"""tests/test_sec_submissions_job_deps.py — sec_submissions_ingest serverless deps.

The KG-0 job ``sec_submissions_ingest`` runs
``pipelines/ingest_sec_submissions.py`` in a serverless ``spark_python_task``
environment.  A serverless environment installs nothing that is not declared
under ``environments[].spec.dependencies``, and this entry point has no
third-party import at module scope — the only one is ``requests``, imported by
``pipelines/_http_adapter.py``, which ``run_ingest_submissions`` imports lazily
on the ``--live`` path (the only path that performs work).  Without the
declaration a live run dies with ``ModuleNotFoundError: No module named
'requests'``, the same failure mode as the 2026-10-13 ``loguru``/``dotenv``
incident that ``tests/test_silver_gold_job_deps.py`` guards for
``silver_gold_refresh``.

This module reuses the AST tracer from ``tests/test_silver_gold_job_deps.py``
with one extra rule: the entry point's *own* function-local imports are part of
its runtime closure, because every one of them is on the ``--live`` path the job
exists to run.  Function-local imports inside the other modules it reaches are
not traced: they belong to code paths this job never executes (the RAG HTML
helpers pull in ``bs4``, its config loader pulls in ``yaml``), and declaring
them would advertise dependencies the job does not use.

``pyspark`` / ``databricks*`` come from the serverless runtime and must never be
declared.  ``pipelines/_http_adapter.py`` currently starts with a UTF-8 BOM, so
sources are decoded with ``utf-8-sig`` (Python's tokenizer strips a BOM before
parsing; ``ast.parse`` on decoded text must too — see the same strip in
``tests/rag/test_sec_embeddings_incremental.py``).
"""
from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import yaml

from tests.test_silver_gold_job_deps import (
    _RUNTIME_PROVIDED,
    _STDLIB,
    _dep_dist_name,
    _dep_to_import_name,
    _local_module_path,
    _missing_declared,
    _module_scope_imports,
    _parent_package_inits,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JOBS_YML = _REPO_ROOT / "resources" / "jobs.yml"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

_JOB_NAME = "sec_submissions_ingest"
_ENTRY_REL = "pipelines/ingest_sec_submissions.py"
_ENTRY_POINT = _REPO_ROOT / _ENTRY_REL

# The module that makes ``requests`` reachable on the --live path.
_HTTP_ADAPTER_REL = "pipelines/_http_adapter.py"

# Transitive third-party imports this job needs at run time.  Asserted exactly
# so a silently vanishing trace (e.g. the lazy import moving out of the entry
# point) cannot make the declaration check pass vacuously.
_EXPECTED_THIRD_PARTY = {"requests"}


# ── AST helpers ─────────────────────────────────────────────────────────────

def _parse(path: Path) -> ast.Module:
    """Parse a source file, tolerating a UTF-8 BOM like Python's tokenizer."""
    return ast.parse(
        path.read_text(encoding="utf-8-sig"),
        filename=str(path),
    )


def _all_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """Every absolute import in a module: module scope *and* function bodies."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0 or not node.module:
                continue  # relative imports cannot name a third-party distribution
            out.append((node.lineno, node.module))
    return out


def _trace_runtime_closure() -> tuple[dict[str, list[str]], set[str]]:
    """Trace third-party imports reachable from the job entry point.

    Returns ``(import name -> ["repo/relative.py:line", ...], visited files)``.
    The entry point is scanned for imports anywhere in the module; every other
    repo-local module it reaches is scanned at module scope only.
    """
    seen: set[Path] = set()
    third_party: dict[str, list[str]] = {}
    queue: list[tuple[Path, bool]] = [(_ENTRY_POINT.resolve(), True)]

    while queue:
        path, deep = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        imports = (
            _all_imports(_parse(path)) if deep else _module_scope_imports(_parse(path))
        )
        rel = str(path.relative_to(_REPO_ROOT))
        for lineno, mod in imports:
            top = mod.split(".")[0]
            if top in _STDLIB or top in _RUNTIME_PROVIDED:
                continue
            local = _local_module_path(mod)
            if local is not None:
                queue.append((local.resolve(), False))
                for init in _parent_package_inits(mod):
                    queue.append((init.resolve(), False))
                continue
            third_party.setdefault(top, []).append(f"{rel}:{lineno}")

    visited = {str(p.relative_to(_REPO_ROOT)) for p in seen}
    return third_party, visited


# ── jobs.yml / pyproject.toml readers ───────────────────────────────────────

def _job_environment_dependencies() -> list[str]:
    """Every ``spec.dependencies`` string declared for the job."""
    with open(_JOBS_YML, encoding="utf-8") as f:
        jobs = (yaml.safe_load(f) or {}).get("resources", {}).get("jobs", {})
    job = jobs.get(_JOB_NAME)
    assert job is not None, f"job {_JOB_NAME!r} missing from {_JOBS_YML}"
    deps: list[str] = []
    for env in job.get("environments", []):
        deps.extend((env.get("spec") or {}).get("dependencies") or [])
    return deps


def _pyproject_runtime_dependencies() -> set[str]:
    return set(
        tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    )


# ── Trace sanity (guards against a vacuous trace) ───────────────────────────

def test_trace_reaches_the_live_http_adapter():
    """The traced closure must reach ``_http_adapter`` — that is where the one
    third-party import of this job lives, so a trace that misses it would
    prove nothing."""
    third_party, visited = _trace_runtime_closure()

    assert _ENTRY_REL in visited, f"entry point not visited; visited={visited}"
    assert _HTTP_ADAPTER_REL in visited, (
        f"the --live import of {_HTTP_ADAPTER_REL} was not traced; visited={visited}"
    )
    origins = third_party.get("requests") or []
    assert origins, f"requests not traced; traced={sorted(third_party)}"
    assert all(o.startswith(f"{_HTTP_ADAPTER_REL}:") for o in origins), origins


def test_traced_third_party_set_is_expected():
    """Exactly one third-party import is reachable, and it is ``requests``.

    This is the anti-vacuity guard for the trace: if the lazy ``from
    pipelines._http_adapter import RequestsAdapter`` ever leaves the entry
    point, the traced set empties (or changes) and this fails instead of the
    declaration check silently passing with nothing to compare.
    """
    third_party, _visited = _trace_runtime_closure()
    assert set(third_party) == _EXPECTED_THIRD_PARTY, (
        f"traced third-party imports {sorted(third_party)} != expected "
        f"{sorted(_EXPECTED_THIRD_PARTY)}; if the import closure genuinely "
        f"changed, update the job dependencies and this expectation"
    )


# ── The actual dependency contract ──────────────────────────────────────────

def test_traced_third_party_imports_are_declared():
    """Every third-party import reachable on the job's run path must be
    declared in the job's serverless environment dependencies.

    Fails on the pre-fix jobs.yml, which declared no dependencies at all.
    """
    third_party, _visited = _trace_runtime_closure()
    assert third_party, "vacuous trace: no third-party imports found"
    missing = _missing_declared(set(third_party), _job_environment_dependencies())
    assert not missing, (
        f"{_JOB_NAME} serverless environment is missing dependencies for "
        f"imports reachable from {_ENTRY_REL}: {missing}"
        f" (traced origins: {third_party})\n"
        f"Declare them under resources/jobs.yml environments[].spec.dependencies "
        f"(currently declared: {sorted(_job_environment_dependencies()) or 'NONE'})"
    )


def test_declared_dependencies_are_used_by_the_closure():
    """The converse: nothing may be declared that the run path never imports.

    An unrelated pin would install a package the job does not use and hide the
    fact that the real runtime dependency is undeclared.
    """
    third_party, _visited = _trace_runtime_closure()
    traced_imports = {_dep_to_import_name(name) for name in third_party}
    extra = sorted(
        d for d in _job_environment_dependencies() if _dep_to_import_name(d) not in traced_imports
    )
    assert not extra, (
        f"{_JOB_NAME} declares {extra}, which no import reachable from "
        f"{_ENTRY_REL} uses (traced: {sorted(traced_imports)})"
    )


def test_declared_dependencies_match_pyproject_specifiers():
    """A declared dependency must reuse a ``[project].dependencies`` specifier
    verbatim: pyproject.toml + uv.lock are the source of truth, so the job must
    not re-pin (or drift from) the runtime requirement."""
    deps = _job_environment_dependencies()
    assert deps, f"{_JOB_NAME} declares no dependencies"
    declared = _pyproject_runtime_dependencies()
    mismatched = sorted(d for d in deps if d.strip() not in declared)
    assert not mismatched, (
        f"job dependencies {mismatched} do not match the runtime dependency "
        f"specifiers in pyproject.toml [project].dependencies; use the same "
        f"'name>=lower' specifier"
    )


def test_requests_specifier_is_the_pyproject_one():
    """The requests entry is exactly the pyproject.toml specifier."""
    expected = sorted(
        s for s in _pyproject_runtime_dependencies()
        if _dep_dist_name(s) == "requests"
    )
    assert expected, "pyproject.toml declares no requests runtime dependency"
    declared = sorted(
        d for d in _job_environment_dependencies() if _dep_dist_name(d) == "requests"
    )
    assert declared == expected, (
        f"{_JOB_NAME} requests specifier {declared} != pyproject.toml {expected}"
    )


def test_runtime_provided_packages_are_not_declared():
    """pyspark / databricks* come from the serverless runtime."""
    offenders = [
        d for d in _job_environment_dependencies()
        if _dep_dist_name(d).split("-")[0] in _RUNTIME_PROVIDED
    ]
    assert not offenders, (
        f"{_JOB_NAME} must not declare runtime-provided packages: {offenders}"
    )


# ── Named mutations (the archive-level proofs live in the evidence file) ────

def test_mutation_drop_requests_is_detected():
    """Mutation: removing the ``requests`` line from jobs.yml must fail the
    declaration check (this is the CodeRabbit finding)."""
    third_party, _visited = _trace_runtime_closure()
    assert "requests" in third_party, "precondition: requests is traced"

    mutated = [
        d for d in _job_environment_dependencies()
        if _dep_to_import_name(d) != "requests"
    ]
    assert "requests" not in {_dep_to_import_name(d) for d in mutated}, (
        "precondition: the mutation removed requests"
    )
    assert "requests" in _missing_declared(set(third_party), mutated), (
        f"mutation (drop requests) was NOT detected; mutated deps={mutated}"
    )


def test_mutation_no_dependencies_is_detected():
    """Mutation: an empty dependency list (the pre-fix jobs.yml) must fail."""
    third_party, _visited = _trace_runtime_closure()
    assert _missing_declared(set(third_party), []), (
        "mutation (no dependencies declared) was NOT detected — the "
        "declaration check would pass vacuously"
    )


def test_jobs_yml_parses_with_the_declaration():
    """The raw YAML still parses and carries the requests specifier under the
    KG-0 job's serverless environment (guards an indentation mistake that
    ``_job_environment_dependencies`` would otherwise report as 'no deps')."""
    text = _JOBS_YML.read_text(encoding="utf-8")
    jobs = (yaml.safe_load(text) or {})["resources"]["jobs"]
    spec = jobs[_JOB_NAME]["environments"][0]["spec"]
    assert spec["client"] == "1"
    deps = spec.get("dependencies") or []
    assert any(re.fullmatch(r"requests>=[0-9.]+", dep) for dep in deps), spec
