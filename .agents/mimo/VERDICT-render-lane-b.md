# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None. The DeepSeek check6 CF-Connecting-IP spoofing finding is fixed.

## Fixes applied (round 8)

### 1. CLIENT_IP_SOURCE — explicit IP source selection (CRITICAL)
**File:** `api/main.py:45-78`
**Problem:** DeepSeek check6 proved that trusting `CF-Connecting-IP` / `True-Client-IP` FIRST is spoofable whenever Cloudflare doesn't rewrite them. Rotating the header 200x gives 200/200 accepted, then a real client gets 429.
**Fix:** Introduced `CLIENT_IP_SOURCE` env var with three modes:

| Value | Default on | Behaviour |
|-------|-----------|-----------|
| `xff_leftmost` | **Render** | Leftmost `X-Forwarded-For` entry if valid; otherwise `request.client.host`. **Never reads** `CF-Connecting-IP` or `True-Client-IP`. |
| `cf_connecting_ip` | — | `CF-Connecting-IP` only (valid IP); otherwise `request.client.host`. Opt-in for verified Cloudflare setups. |
| `peer` | **non-Render** | `request.client.host` only; all headers ignored. |

Outside Render (`RENDER` unset), the default is `peer` and headers are ignored regardless of `CLIENT_IP_SOURCE`. An unknown value raises `PublicDemoConfigurationError` at startup.

### 2. Render allow-list updated
**File:** `api/demo.py:83`
**Fix:** Added `CLIENT_IP_SOURCE` to `_RENDER_ALLOW_LIST`.

### 3. Startup validation + debug log
**File:** `api/main.py:49-78, 276`
**Fix:** `_resolve_client_ip_source()` validates at import time and raises `PublicDemoConfigurationError` for unrecognised values. Debug-safe log line at startup: `client_ip_source=xff_leftmost (render=True)`.

### 4. Documentation updated
**File:** `docs/DEPLOYMENT.md:181-242`
**Fix:** Replaced old CF-Connecting-IP priority docs with `CLIENT_IP_SOURCE` table, rationale (Render quote + source URL + DeepSeek check6 proof), and post-deploy verification (a/b/c).

### 5. Tests — 6 new functions, 6 updated (round 8)
**File:** `tests/api/test_public_demo_security.py`

| Test | What it proves |
|------|---------------|
| `test_default_xff_leftmost_ignores_cf_connecting_ip` (was test 28) | Default: CF-Connecting-IP ignored, XFF leftmost is the key |
| `test_cf_connecting_ip_mode_uses_cf` (test 36) | `cf_connecting_ip` mode uses CF header, falls back to client.host |
| `test_cf_connecting_ip_mode_61st_gives_429` (test 37) | `cf_connecting_ip` mode: rotating XFF with fixed CF gives 61st 429 |
| `test_peer_mode_ignores_all_headers` (test 38) | `peer` mode ignores all headers |
| `test_peer_mode_single_bucket` (test 39) | `peer` mode: all headers ignored, one bucket per client.host |
| `test_unknown_client_ip_source_raises` (test 40) | Unknown `CLIENT_IP_SOURCE` raises `PublicDemoConfigurationError` at startup |
| `test_client_ip_source_in_render_allow_list` (test 41) | `CLIENT_IP_SOURCE` is in Render allow-list |

Updated tests 16, 17, 28, 29, 30, 31, 33 to patch `_CLIENT_IP_SOURCE` alongside `_IS_RENDER`.

## Checks run
```
# Public-demo security tests only
python3 -m pytest tests/api/test_public_demo_security.py -q -p no:cacheprovider -x
-> 128 passed in 3.65s

# Full suite excluding lakebase
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
-> 649 passed, 67 skipped in 102.99s

# Full suite with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
-> 649 passed, 67 skipped in 106.05s
```

## Changed files (round 8 only)
| File | Change |
|------|--------|
| `api/main.py` | Added `logging` import; new `_VALID_CLIENT_IP_SOURCES`, `_resolve_client_ip_source()`, `_CLIENT_IP_SOURCE` module-level var; rewrote `_get_client_ip()` with `xff_leftmost` / `cf_connecting_ip` / `peer` branching; startup log line in `create_app()` |
| `api/demo.py` | Added `CLIENT_IP_SOURCE` to `_RENDER_ALLOW_LIST` |
| `docs/DEPLOYMENT.md` | Replaced old CF-Connecting-IP priority docs with `CLIENT_IP_SOURCE` table, rationale, and post-deploy verification |
| `tests/api/test_public_demo_security.py` | 6 new test functions (tests 36-41); updated tests 16, 17, 28, 29, 30, 31, 33 |

## Previous rounds
- Round 4: `88ca7b8` — per-IP before global counter, single OrderedDict, broadened secret check
- Round 5: `194fe03` — path traversal fix, rate limit all GET/HEAD, 31 traversal tests
- Round 6: `774efae` — over-long path ENAMETOOLONG + symlink loop + global exception handler
- Round 7: `6213f24` — CF-Connecting-IP priority, token bucket, generic secret names, 8 new tests
- Round 8: (this round) — `CLIENT_IP_SOURCE` env var, `xff_leftmost` default, 6 new tests