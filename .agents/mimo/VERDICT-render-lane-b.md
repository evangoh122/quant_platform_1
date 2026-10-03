# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
None. The critical path-traversal vulnerability (DeepSeek check3) is fixed.

## Fixes applied (round 5)

### 1. Path traversal in SPA catch-all (CRITICAL)
**File:** `api/main.py:217-239`
**Problem:** `candidate = FRONTEND_DIST / full_path` was never confined. `GET /%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd` returned `200 root:x:0:0...`. This affected both demo and non-demo mode, bypassed the `/api` rate limiter, and was present since app scaffold (#7).
**Fix:**
- Resolve root once: `_static_root = FRONTEND_DIST.resolve()`
- Resolve candidate: `candidate = (_static_root / decoded).resolve()`
- Confine check: `candidate.is_file() and candidate.is_relative_to(_static_root)`
- Reject decoded segments containing `..`, `\`, `\x00`, or absolute paths (`os.path.isabs`)
- Symlink escape blocked: `resolve()` + `is_relative_to` follows symlinks and checks the resolved path is inside root

### 2. Rate limit ALL requests, not only /api
**File:** `api/main.py:255-268`
**Problem:** Rate limiting only applied to `/api` routes. Static file fetches (including traversal attempts) were unbounded.
**Fix:** Moved rate-limit check before the `/api` method gate. All GET/HEAD requests (including `/{full_path:path}` static serves) are now rate-limited per client IP. `/api/health` is NOT exempt; Render's health check uses few enough requests to stay within limits.
**Docstring updated:** Documents the new behavior and health-check policy.

### 3. Comprehensive path-traversal test suite
**File:** `tests/api/test_path_traversal.py` (new, 275 lines)
**Coverage:**
- 8 traversal payloads in BOTH demo and non-demo mode (16 tests): `/../secret.txt`, `/%2e%2e/secret.txt`, `/%2e%2e%2fsecret.txt`, `/..%2fsecret.txt`, `/%252e%252e/secret.txt`, `/assets/../../secret.txt`, `/....//secret.txt`, backslash variant
- Symlink outside dist → not served (2 tests, demo + non-demo)
- Symlink inside dist → served (2 tests)
- Legit asset `/assets/x.js` → 200 with content (2 tests)
- Deep SPA link `/signals/AAPL` → index.html (2 tests)
- Empty path → index.html (2 tests)
- NUL byte rejection (logic test)
- Absolute path `/etc/passwd` → index.html (2 tests)
- Real uvicorn subprocess on random port: traversal + legit asset (1 test)
- `_strip_ambient_secrets` autouse fixture handles `CLAUDE_CODE_MESSAGING_TOKEN` / `DATABRICKS_WORKSPACE_ID`

## Checks run
```
# Path traversal tests only
python3 -m pytest tests/api/test_path_traversal.py -q -p no:cacheprovider
→ 31 passed in 2.27s

# Path traversal tests with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest tests/api/test_path_traversal.py -q -p no:cacheprovider
→ 31 passed in 2.35s

# Full suite excluding lakebase
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 620 passed, 67 skipped in 115.91s

# Full suite with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 620 passed, 67 skipped in 113.31s
```

## Changed files (round 5 only)
| File | Change |
|------|--------|
| `api/main.py` | SPA catch-all: resolve+confine, reject `..`/`\`/NUL/absolute segments; rate limit ALL GET/HEAD (not only `/api`); update docstring |
| `tests/api/test_path_traversal.py` | New: 31 tests covering 8 traversal payloads × 2 modes, symlinks, legit assets, SPA links, NUL, absolute paths, uvicorn subprocess |

## Previous rounds
- Round 4: `88ca7b8` — per-IP before global counter, single OrderedDict, broadened secret check
- Round 5 commit: `194fe03` (branch: `slice/render-lane-b`)