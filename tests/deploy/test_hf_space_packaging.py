"""Offline packaging tests for the Hugging Face Docker Space.

Ports the guarantees the deleted Render lane enforced, against the new layout:

* the image is built from pinned base images and installs the runtime group
  from ``uv.lock`` (``uv sync --frozen --no-dev``) — no hand-maintained
  minimal pin list to drift;
* it runs as the HF-required non-root uid 1000 and listens on 7860;
* the Space README carries the required ``sdk: docker`` / ``app_port: 7860``
  front matter without overwriting the project README;
* the publish script is dry-run by default, needs ``--yes``, never accepts a
  token as an argument, and refuses anything but a clean ``origin/main``;
* ``.dockerignore`` keeps secrets and build state out of the image context;
* the retired Render files cannot come back.

All tests are offline.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest
import yaml

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

DOCKERFILE = os.path.join(REPO_ROOT, "deploy", "hf", "Dockerfile")
SPACE_README = os.path.join(REPO_ROOT, "deploy", "hf", "README.space.md")
DOCKERIGNORE = os.path.join(REPO_ROOT, ".dockerignore")
PUBLISH_SCRIPT = os.path.join(REPO_ROOT, "scripts", "publish_hf_space.sh")
HF_DEPLOY_DOC = os.path.join(REPO_ROOT, "docs", "HF_SPACE_DEPLOY.md")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _dockerfile() -> str:
    assert os.path.exists(DOCKERFILE), f"missing {DOCKERFILE}"
    return _read(DOCKERFILE)


def _instructions() -> list[str]:
    """Dockerfile lines with comments/blank lines removed (case preserved)."""
    return [
        line.strip()
        for line in _dockerfile().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# ── base images ─────────────────────────────────────────────────────────────

def test_uses_pinned_base_images():
    """Both stages use explicit tags — never :latest, never a floating major."""
    text = _dockerfile()
    assert "FROM node:20.18.0-slim AS frontend" in text
    assert re.search(r"^FROM python:3\.12(-slim|\.\d+-slim)\b", text, re.MULTILINE), (
        "expected a pinned python:3.12-slim runtime base"
    )
    assert ":latest" not in text


def test_uv_is_pinned_to_an_explicit_version():
    text = _dockerfile()
    m = re.search(r"ghcr\.io/astral-sh/uv:(\d+\.\d+\.\d+)", text)
    assert m, "uv must be copied from a version-pinned official image"
    assert m.group(1) != "latest"


# ── build stages ────────────────────────────────────────────────────────────

def test_frontend_stage_builds_the_spa():
    text = _dockerfile()
    assert "npm ci" in text
    assert "npm run build" in text
    assert "COPY --chown=user --from=frontend /build/frontend/dist ./frontend/dist" in text


def test_runtime_installs_from_the_lock_without_dev_dependencies():
    """The image's dependency set comes from pyproject.toml + uv.lock."""
    text = _dockerfile()
    assert "uv sync --frozen --no-dev" in text
    assert "requirements-render.txt" not in text
    # The lock, not a hand-maintained requirements file, is what gets installed.
    assert "COPY pyproject.toml uv.lock ./" in text


def test_runtime_copies_only_the_demo_packages():
    text = _dockerfile()
    for pkg in ("api", "agent", "db", "config", "security", "pipelines", "sec_kg"):
        assert f"COPY --chown=user {pkg} ./{pkg}" in text, f"missing runtime package {pkg}"
    # Never ship the whole repo (tests/docs/notebooks) into the image.
    assert "COPY . ." not in text
    assert "COPY --chown=user . " not in text


# ── runtime contract ────────────────────────────────────────────────────────

def test_runs_as_hf_non_root_user_1000():
    instructions = _instructions()
    assert any(re.match(r"RUN useradd .*-u 1000\b", line) for line in instructions), (
        "HF Spaces require a uid 1000 user"
    )
    assert "USER user" in instructions


def test_exposes_7860_and_starts_uvicorn_on_it():
    text = _dockerfile()
    assert "EXPOSE 7860" in text
    assert '"--port", "7860"' in text or "--port 7860" in text
    assert "--proxy-headers" in text
    assert "api.main:app" in text


def test_demo_environment_is_set():
    text = _dockerfile()
    assert re.search(r"PUBLIC_DEMO=1", text), "PUBLIC_DEMO=1 must be baked in"
    assert re.search(r"APP_ENV=demo", text), "APP_ENV=demo must be baked in"


def test_healthcheck_hits_the_api_health_route():
    text = _dockerfile()
    assert "HEALTHCHECK" in text
    assert "/api/health" in text


def test_posthog_build_args_are_public_values_only():
    text = _dockerfile()
    assert "ARG VITE_POSTHOG_KEY" in text
    assert "ARG VITE_POSTHOG_HOST" in text
    # Values must be the public PostHog project key, not a secret family.
    for forbidden in ("LAKEBASE_", "DATABRICKS_", "HF_TOKEN", "POLYGON_API_KEY", "IBKR_"):
        assert forbidden not in text, f"{forbidden} must not appear in the demo image recipe"


def test_dockerfile_has_no_embedded_secret_values():
    text = _dockerfile()
    assert not re.search(r"hf_[A-Za-z0-9]{30,}", text)
    assert "PRIVATE KEY" not in text
    assert not re.search(r"(?i)(password|token)\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}", text)


