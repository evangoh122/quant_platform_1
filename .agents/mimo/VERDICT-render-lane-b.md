# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None.

## Non-blocking notes
- `test_new_viewer_cannot_approve_order` in `tests/api/test_rbac.py` fails with 503 due to Lakebase endpoint being disabled (infrastructure issue, not caused by this lane). Pre-existing.
- The `_isolate_modules` autouse fixture in `test_public_demo_security.py` prevents demo-mode app instances from leaking into subsequent tests that use the `client` fixture.

## Checks run
```
# Test 1: Demo security + write guard (PUBLIC_DEMO=1)
PYTHONPATH="/tmp/pyspark_hide:$PYTHONPATH" PUBLIC_DEMO=1 python3 -m pytest -q tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
→ 29 passed in 1.43s

# Test 2: All existing tests (non-demo)
PYTHONPATH="/tmp/pyspark_hide:$PYTHONPATH" python3 -m pytest -q tests/api tests/lakebase/test_guardrails.py tests/lakebase/test_execution_boundary.py
→ 66 passed, 1 failed (pre-existing infrastructure: Lakebase endpoint disabled)

# Red status proof: new tests against OLD code (git archive HEAD)
PUBLIC_DEMO=1 python3 -m pytest -q tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
→ 29 failed in 1.19s
```

## Changed files
| File | Change |
|------|--------|
| `api/demo.py` | NEW — `is_public_demo()`, `PublicDemoConfigurationError`, `validate_public_demo_environment()`, constants |
| `api/deps.py` | MOD — `get_current_user()` demo bypass (returns fixed viewer before header/DB); `read_delta()` extended with `snapshot_key` seam |
| `api/main.py` | MOD — `create_app()` factory, conditional route registration, `_FixedWindowLimiter`, demo middleware (rate limit, body size, timeout, security headers, no CORS), non-demo CORS restricted |
| `agent/tools_write.py` | MOD — `PublicDemoWriteDisabled` exception, `_reject_public_demo_write()` guard on all 7 write tools |
| `tests/api/test_public_demo_security.py` | NEW — 10 test functions (22 with parametrize): anonymous viewer, spoofed identity, no Lakebase, route methods, unsafe vars, safe env, rate limit, body size, headers, CORS |
| `tests/lakebase/test_public_demo_write_guard.py` | NEW — 1 parametrized test covering 7 write tools, asserts zero DB/broker/risk/clock calls |

## Commit SHA
`6365661ca50fb0cd303aee0c8a34d3702254d782` (branch: `slice/render-lane-b`)