"""Tests for databricks.yml sync configuration.

Verifies that sync.include overrides .gitignore for frontend/dist and that
the exclude list still blocks frontend/node_modules.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATABRICKS_YML = _REPO_ROOT / "databricks.yml"
_JOBS_YML = _REPO_ROOT / "resources" / "jobs.yml"


def _load_bundle_config() -> dict:
    with open(_DATABRICKS_YML) as f:
        return yaml.safe_load(f)


def _load_jobs_config() -> dict:
    with open(_JOBS_YML) as f:
        return yaml.safe_load(f)


def test_sync_include_has_frontend_dist():
    """sync.include must contain frontend/dist/** so bundle deploy ships the SPA."""
    cfg = _load_bundle_config()
    includes = cfg.get("sync", {}).get("include", [])
    assert "frontend/dist/**" in includes, (
        f"sync.include missing 'frontend/dist/**'; got {includes}"
    )


def test_sync_exclude_has_node_modules():
    """sync.exclude must still block frontend/node_modules from the bundle."""
    cfg = _load_bundle_config()
    excludes = cfg.get("sync", {}).get("exclude", [])
    assert "frontend/node_modules" in excludes, (
        f"sync.exclude missing 'frontend/node_modules'; got {excludes}"
    )


def test_sync_exclude_has_pycache():
    """sync.exclude must block __pycache__ directories."""
    cfg = _load_bundle_config()
    excludes = cfg.get("sync", {}).get("exclude", [])
    assert "**/__pycache__" in excludes


def test_lakebase_analytics_schedule_pause_status_is_a_paused_by_default_variable():
    """The nightly schedule ships paused, but stays opt-in via a bundle variable.

    Owner decision 2026-10-23: "Keep it paused but give me the option to
    schedule." ``resources/jobs.yml`` therefore references
    ``${var.analytics_schedule_pause_status}`` instead of hard-coding a status,
    ``databricks.yml`` declares that variable with the default ``PAUSED``, and
    no target may default it to anything else. The Jobs API accepts only
    ``PAUSED`` and ``UNPAUSED``, so the value is restricted to those two.

    Mutations this catches: hard-coding ``pause_status: UNPAUSED`` (or
    ``PAUSED``) in resources/jobs.yml, and defaulting the variable to
    ``UNPAUSED`` in databricks.yml.
    """
    allowed = ("PAUSED", "UNPAUSED")

    def status_of(spec, context: str) -> str:
        # A bundle variable / target variable is either the status itself or a
        # map carrying it under `default`.
        if isinstance(spec, dict):
            spec = spec.get("default")
        assert spec in allowed, (
            f"{context} must be one of {allowed}; got {spec!r}"
        )
        return spec

    jobs = _load_jobs_config().get("resources", {}).get("jobs", {})
    job = jobs.get("lakebase_analytics_refresh", {})
    schedule = job.get("schedule", {})
    assert schedule.get("pause_status") == "${var.analytics_schedule_pause_status}", (
        "lakebase_analytics_refresh schedule.pause_status must reference "
        "${var.analytics_schedule_pause_status} (PAUSED by default, UNPAUSED "
        f"on owner opt-in); got {schedule.get('pause_status')!r}"
    )

    cfg = _load_bundle_config()
    variables = cfg.get("variables") or {}
    spec = variables.get("analytics_schedule_pause_status")
    assert spec is not None, (
        "databricks.yml must declare the bundle variable "
        f"analytics_schedule_pause_status; declared: {sorted(variables)}"
    )
    if isinstance(spec, dict):
        assert str(spec.get("description", "")).strip(), (
            "analytics_schedule_pause_status must carry a description"
        )
    root_default = status_of(spec, "variables.analytics_schedule_pause_status")
    assert root_default == "PAUSED", (
        "variables.analytics_schedule_pause_status must default to PAUSED; "
        f"got {root_default!r}"
    )

    targets = cfg.get("targets") or {}
    assert targets, "databricks.yml must declare at least one target"
    for target_name in sorted(targets):
        target_vars = (targets[target_name] or {}).get("variables") or {}
        target_default = status_of(
            target_vars.get("analytics_schedule_pause_status", root_default),
            f"targets.{target_name}.variables.analytics_schedule_pause_status",
        )
        assert target_default == "PAUSED", (
            f"target {target_name} must default analytics_schedule_pause_status "
            f"to PAUSED; got {target_default!r}"
        )


