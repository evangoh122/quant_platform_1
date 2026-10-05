"""Tests for databricks.yml sync configuration.

Verifies that sync.include overrides .gitignore for frontend/dist and that
the exclude list still blocks frontend/node_modules.
"""

from __future__ import annotations

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


def test_lakebase_analytics_job_paused():
    """lakebase_analytics_refresh must have PAUSED schedule by default."""
    cfg = _load_jobs_config()
    jobs = cfg.get("resources", {}).get("jobs", {})
    job = jobs.get("lakebase_analytics_refresh", {})
    schedule = job.get("schedule", {})
    assert schedule.get("pause_status") == "PAUSED", (
        f"lakebase_analytics_refresh schedule should be PAUSED; got {schedule.get('pause_status')}"
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