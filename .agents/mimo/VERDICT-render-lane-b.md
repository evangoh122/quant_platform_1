# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Fixes applied (round 2)

### 1. Ambient environment variable isolation
**File:** `tests/api/test_public_demo_security.py`
**Problem:** On WSL (and any CI runner), shell env vars like `CLAUDE_CODE_MESSAGING_TOKEN` (`*_TOKEN` suffix) and `DATABRICKS_WORKSPACE_ID` (`DATABRICKS_` prefix) trigger `api.demo._is_unsafe_key`, causing `PublicDemoConfigurationError` in 9 tests.
**Fix:** Added `_strip_ambient_secrets` autouse fixture that removes all env vars matching `_is_unsafe_key` (reusing the predicate from `api/demo.py` so the two cannot drift). Uses `monkeypatch.delenv` per-key.

### 2. Test pollution: `test_no_lakebase_import_in_demo` deleted `db.lakebase` from `sys.modules`
**File:** `tests/api/test_public_demo_security.py`
**Problem:** `test_no_lakebase_import_in_demo` deleted `db.lakebase` from `sys.modules` and never restored it. When `db.lakebase` was later reimported, `fake_lakebase`'s `monkeypatch.setattr("db.lakebase.get_lakebase", ...)` targeted the old (deleted) module object. All subsequent tests using `fake_lakebase` hit the real Lakebase pool → 30s timeout → 503.
**Fix:** Save and restore `db.lakebase*` modules around the assertion instead of leaving them deleted.

### 3. Test pollution: `api.main` first-import with `PUBLIC_DEMO=1`
**Files:** `tests/api/test_public_demo_security.py`, `tests/api/conftest.py`
**Problem:** `_make_demo_app` set `PUBLIC_DEMO=1` then imported `api.main` for the first time. The module-level `app = create_app()` at `api/main.py:220` executed with demo mode active, baking demo middleware into the module-level `app`. The conftest `client` fixture read this same demo `app`.
**Fix (two-part):**
- `_make_demo_app` no longer clears `sys.modules`. It calls `create_app()` directly (the application factory), so the module-level `app` is never overwritten.
- Conftest `client` fixture changed from `from api.main import app` to `from api.main import create_app; TestClient(create_app())`, creating a fresh non-demo app each time.

### 4. Removed stale `_isolate_modules` fixture
**File:** `tests/api/test_public_demo_security.py`
**Problem:** The old `_isolate_modules` fixture cleared `api.*` from `sys.modules` in teardown, causing the conftest `client` fixture to reimport `api.main` (which could pick up demo mode). The save/restore variant caused stale module references that bypassed `fake_lakebase` patches.
**Fix:** Removed entirely. With `_make_demo_app` using `create_app()` directly and conftest using `create_app()` directly, no module clearing is needed.

## Non-blocking notes
- Suite runtime improved from ~162s to ~115s because the `fake_lakebase` patch now correctly intercepts all `db.lakebase.get_lakebase()` calls, eliminating the30s PoolTimeout.

## Checks run
```
# Test 1: Demo security with ambient env vars (the original failure)
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q tests/api/test_public_demo_security.py
→ 22 passed in 1.06s

# Test 2: Both file orders with ambient env vars
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:randomly tests/api/test_public_demo_security.py tests/api/test_rbac.py
→ 25 passed in 1.22s

CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:randomly tests/api/test_rbac.py tests/api/test_public_demo_security.py
→ 25 passed in 1.12s

# Test 3: All API tests
python3 -m pytest -q -p no:randomly tests/api/
→ 30 passed in 2.02s

# Test 4: Full suite (ignore lakebase)
python3 -m pytest -q --ignore=tests/lakebase
→ 501 passed, 67 skipped in 114.83s
```

## Changed files (round 2 only)
| File | Change |
|------|--------|
| `tests/api/test_public_demo_security.py` | `_strip_ambient_secrets` autouse fixture; `_make_demo_app` calls `create_app()` directly; `test_no_lakebase_import_in_demo` saves/restores `db.lakebase`; removed `_isolate_modules`; removed `sys.modules` clearing from `test_unsafe_variable_rejected_at_construction` and `test_safe_empty_environment_starts` |
| `tests/api/conftest.py` | `client` fixture uses `create_app()` instead of module-level `app` |

## Commit SHA (round 2)
`888f757` (branch: `slice/render-lane-b`)