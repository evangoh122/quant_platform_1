# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None. Both blocking findings from Codex's verdict are resolved.

## Fixes applied (round 4)

### 1. Per-IP check before global counter (Codex finding #1)
**File:** `api/main.py`
**Problem:** Global counter was incremented BEFORE the per-IP check. Requests already rejected by the 60-request per-IP limit still consumed the 600-request global allowance. One attacker IP could exhaust the global ceiling and deny service to all other IPs.
**Fix:** Reordered `check()` method: per-IP limit is enforced first. If per-IP rejects, return 429 WITHOUT touching the global counter. Global counter is only charged for requests that pass per-IP.
**Regression test:** `test_per_ip_rejection_does_not_consume_global` — attacker sends 50 requests (per-IP limit=5, global=20). Victim's first request then gets 200 (global counter = 5, not 51).

### 2. Single bounded OrderedDict (Codex finding #2)
**File:** `api/main.py`
**Problem:** `_lru` (LRUCache) and `_counts` (dict) were parallel structures. Evicting an IP from `_lru` did NOT remove its `(ip, window_ts)` entry from `_counts`. With `lru_max=5` and 1,000 IPs: `key_count=5` but `len(_counts)=1,000`.
**Fix:** Replaced `_lru: _LRUCache[str, None]` + `_counts: dict[tuple[str, int], int]` with single `_counts: OrderedDict[str, tuple[int, int]]` mapping `ip -> (window_ts, count)`. LRU eviction (`popitem(last=False)`) atomically removes both the key and its counter. Removed dead `_LRUCache` class.
**Regression test:** `test_lru_bound_bounds_counts_structure` — `lru_max=5` with 1,000 IPs: asserts both `key_count <= 5` AND `len(_counts) <= 5`.

### 3. Broadened startup secret check (Codex secret gaps)
**File:** `api/demo.py`
**Problem:** `_is_unsafe_key()` didn't catch cloud-provider keys (`AWS_*`, `AZURE_*`, `GOOGLE_*`, `GCP_*`), CI/CD tokens (`GITHUB_*`, `GH_*`), payment/analytics keys (`STRIPE_*`, `SENTRY_*`), or URLs with embedded credentials.
**Fix:** Added to `_SECRET_PREFIXES`: `AWS_`, `AZURE_`, `GOOGLE_`, `GCP_`, `GITHUB_`, `GH_`, `STRIPE_`, `SENTRY_`. Added to `_SECRET_SUFFIXES`: `_DSN`, `_URI`, `_PAT`, `_APIKEY`, `_CREDENTIALS`, `_KEY_BASE`. Added to `_SECRET_EXACT`: `CREDENTIALS`, `REDIS_URL`, `MONGODB_URI`, `SECRET_KEY_BASE`. Added URL credential rule: any `*_URL` with `@` or `://user:` in value.
**Regression tests:** 6 parametrised test functions covering all new families plus Codex's specific examples (`AWS_ACCESS_KEY_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `GITHUB_PAT`, `REDIS_URL`, `MONGODB_URI`, `SENTRY_DSN`, `STRIPE_APIKEY`, `SECRET_KEY_BASE`, `AZURE_CLIENT_ID`, `CREDENTIALS`).

## Checks run
```
# New regression tests only
python3 -m pytest -q -p no:cacheprovider tests/api/test_public_demo_security.py::test_per_ip_rejection_does_not_consume_global tests/api/test_public_demo_security.py::test_lru_bound_bounds_counts_structure tests/api/test_public_demo_security.py::test_broadened_secret_prefixes_rejected tests/api/test_public_demo_security.py::test_broadened_secret_suffixes_rejected tests/api/test_public_demo_security.py::test_broadened_exact_names_rejected tests/api/test_public_demo_security.py::test_url_with_embedded_credentials_rejected tests/api/test_public_demo_security.py::test_clean_url_without_credentials_allowed tests/api/test_public_demo_security.py::test_codex_examples_all_rejected
→ 40 passed in 0.48s

# Full suite excluding lakebase
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 589 passed, 67 skipped in 107.52s

# All API tests with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q tests/api
→ 118 passed in 2.92s

# Both file orders with ambient secrets
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_rbac.py tests/api/test_public_demo_security.py
→ 113 passed in 2.24s

CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_public_demo_security.py tests/api/test_rbac.py
→ 113 passed in 2.47s

# Prove tests FAIL on pre-fix code (git stash + restore)
→ 17 failed, 5 passed in 0.67s (5 passed = clean-URL allowed tests)
```

## Changed files (round 4 only)
| File | Change |
|------|--------|
| `api/main.py` | Reorder `check()`: per-IP first, global only for passing requests; single `OrderedDict[ip] → (window, count)` replaces dual `_lru`+`_counts`; remove dead `_LRUCache` class and unused `Any` import |
| `api/demo.py` | Broaden `_is_unsafe_key()`: 8 new prefixes, 6 new suffixes, 4 new exact names, URL-credential rule |
| `tests/api/test_public_demo_security.py` | 70→110 tests: 8 new pure-function test functions (40 parametrised cases) covering limiter order, LRU bound, and all secret families |

## Commit SHA (round 4)
`88ca7b8` (branch: `slice/render-lane-b`)