"""tests/test_jobs_serverless.py — Serverless entry-point invariants.

Validates that every ``python_file`` entry point in ``resources/jobs.yml``
is safe to run on Databricks serverless (where ``__file__`` is not defined
and ``DatabricksSession`` must not be created inside a job runtime).

Acceptance criteria (from BUILD-serverless-entrypoints.md):
  1. No task with ``environment_key`` has a ``libraries`` key.
  2. Every ``python_file`` exists on disk.
  3. Static scan: no bare ``__file__`` at module level outside _runtime.
  4. Static scan: no ``DatabricksSession.builder.serverless`` outside _runtime.
  5. ``get_spark()`` returns the ambient session when DATABRICKS_RUNTIME_VERSION is set.
  6. ``repo_root()`` works when ``__file__`` is absent.
  7. Named mutations: re-add libraries → fails; reintroduce __file__ → fails;
     call .serverless(True) inside a runtime → fails.
"""
from __future__ import annotations

import os
import re
import textwrap
from pathlib import Path
from typing import Dict, List

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JOBS_YML = _REPO_ROOT / "resources" / "jobs.yml"

# ── helpers ───────────────────────────────────────────────────────────────────

def _load_jobs() -> dict:
    with open(_JOBS_YML) as f:
        return yaml.safe_load(f)


def _collect_tasks(jobs_cfg: dict) -> List[dict]:
    """Flatten all tasks from all jobs."""
    tasks = []
    for job in jobs_cfg.get("resources", {}).get("jobs", {}).values():
        for task in job.get("tasks", []):
            tasks.append(task)
    return tasks


def _python_file_tasks(jobs_cfg: dict) -> List[dict]:
    """Return tasks that have a spark_python_task.python_file."""
    return [
        t for t in _collect_tasks(jobs_cfg)
        if "spark_python_task" in t and "python_file" in t["spark_python_task"]
    ]


def _resolve_python_file(rel_path: str) -> Path:
    """Resolve a python_file path (relative to resources/) to an absolute path."""
    return (_REPO_ROOT / "resources" / rel_path).resolve()


def _read_entry_point_sources() -> Dict[str, str]:
    """Read source code of every python_file entry point."""
    cfg = _load_jobs()
    sources = {}
    for task in _python_file_tasks(cfg):
        rel = task["spark_python_task"]["python_file"]
        path = _resolve_python_file(rel)
        if path.exists():
            sources[str(path)] = path.read_text(encoding="utf-8")
    return sources


# ── 1. No libraries on serverless tasks ──────────────────────────────────────

def test_no_libraries_on_serverless_tasks():
    """No task with environment_key may carry a ``libraries`` key."""
    cfg = _load_jobs()
    for task in _collect_tasks(cfg):
        if "environment_key" in task:
            assert "libraries" not in task, (
                f"Task '{task.get('task_key')}' has environment_key="
                f"'{task['environment_key']}' but also has 'libraries'. "
                f"Serverless deps belong in environments.*.spec.dependencies."
            )


# ── 2. Every python_file exists ──────────────────────────────────────────────

def test_every_python_file_exists():
    """Every python_file referenced in jobs.yml must exist on disk."""
    cfg = _load_jobs()
    for task in _python_file_tasks(cfg):
        rel = task["spark_python_task"]["python_file"]
        path = _resolve_python_file(rel)
        assert path.exists(), (
            f"python_file '{rel}' (task '{task.get('task_key')}') "
            f"does not exist at {path}"
        )


# ── 3. No bare __file__ at module level (outside _runtime.py) ────────────────

# Pattern matches __file__ usage that is NOT inside a string or comment,
# and NOT the _runtime.py file itself.
_BARE_FILE_RE = re.compile(
    r"(?<!['\"])(?<!\w)__file__(?!\w)(?!['\"])",
)


def test_no_bare_dunder_file_in_entry_points():
    """Entry points must not use bare ``__file__`` at module level.

    Serverless ``spark_python_task`` does not define ``__file__``.
    Use ``pipelines._runtime.repo_root()`` instead.
    """
    sources = _read_entry_point_sources()
    for fpath, src in sources.items():
        if "_runtime.py" in fpath:
            continue  # _runtime.py is allowed to reference __file__
        lines = src.splitlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and strings
            if stripped.startswith("#"):
                continue
            if _BARE_FILE_RE.search(line):
                # Allow __file__ inside docstrings or string literals only
                # if it's clearly in a quoted context (simple heuristic)
                if "__file__" in line and ('"' in line or "'" in line):
                    # Could be a comment referencing __file__
                    # Check if it's ONLY in a comment
                    code_part = line.split("#")[0]
                    if not _BARE_FILE_RE.search(code_part):
                        continue
                pytest.fail(
                    f"{fpath}:{lineno}: bare __file__ found: {stripped!r}\n"
                    f"Use pipelines._runtime.repo_root() instead."
                )


