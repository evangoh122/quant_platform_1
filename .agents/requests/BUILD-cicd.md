# BUILD-REQUEST: cicd

**Branch:** `ci/github-actions-dab` (worktree `/home/jianj/code/qp1-ci`)
**Builder:** Codex · **Validator:** Claude (runs every step locally, `bundle validate` against
the workspace, and a real GitHub Actions run), then CodeRabbit on the PR.

This branch is an **integration branch**: `main` + PR #13 (test collection) + #7 (app, incl.
#11) + #8 (silver/gold) + #9 (ML). It is what `main` will be once those merge. Measured
baseline here: `pytest --co` → 446 collected, 0 errors; offline suite
(`-m "not spark and not lakebase and not databricks"`) → **368 passed, 67 skipped, 0 failed**.
Do not change application code — this request is CI/CD only.

## Owner constraints (non-negotiable)
- **Nothing deploys automatically.** No workflow may run `databricks bundle deploy` on push or
  PR. Deployment is a manual `workflow_dispatch`, and `prod` additionally requires a GitHub
  Environment approval.
- **Nothing runs or starts automatically.** No workflow may run `databricks bundle run`, start
  a job, or start a pipeline. The owner has said the streaming DLT pipeline must not run yet.
- No secrets in files. Workflows read credentials only from GitHub secrets/variables.
- Least-privilege `permissions:` on every workflow.

## Build

### 1. `.github/workflows/ci.yml` — on `pull_request` and `push` to `main`
Jobs (with `concurrency` cancelling superseded runs):
- **python-tests** — Python **3.12**. `requirements.txt` lists `ibapi`, which is **not on
  PyPI** (install fails; `conftest.py` stubs it) — install requirements with `ibapi` filtered
  out. Also install `requirements-app.txt` if present and the test deps the suite actually
  needs (read the imports; `requirements-dev.txt` may be incomplete). Cache pip.
  Run `pytest -q -m "not spark and not lakebase and not databricks"`. If `bundles/streaming/`
  exists, also run its `tests/`.
- **frontend** — Node 20, only if `frontend/package.json` exists: `npm ci`,
  `npx tsc --noEmit`, `npm run build`. Cache npm.
- **bundle-validate** — runs **only when** the `DATABRICKS_HOST` secret/var is set (skip
  cleanly otherwise, so forks and the current secret-less repo stay green). Use the official
  `databricks/setup-cli` action pinned to a version; `databricks bundle validate -t dev` for the
  root bundle and for `bundles/streaming` if present.
- **secret-scan** — a gitleaks (or equivalent) step, pinned.

Pin third-party actions to a version tag at minimum (full SHA preferred where practical).

### 2. Root Databricks Asset Bundle — `databricks.yml` (+ `resources/*.yml`)
- `bundle.name: quant-platform`; variables `catalog` (`bootcamp_students`), `schema`
  (`evangoh_capstone`).
- Resources:
  - **App** — the Databricks App from `app.yaml` / `api/` + built `frontend/dist`.
  - **Job `silver_gold_refresh`** — runs `pipelines/run_silver_gold.py` on serverless;
    schedule present but **`pause_status: PAUSED`**.
  - **Job `ml_ablation`** — runs `ml/run_ablation.py` on serverless; no schedule, or PAUSED.
- **Do not include the streaming pipeline** — it is its own bundle under `bundles/streaming/`.
- Targets: `dev` (`mode: development`, default) and `prod` (`mode: production`, explicit
  `root_path`, and a separate `schema` variable value — check the old exercise bundle's
  pattern in `/home/jianj/code/quant-trading-capstone/databricks.yml`, read-only).
- `sync.exclude`: `frontend/node_modules`, `.agents`, `.agentlogs`, caches, notebooks/archive.

### 3. `.github/workflows/cd.yml` — manual only
`on: workflow_dispatch` with input `target` (`dev` | `prod`). `environment: ${{ inputs.target }}`
so the owner can require reviewers on `prod`. Steps: checkout, build the frontend, set up the
Databricks CLI, `databricks bundle deploy -t <target>`. **No `bundle run`.**
Authentication: prefer **GitHub OIDC / workload identity federation** (`permissions:
id-token: write`, `DATABRICKS_AUTH_TYPE: github-oidc`, `DATABRICKS_HOST`,
`DATABRICKS_CLIENT_ID` from vars). Document the PAT fallback but do not make it the default.

### 4. `docs/CICD.md`
What runs on PR / push / manual dispatch; exactly what the owner must configure (secrets or
vars, the Databricks service principal + federation policy for OIDC, GitHub Environments
`dev`/`prod` with required reviewers on `prod`); and an explicit statement that nothing
deploys or runs automatically and the streaming pipeline is never touched.

## What you can and cannot verify in your sandbox
You have no network: you cannot `pip install`, `npm ci`, or reach Databricks. Write the files
carefully; Claude will execute every step and run `bundle validate` and a real Actions run.
Do sanity-check YAML syntax locally (`python3 -c "import yaml; yaml.safe_load(open(...))"`).

## Reporting
You cannot commit from this worktree. Leave changes on disk and print a report to stdout
starting `===REPORT START===`: files created, every assumption you could not verify, and any
place you deviated from this request and why.
