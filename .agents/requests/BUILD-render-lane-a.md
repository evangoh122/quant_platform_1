# BUILD — Render lane A (R1 + R8)

## Scope and ownership

Lane A owns only `requirements-render.txt`, `render.yaml`, the new Render section in
`docs/DEPLOYMENT.md`, and `tests/render/test_render_packaging.py`. Do not edit any file under
`api/`, `agent/`, `demo_data/`, or any Lane B/C test. Section 7 of
`docs/RENDER_DEPLOY_PLAN.md:260-364` is authoritative where the earlier plan conflicts.

## Numbered changes

1. At `requirements.txt:1-16` and `requirements-app.txt:1-14`, use the existing imports only as
   evidence and add root `requirements-render.txt`. Pin exact, mutually compatible versions with
   `==` for exactly these four direct packages: `fastapi`, `uvicorn[standard]`, `pydantic`, and
   `loguru`. Do not include or transitively install `pyspark`, `psycopg`, `psycopg-pool`,
   `databricks-sdk`, `databricks-sql-connector`, `langchain`, `langchain-community`, `langgraph`,
   `mlflow`, or `ibapi`. Keep pip; do not add uv/Poetry artifacts.
2. Add root `render.yaml` exactly following the superseding blueprint at
   `docs/RENDER_DEPLOY_PLAN.md:310-333`: one Python web service named `qp1-showcase`, Starter plan,
   Python 3.12.7, Node 20.18.0, manual deploy, `PUBLIC_DEMO=1`, `APP_ENV=demo`, build command
   `pip install -r requirements-render.txt && cd frontend && npm ci && npm run build`, start command
   `uvicorn api.main:app --host 0.0.0.0 --port $PORT --proxy-headers`, and health path
   `/api/health`. Add no secret/sync-false variables and no second/static service.
3. Append a `Render public demo` section after the current deployment material anchored at
   `docs/DEPLOYMENT.md:118-154`. State that §7's single-service snapshot demo is separate from the
   Databricks deployment, uses manual deploy, contains no credentials, serves `frontend/dist`
   through FastAPI, and requires Lane B/C safety gates. Document the exact clean build/start/smoke
   commands, SPA deep-link behavior, empty-secret environment, rollback/manual-deploy procedure,
   and the prohibition on all `LAKEBASE_*`, `DATABRICKS_*`, broker/API tokens, and credential-like
   `VITE_*` values. Do not copy example secret values from `docs/DEPLOYMENT.md:89-108`.
4. Add `tests/render/test_render_packaging.py` with four offline packaging tests:
   `test_render_requirements_are_exact_and_minimal`, `test_render_blueprint_matches_contract`,
   `test_render_blueprint_contains_no_secret_configuration`, and
   `test_render_documentation_has_build_start_and_smoke_contract`. Parse YAML as text or with only
   stdlib/test-environment facilities; do not add a production YAML dependency. The first test must
   also create a temporary venv, install only `requirements-render.txt`, run
   `python -I -c 'import api.main'` from the repository, and assert forbidden distributions/modules
   are absent. Mark this test `render_install` if needed, but acceptance must run it.

## Tests must fail on the current code

All four tests are new and must fail before implementation because `requirements-render.txt` and
`render.yaml` do not exist and the Render documentation section is absent. Demonstrate this rather
than merely asserting it: copy the pre-change tree from `git archive HEAD` into a fresh `/tmp`
directory, copy only `tests/render/test_render_packaging.py` into that copy, run the test there, and
record the expected failures in the MiMo verdict. Never mutate the working tree to simulate old code.

## Acceptance commands

```bash
python -m pytest -q tests/render/test_render_packaging.py
tmpvenv="$(mktemp -d)/venv" && python -m venv "$tmpvenv" && "$tmpvenv/bin/pip" install -r requirements-render.txt && "$tmpvenv/bin/python" -I -c 'import api.main'
"$tmpvenv/bin/pip" freeze | tee /tmp/render-freeze.txt
! grep -Eiq '^(pyspark|psycopg|psycopg-pool|langchain|langchain-community|langgraph|mlflow|ibapi|databricks-sdk|databricks-sql-connector)==' /tmp/render-freeze.txt
cd frontend && npm ci && npm run build
```

Run the relevant suite with PySpark forcibly hidden (the four exact module entries are mandatory):

```bash
hide="$(mktemp -d)"; printf '%s\n' 'import sys' 'for m in ("pyspark", "pyspark.sql", "pyspark.sql.functions", "pyspark.sql.types"):' '    sys.modules[m] = None' > "$hide/sitecustomize.py"
PYTHONPATH="$hide${PYTHONPATH:+:$PYTHONPATH}" python -m pytest -q tests/render/test_render_packaging.py tests/api
```

After `frontend/dist` exists, start on a disposable local port with `PUBLIC_DEMO=1` and no secret
variables; assert `/api/health`, `/`, and a deep link such as `/results/walk-forward` return 200 and
the deep link body is `frontend/dist/index.html`. Scan the authored files and built frontend for
credential patterns and actual secret values; variable names in prohibition documentation are
allowed, values are not.

## DeepSeek must check

- The dependency file is truly standalone, exact-pinned, and clean-venv import works with no
  forbidden transitive distribution.
- Blueprint schema is the §7 single-service contract (not superseded §2), binds `$PORT`, and has no
  secret slots or auto-deploy.
- Node is available in the Python Render build path and `npm ci` uses the lockfile.
- SPA fallback works without swallowing `/api/*`; documentation does not promise deployment before
  B/C gates.
- Secret scanning distinguishes harmless variable names from embedded credential values.

## Delivery constraints

No secrets in any file. Use LF line endings. Do not touch `.agents/dispatch.sh`. Do not edit files
outside this lane's ownership. Commit the lane. Write the implementation self-report to
`.agents/mimo/VERDICT-render-lane-a.md` with changed files, commands/results, old-code failure proof,
and commit SHA.
