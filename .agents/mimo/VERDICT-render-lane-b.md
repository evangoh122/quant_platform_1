# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
None. The CRITICAL XFF finding from Codex re-review is fixed.

## Fixes applied (round 7)

### 1. Client-IP extraction — CF-Connecting-IP priority (CRITICAL)
**File:** `api/main.py:148-184`
**Problem:** `_get_client_ip` used the rightmost `X-Forwarded-For` entry when `RENDER` is set. Render prepends the real client IP to the leftmost position; client-supplied XFF values remain to the right. An attacker could rotate the rightmost value to evade per-IP limits, churn the LRU, and exhaust the global ceiling.
**Fix:** New priority order when `RENDER` is set:
1. `CF-Connecting-IP` (Cloudflare, validated as real IP)
2. `True-Client-IP` (Cloudflare/CDN, validated)
3. Leftmost `X-Forwarded-For` entry (Render's documented position, validated)
4. `request.client.host` (fallback)

Each candidate is parsed via `ipaddress.ip_address()`; invalid values are silently skipped. Outside Render, only `request.client.host` is used and all headers are ignored.

### 2. Token bucket replaces hard global ceiling
**File:** `api/main.py:67-107`
**Problem:** The fixed-window global ceiling (600 req/min) caused a hard minute-long outage once exhausted — all clients blocked until the window reset.
**Fix:** Replaced with a `_TokenBucket` (capacity=600, refill_rate=10 tokens/sec). Aggregate load now causes brief 429s that self-recover within seconds. Per-IP rejection still happens first (unchanged), so a single attacker cannot drain the bucket alone.

### 3. Generic secret names in startup check
**File:** `api/demo.py:74-77, 62`
**Problem:** Codex flagged that bare names `TOKEN`, `SECRET`, `PASSWORD`, `DOCKER_AUTH_CONFIG`, and suffix `_CONNECTION_STRING` were not rejected by the demo-mode secret check.
**Fix:** Added `TOKEN`, `SECRET`, `PASSWORD`, `DOCKER_AUTH_CONFIG` to `_SECRET_EXACT`; added `_CONNECTION_STRING` to `_SECRET_SUFFIXES`.

### 4. Documentation corrected
**File:** `docs/DEPLOYMENT.md:181-232`
**Problem:** Docs claimed the rightmost XFF entry "cannot be spoofed by the client" — false on Render, which does not strip client-supplied XFF values.
**Fix:** Replaced with accurate documentation of the new header priority order, token bucket behavior, and post-deploy verification steps.

### 5. Tests — 8 new functions (round 7)
**File:** `tests/api/test_public_demo_security.py`

| Test | What it proves |
|------|---------------|
| `test_cf_connecting_ip_takes_priority_over_xff` | CF-Connecting-IP used over XFF; rotating XFF doesn't evade |
| `test_no_cf_header_leftmost_xff_used` | Without CF header, leftmost XFF is the key; rotating rightmost doesn't evade |
| `test_invalid_cf_header_falls_back` | Invalid CF → True-Client-IP → XFF → client.host |
| `test_outside_render_headers_ignored` | No RENDER env → headers ignored, only client.host used |
| `test_token_bucket_self_recovers` | Bucket recovers after refill interval; no minute-long outage |
| `test_render_cf_connecting_ip_61st_request_gives_429` | RENDER + CF-Connecting-IP + rotating XFF → 61st gets 429 |
| `test_generic_secret_names_rejected` | TOKEN, SECRET, PASSWORD, DOCKER_AUTH_CONFIG rejected in demo |
| `test_connection_string_suffix_rejected` | *_CONNECTION_STRING rejected in demo |

Existing tests 16/17 updated to match leftmost-XFF behavior.

## Checks run
```
# Public-demo security tests only
python3 -m pytest tests/api/test_public_demo_security.py -q -p no:cacheprovider -x
→ 122 passed in 3.55s

# Full suite excluding lakebase
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 643 passed, 67 skipped in 115.49s

# Full suite with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 643 passed, 67 skipped in 114.77s
```

## Changed files (round 7 only)
| File | Change |
|------|--------|
| `api/main.py` | Added `ipaddress` import; new `_parse_ip` helper; rewrote `_get_client_ip` with CF-Connecting-IP > True-Client-IP > leftmost XFF priority; new `_TokenBucket` class; `_FixedWindowLimiter` uses token bucket instead of global counter |
| `api/demo.py` | Added TOKEN, SECRET, PASSWORD, DOCKER_AUTH_CONFIG to `_SECRET_EXACT`; added `_CONNECTION_STRING` to `_SECRET_SUFFIXES` |
| `docs/DEPLOYMENT.md` | Replaced rightmost-XFF claim with accurate header priority docs; documented token bucket and post-deploy check |
| `tests/api/test_public_demo_security.py` | 8 new test functions; updated tests 16/17 for leftmost-XFF; updated docstring |

## Previous rounds
- Round 4: `88ca7b8` — per-IP before global counter, single OrderedDict, broadened secret check
- Round 5: `194fe03` — path traversal fix, rate limit all GET/HEAD, 31 traversal tests
- Round 6: `774efae` — over-long path ENAMETOOLONG + symlink loop + global exception handler
- Round 7 commit: `6213f24` (branch: `slice/render-lane-b`)