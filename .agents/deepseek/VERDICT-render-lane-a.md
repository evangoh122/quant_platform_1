# VERDICT: render-lane-a — DeepSeek (checker)

**Status:** APPROVED
**Round:** 1 (check)

===VERDICT START===

## Scope reviewed

`requirements-render.txt`, `render.yaml`, the `## 10. Render public demo` section of
`docs/DEPLOYMENT.md`, and `tests/render/test_render_packaging.py` — against
`.agents/requests/CHECK-render-lane-a.md` and §7 of `docs/RENDER_DEPLOY_PLAN.md:260-364`.

## Independent checks

1. **`requirements-render.txt` is standalone, exact-pinned, and clean-venv importable — PASS.**
   Exactly four lines, all `==`: `fastapi==0.115.6`, `uvicorn[standard]==0.34.0`,
   `pydantic==2.13.5`, `loguru==0.7.3`. All four versions are real (resolved from PyPI).
   `fastapi 0.115.6` accepts `pydantic 2.13.5` (pydantic `>=1.7.4,<3`) and the install
   resolved without a version conflict. Clean venv on Python 3.12.3:
   `pip install -r requirements-render.txt` → OK; `import api.main` (cwd on path, as
   uvicorn does) → `IMPORT-OK`. Freeze/dist-info shows only the four packages + their
   transitives (starlette, anyio, pydantic_core, annotated_types, typing_extensions,
   typing_inspection, httptools, uvloop, click, h11, python-dotenv, pyyaml, idna, sniffio).
   **No** forbidden distribution (`pyspark`/`psycopg`/`psycopg-pool`/`langchain*`/`langgraph`/
   `mlflow`/`ibapi`/`databricks-*`) is installed.

2. **No request-time import that hard-fails — PASS.**
   Live smoke: `uvicorn api.main:app` from the clean venv → `/api/health` returns
   `200 {"status":"degraded", ...}` (Lakebase/delta reported as `ModuleNotFoundError` /
   `pyspark not installed`, i.e. graceful degradation); `/api/signals` (no header) → `401`.
   No crash. Heavy backends (`pyspark`, `psycopg`, `databricks`) are imported lazily and
   guarded: `api/deps.py:153-169` `read_delta` catches `ImportError` → `unavailable`;
   `api/routes/agent_chat.py:63-102` `_run_tool` catches `Exception`. `api/services/
   langgraph_engine.py` / `graph_rag_engine.py` import `langgraph`/`langchain` at module
   top-level, but nothing in the `api.main` import chain reaches them, so startup is
   unaffected (their exposure is Lane B's R2/R3 write-surface work).

3. **`render.yaml` matches the §7 contract — PASS.**
   Field-for-field identical to `docs/RENDER_DEPLOY_PLAN.md:312-331`: single `web` service
   `qp1-showcase`, `plan: starter`, `runtime: python`, build `pip install -r
   requirements-render.txt && cd frontend && npm ci && npm run build`, start `uvicorn
   api.main:app --host 0.0.0.0 --port $PORT --proxy-headers` (binds `$PORT`),
   `healthCheckPath: /api/health`, `autoDeploy: false`, envVars `PYTHON_VERSION=3.12.7`,
   `NODE_VERSION=20.18.0`, `PUBLIC_DEMO=1`, `APP_ENV=demo`. No secret/sync-false variables,
   no second/static service. LF line endings.

4. **`docs/DEPLOYMENT.md` Render section is accurate & consistent with the Blueprint — PASS.**
   `## 10. Render public demo` (`docs/DEPLOYMENT.md:219-321`) states it is a single-service
   snapshot demo separate from the Databricks deployment, manual-deploy (`autoDeploy: false`),
   contains no credentials, serves `frontend/dist` through FastAPI, and requires Lane B/C
   safety gates. Documents the exact build/start/smoke commands, SPA deep-link fallback
   (`/results/walk-forward` → `index.html`, without swallowing `/api/*`), empty-secret env,
   rollback/redeploy, and the prohibition on `LAKEBASE_*`, `DATABRICKS_*`, broker/API tokens,
   and credential-like `VITE_*` values. No example secret **values** copied from
   `docs/DEPLOYMENT.md:89-108` — only variable-name families.

5. **Tests verify behaviour, not file mirroring — PASS (mutation-verified).**
   - Add `langchain==0.3.0` to `requirements-render.txt` (isolated `/tmp` copy) →
     `test_render_requirements_are_exact_and_minimal` FAILS (`Expected exactly {…}, got
     {…, 'langchain'}`).
   - Add `- key: DATABRICKS_TOKEN` / `value: "dapi1234…"` to `render.yaml` (isolated
     `/tmp` copy) → `test_render_blueprint_contains_no_secret_configuration` FAILS
     (`'DATABRICKS_' is contained here`).
   - Default path has no network: tests 2–4 are pure file reads; only test 1 (marked
     `render_install`) does `pip install`.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/render` → `3 passed, 1 skipped in 0.14s`
- `python3 -m pytest -q -p no:cacheprovider tests/render -rs` → skip reason:
  `cannot create a venv on this host: ensurepip is not available` (host lacks `python3-venv`)
- clean venv (`python3 -m venv --without-pip` + `pip install -r requirements-render.txt`)
  then `import api.main` → `IMPORT-OK`; dist-info list contains no forbidden distribution → pass
- `uvicorn api.main:app` smoke (clean venv) → `/api/health` `200`, `/api/signals` `401`, no crash → pass
- mutation 1 (add `langchain`, /tmp copy) → exact-minimal test FAIL → pass
- mutation 2 (add `DATABRICKS_TOKEN`, /tmp copy) → no-secret test FAIL → pass
- CRLF scan on the four authored files → all LF → pass

## Non-blocking notes

- **Node availability is the one first-deploy risk.** `runtime: python` on Render does not
  include Node by default, yet `buildCommand` runs `cd frontend && npm ci && npm run build`.
  This is explicitly flagged in §7 blocker 6 and repeated in `docs/DEPLOYMENT.md` ("Node must
  be available in the Python build environment"); if the native Python image lacks Node, the
  fallback is a Docker runtime. Not a code defect, but should be confirmed on the first manual
  deploy before a public URL is shared.
- `test_render_requirements_are_exact_and_minimal` skips on this WSL host because
  `python3-venv`/`ensurepip` is absent. The critical clean-venv install + `import api.main` +
  forbidden-distribution assertions were re-run manually and pass; on CI (ubuntu runner with
  `python3-venv`) the test executes for real. Worth keeping the skip guard for other bare hosts.
- `pytest.ini` gained a `render_install` marker registration — a fifth file beyond the four
  named in the lane's ownership, but it is test-infrastructure-only, needed to silence the
  unknown-marker warning, and low risk.
- `python -I -c 'import api.main'` (the literal acceptance line in the BUILD spec) cannot pass
  without installing `api` as a package, because `-I` drops the CWD from `sys.path`; the test
  correctly uses `python -c` + `PYTHONPATH=REPO_ROOT`. This matches the MiMo verdict's note and
  is a spec-wording nit, not a deliverable defect.

===VERDICT END===
