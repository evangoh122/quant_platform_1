# BUILD-ci-uv — IMPLEMENT NOW (small, single PR)

You are MiMo. Branch `ci/uv-install` (worktree qp1-uvci). Stay on it. One or two commits, LF endings, never touch `.agents/dispatch.sh`.
Goal: faster CI installs with uv, same requirement files, no behaviour change.
1. .github/workflows/ci.yml — in every job that pip-installs (Python tests, Dependency audit, any other): add
   `astral-sh/setup-uv` (pin to a full commit SHA like the other actions, with a version comment) and replace
   `python -m pip install ...` with `uv pip install --system ...` (keep the ibapi / `-r requirements.txt` stripping logic exactly;
   keep `pip-audit` installed via `uv pip install --system pip-audit`). Keep actions/setup-python. Drop `python -m pip install --upgrade pip`.
   Keep the pip cache config working or switch to setup-uv's `enable-cache: true` with `cache-dependency-glob` covering requirements*.txt.
2. Do NOT change render.yaml, Databricks bundle files, app.yaml or requirements*.txt (Render and Databricks Apps keep pip).
3. Add a short note in docs/CICD.md: CI installs with uv; Render/Databricks use pip; same requirement files.
Validation: YAML parses (python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"); `uv pip install --system --dry-run -r requirements.txt`
style check locally if possible. Claude verifies by pushing and watching CI. Verdict: .agents/mimo/VERDICT-ci-uv.md.
