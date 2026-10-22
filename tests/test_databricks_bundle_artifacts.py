"""databricks.yml artifacts: `bundle deploy` builds npm and uv outputs itself.

The bundle previously relied on a manual `scripts/build_frontend.sh` (and a
manual `uv export`) before `databricks bundle deploy`. These tests pin the
replacement contract:

* a `frontend` artifact runs `npm ci && npm run build` in frontend/ and fails
  the deploy when `dist/index.html` is missing;
* a `python_requirements` artifact regenerates the root requirements.txt from
  uv.lock (`uv export --frozen ...`);
* `sync.include` covers every generated path, so the built/locked outputs are
  actually uploaded (sync.include overrides .gitignore for frontend/dist).

Removing or renaming either artifact, or dropping a sync.include entry, makes
one of these tests fail.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATABRICKS_YML = REPO_ROOT / "databricks.yml"
CD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cd.yml"

# Fields the CLI supports for an artifact (verified with `databricks bundle
# schema`, CLI v1.16.1): build, path, type, files, executable, dynamic_version,
# git, include.  We use only build/path.
SUPPORTED_FIELDS = {
    "build", "path", "type", "files", "executable", "dynamic_version",
    "git", "include",
}


@pytest.fixture(scope="module")
def bundle() -> dict:
    return yaml.safe_load(DATABRICKS_YML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def artifacts(bundle: dict) -> dict:
    return bundle.get("artifacts") or {}


def test_bundle_declares_both_artifacts(artifacts: dict):
    assert set(artifacts) == {"frontend", "python_requirements"}, (
        "databricks.yml must declare exactly the frontend and python_requirements "
        f"artifacts, got {sorted(artifacts)}"
    )


def test_frontend_artifact_builds_the_spa(artifacts: dict):
    frontend = artifacts["frontend"]
    assert frontend["path"] == "frontend"
    build = frontend["build"]
    assert "npm ci" in build
    assert "npm run build" in build
    # A missing SPA build must fail the deploy instead of shipping an API-only app.
    assert "dist/index.html" in build
    assert "test -f" in build


def test_python_requirements_artifact_regenerates_from_the_lock(artifacts: dict):
    art = artifacts["python_requirements"]
    assert art["path"] == "."
    build = art["build"]
    assert "uv export" in build or "export_requirements.sh" in build, (
        "the requirements artifact must be generated from uv.lock"
    )
    if "export_requirements.sh" in build:
        script = REPO_ROOT / "scripts" / "export_requirements.sh"
        assert script.exists(), "the referenced export script must exist"
        assert "uv export" in script.read_text(encoding="utf-8")
    assert "requirements.txt" in build


def test_artifacts_use_only_supported_fields(artifacts: dict):
    for name, art in artifacts.items():
        assert isinstance(art, dict), f"artifact {name} must be a mapping"
        unknown = set(art) - SUPPORTED_FIELDS
        assert not unknown, f"artifact {name} uses unsupported field(s): {sorted(unknown)}"
        assert art.get("build"), f"artifact {name} must declare a build command"
        assert art.get("path"), f"artifact {name} must declare a path"


def test_sync_include_covers_every_generated_path(bundle: dict, artifacts: dict):
    include = set((bundle.get("sync") or {}).get("include") or [])
    generated = {"frontend/dist/**", "requirements.txt"}
    missing = generated - include
    assert not missing, (
        f"sync.include must cover generated path(s) {sorted(missing)}; "
        f"currently {sorted(include)}"
    )


def test_no_manual_frontend_build_in_the_deploy_workflow():
    """The bundle artifacts replace the manual npm build in cd.yml."""
    cd = CD_WORKFLOW.read_text(encoding="utf-8")
    assert "npm ci" not in cd, "cd.yml must rely on the bundle's frontend artifact"
    assert "bundle deploy" in cd
