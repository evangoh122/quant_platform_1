"""tests/test_job_environment_dependencies.py — declared vs imported YAML.

A Databricks serverless job environment installs nothing unless it is listed
under ``environments[].spec.dependencies``.  ``notebooks/refresh_bronze_corporate_actions.py``
imports ``config.research_symbols``, which imports ``yaml`` at module scope, so
the ``corporate_action_refresh`` job could not import its own entry point
without the ``pyyaml`` distribution.

This test walks **every** task in ``resources/jobs.yml`` — both
``spark_python_task.python_file`` and ``notebook_task.notebook_path`` — traces
the module-scope third-party imports reachable from that entry point, and
asserts that a task whose entry point needs ``yaml`` declares ``pyyaml`` in the
environment it runs in.

Tracing reuses the AST tracer in ``tests/test_silver_gold_job_deps.py``: only
module-scope imports count (a lazy function-body ``import yaml``, as in
``pipelines/sec_rag_ingest.py:565``, must not force a declaration), repo-local
modules are followed transitively, and runtime-provided packages are ignored.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tests.test_silver_gold_job_deps import (
    _REPO_ROOT,
    _dep_to_import_name,
    _trace_third_party,
)

_JOBS_YML = _REPO_ROOT / "resources" / "jobs.yml"
_IMPORT_NAME = "yaml"
_CORPORATE_ACTION_JOB = "corporate_action_refresh"
_CORPORATE_ACTION_TASK = "refresh_bronze_corporate_actions"


# ── jobs.yml helpers ─────────────────────────────────────────────────────────

def _jobs() -> dict:
    with open(_JOBS_YML, encoding="utf-8") as f:
        return yaml.safe_load(f)["resources"]["jobs"]


def _entry_point(task: dict) -> Path | None:
    """Resolve a task's Python entry point, or None when it has none."""
    if "spark_python_task" in task:
        rel = task["spark_python_task"].get("python_file")
    elif "notebook_task" in task:
        rel = task["notebook_task"].get("notebook_path")
    else:
        rel = None
    if not rel:
        return None
    # jobs.yml paths are relative to resources/ (e.g. ../notebooks/x.py).
    return (_REPO_ROOT / "resources" / rel).resolve()


def _environment_dependencies(job_key: str, job: dict, task: dict) -> list[str]:
    """Dependencies declared by the environment that runs ``task``."""
    key = task.get("environment_key")
    if key is None:
        return []
    matching = [
        env for env in (job.get("environments") or [])
        if env.get("environment_key") == key
    ]
    assert matching, (
        f"{job_key}: task {task.get('task_key')!r} references environment "
        f"{key!r}, which the job does not declare"
    )
    deps: list[str] = []
    for env in matching:
        deps.extend((env.get("spec") or {}).get("dependencies") or [])
    return deps


def _traced_tasks() -> list[tuple[str, str, Path, set[str], list[str]]]:
    """(job_key, task_key, entry_point, traced imports, declared deps) per task."""
    traced = []
    for job_key, job in _jobs().items():
        for task in job.get("tasks") or []:
            entry = _entry_point(task)
            if entry is None:
                continue
            third_party, _visited = _trace_third_party([entry])
            traced.append(
                (
                    job_key,
                    str(task.get("task_key")),
                    entry,
                    third_party,
                    _environment_dependencies(job_key, job, task),
                )
            )
    return traced


def _yaml_consumers() -> list[tuple[str, str, Path, list[str]]]:
    """Tasks whose entry point imports ``yaml`` at module scope."""
    return [
        (job_key, task_key, entry, deps)
        for job_key, task_key, entry, third_party, deps in _traced_tasks()
        if _IMPORT_NAME in third_party
    ]


def _declares_pyyaml(deps: list[str]) -> bool:
    return _IMPORT_NAME in {_dep_to_import_name(dep) for dep in deps}


# ── tracer sanity (guards against a vacuous pass) ────────────────────────────

def test_trace_reaches_yaml_through_config_research_symbols():
    """The notebook path must cross into config/research_symbols.py -> yaml."""
    entry = (_REPO_ROOT / "notebooks" / "refresh_bronze_corporate_actions.py").resolve()
    third_party, visited = _trace_third_party([entry])
    assert "config/research_symbols.py" in visited, (
        f"tracer did not visit config/research_symbols.py; visited={sorted(visited)}"
    )
    assert _IMPORT_NAME in third_party, (
        f"tracer missed yaml on the corporate-action path; traced={sorted(third_party)}"
    )


def test_at_least_one_job_needs_pyyaml():
    """A trace that finds no yaml consumer would make the contract vacuous."""
    consumers = _yaml_consumers()
    assert consumers, (
        "no jobs.yml task imports a module that imports yaml; the declaration "
        "check below would pass vacuously"
    )


# ── The actual dependency contract ───────────────────────────────────────────

def test_every_yaml_importing_job_declares_pyyaml():
    """Every job whose entry point needs ``yaml`` must declare ``pyyaml``."""
    offenders = [
        f"{job_key}:{task_key} ({entry.relative_to(_REPO_ROOT)} declares "
        f"{deps or 'NONE'})"
        for job_key, task_key, entry, deps in _yaml_consumers()
        if not _declares_pyyaml(deps)
    ]
    assert not offenders, (
        "serverless environments are missing pyyaml for entry points that "
        "import yaml:\n  " + "\n  ".join(offenders)
        + "\nDeclare 'pyyaml>=6.0' under resources/jobs.yml "
        "environments[].spec.dependencies."
    )


def test_corporate_action_refresh_declares_pyyaml():
    """Named contract: the corporate-action job declares pyyaml."""
    consumers = {
        (job_key, task_key): deps
        for job_key, task_key, _entry, deps in _yaml_consumers()
    }
    key = (_CORPORATE_ACTION_JOB, _CORPORATE_ACTION_TASK)
    assert key in consumers, (
        f"{_CORPORATE_ACTION_JOB}:{_CORPORATE_ACTION_TASK} does not trace a "
        f"module-scope yaml import; traced consumers={sorted(consumers)}"
    )
    assert _declares_pyyaml(consumers[key]), (
        f"{_CORPORATE_ACTION_JOB} must declare pyyaml in its environment; "
        f"declared={consumers[key] or 'NONE'}"
    )


def test_declared_pyyaml_reuses_the_requirements_specifier():
    """The declared line must be the same specifier requirements.txt uses."""
    requirement_lines = {
        line.strip()
        for line in (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    declared = [
        dep
        for _job_key, _task_key, _entry, deps in _yaml_consumers()
        for dep in deps
        if _dep_to_import_name(dep) == _IMPORT_NAME
    ]
    assert declared, "no pyyaml declaration found among the yaml consumers"
    unmatched = set(declared) - requirement_lines
    assert not unmatched, (
        f"pyyaml declarations {sorted(unmatched)} do not match a "
        "requirements.txt line"
    )


# ── Named mutation (self-contained; archive proof lives in evidence) ─────────

def test_mutation_removing_pyyaml_is_detected():
    """Mutation: dropping pyyaml from the corporate-action environment fails."""
    consumers = {
        (job_key, task_key): deps
        for job_key, task_key, _entry, deps in _yaml_consumers()
    }
    deps = consumers[(_CORPORATE_ACTION_JOB, _CORPORATE_ACTION_TASK)]
    assert _declares_pyyaml(deps), "precondition: pyyaml is declared"

    mutated = [dep for dep in deps if _dep_to_import_name(dep) != _IMPORT_NAME]
    assert not _declares_pyyaml(mutated), (
        "mutation (drop pyyaml) was NOT detected by the declaration check"
    )