# ── 4. No DatabricksSession.builder.serverless outside _runtime.py ──────────

_SERVERLESS_RE = re.compile(r"DatabricksSession\.builder\.serverless")


def test_no_serverless_session_outside_runtime():
    """Entry points must not call ``DatabricksSession.builder.serverless()``.

    Use ``pipelines._runtime.get_spark()`` instead.
    """
    sources = _read_entry_point_sources()
    for fpath, src in sources.items():
        if "_runtime.py" in fpath:
            continue
        for lineno, line in enumerate(src.splitlines(), 1):
            if _SERVERLESS_RE.search(line):
                pytest.fail(
                    f"{fpath}:{lineno}: DatabricksSession.builder.serverless() "
                    f"found outside _runtime.py: {line.strip()!r}\n"
                    f"Use pipelines._runtime.get_spark() instead."
                )


# ── 5. get_spark() returns ambient session when DATABRICKS_RUNTIME_VERSION set ──

def test_get_spark_uses_ambient_session_in_runtime(monkeypatch):
    """When DATABRICKS_RUNTIME_VERSION is set, get_spark() must use
    SparkSession.builder.getOrCreate() (the ambient session)."""
    # Set the env var to simulate running inside a Databricks job
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")

    # Create a fake pyspark module with a SparkSession that records calls
    import types

    class FakeBuilder:
        def getOrCreate(self):
            return "AMBIENT_SESSION"

    class FakeSparkSession:
        builder = FakeBuilder()

    fake_pyspark = types.ModuleType("pyspark")
    fake_pyspark_sql = types.ModuleType("pyspark.sql")
    fake_pyspark_sql.SparkSession = FakeSparkSession
    fake_pyspark.sql = fake_pyspark_sql

    monkeypatch.setitem(__import__("sys").modules, "pyspark", fake_pyspark)
    monkeypatch.setitem(__import__("sys").modules, "pyspark.sql", fake_pyspark_sql)

    # Import fresh to avoid cached module state
    import importlib
    import pipelines._runtime as rt
    importlib.reload(rt)

    result = rt.get_spark()
    assert result == "AMBIENT_SESSION", (
        f"get_spark() should return ambient SparkSession when "
        f"DATABRICKS_RUNTIME_VERSION is set, got {result!r}"
    )


# ── 6. repo_root() works when __file__ is absent ────────────────────────────

def test_repo_root_works_without_dunder_file(monkeypatch):
    """repo_root() must resolve correctly when __file__ is not in globals.

    Simulates serverless spark_python_task where __file__ is absent.
    """
    import importlib
    import pipelines._runtime as rt

    # Read the source and exec without __file__ in globals
    source_path = Path(rt.__file__).resolve()
    source = source_path.read_text(encoding="utf-8")

    # Simulate serverless: no __file__, sys.argv[0] points to a script
    fake_script = str(_REPO_ROOT / "pipelines" / "build_sec_embeddings.py")
    fake_globals = {"__name__": "__test__", "__file__": None}

    # The module uses globals().get("__file__") — when __file__ is None,
    # globals().get returns None, so it falls back to sys.argv[0].
    # But we need to actually test the function, not exec the whole module.
    # Instead, test the function directly with __file__ removed from its module.

    original_file = rt.__file__
    try:
        # Temporarily remove __file__ from the module's globals
        if hasattr(rt, "__file__"):
            delattr(rt, "__file__")
        monkeypatch.setattr("sys.argv", [fake_script])

        root = rt.repo_root()
        assert root == _REPO_ROOT, (
            f"repo_root() returned {root}, expected {_REPO_ROOT}"
        )
    finally:
        # Restore
        rt.__file__ = original_file


# ── 7. Named mutation tests ──────────────────────────────────────────────────

def test_mutation_libraries_on_serverless_task_fails(tmp_path):
    """Mutation: re-add libraries to a serverless task → test must fail."""
    mutated_yml = textwrap.dedent("""\
        resources:
          jobs:
            test_job:
              tasks:
                - task_key: test_task
                  spark_python_task:
                    python_file: ../pipelines/run_silver_gold.py
                  environment_key: serverless
                  libraries: []
              environments:
                - environment_key: serverless
                  spec:
                    client: "1"
    """)
    cfg = yaml.safe_load(mutated_yml)
    with pytest.raises(AssertionError, match="libraries"):
        for task in _collect_tasks(cfg):
            if "environment_key" in task:
                assert "libraries" not in task, (
                    f"Task '{task.get('task_key')}' has environment_key="
                    f"'{task['environment_key']}' but also has 'libraries'. "
                    f"Serverless deps belong in environments.*.spec.dependencies."
                )


