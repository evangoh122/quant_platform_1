# CI/CD

This repository separates validation from deployment. Nothing deploys or runs automatically. In particular, no workflow invokes `databricks bundle run`, starts a job, or starts a pipeline. The streaming pipeline in `bundles/streaming` remains a separate bundle and is never deployed or run by these workflows.

## Continuous integration

The `CI` workflow runs for every pull request and for pushes to `main`. Superseded runs for the same ref are cancelled.

- **Python tests** use Python 3.12 and run the offline suite with `uv run pytest -q -m "not spark and not lakebase and not databricks"`. [uv](https://docs.astral.sh/uv/) installs the committed lockfile (`uv sync --frozen --group dev`); `pyproject.toml` + `uv.lock` are the single source of truth and `setup-uv` caches the download cache keyed on `uv.lock`. CI fails when the lock is stale (`uv lock --check`) or when the committed `requirements.txt` was not regenerated after a dependency change (export drift). `pyspark` is not a dependency, so the CI interpreter never has it. `ibapi` is not on PyPI and is deliberately absent from the lock; `conftest.py` stubs it for the offline suite. If `bundles/streaming/tests` exists, CI runs those tests as a separate step. Databricks Apps and the Hugging Face Docker image install from the same lock (see "Dependency workflow" below).
- **Frontend** uses Node 20 to run `npm ci`, TypeScript checking, and the production build. The job is skipped when `frontend/package.json` is absent.
- **Bundle validation** validates the root development target and, if present, the separate streaming bundle. Workspace-backed validation steps are skipped cleanly when `DATABRICKS_HOST` is not configured or when OIDC credentials (client ID) or a PAT token are missing.
- **Secret scanning** runs Gitleaks against the checked-out history.
- **Dependency audit** exports the locked runtime and dev groups and audits both with `pip-audit` (see `docs/SECURITY.md`).

CI never deploys any bundle.

## Dependency workflow (uv)

`pyproject.toml` declares the dependencies; `uv.lock` pins the full resolution.
Every entry point installs from the lock:

| Consumer | Install command |
| :--- | :--- |
| Developers / CI | `uv sync --frozen --group dev` |
| Databricks Apps | root `requirements.txt` (generated, pip) — see below |
| Hugging Face Space | `uv sync --frozen --no-dev` during `docker build` |

Common commands:

```bash
uv lock                      # after editing pyproject.toml
uv sync --frozen --group dev # install exactly the lock
uv run pytest -q             # run commands in the project environment
./scripts/export_requirements.sh   # regenerate the committed requirements.txt
```

**`requirements.txt` is a generated artifact.** Databricks Apps installs the
root `requirements.txt` when it exists, and a `requirements.txt` always takes
precedence over `pyproject.toml`/`uv.lock` (Databricks docs, "Define Python
dependencies with uv"). Keeping it committed therefore preserves the existing
pip install path for bundle *and* UI-driven deployments, at the cost of one
generated file that CI drift-checks. Never edit it by hand; the DAB
`python_requirements` artifact regenerates it before `bundle deploy`.

**ibapi** is not published on PyPI (IBKR ships it as a zip on their website).
It is intentionally absent from `pyproject.toml`, `uv.lock` and
`requirements.txt` so `uv sync` always succeeds. `conftest.py` installs a stub
for the offline suite; live paper trading (`etl/ibkr_client.py`) needs a manual
`pip install` of that zip into the active environment, and CI has an explicit
step asserting `ibapi` never enters the lock.


## Manual deployment

The `Deploy Databricks bundle` workflow has only a `workflow_dispatch` trigger. An operator chooses `dev` or `prod`; the workflow runs `databricks bundle deploy` for that target, and the bundle's `artifacts` section builds `frontend/dist` (`npm ci && npm run build`) and regenerates `requirements.txt` (`uv export` of the locked runtime group) as part of that command. The deploying machine therefore needs `npm`/`node` and `uv` on `PATH`. An optional `start_app` boolean input (default false) restarts the app after deploy by running `databricks bundle run quant_platform -t <target>`. It does not run any job or pipeline.

The selected target is also the GitHub Environment name. Configure two repository environments:

1. Create `dev` and `prod` environments under **Settings → Environments**.
2. Add required reviewers to `prod` so production deployment cannot proceed without approval. Apply any desired branch/tag deployment restrictions as well.
3. Define `DATABRICKS_HOST` and `DATABRICKS_CLIENT_ID` as environment variables in both environments, using the values for each target workspace and service principal.

## Databricks OIDC configuration

Deployment uses GitHub OIDC (Databricks workload identity federation), not a stored Databricks token. In Databricks:

1. Create or select a service principal dedicated to these deployments.
2. Grant it only the workspace, app, job, compute/serverless, and Unity Catalog privileges required to deploy these bundle resources. Do not grant workspace admin or metastore admin merely for CI/CD.
3. Create a federation policy for the service principal that trusts this GitHub repository. Restrict the policy subject to the intended repository and, where supported by the release policy, the matching `dev` or `prod` GitHub Environment.
4. Put the workspace URL in the environment variable `DATABRICKS_HOST` and the service-principal application ID in `DATABRICKS_CLIENT_ID`.

The deployment job requests only `contents: read` and `id-token: write`; the latter lets GitHub mint the OIDC token consumed by the Databricks CLI.

For CI bundle validation, configure `DATABRICKS_HOST` as a repository variable or secret. If authenticated validation is required, also configure `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`; omit them to keep validation skipped or use the authentication method approved for the repository. Forks without these settings remain green because workspace-backed validation is skipped. Validation requires `DATABRICKS_HOST` and either `DATABRICKS_CLIENT_ID` (for OIDC) or `DATABRICKS_TOKEN` (for PAT); all three are checked before any validation step runs.

### PAT fallback

If workload identity federation cannot be used, a repository administrator may adapt the manual deployment environment to provide a `DATABRICKS_TOKEN` GitHub Environment secret and remove `DATABRICKS_AUTH_TYPE: github-oidc` and `DATABRICKS_CLIENT_ID` from the job. Use a short-lived token belonging to a least-privileged service principal. PAT authentication is a fallback only and is not enabled by the checked-in workflow.

## Safety boundaries

- Pushes and pull requests validate and test only; they never deploy.
- Deployment requires a person to dispatch the workflow, and `prod` should require an environment reviewer.
- Deployment creates or updates resource definitions. The optional `start_app` input restarts the app; it is the only `bundle run` the workflow can invoke. Jobs and pipelines are never started from CD.
- Both batch job schedules are absent or checked in as paused. The `silver_gold_refresh` schedule is explicitly `PAUSED`.
- The root bundle excludes `bundles/streaming`; the CD workflow deploys only the root bundle. The streaming pipeline is never touched.
- Credentials belong in GitHub variables/secrets and Databricks federation policies, never in repository files.

## Prerequisites found during validation (coordinator)

- **`prod` schema does not exist yet.** The `prod` target uses schema
  `bootcamp_students.evangoh_capstone_prod`, which is not created. A prod deploy succeeds, but
  its jobs would fail until the schema exists (and is populated). Create it deliberately before
  the first prod deploy, or point `prod` at an existing schema.
- **`prod` deploys under your user folder, not `/Workspace/Shared`.** In this shared workspace,
  `/Workspace/Shared` is writable by every user, so another user could alter production code
  that runs as the app. Databricks' own `bundle validate` flags that path.
- `databricks bundle validate` passes for both `dev` and `prod` (remaining warnings are only
  `sync.exclude` patterns for cache folders that do not exist yet).

## CodeRabbit auto-trigger

`.github/workflows/coderabbit-trigger.yml` comments `@coderabbitai review` on every PR when it is
opened, reopened or marked ready for review, because CodeRabbit does not auto-review repositories
with fewer than 10 stars. It never checks out or runs PR code, so `pull_request_target` is safe.
If CodeRabbit ignores comments from the Actions bot, add a `CODERABBIT_TRIGGER_TOKEN` secret (a
fine-grained token with pull-request write) and the workflow will post as that user instead.