def test_lakebase_analytics_job_single_concurrency():
    """lakebase_analytics_refresh must have max_concurrent_runs: 1."""
    cfg = _load_jobs_config()
    jobs = cfg.get("resources", {}).get("jobs", {})
    job = jobs.get("lakebase_analytics_refresh", {})
    assert job.get("max_concurrent_runs") == 1, (
        f"lakebase_analytics_refresh max_concurrent_runs should be 1; "
        f"got {job.get('max_concurrent_runs')}"
    )


def test_lakebase_analytics_job_retries_and_timeout():
    """Retry/timeout settings must live on the task, per the bundle schema.

    ``max_retries`` and ``min_retry_interval_millis`` are task-level fields in
    the Databricks bundle schema (``databricks bundle validate`` warns
    "unknown field" at job level). ``timeout_seconds`` is asserted on the task;
    the job-level per-run timeout must be absent (or large enough to cover all
    attempts), because a job timeout equal to one task timeout lets the first
    timed-out attempt consume the whole run budget and starves the retries.
    """
    cfg = _load_jobs_config()
    jobs = cfg.get("resources", {}).get("jobs", {})
    job = jobs.get("lakebase_analytics_refresh", {})
    tasks = {t.get("task_key"): t for t in job.get("tasks", [])}
    task = tasks.get("refresh_analytics", {})
    assert task.get("max_retries") == 2, (
        f"refresh_analytics task max_retries should be 2; "
        f"got {task.get('max_retries')}"
    )
    assert task.get("min_retry_interval_millis") == 60000, (
        f"refresh_analytics task min_retry_interval_millis should be 60000; "
        f"got {task.get('min_retry_interval_millis')}"
    )
    assert task.get("timeout_seconds") == 3600, (
        f"refresh_analytics task timeout_seconds should be 3600; "
        f"got {task.get('timeout_seconds')}"
    )
    # Bundle schema: max_retries / min_retry_interval_millis are invalid at
    # job level ("unknown field" warnings from `databricks bundle validate`).
    assert "max_retries" not in job, (
        "lakebase_analytics_refresh must not set job-level max_retries "
        "(task-level field in the bundle schema)"
    )
    assert "min_retry_interval_millis" not in job, (
        "lakebase_analytics_refresh must not set job-level "
        "min_retry_interval_millis (task-level field in the bundle schema)"
    )
    # Job-level per-run timeout: absent, or >= budget for every attempt plus
    # the retry back-off intervals (3 * task timeout + 2 * retry intervals).
    retries = task.get("max_retries", 0)
    task_timeout = task.get("timeout_seconds", 0)
    retry_interval_s = task.get("min_retry_interval_millis", 0) / 1000.0
    min_run_budget = (retries + 1) * task_timeout + retries * retry_interval_s
    job_timeout = job.get("timeout_seconds")
    assert job_timeout is None or job_timeout >= min_run_budget, (
        f"lakebase_analytics_refresh job-level timeout_seconds must be absent "
        f"or >= {min_run_budget:.0f} (3 * task timeout + retry intervals); "
        f"got {job_timeout}"
    )


# ── job env dependency coverage (imports reachable from the entry point) ─────

_IMPORT_TO_DIST = {
    "psycopg_pool": "psycopg-pool",
    "yaml": "pyyaml",
    "databricks": "databricks-sdk",
    "databricks.sdk": "databricks-sdk",
    "databricks.sql": "databricks-sql-connector",
}

# Provided by the Databricks serverless runtime, never pip-installed into the
# job environment.
_RUNTIME_PROVIDED = {"pyspark", "databricks.connect"}

_STDLIB_MODULES = set(sys.stdlib_module_names) | {"__future__"}


def _resolve_local_module(mod: str) -> Path | None:
    """Resolve a dotted module name to a repo-local file, if any."""
    candidate = _REPO_ROOT.joinpath(*mod.split("."))
    file_candidate = candidate.with_suffix(".py")
    if file_candidate.is_file():
        return file_candidate
    init_candidate = candidate / "__init__.py"
    if init_candidate.is_file():
        return init_candidate
    return None


def _is_runtime_provided(name: str) -> bool:
    parts = name.split(".")
    return any(".".join(parts[:i]) in _RUNTIME_PROVIDED for i in range(1, len(parts) + 1))


