# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
None. The round-5 regression (ENAMETOOLONG on over-long path segments) and the symlink-loop crash are both fixed.

## Fixes applied (round 6)

### 1. Over-long path segment ENAMETOOLONG regression (CRITICAL)
**File:** `api/main.py:247-253`
**Problem:** `candidate = (_static_root / decoded).resolve()` at line 236 (now 259) raised `OSError [Errno 36] File name too long` for any URL path segment >255 bytes. The exception escaped `_spa` uncaught, producing a 500 without security headers (Starlette's `ServerErrorMiddleware` runs outside the demo guard). Round 4 returned `index.html` for the same input — this was a round-5 regression.
**Fix:**
- Pre-reject decoded segments >255 bytes (UTF-8 encoded length) before `resolve()`
- Pre-reject total decoded path >2048 bytes before `resolve()`
- Wrap `resolve()` + `is_file()` + `is_relative_to()` in `try/except (OSError, RuntimeError, ValueError)` → serve `index.html`

### 2. Symlink loop inside dist → RuntimeError
**File:** `api/main.py:258-267`
**Problem:** A symlink loop inside dist (e.g., `dist/loop -> dist/loop`) made `Path.resolve()` raise `RuntimeError("Symlink loop …")`, also escaping `_spa` uncaught. Not attacker-reachable (requires writing a symlink into deployed dist), but the same `try/except` fixes it.
**Fix:** `RuntimeError` is caught by the same `except (OSError, RuntimeError, ValueError)` block.

### 3. Global exception handler with security headers
**File:** `api/main.py:197-210`
**Problem:** Any unhandled exception outside the demo middleware (e.g., in a route handler) would be caught by Starlette's `ServerErrorMiddleware`, which returns a bare 500 without security headers and may leak stack traces.
**Fix:** Registered `@app.exception_handler(Exception)` that returns `{"detail":"internal error"}` 500 with all security headers (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Content-Security-Policy`). Works in both demo and non-demo mode.

### 4. Tests for round-6 fixes
**File:** `tests/api/test_path_traversal.py` (extended, +111 lines)
**New tests (11 total, each in demo + non-demo = 11 test points):**
- `test_256_segment_returns_index` — 256-char segment → 200 index.html, no 500
- `test_10000_segment_returns_index` — 10,000-char segment → 200 index.html, no 500
- `test_long_path_security_headers` — 256-char segment → security headers in demo mode
- `test_symlink_loop_returns_index` — symlink loop in dist → 200 index.html, no crash
- `test_unhandled_exception_returns_500_with_security_headers` — middleware raises → 500 with all security headers, no traceback text
- `test_long_path_via_real_uvicorn` — 256-char and 10,000-char segments via real uvicorn subprocess → 200, not 500

## Checks run
```
# Path traversal tests only
python3 -m pytest tests/api/test_path_traversal.py -q -p no:cacheprovider
→ 42 passed in 3.05s

# Path traversal tests with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest tests/api/test_path_traversal.py -q -p no:cacheprovider
→ 42 passed in 2.84s

# Full suite excluding lakebase
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 631 passed, 67 skipped in 105.47s

# Full suite with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 631 passed, 67 skipped in 107.01s
```

## Changed files (round 6 only)
| File | Change |
|------|--------|
| `api/main.py` | SPA catch-all: pre-reject segments >255 bytes and total >2048 bytes; wrap resolve in try/except (OSError, RuntimeError, ValueError); add global exception handler with security headers |
| `tests/api/test_path_traversal.py` | Extended: 6 new test functions (11 test points) covering over-long paths, symlink loops, exception handler security headers, real uvicorn long-path check |

## Previous rounds
- Round 4: `88ca7b8` — per-IP before global counter, single OrderedDict, broadened secret check
- Round 5: `194fe03` — path traversal fix, rate limit all GET/HEAD, 31 traversal tests
- Round 6 commit: `774efae` (branch: `slice/render-lane-b`)