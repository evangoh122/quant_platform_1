"""cd.yml must install the toolchain that `databricks bundle deploy` shells out to.

The CD workflow does not build anything itself: `bundle deploy` builds the
`python_requirements` artifact with `uv export` and the `frontend` artifact with
the package manager (see databricks.yml and
tests/test_databricks_bundle_artifacts.py). The GitHub runner image ships
neither uv nor a guaranteed Node version, so the deploy job has to install both
*before* the deploy step, with the same pinned actions and inputs CI uses.

Removing either setup step, unpinning it (tag instead of commit SHA), or moving
it after the deploy step makes one of these tests fail.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
CD_WORKFLOW = WORKFLOW_DIR / "cd.yml"
CI_WORKFLOW = WORKFLOW_DIR / "ci.yml"

# Supply-chain rule: third-party actions are pinned to a full commit SHA, never
# to a mutable tag or branch.
SHA_PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

SETUP_UV = "astral-sh/setup-uv"
SETUP_NODE = "actions/setup-node"


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cd_steps() -> list[dict]:
    jobs = _workflow(CD_WORKFLOW).get("jobs") or {}
    assert set(jobs) == {"deploy"}, (
        f"cd.yml is expected to declare exactly the deploy job, got {sorted(jobs)}"
    )
    steps = jobs["deploy"].get("steps") or []
    assert steps, "cd.yml deploy job must declare steps"
    return steps


def _action(step: dict) -> str:
    return str(step.get("uses") or "").split("@", 1)[0]


def _step_index(steps: list[dict], action: str) -> int:
    hits = [i for i, step in enumerate(steps) if _action(step) == action]
    assert len(hits) == 1, (
        f"cd.yml deploy job must install {action} exactly once, found {len(hits)}"
    )
    return hits[0]


def _deploy_index(steps: list[dict]) -> int:
    hits = [
        i
        for i, step in enumerate(steps)
        if "databricks bundle deploy" in str(step.get("run") or "")
    ]
    assert len(hits) == 1, (
        f"cd.yml deploy job must run `databricks bundle deploy` exactly once, found {len(hits)}"
    )
    return hits[0]


def _ci_step(job_name: str, action: str) -> dict:
    steps = _workflow(CI_WORKFLOW)["jobs"][job_name]["steps"]
    hits = [step for step in steps if _action(step) == action]
    assert len(hits) == 1, f"ci.yml {job_name} job must use {action} exactly once"
    return hits[0]


def test_cd_installs_uv_before_the_deploy_step(cd_steps: list[dict]):
    uv_index = _step_index(cd_steps, SETUP_UV)
    deploy_index = _deploy_index(cd_steps)
    assert uv_index < deploy_index, (
        "cd.yml must install uv before `databricks bundle deploy`, because the "
        "python_requirements artifact runs `uv export` during the deploy"
    )
    # An unconditional step cannot be skipped and leave the deploy without uv.
    assert "if" not in cd_steps[uv_index], "the uv setup step must not be conditional"


def test_cd_installs_node_before_the_deploy_step(cd_steps: list[dict]):
    node_index = _step_index(cd_steps, SETUP_NODE)
    deploy_index = _deploy_index(cd_steps)
    assert node_index < deploy_index, (
        "cd.yml must install Node.js before `databricks bundle deploy`, because "
        "the frontend artifact builds the SPA with npm during the deploy"
    )
    assert "if" not in cd_steps[node_index], "the Node.js setup step must not be conditional"


def test_cd_setup_actions_are_sha_pinned(cd_steps: list[dict]):
    for action in (SETUP_UV, SETUP_NODE):
        uses = str(cd_steps[_step_index(cd_steps, action)].get("uses") or "")
        assert SHA_PINNED.match(uses), (
            f"{action} must be pinned to a full 40-character commit SHA, got {uses!r}"
        )


def test_cd_toolchain_matches_ci(cd_steps: list[dict]):
    """CD and CI must install the same uv/Node versions and cache keys."""
    pairs = (
        (SETUP_UV, "python-tests"),
        (SETUP_NODE, "frontend"),
    )
    for action, ci_job in pairs:
        cd_step = cd_steps[_step_index(cd_steps, action)]
        ci_step = _ci_step(ci_job, action)
        assert cd_step.get("uses") == ci_step.get("uses"), (
            f"cd.yml {action} pins {cd_step.get('uses')!r} but ci.yml {ci_job} "
            f"pins {ci_step.get('uses')!r}; keep the same pinned action"
        )
        assert cd_step.get("with") == ci_step.get("with"), (
            f"cd.yml {action} uses inputs {cd_step.get('with')!r} but ci.yml "
            f"{ci_job} uses {ci_step.get('with')!r}; keep the same inputs"
        )