def _import_to_dist(import_name: str) -> str:
    """Map an import name to its likely PyPI distribution name."""
    if import_name in _IMPORT_TO_DIST:
        return _IMPORT_TO_DIST[import_name]
    parts = import_name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in _IMPORT_TO_DIST:
            return _IMPORT_TO_DIST[prefix]
    if len(parts) > 1:
        return parts[0].replace("_", "-")
    return import_name.replace("_", "-")


def _reachable_imports(entry: Path) -> set[str]:
    """Transitive AST import closure from *entry*, following repo-local modules.

    Walks whole files (including function bodies) so deferred imports such as
    ``from db import lakebase`` or ``from databricks.sdk import ...`` are
    collected too.
    """
    third_party: set[str] = set()
    seen_files: set[Path] = set()
    queue: list[Path] = [entry]
    while queue:
        path = queue.pop()
        if path in seen_files:
            continue
        seen_files.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
                names += [
                    f"{node.module}.{alias.name}"
                    for alias in node.names
                    if alias.name != "*"
                ]
            for name in names:
                top = name.split(".")[0]
                if top in _STDLIB_MODULES:
                    continue
                if _resolve_local_module(top) is not None:
                    parts = name.split(".")
                    for i in range(1, len(parts) + 1):
                        local = _resolve_local_module(".".join(parts[:i]))
                        if local is not None:
                            queue.append(local)
                    continue
                third_party.add(name)
                third_party.add(top)
    return third_party


def test_lakebase_analytics_job_env_declares_runtime_imports():
    """Every third-party import reachable from ``pipelines/lakebase_analytics.py``
    (including ``db.lakebase`` and its ``psycopg_pool`` / ``databricks.sdk``
    imports) must be declared in the job environment dependencies.

    Fails when e.g. ``psycopg-pool`` is removed from the environment spec.
    """
    cfg = _load_jobs_config()
    job = cfg.get("resources", {}).get("jobs", {}).get("lakebase_analytics_refresh", {})
    env_keys = {t.get("environment_key") for t in job.get("tasks", [])}
    declared: set[str] = set()
    for env in job.get("environments", []):
        if env.get("environment_key") in env_keys:
            for dep in env.get("spec", {}).get("dependencies", []):
                name = re.split(r"[><=\[;,\s]", dep.strip())[0].strip().lower()
                if name:
                    declared.add(name)
    assert declared, (
        "lakebase_analytics_refresh has no environment dependencies; "
        "runtime imports cannot be satisfied"
    )

    entry = _REPO_ROOT / "pipelines" / "lakebase_analytics.py"
    assert entry.is_file(), f"entry point missing: {entry}"
    imports = _reachable_imports(entry)

    derived: set[str] = set()
    for imp in imports:
        if imp.split(".")[0] in _STDLIB_MODULES:
            continue
        if _is_runtime_provided(imp):
            continue
        derived.add(_import_to_dist(imp))

    missing = sorted(d for d in derived if d not in declared)
    assert not missing, (
        f"third-party imports reachable from pipelines/lakebase_analytics.py "
        f"(incl. db.lakebase) are not declared in the job environment: "
        f"{missing}; declared={sorted(declared)}"
    )


# db/lakebase.py:_mint_token_via_sdk calls
# WorkspaceClient().database.generate_database_credential(instance_names=[...],
# request_id=...), which lives in databricks.sdk.service.database and first
# exists in databricks-sdk 0.56.0, and then reads
# DatabaseCredential.expiration_time (db/lakebase.py:65), which only exists
# from databricks-sdk 0.57.0. Older floors are satisfied by the preinstalled
# serverless SDK, which never upgrades, so the mint would fail on every run.
_DATABRICKS_SDK_MIN_VERSION = (0, 57, 0)


