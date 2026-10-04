# VERDICT: app-frontend-deploy — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 1 (check)

===VERDICT START===

## Blocking findings

1. **`scripts/smoke_app.py:42-46` — the smoke script authenticates with a header the app never reads.**
   `_make_headers()` sets `Authorization: Bearer <AUTH_TOKEN>`, but the API's
   inbound auth path never inspects `Authorization`. `api/deps.py:31` reads only
   `_AUTH_USER_HEADER` (default `x-forwarded-email`), and `get_current_user`
   (`api/deps.py:112`) is the dependency on every read route
   (`signals`, `market`, `analytics`, `portfolio`, `watchlists`). The identity is
   injected by the Databricks Apps reverse proxy after browser SSO; `app.yaml` and
   `resources/app.yml` configure **no OAuth**, so there is no Bearer-token flow at
   all. A repo-wide grep for `Authorization`/`Bearer` confirms the only inbound use
   is this script; the other hits (`api/services/sec_analyzer.py:39`,
   `api/services/embeddings.py:124`) are outbound calls to external providers.
   → **Concrete failure:** an operator follows `docs/DEPLOYMENT.md` §7 step 5
   (`python scripts/smoke_app.py <APP_URL>`) against a deployed app with
   `AUTH_TOKEN=<databricks PAT>`. The proxy does not translate a PAT/Bearer token
   into an identity (it uses the SSO session cookie), so it redirects to the
   Databricks login page; the app then returns 401 on every read route (missing
   `x-forwarded-email`). Every `/api/*` check prints `FAIL` even though the app is
   healthy — the script cannot do the post-deploy verification it exists for.
   Related: the `/` check (`scripts/smoke_app.py:75`) accepts any body starting with
   `<`, so an unauthenticated request that lands on the SSO login page is reported
   `PASS` — a false positive masking the same defect.

## Verified (non-blocking)

1. **`databricks.yml` sync.include + excludes — PASS.** `sync.include: [frontend/dist/**]`
   with a comment stating include overrides `.gitignore`; `sync.exclude` still lists
   `frontend/node_modules`, `.agents`, `**/__pycache__`, etc. `.gitignore:64` still
   gitignores `frontend/dist/` and `git ls-files frontend/` shows no `dist` committed.
2. **`scripts/build_frontend.sh` fails loudly — PASS.** `set -euo pipefail`, checks
   `package.json`, runs `npm ci` + `npm run build`, then verifies `frontend/dist`
   exists and exits 1 otherwise. `docs/DEPLOYMENT.md` §2 + §7 give the full
   build → validate → deploy → apps start → smoke-test runbook.
3. **`api/main.py` missing-dist warning + hint — PASS.** `FRONTEND_DIST.is_dir()` false
   branch (`:393-407`) logs the warning (only when `DATABRICKS_APP_PORT`/`RENDER` set)
   and registers a `GET /` JSON hint; API routers are registered before/independently
   so they keep working. Mutation-verified: removing the fallback in a
   `git archive HEAD` copy makes `test_root_returns_hint_json` FAIL (`404 == 200`).
4. **`tests/test_bundle_sync.py` real — PASS.** Parses the actual `databricks.yml`
   with `yaml.safe_load` and asserts include/exclude contents; all 3 tests pass.
5. **`scripts/smoke_app.py` coverage — PASS.** Covers `/`, `/api/health`, and one
   read-only route per backed screen (`signals`, `market/NVDA`, `analytics`,
   `portfolio`, `watchlists`); the two chat-only screens (ResearchAgent,
   SecFilingExplorer) hit `POST /api/agent/chat` and are correctly excluded. No
   secrets embedded (token read from env only).

## Non-blocking notes

- `npm ci`/`npm run build` cannot run through the WSL UNC path (`\\wsl.localhost\…`)
  — Windows `node` resolves and fails with "UNC paths are not supported". This is an
  environment limitation, not a script defect (consistent with the MiMo note).
- `pytest` emits `PytestConfigWarning: Unknown config option: timeout` — `pytest-timeout`
  appears uninstalled in this env; pre-existing, unrelated to this slice.

## Checks run

- `python3 -m pytest tests/test_bundle_sync.py tests/api/test_frontend_serving.py -q` → `10 passed`
- mutation: `git archive HEAD | tar -x -C /tmp/check-fe-mut`; delete `_no_frontend`
  fallback → `pytest tests/api/test_frontend_serving.py -q` → `1 failed (test_root_returns_hint_json: 404 == 200)`, 6 passed → confirms test is load-bearing
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → `1470 passed, 97 skipped, 24 deselected`
- `cd frontend && npm ci && npm run build` (extracted to a Windows-path temp dir to
  bypass the UNC limitation) → `added 134 packages`; `vite v5.4.21 built` → `dist/index.html` + `assets/*` produced → pass
- `git ls-files frontend/` → no `dist` tracked → pass

===VERDICT END===