# ── Space README front matter ───────────────────────────────────────────────

def test_space_readme_front_matter():
    text = _read(SPACE_README)
    assert text.startswith("---\n"), "Space README must start with YAML front matter"
    front_matter = text.split("---", 2)[1]
    meta = yaml.safe_load(front_matter)

    assert meta["sdk"] == "docker"
    assert meta["app_port"] == 7860
    assert meta["pinned"] is False
    assert meta["title"]
    assert meta["emoji"]
    assert meta["colorFrom"] in {
        "red", "yellow", "green", "blue", "indigo", "purple", "pink", "gray",
    }
    assert meta["colorTo"] in {
        "red", "yellow", "green", "blue", "indigo", "purple", "pink", "gray",
    }
    assert meta["short_description"]
    assert len(meta["short_description"]) <= 60


def test_project_readme_is_not_replaced_by_the_space_template():
    """The repo README stays the project README (no HF front matter)."""
    project_readme = _read(os.path.join(REPO_ROOT, "README.md"))
    assert not project_readme.startswith("---\n")
    assert "sdk: docker" not in project_readme


# ── dockerignore ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pattern", [
    ".git",
    ".agents",
    ".agentlogs",
    ".venv",
    "**/node_modules",
    "frontend/dist",
    "tests",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    ".databrickscfg",
])
def test_dockerignore_excludes_secrets_and_build_state(pattern):
    lines = {
        line.strip()
        for line in _read(DOCKERIGNORE).splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert pattern in lines, f".dockerignore must exclude {pattern}"


# ── publish script safety ───────────────────────────────────────────────────

def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", PUBLISH_SCRIPT, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=120,
    )


def test_publish_script_is_dry_run_by_default():
    text = _read(PUBLISH_SCRIPT)
    assert "DRY_RUN=1" in text, "publishing must default to a dry run"
    # The upload command is guarded by the --yes flag path.
    assert "--yes" in text
    assert text.count("hf upload") == 1


def test_publish_script_refuses_a_token_argument():
    result = _run_script("--token", "hf_thisisnotarealtoken")
    assert result.returncode != 0
    assert "never accepted as arguments" in result.stderr
    assert "hf_thisisnotarealtoken" not in result.stdout + result.stderr


def test_publish_script_never_prints_the_env_token():
    sentinel = "hf_sentinel-valuedoesnotexist000000000000"
    result = _run_script("--dry-run", "--ref", "HEAD", env={"HF_TOKEN": sentinel})
    # Dry run may succeed or refuse depending on the worktree, but must never
    # echo the token value.
    assert sentinel not in result.stdout + result.stderr


def test_publish_script_uses_git_archive_and_a_temp_dir_outside_the_repo():
    text = _read(PUBLISH_SCRIPT)
    assert "git archive" in text
    assert "mktemp -d" in text
    # The stage dir must not default to a path inside the repo.
    assert "qp1-hf-space" in text


def test_publish_script_refuses_dirty_worktree_and_non_main_head():
    text = _read(PUBLISH_SCRIPT)
    assert "git status --porcelain" in text
    assert "is not origin/main" in text


def test_publish_script_space_id_is_a_single_placeholder_constant():
    text = _read(PUBLISH_SCRIPT)
    assert '<HF_NAMESPACE>/<HF_SPACE>' in text
    # No invented namespace/space anywhere in the script.
    assert not re.search(r"hf upload [A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)


def test_publish_script_only_reads_token_from_environment():
    text = _read(PUBLISH_SCRIPT)
    assert "HF_TOKEN" in text
    # Never read a token file, never accept --token, never echo the value.
    assert not re.search(r"cat\s+.*\.hf|hf_token\s*=|echo\s+\"?\$\{?HF_TOKEN", text)


# ── Render is retired ───────────────────────────────────────────────────────

def test_render_files_are_gone():
    assert not os.path.exists(os.path.join(REPO_ROOT, "render.yaml"))
    assert not os.path.exists(os.path.join(REPO_ROOT, "requirements-render.txt"))
    assert not os.path.exists(os.path.join(REPO_ROOT, "tests", "render"))


def test_render_ci_audit_step_is_gone():
    ci = _read(os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml"))
    assert "requirements-render.txt" not in ci
    assert "requirements-app.txt" not in ci


# ── docs ────────────────────────────────────────────────────────────────────

def test_hf_deploy_doc_covers_the_contract():
    assert os.path.exists(HF_DEPLOY_DOC), "docs/HF_SPACE_DEPLOY.md must exist"
    content = _read(HF_DEPLOY_DOC)

    assert "<HF_NAMESPACE>/<HF_SPACE>" in content, "the placeholder must be documented"
    assert "Render" in content and "retired" in content.lower()
    assert "sdk: docker" in content
    assert "app_port: 7860" in content
    assert "7860" in content
    assert "uv sync --frozen" in content
    assert "/api/health" in content
    assert "deep link" in content.lower() or "deep-link" in content.lower()
    assert "no credentials" in content.lower() or "no secrets" in content.lower()
    assert "LAKEBASE_*" in content
    assert "DATABRICKS_*" in content
    assert "manual" in content.lower()
    assert "rollback" in content.lower() or "redeploy" in content.lower()
    assert "Lane B" in content
    assert "Lane C" in content