def test_lakebase_analytics_job_databricks_sdk_floor():
    """The declared databricks-sdk lower bound must be >= 0.57.0.

    Parses the declared version specifier and asserts its ``>=`` floor covers
    DatabaseCredential.expiration_time. Fails when the floor is e.g. 0.20.0
    or 0.56.0 (whose DatabaseCredential has ``token`` but no
    ``expiration_time``).
    """
    cfg = _load_jobs_config()
    job = cfg.get("resources", {}).get("jobs", {}).get("lakebase_analytics_refresh", {})
    env_keys = {t.get("environment_key") for t in job.get("tasks", [])}
    deps: list[str] = []
    for env in job.get("environments", []):
        if env.get("environment_key") in env_keys:
            deps.extend(env.get("spec", {}).get("dependencies", []))
    sdk_specs = [
        d for d in deps
        if re.split(r"[><=\[;,\s]", d.strip())[0].strip().lower() == "databricks-sdk"
    ]
    assert len(sdk_specs) == 1, (
        f"expected exactly one databricks-sdk dependency in the job environment; "
        f"got {sdk_specs}"
    )
    spec = sdk_specs[0]
    match = re.search(r">=\s*(\d+(?:\.\d+)*)", spec)
    assert match, (
        f"databricks-sdk dependency must declare a >= lower bound; got {spec!r}"
    )
    floor = tuple(int(part) for part in match.group(1).split("."))
    floor += (0,) * (3 - len(floor))
    assert floor >= _DATABRICKS_SDK_MIN_VERSION, (
        f"databricks-sdk floor {floor} is below {_DATABRICKS_SDK_MIN_VERSION}: "
        f"databricks.sdk.service.database.DatabaseCredential.expiration_time "
        f"(read by db/lakebase.py) only exists from 0.57.0; got {spec!r}"
    )


def test_lakebase_analytics_job_no_empty_or_unresolved_notifications():
    """No resolved job in resources/jobs.yml may carry a bad notification address.

    ``email_notifications.on_failure: ["${var.alert_email}"]`` resolved to
    ``[""]`` while ``alert_email`` defaulted to "", and the Jobs API may reject
    an empty address and fail the whole bundle deploy. Fails on an empty-string
    address or an unresolved ``${var.alert_email}`` reference; operators add
    failure notifications at deploy time instead (see the runbook).
    """
    bundle = _load_bundle_config()
    variables = bundle.get("variables") or {}
    cfg = _load_jobs_config()
    jobs = cfg.get("resources", {}).get("jobs", {})

    def resolve(text: str, context: str) -> str:
        def repl(match: "re.Match[str]") -> str:
            name = match.group(1)
            spec = variables.get(name)
            assert spec is not None, (
                f"unresolved ${{var.{name}}} in {context}; declared bundle "
                f"variables: {sorted(variables)}"
            )
            return str(spec.get("default", ""))
        return re.sub(r"\$\{var\.([A-Za-z0-9_]+)\}", repl, text)

    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from strings(value)

    for job_name, job in jobs.items():
        for section in ("email_notifications", "webhook_notifications"):
            notifications = job.get(section) or {}
            for field, node in notifications.items():
                for value in strings(node):
                    resolved = resolve(value, f"job {job_name} {section}.{field}")
                    assert resolved.strip(), (
                        f"job {job_name} {section}.{field} resolves to an "
                        f"empty notification address (was {value!r})"
                    )
                    assert "${" not in resolved, (
                        f"job {job_name} {section}.{field} keeps an "
                        f"unresolved placeholder: {resolved!r}"
                    )
        # alert_email is no longer a declared bundle variable, so any job still
        # referencing ${var.alert_email} would deploy with an unresolved/empty
        # notification address.
        assert "alert_email" not in yaml.dump(job), (
            f"job {job_name} references the removed alert_email variable"
        )


def test_lakebase_analytics_job_no_secrets_or_url():
    """lakebase_analytics_refresh must not contain secret literals or LAKEBASE_URL."""
    import yaml as _yaml
    _JOBS_YML = Path(__file__).resolve().parent.parent / "resources" / "jobs.yml"
    raw = _JOBS_YML.read_text(encoding="utf-8")

    cfg = _load_jobs_config()
    jobs = cfg.get("resources", {}).get("jobs", {})
    job = jobs.get("lakebase_analytics_refresh", {})
    job_str = _yaml.dump(job)

    for forbidden in ["LAKEBASE_URL", "password", "token", "secret", "api_key"]:
        assert forbidden.lower() not in job_str.lower(), (
            f"lakebase_analytics_refresh contains forbidden term: {forbidden}"
        )

    params = []
    for task in job.get("tasks", []):
        params.extend(task.get("spark_python_task", {}).get("parameters", []))
    for p in params:
        assert "LAKEBASE_URL" not in str(p)
        assert "password" not in str(p).lower()
        assert "@" not in str(p)

    env_specs = job.get("environments", [])
    for env in env_specs:
        deps = env.get("spec", {}).get("dependencies", [])
        for dep in deps:
            assert "password" not in dep.lower()
            assert "@" not in dep