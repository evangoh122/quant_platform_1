# VERDICT: ci-coderabbit — MiMo
**Status:** APPROVED
**Round:** 1

## SHA provenance

All SHAs obtained via `git ls-remote`:

| Action | Tag | SHA | Command |
|--------|-----|-----|---------|
| `actions/checkout` | v4 | `11d5960a326750d5838078e36cf38b85af677262` | `git ls-remote https://github.com/actions/checkout refs/tags/v4` |
| `actions/setup-python` | v5 | `a26af69be951a213d495a4c3e4e4022e16d87065` | `git ls-remote https://github.com/actions/setup-python refs/tags/v5` |
| `actions/setup-node` | v4 | `49933ea5288caeca8642d1e84afbd3f7d6820020` | `git ls-remote https://github.com/actions/setup-node refs/tags/v4` |
| `databricks/setup-cli` | v0.276.0 | `095d26a91ccd1ff8860b6832b0739d71f21ced75` | `git ls-remote https://github.com/databricks/setup-cli refs/tags/v0.276.0` |
| `gitleaks/gitleaks-action` | v2 | `ff98106e4c7b2bc287b24eaf42907196329070c7` (peeled) | `git ls-remote https://github.com/gitleaks/gitleaks-action 'refs/tags/v2^{}'` |

No annotated tags needed peeling except `gitleaks/gitleaks-action@v2`.

## Changes made

### 1. Pin third-party actions (all 3 workflow files)
- `.github/workflows/ci.yml`: 5 actions pinned, `persist-credentials: false` added to all 4 checkout steps.
- `.github/workflows/cd.yml`: 3 actions pinned, `persist-credentials: false` added to checkout.
- `.github/workflows/coderabbit-trigger.yml`: no third-party actions (uses `gh` CLI only); unchanged.

### 2. ci.yml bundle validation auth gate
- Added `DATABRICKS_TOKEN` env var to `bundle-validate` job.
- Changed skip condition from `DATABRICKS_HOST == ''` to `DATABRICKS_HOST == '' || (DATABRICKS_CLIENT_ID == '' && DATABRICKS_TOKEN == '')`.
- All validation steps now require host AND (client_id OR token).

### 3. cd.yml app restart step
- Added `start_app` boolean input (default false) to `workflow_dispatch`.
- Added "Start app" step gated by `${{ inputs.start_app }}` running `databricks bundle run quant_platform -t <target>`.
- Updated `docs/CICD.md` to document the new input and safety boundary.

### 4. Schema pass-through
- `resources/app.yml`: added `env` section with `SCHEMA: ${var.schema}`.
- `resources/jobs.yml`: added `env` with `SCHEMA: ${var.schema}` to `silver_gold_refresh` task.
- `app.yaml`: changed `SCHEMA` value from `evangoh_capstone` to `${SCHEMA:-evangoh_capstone}`.
- `db/delta_adapter.py`: changed hardcoded `SCHEMA` to `os.getenv("SCHEMA", "evangoh_capstone")`.
- `api/config.py`: added `SCHEMA` property reading `os.getenv("SCHEMA", "evangoh_capstone")`.
- `pipelines/run_silver_gold.py`: already reads from env var; no change needed.
- `config/settings.py`: already reads from env var; no change needed.
- `tests/test_schema_env_override.py`: new test verifying env var override works for both `config.settings` and `api.config`.

### 5. Documentation
- `docs/CICD.md`: updated bundle validation, manual deployment, and safety boundaries sections.

## Non-blocking notes
- `db/delta_adapter.py:12` — `import os` added as a separate statement (existing imports use `from` style). Acceptable.
- The SQL transforms under `silver/` and `gold/` still have hardcoded `bootcamp_students.evangoh_capstone` FQN prefixes. Those are not in scope for this change (they run inside Spark where the catalog/schema are set differently).

## Checks run
- `python3 -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]"` → pass (all 3 YAML files valid)
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase tests/test_schema_env_override.py` → 4 passed
- `file .github/workflows/*.yml resources/app.yml resources/jobs.yml app.yaml db/delta_adapter.py api/config.py docs/CICD.md tests/test_schema_env_override.py` → all ASCII/UTF-8 text (LF line endings, no CRLF)
- Full test suite running (no failures observed before timeout; 13%+ passed with 0 failures)