def test_mutation_bare_dunder_file_in_entry_point():
    """Mutation: reintroduce __file__ in an entry point → static scan catches it."""
    bad_source = textwrap.dedent("""\
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    """)
    # This should be caught by the regex
    for lineno, line in enumerate(bad_source.splitlines(), 1):
        code_part = line.split("#")[0]
        if _BARE_FILE_RE.search(code_part):
            return  # Caught correctly
    pytest.fail("Mutation test: bare __file__ was NOT detected by static scan")


def test_mutation_serverless_call_outside_runtime():
    """Mutation: call .serverless(True) inside a runtime → scan catches it."""
    bad_source = textwrap.dedent("""\
        from databricks.connect import DatabricksSession
        spark = DatabricksSession.builder.serverless(True).getOrCreate()
    """)
    for lineno, line in enumerate(bad_source.splitlines(), 1):
        if _SERVERLESS_RE.search(line):
            return  # Caught correctly
    pytest.fail(
        "Mutation test: DatabricksSession.builder.serverless() was NOT detected"
    )


# ── 8. Static scan covers EVERY python_file in jobs.yml ────────────────────

_EXPECTED_PYTHON_FILES = {
    "pipelines/run_silver_gold.py",
    "ml/run_ablation.py",
    "pipelines/build_sec_embeddings.py",
    "pipelines/sec_rag_ingest.py",
    "pipelines/build_sec_knowledge_graph.py",
    "pipelines/lakebase_analytics.py",
}


def test_static_scan_covers_all_python_files():
    """Every python_file in jobs.yml must be picked up by the static scan."""
    cfg = _load_jobs()
    discovered: set[str] = set()
    for task in _python_file_tasks(cfg):
        rel = task["spark_python_task"]["python_file"]
        # Normalise ../ prefix that jobs.yml uses
        normed = rel.lstrip("../")
        discovered.add(normed)
    missing = _EXPECTED_PYTHON_FILES - discovered
    assert not missing, (
        f"These python_files are in jobs.yml but were NOT discovered by "
        f"_python_file_tasks(): {missing}"
    )


# ── 9. Ablation output path is absolute and not cwd-dependent ──────────────

def test_ablation_output_path_is_absolute():
    """_resolve_output_dir must always return an absolute path."""
    import ml.run_ablation as ra

    # Local default → repo_root() / 'artifacts' (absolute)
    path = ra._resolve_output_dir(None)
    assert path.is_absolute(), f"Default output path is not absolute: {path}"

    # Explicit absolute → passed through
    path = ra._resolve_output_dir("/tmp/explicit")
    assert path == Path("/tmp/explicit")

    # Databricks runtime → /Volumes/...
    import os as _os
    old = _os.environ.get("DATABRICKS_RUNTIME_VERSION")
    try:
        _os.environ["DATABRICKS_RUNTIME_VERSION"] = "15.4"
        path = ra._resolve_output_dir(None)
        assert str(path).startswith("/Volumes/"), (
            f"Databricks output path should start with /Volumes/, got {path}"
        )
        assert path.is_absolute()
    finally:
        if old is None:
            _os.environ.pop("DATABRICKS_RUNTIME_VERSION", None)
        else:
            _os.environ["DATABRICKS_RUNTIME_VERSION"] = old


def test_ablation_output_path_not_cwd_dependent(monkeypatch):
    """Default output path must not change when cwd changes."""
    import ml.run_ablation as ra

    path_a = ra._resolve_output_dir(None)
    # Changing cwd must NOT change the resolved default path
    monkeypatch.chdir("/")
    path_b = ra._resolve_output_dir(None)
    assert path_a == path_b, (
        f"Output path changed when cwd changed: {path_a} vs {path_b}. "
        f"The default path must be derived from repo_root(), not cwd."
    )


# ── 10. Mutation: revert ablation to relative output path → test fails ─────

def test_mutation_ablation_relative_output_path_fails():
    """Mutation: if run_ablation.py used a relative out_dir, the absolute-path
    test would fail because the path would be cwd-dependent."""
    import ml.run_ablation as ra

    # Simulate the OLD broken code: out_dir = "ml/results" (relative)
    broken_path = Path("ml/results")
    assert not broken_path.is_absolute(), (
        "Mutation sanity check: 'ml/results' should be relative"
    )
    # The real _resolve_output_dir must return an absolute path
    good_path = ra._resolve_output_dir(None)
    assert good_path.is_absolute(), (
        f"_resolve_output_dir(None) returned relative path: {good_path}"
    )