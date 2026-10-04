"""Offline packaging tests for the Render public demo (R1 + R8).

These tests validate that requirements-render.txt, render.yaml, and the
Render documentation section are correct without needing network access
(except for the venv install test, which is marked ``render_install``).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

RENDER_REQ = os.path.join(REPO_ROOT, "requirements-render.txt")
RENDER_YAML = os.path.join(REPO_ROOT, "render.yaml")
DEPLOYMENT_MD = os.path.join(REPO_ROOT, "docs", "DEPLOYMENT.md")

ALLOWED_PACKAGES = {"fastapi", "uvicorn", "pydantic", "loguru"}

FORBIDDEN_DISTRIBUTIONS = [
    "pyspark",
    "psycopg",
    "psycopg-pool",
    "langchain",
    "langchain-community",
    "langgraph",
    "mlflow",
    "ibapi",
    "databricks-sdk",
    "databricks-sql-connector",
]

FORBIDDEN_MODULES = [
    "pyspark",
    "psycopg",
    "langchain",
    "langchain_community",
    "langgraph",
    "mlflow",
    "ibapi",
    "databricks",
    "databricks_sdk",
    "databricks_sql_connector",
]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _parse_render_yaml(text: str) -> dict:
    """Minimal YAML-ish parser for the flat render.yaml structure.

    Returns a dict with top-level keys: type, name, runtime, plan,
    buildCommand, startCommand, healthCheckPath, autoDeploy, envVars
    (list of {key, value}).  Only handles the single-service, no-nesting
    case expected here.
    """
    result: dict = {}
    env_vars: list[dict[str, str]] = []
    current_env: dict[str, str] | None = None
    in_env_list = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Detect start of envVars list
        if re.match(r"\s*envVars:\s*$", line):
            in_env_list = True
            continue

        if in_env_list:
            # List item with key: value on same line
            m = re.match(r"\s*-\s+key:\s*(.+)", stripped)
            if m:
                current_env = {"key": m.group(1).strip().strip("\"'")}
                continue
            m = re.match(r"\s*value:\s*(.+)", stripped)
            if m and current_env is not None:
                current_env["value"] = m.group(1).strip().strip("\"'")
                env_vars.append(current_env)
                current_env = None
                continue
            # If we hit a line that's not an envVars list item, exit
            if not stripped.startswith("-") and "key:" not in stripped and "value:" not in stripped:
                in_env_list = False

        if not in_env_list:
            # Handle "- key: value" (list item) and "key: value" (mapping)
            m = re.match(r"(?:-\s+)?(\w+):\s*(.+)", stripped)
            if m:
                key, val = m.group(1), m.group(2).strip().strip("\"'")
                if key not in ("envVars",):
                    result[key] = val

    result["envVars"] = env_vars
    return result


# ---------------------------------------------------------------------------
# Test 1: requirements-render.txt is exact and minimal
# ---------------------------------------------------------------------------
@pytest.mark.render_install
@pytest.mark.timeout(900)  # clean-venv install exceeds the 30 s global pytest-timeout
def test_render_requirements_are_exact_and_minimal(tmp_path):
    """requirements-render.txt must pin exactly 4 packages with == and exclude
    all forbidden distributions.  After installing into a clean venv,
    ``import api.main`` must succeed and no forbidden distribution may be
    present in ``pip freeze`` output.
    """
    content = _read(RENDER_REQ)
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]

    # Parse package names and verify == pins
    parsed: list[tuple[str, str]] = []
    for line in lines:
        m = re.match(r"^([a-zA-Z0-9_-]+)(?:\[.*?\])?==(.+)$", line)
        assert m, f"Line must use == pin: {line}"
        parsed.append((m.group(1).lower(), m.group(2)))

    names = {p[0] for p in parsed}
    assert names == ALLOWED_PACKAGES, (
        f"Expected exactly {ALLOWED_PACKAGES}, got {names}"
    )
    assert len(parsed) == 4, f"Expected 4 packages, got {len(parsed)}"

    # Install into a clean venv and verify
    tmp_venv = str(tmp_path / "render_test_venv")
    created = subprocess.run(
        [sys.executable, "-m", "venv", tmp_venv],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        # Some hosts (e.g. Debian without python3-venv) cannot create a venv with pip.
        # The pin checks above still ran; CI runners can create venvs.
        pytest.skip(f"cannot create a venv on this host: {created.stdout.strip()[:120]}")
    if sys.platform == "win32":
        pip = os.path.join(tmp_venv, "Scripts", "pip")
        python = os.path.join(tmp_venv, "Scripts", "python")
    else:
        pip = os.path.join(tmp_venv, "bin", "pip")
        python = os.path.join(tmp_venv, "bin", "python")

    try:
        result = subprocess.run(
            [pip, "install", "-r", RENDER_REQ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"pip install failed:\n{result.stderr}"

        # Verify import works (set PYTHONPATH so the venv Python can find api/)
        env = {**os.environ, "PYTHONPATH": REPO_ROOT}
        result = subprocess.run(
            [python, "-c", "import api.main"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=env,
        )
        assert result.returncode == 0, f"import api.main failed:\n{result.stderr}"

        # Verify no forbidden distributions
        freeze = subprocess.run(
            [pip, "freeze"],
            capture_output=True,
            text=True,
        )
        freeze_lower = freeze.stdout.lower()
        for pkg in FORBIDDEN_DISTRIBUTIONS:
            assert pkg.lower() not in freeze_lower, (
                f"Forbidden distribution '{pkg}' found in pip freeze:\n{freeze.stdout}"
            )
    finally:
        import shutil
        shutil.rmtree(tmp_venv, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 2: render.yaml matches the §7 contract
# ---------------------------------------------------------------------------
def test_render_blueprint_matches_contract():
    """render.yaml must define a single web service named qp1-showcase with
    starter plan, Python 3.12.7, Node 20.18.0, manual deploy, correct
    build/start commands, and the required environment variables.
    """
    content = _read(RENDER_YAML)
    svc = _parse_render_yaml(content)

    assert svc.get("type") == "web", f"Expected type 'web', got {svc.get('type')}"
    assert svc.get("name") == "qp1-showcase", f"Expected name 'qp1-showcase', got {svc.get('name')}"
    assert svc.get("runtime") == "python", f"Expected runtime 'python', got {svc.get('runtime')}"
    assert svc.get("plan") == "starter", f"Expected plan 'starter', got {svc.get('plan')}"
    assert svc.get("autoDeploy") == "false", f"Expected autoDeploy false, got {svc.get('autoDeploy')}"

    build_cmd = svc.get("buildCommand", "")
    assert "pip install -r requirements-render.txt" in build_cmd, f"buildCommand must install requirements-render.txt"
    assert "npm ci" in build_cmd, f"buildCommand must run npm ci"
    assert "npm run build" in build_cmd, f"buildCommand must run npm run build"

    start_cmd = svc.get("startCommand", "")
    assert "uvicorn api.main:app" in start_cmd, f"startCommand must run uvicorn"
    assert "$PORT" in start_cmd, f"startCommand must bind $PORT"
    assert "--proxy-headers" in start_cmd, f"startCommand must use --proxy-headers"

    assert svc.get("healthCheckPath") == "/api/health", (
        f"Expected healthCheckPath '/api/health', got {svc.get('healthCheckPath')}"
    )

    # Verify required env vars
    env_map = {e["key"]: e["value"] for e in svc.get("envVars", [])}
    assert env_map.get("PYTHON_VERSION") == "3.12.7", (
        f"Expected PYTHON_VERSION 3.12.7, got {env_map.get('PYTHON_VERSION')}"
    )
    assert env_map.get("NODE_VERSION") == "20.18.0", (
        f"Expected NODE_VERSION 20.18.0, got {env_map.get('NODE_VERSION')}"
    )
    assert env_map.get("PUBLIC_DEMO") == "1", (
        f"Expected PUBLIC_DEMO 1, got {env_map.get('PUBLIC_DEMO')}"
    )
    assert env_map.get("APP_ENV") == "demo", (
        f"Expected APP_ENV demo, got {env_map.get('APP_ENV')}"
    )


# ---------------------------------------------------------------------------
# Test 3: render.yaml contains no secret configuration
# ---------------------------------------------------------------------------
def test_render_blueprint_contains_no_secret_configuration():
    """render.yaml must not contain any secret/sync-false variables or
    sensitive environment variable names.
    """
    content = _read(RENDER_YAML)

    # No syncBlock or sync: false indicators
    assert "syncBlock" not in content, "render.yaml must not contain syncBlock"
    assert "sync: false" not in content.lower(), "render.yaml must not contain sync: false"

    # No secret env var names
    secret_patterns = [
        "LAKEBASE_",
        "DATABRICKS_",
        "POLYGON_API_KEY",
        "IBKR_",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
    ]
    for pattern in secret_patterns:
        assert pattern not in content, (
            f"render.yaml must not contain secret variable '{pattern}'"
        )

    # Verify all env var values are non-secret (no base64 blobs, no long strings)
    env_vars = _parse_render_yaml(content).get("envVars", [])
    for ev in env_vars:
        val = ev.get("value", "")
        assert len(val) < 100, (
            f"Env var {ev['key']} has suspiciously long value ({len(val)} chars)"
        )


# ---------------------------------------------------------------------------
# Test 4: documentation has build, start, and smoke contract
# ---------------------------------------------------------------------------
def test_render_documentation_has_build_start_and_smoke_contract():
    """docs/DEPLOYMENT.md must contain a Render public demo section with the
    exact build command, start command, and smoke test contract.
    """
    content = _read(DEPLOYMENT_MD)

    # Section heading exists
    assert "Render public demo" in content, (
        "docs/DEPLOYMENT.md must contain a 'Render public demo' section"
    )

    # Build command
    assert "pip install -r requirements-render.txt" in content, (
        "Documentation must contain the build command"
    )
    assert "npm ci" in content, "Documentation must reference npm ci"
    assert "npm run build" in content, "Documentation must reference npm run build"

    # Start command
    assert "uvicorn api.main:app" in content, (
        "Documentation must contain the start command"
    )
    assert "$PORT" in content, "Documentation must reference $PORT"

    # Smoke tests
    assert "/api/health" in content, "Documentation must contain health check smoke test"

    # SPA deep-link behavior
    assert "deep link" in content.lower() or "deep-link" in content.lower(), (
        "Documentation must describe SPA deep-link behavior"
    )

    # Empty-secret / no-credentials requirement
    assert "no credentials" in content.lower() or "no secrets" in content.lower() or "no secret" in content.lower(), (
        "Documentation must state the service contains no credentials"
    )

    # Prohibition on secret variable families
    assert "LAKEBASE_*" in content, "Documentation must prohibit LAKEBASE_* variables"
    assert "DATABRICKS_*" in content, "Documentation must prohibit DATABRICKS_* variables"

    # Manual deploy
    assert "manual deploy" in content.lower(), (
        "Documentation must describe manual deploy procedure"
    )

    # Safety gates
    assert "Lane B" in content, "Documentation must reference Lane B safety gates"
    assert "Lane C" in content, "Documentation must reference Lane C safety gates"

    # Rollback
    assert "rollback" in content.lower() or "redeploy" in content.lower(), (
        "Documentation must describe rollback procedure"
    )