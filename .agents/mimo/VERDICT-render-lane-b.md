# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
None. Both blocking findings from DeepSeek's verdict are resolved.

## Fixes applied (round 3)

### 1. `/api/health` short-circuit in demo mode
**File:** `api/routes/health.py`
**Problem:** Health handler imported `db.lakebase` and called `subprocess.run` (via `mint_token_via_cli`) in demo mode, violating the "demo never touches Lakebase" design. The existing test only hit `/api/analytics`, missing the health route.
**Fix:** Health handler now checks `is_public_demo()` first and returns a degraded response with both `lakebase` and `delta` reported as `{"ok": false, "detail": "disabled in public demo"}` — no import of `db.lakebase`, no subprocess. Test `test_no_lakebase_import_in_demo` now hits EVERY registered GET route and patches `subprocess.run` to raise if called.

### 2. Fail-closed Render default
**File:** `api/demo.py`, `api/main.py`
**Problem:** `is_public_demo()` returned `False` for unrecognised values like `"t"`, `"1.0"`, `"0"`. On Render (where `RENDER=true` is always set), the default state was the insecure one with full write surface.
**Fix:** Two-part fail-closed guard:
- `validate_render_environment()`: if `RENDER` is set (any non-empty value) and `is_public_demo()` is False, raises `PublicDemoConfigurationError("refusing to start with write routes on Render; set PUBLIC_DEMO=1")`. Called from `create_app()` before any route registration.
- `is_public_demo()` now raises on unrecognised non-empty `PUBLIC_DEMO` values. Only the known set (`1/true/yes/on` for on, `0/false/no/off/""` for off) is accepted. Anything else raises with a clear error message.

### 3. Security headers on every response
**File:** `api/main.py`
**Problem:** The middleware returned `JSONResponse` for 405, 413, and 429 BEFORE the security header block, so those responses lacked `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Content-Security-Policy`, and `Cache-Control: no-store`.
**Fix:** Extracted `_apply_security_headers()` helper. Called on every early-return path (405, 413, 429) and on the final response. All four status codes now carry the full header set (tested individually).

### 4. Broadened startup secret check
**File:** `api/demo.py`
**Problem:** `_is_unsafe_key()` only caught `_API_KEY`, `_TOKEN`, `_SECRET` suffixes and `LAKEBASE_`/`DATABRICKS_` prefixes. Missing: `*_PASSWORD`, `*_KEY`, `*_PASS`, `*_PWD` suffixes; `PG`, `POSTGRES_`, `IBKR_`, `POLYGON_`, `OPENAI_`, `ANTHROPIC_` prefixes; `DATABASE_URL`, `HF_TOKEN` exact names.
**Fix:** Added `_SECRET_SUFFIXES`, `_SECRET_PREFIXES`, `_SECRET_EXACT` tuples/frozensets. Added `_RENDER_ALLOW_LIST` for harmless Render-injected vars (`RENDER*`, `PORT`, `PYTHON_VERSION`, `NODE_VERSION`, `PATH`, `HOME`). Parametrised test covers all families.

**Render allow-listed env vars** (documented in `_RENDER_ALLOW_LIST`):
- `RENDER`, `RENDER_SERVICE_ID`, `RENDER_SERVICE_NAME`, `RENDER_SERVICE_TYPE`
- `RENDER_GIT_BRANCH`, `RENDER_GIT_COMMIT`, `RENDER_GIT_REPO_SLUG`
- `RENDER_GIT_OWNER`, `RENDER_GIT_PROVIDER`, `RENDER_GIT_PR_NUMBER`
- `RENDER_INSTANCE_ID`, `RENDER_REGION`, `RENDER_EXTERNAL_URL`
- `RENDER_EXTERNAL_HOSTNAME`, `RENDER_DISK_MOUNT_PATH`
- `PORT`, `PYTHON_VERSION`, `NODE_VERSION`, `PATH`, `HOME`

### 5. Rate limiter behind Render's proxy
**File:** `api/main.py`, `docs/DEPLOYMENT.md`
**Problem:** Rate limiter keyed on `request.client.host` which, behind Render's proxy, would either collapse all visitors to one proxy IP (default) or become spoofable if `--forwarded-allow-ips='*'` were set. No LRU cap on distinct keys; no global ceiling.
**Fix:** Three-part fix:
- `_get_client_ip()`: on Render (`RENDER` env set), extracts the **rightmost** `X-Forwarded-For` entry (the address Render's edge saw). Otherwise uses `request.client.host`. Does NOT use `--forwarded-allow-ips='*'`.
- `_LRUCache` (OrderedDict-based): bounds the limiter's key set to 10,000 distinct IPs (configurable via `RATE_LIMIT_LRU_MAX`). Evicts oldest on overflow.
- Global ceiling: `_RATE_LIMIT_GLOBAL` (default 600 req/min) acts as a backstop across all IPs.
- Documented in `docs/DEPLOYMENT.md` §10.

### 6. Normalise `/api` prefix check
**File:** `api/main.py`
**Problem:** `path.startswith("/api")` was evadable by `//api/…`, `/%2fapi/…`, `/API/…`. The demo guard and rate limiter didn't match those paths.
**Fix:** `_normalize_api_path()` decodes percent-encoding, collapses repeated slashes, and case-folds. The middleware uses the normalised path for all checks. Tests use `client.request("POST", "http://testserver//api/orders")` to preserve double slashes (TestClient.post normalises them).

### 7. Fix vacuous route-enumeration test
**File:** `tests/api/test_public_demo_security.py`
**Problem:** `app.routes` exposes `_IncludedRouter` placeholders with `path=None`/`methods=set()`, so the "methods ⊆ {GET,HEAD,OPTIONS}" loop and the "prohibited paths absent" set were trivially true.
**Fix:** Walk `_IncludedRouter.include_context.prefix` + `original_router.routes` to get the effective route set with full paths. Test now FAILs if a POST route is registered in demo (mutation-proved).

## Checks run
```
# Demo security tests
python3 -m pytest -q -p no:cacheprovider tests/api/test_public_demo_security.py
→ 70 passed in 2.02s

# All API tests with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider tests/api
→ 78 passed in 3.09s

# Both file orders with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_rbac.py tests/api/test_public_demo_security.py
→ 73 passed in 1.97s

CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_public_demo_security.py tests/api/test_rbac.py
→ 73 passed in 1.84s

# Full suite excluding lakebase
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 549 passed, 67 skipped in 108.18s
```

## Changed files (round 3 only)
| File | Change |
|------|--------|
| `api/routes/health.py` | Demo short-circuit: returns degraded without importing `db.lakebase` or spawning subprocess |
| `api/demo.py` | `validate_render_environment()` fail-closed guard; strict `PUBLIC_DEMO` validation; broadened `_is_unsafe_key()` with suffixes/prefixes/exact names; `_RENDER_ALLOW_LIST` |
| `api/main.py` | `_apply_security_headers()` helper on all paths; `_normalize_api_path()` for prefix matching; `_LRUCache` for LRU-bounded keys; `_get_client_ip()` for rightmost XFF on Render; global rate ceiling; `validate_render_environment()` call in `create_app()` |
| `tests/api/test_public_demo_security.py` | 22→70 tests: health demo gate, route enumeration via `_IncludedRouter`, security headers on 405/429/413, Render fail-closed, unrecognised PUBLIC_DEMO, path normalisation, XFF rate limiting, LRU cap, global ceiling, allow-list |
| `docs/DEPLOYMENT.md` | §10 Render deployment: proxy trust choice, rate limiting config, uvicorn command |

## Commit SHA (round 3)
`5282117` (branch: `slice/render-lane-b`)