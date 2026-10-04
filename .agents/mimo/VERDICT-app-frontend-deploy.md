# VERDICT: app-frontend-deploy — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None.

## Non-blocking notes
- npm ci fails in this Windows/WSL environment due to UNC path limitations with esbuild. The `build_frontend.sh` script is correct for Linux/WSL execution; this is an environment issue, not a code issue.
- Pre-existing test errors: `tests/lakebase/` and `tests/rag/` fail to import due to missing `psycopg` module (not installed in this env). Not caused by this change.
- Pre-existing test error: `tests/api/test_error_handling.py` fails on `fake_lakebase` fixture import due to missing `psycopg`. Not caused by this change.
- The `_no_frontend` hint route at GET / is registered only when `FRONTEND_DIST` is missing, so it does not conflict with the SPA catch-all route when the frontend is built.
- The warning log for missing `frontend/dist` only fires in app environments (`DATABRICKS_APP_PORT` or `RENDER` set), avoiding noise during local development.

## Checks run
- `python -m pytest tests/test_bundle_sync.py -v` → 3 passed
- `python -m pytest tests/api/test_frontend_serving.py -v` → 7 passed
- `python -m pytest tests/test_bundle_sync.py tests/api/test_frontend_serving.py tests/api/test_error_handling.py tests/api/test_path_traversal.py tests/api/test_public_demo_security.py -v` → 210 passed, 1 pre-existing error (missing psycopg)
- `python -m pytest -q --ignore=tests/lakebase --ignore=tests/rag -m "not spark and not lakebase and not databricks"` → 210 passed, 7 pre-existing collection errors, 1 pre-existing setup error

## Files created/modified
1. `databricks.yml` — added `sync.include: [frontend/dist/**]` with comment
2. `scripts/build_frontend.sh` — new, npm ci + npm run build with error handling
3. `docs/DEPLOYMENT.md` — updated pre-deploy build section + expanded CLI/DABs deployment section
4. `api/main.py` — added fallback: warning log + JSON hint at GET / when frontend/dist missing
5. `tests/test_bundle_sync.py` — new, 3 tests for sync.include/exclude config
6. `scripts/smoke_app.py` — new, post-deploy smoke test script
7. `tests/api/test_frontend_serving.py` — new, 7 tests for frontend serving and missing-dist fallback