"""Offline regression: the HF Space image environment must boot in demo mode.

The runtime stage of ``deploy/hf/Dockerfile`` starts from ``python:3.12-slim``,
which sets ``ENV GPG_KEY=<CPython release-signing fingerprint>``.  Docker keeps
that variable in the child image, and ``api/demo.py`` rejects every non-empty
``*_KEY`` while ``PUBLIC_DEMO=1`` (the gate is deliberately broad: a false
positive is far cheaper than a shipped credential).  The image therefore
refused to start with ``PublicDemoConfigurationError ... GPG_KEY``, even though
the Dockerfile bakes ``PUBLIC_DEMO=1``.  Docker is not available in the review
environment, so nothing caught it before a Space restart would have.

These tests reconstruct the *effective* container environment exactly the way
the Docker build does — the known base-image ENV, overlaid with every ``ENV``
instruction of the runtime stage, overlaid with the variables Hugging Face
Spaces inject at runtime — and assert that
:func:`api.demo.validate_public_demo_environment` accepts it.

The Dockerfile ``ENV`` values are parsed from the file (continuations, quoting
and ``${VAR}`` expansion included) and never hard-coded, so dropping the
``GPG_KEY=`` override makes the boot test fail instead of passing vacuously.

All tests are offline and do not need Docker.
"""
from __future__ import annotations

import os
import re

import pytest

from api.demo import PublicDemoConfigurationError, validate_public_demo_environment

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKERFILE = os.path.join(REPO_ROOT, "deploy", "hf", "Dockerfile")

_RUNTIME_BASE = re.compile(r"^FROM\s+python:3\.12-slim\s+AS\s+runtime\s*$")

# ENV recorded by ``python:3.12-slim`` — what ``docker run --rm python:3.12-slim
# env`` prints, minus the variables the Dockerfile itself sets.  ``GPG_KEY`` is
# the CPython release-signing fingerprint baked in by the official image; it is
# not a credential, but ``api/demo.py`` matches on the ``_KEY`` suffix.
# Both ``GPG_KEY`` and ``PYTHON_SHA256`` use placeholder values: the gate never
# inspects them, only that the variables exist and are non-empty (a real
# fingerprint here would trip the gitleaks generic-api-key rule).
_BASE_IMAGE_ENV = {
    "PATH": "/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "GPG_KEY": "CPython-release-signing-fingerprint-placeholder",
    "PYTHON_VERSION": "3.12.11",
    "PYTHON_SHA256": "6f8d0b1c6f8d0b1c6f8d0b1c6f8d0b1c6f8d0b1c6f8d0b1c6f8d0b1c6f8d0b1c",
}

# Variables Hugging Face Spaces injects into every Docker Space at runtime:
# https://huggingface.co/docs/hub/en/spaces-overview#built-in-environment-variables
# plus HF_HOME (cache location on the persistent volume).  SPACE_SIGNING_SECRET
# is HF-managed and Space-local; it is on the demo allow-list because it grants
# no access to Lakebase, Databricks or a broker.
_HF_INJECTED_ENV = {
    "SPACE_ID": "example-owner/example-space",
    "SPACE_HOST": "example-owner-example-space.hf.space",
    "SPACE_AUTHOR_NAME": "example-owner",
    "SPACE_REPO_NAME": "example-space",
    "SPACE_TITLE": "Quant Platform Demo",
    "SPACE_CREATOR_USER_ID": "64f0c0ffee00000000000000",
    "CPU_CORES": "2",
    "MEMORY": "16Gi",
    "ACCELERATOR": "none",
    "HF_HOME": "/home/user/.cache/huggingface",
    "SPACE_SIGNING_SECRET": "hf-space-local-signing-value",
}

# One ``KEY=VALUE`` assignment as Docker accepts it: double-quoted, single-quoted
# or bare.
_ENV_ASSIGNMENT = re.compile(
    r"""(?P<key>[A-Za-z_][A-Za-z0-9_]*)="""
    r"""(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>\S*))"""
)

_VAR_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _dockerfile_text() -> str:
    assert os.path.exists(DOCKERFILE), f"missing {DOCKERFILE}"
    with open(DOCKERFILE, encoding="utf-8") as handle:
        return handle.read()


def _runtime_stage_instructions() -> list[str]:
    """Return the runtime stage's instructions with continuations joined."""
    lines = _dockerfile_text().splitlines()
    for index, line in enumerate(lines):
        if _RUNTIME_BASE.match(line.strip()):
            stage_lines = lines[index + 1:]
            break
    else:  # pragma: no cover - test_hf_space_packaging pins the FROM line
        raise AssertionError(
            "runtime stage 'FROM python:3.12-slim AS runtime' not found in "
            f"{DOCKERFILE}"
        )

    instructions: list[str] = []
    pending = ""
    for raw in stage_lines:
        line = raw.rstrip()
        if not pending and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        pending += line
        instructions.append(pending.strip())
        pending = ""
    if pending:  # pragma: no cover - a dangling continuation is a broken file
        raise AssertionError(f"dangling line continuation in {DOCKERFILE}: {pending!r}")
    return instructions


def _expand(value: str, known: dict[str, str]) -> str:
    """Expand ``${VAR}`` / ``$VAR`` references the way Docker does."""

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        if name not in known:
            raise AssertionError(f"Dockerfile ENV references undefined ${{{name}}}")
        return known[name]

    return _VAR_REFERENCE.sub(_replace, value)


def _parse_env_body(body: str, known: dict[str, str]) -> dict[str, str]:
    """Parse the ``KEY=VALUE ...`` body of one ``ENV`` instruction."""
    parsed: dict[str, str] = {}
    position = 0
    while position < len(body):
        while position < len(body) and body[position].isspace():
            position += 1
        if position >= len(body):
            break
        match = _ENV_ASSIGNMENT.match(body, position)
        if match is None:
            raise AssertionError(
                f"unparsed ENV fragment in {DOCKERFILE}: {body[position:]!r}"
            )
        raw = next(
            value
            for value in (
                match.group("double"),
                match.group("single"),
                match.group("bare"),
            )
            if value is not None
        )
        parsed[match.group("key")] = _expand(raw, {**known, **parsed})
        position = match.end()
    return parsed


def _dockerfile_runtime_env() -> dict[str, str]:
    """Every ENV the Dockerfile sets in the runtime stage, values expanded."""
    env: dict[str, str] = {}
    for instruction in _runtime_stage_instructions():
        if instruction.upper().startswith("ENV "):
            env.update(
                _parse_env_body(instruction[4:].strip(), {**_BASE_IMAGE_ENV, **env})
            )
    assert env, f"no ENV instructions found in the runtime stage of {DOCKERFILE}"
    return env


def _effective_space_env(*, include_dockerfile_env: bool = True) -> dict[str, str]:
    """Base image ENV + Dockerfile ENV + HF-injected vars (later wins)."""
    env = dict(_BASE_IMAGE_ENV)
    if include_dockerfile_env:
        env.update(_dockerfile_runtime_env())
    env.update(_HF_INJECTED_ENV)
    return env


# ── the parser is not vacuous ────────────────────────────────────────────────

def test_runtime_env_is_parsed_from_the_dockerfile():
    """The parsed ENV really is the Dockerfile's, continuations and all."""
    env = _dockerfile_runtime_env()

    assert env["PUBLIC_DEMO"] == "1"
    assert env["APP_ENV"] == "demo"
    assert env["HF_HOME"] == "/home/user/.cache/huggingface"
    # Quoted, ${PATH}-expanded continuation line:
    assert env["PATH"].startswith("/home/user/app/.venv/bin:")
    assert env["PATH"].endswith(_BASE_IMAGE_ENV["PATH"])
    assert env["HOME"] == "/home/user"


def test_dockerfile_shadows_the_base_image_gpg_key():
    """The runtime stage must neutralise the inherited GPG_KEY, not inherit it."""
    env = _dockerfile_runtime_env()

    assert "GPG_KEY" in env, (
        "deploy/hf/Dockerfile must set an empty GPG_KEY in the runtime stage; "
        "python:3.12-slim sets a non-empty one and PUBLIC_DEMO=1 rejects it"
    )
    assert env["GPG_KEY"] == ""


# ── the image environment boots (and the old environment did not) ────────────

def test_space_environment_passes_public_demo_validation(monkeypatch):
    """The built image's effective environment starts under PUBLIC_DEMO=1."""
    monkeypatch.setenv("PUBLIC_DEMO", "1")

    env = _effective_space_env()

    # Must not raise PublicDemoConfigurationError.
    validate_public_demo_environment(env)


def test_space_environment_without_the_override_is_rejected(monkeypatch):
    """Regression: without the Dockerfile's GPG_KEY= the base value is fatal.

    This is the reported boot failure, reproduced with the same effective
    environment minus one Dockerfile ENV line.
    """
    monkeypatch.setenv("PUBLIC_DEMO", "1")

    env = _effective_space_env(include_dockerfile_env=False)
    assert env["GPG_KEY"] == _BASE_IMAGE_ENV["GPG_KEY"], "base GPG_KEY must be non-empty"

    with pytest.raises(PublicDemoConfigurationError) as excinfo:
        validate_public_demo_environment(env)

    message = str(excinfo.value)
    assert "GPG_KEY" in message, f"expected GPG_KEY to be named, got: {message}"
    # The gate reports variable names only, never values.
    assert _BASE_IMAGE_ENV["GPG_KEY"] not in message
