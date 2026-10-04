===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, round-8 re-check)

**Status:** APPROVED
**Round:** 8 (re-check per `CHECK-render-lane-b.md` "Re-check after round 8", targeting `eb37097`; HEAD `0070b47`)
**Branch:** `slice/render-lane-b`

Round 8 fixes the check6 CHANGES_REQUESTED finding correctly. `CLIENT_IP_SOURCE` now defaults to
`xff_leftmost` on Render and **never** reads `CF-Connecting-IP` / `True-Client-IP` in that mode, so
a client that can inject those headers no longer overrides Render's documented client-IP position.
The unknown-mode startup guard and the documented post-deploy verification are both present. No
regression in any earlier attack.

## Re-verified (round 8 items)

- **check6 attack closed.** `RENDER=true`, default `xff_leftmost`: rotating `CF-Connecting-IP` and
  `True-Client-IP` across 60 requests with a fixed leftmost `X-Forwarded-For: 3.3.3.3, 9.9.9.9`
  produced one key — request 61 returned **429** (`first60={200}, r61=429`). The two Cloudflare
  headers are simply not read in this mode (`_get_client_ip` only touches `x-forwarded-for` then
  `client.host`).
- **Unknown mode raises at startup.** A fresh subprocess with `CLIENT_IP_SOURCE=bogus` failed to
  import `api.main` with a `PublicDemoConfigurationError` whose text names `CLIENT_IP_SOURCE` and
  echoes only the value (not a secret): `rc=1`, `"CLIENT_IP_SOURCE"` and `"bogus"` in stderr.
- **`cf_connecting_ip` (opt-in) mode.** Uses `CF-Connecting-IP` when valid (`7.7.7.7`), ignores
  `X-Forwarded-For`, falls back to `client.host` when invalid (`not-ip` → `1.2.3.4`).
- **`peer` mode and off-Render default.** `peer` ignores CF/True-Client/XFF entirely (`1.2.3.4`);
  outside Render `_get_client_ip` short-circuits to `client.host` regardless of headers.
- **Docs carry post-deploy verification.** `docs/DEPLOYMENT.md` has the `CLIENT_IP_SOURCE` table,
  the rationale + Render source URL, and a three-step "Post-deploy verification" (log the keyed IP,
  send 70 rotating-spoofed-header requests expecting 429 on #61, switch `CLIENT_IP_SOURCE` if (b)
  fails). The debug-safe log line is in `create_app()` and prints mode+render flag only, no IP.

## Earlier attacks — no regression

- **Path traversal / SPA confinement.** `tests/api/test_path_traversal.py` green (single/double/
  triple encoding, backslash, NUL, external symlink, symlink loop, drive/absolute, over-long
  256/10000-byte segments, real-uvicorn traversal). All traversal payloads return `index.html`; the
  secret never leaks.
- **Global exception handler.** Unhandled exception → generic 500 with all security headers and no
  traceback; `HTTPException` (404/405/413/429) keeps its code.
- **Security headers.** Present on 200/405/413/429/504 (and long-path SPA responses in demo).
- **Rate limiter internals.** Per-IP checked before global (victim's first request allowed after an
  attacker floods 50), single bounded `OrderedDict` (`lru_max=5` with 1000 IPs → `key_count=5`,
  `len(_counts)=5`), self-recovering token bucket.
- **Secret families / Render allow-list.** `validate_public_demo_environment()` over a realistic
  Render env (all `RENDER_*`, `PORT`, `PYTHON_VERSION`, `NODE_VERSION`, `PATH`, `HOME`,
  `CLIENT_IP_SOURCE`) raised nothing — no false positive. Broadened prefixes/suffixes/exact names
  still reject.
- **Fail-closed.** `RENDER=true` without `PUBLIC_DEMO` refuses; unrecognised `PUBLIC_DEMO` raises.
- **Demo surface.** `/api` methods are a subset of GET/HEAD/OPTIONS; `/api/orders|watchlists|agent|
  portfolio` absent; `/api/health` returns 200 in ~5 ms with no `db.lakebase` import and no
  subprocess.

## Non-blocking notes

- **[api/main.py:207-216] IPv4-mapped IPv6 is not collapsed.** `_parse_ip` normalises textual forms
  but `::ffff:9.9.9.9` → `::ffff:909:909` keys separately from `9.9.9.9`. In production this is moot:
  under a correctly-configured proxy the client cannot control the key (Render prepends the real IP
  / Cloudflare rewrites CF-Connecting-IP / peer is the TCP address). Only exploitable if a client
  can inject the leftmost XFF, which is the exact failure the post-deploy verification (b) is meant
  to catch. Consider `ip.ipv4_mapped` for completeness.
- **[api/main.py:47-67] `CLIENT_IP_SOURCE` is read once at import, not in `create_app()`.** Fine for
  production (env is fixed before process start) but means an unknown value aborts import even for
  non-Render, non-demo deployments. Intended fail-closed; worth a one-line doc note.
- **Residual proxy premise.** The whole scheme trusts "Render sets the first XFF entry to the real
  client IP". This is the project's established threat model (Codex's CRITICAL + Claude's decision),
  but it is asserted, not independently verified here (Render's `/docs/forwarding-and-proxying`
  returned 404 during this check). The new post-deploy verification (b) is the correct empirical
  safety net and should be mandatory before going public.

## Checks run

```
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
  -> 649 passed, 67 skipped

PUBLIC_DEMO=1 python3 -m pytest -q -p no:cacheprovider \
    tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
  -> 135 passed

CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y PUBLIC_DEMO=1 \
    python3 -m pytest -q -p no:cacheprovider tests/api/test_public_demo_security.py
  -> 128 passed

# scratch probes in /tmp only (worktree clean): default-xff 61st->429; unknown-source rc=1;
#   cf/peer/off-Render key selection; per-IP-before-global; LRU<=5; Render env -> no false
#   positives; headers on 405/413/429; RENDER fail-closed; health fast+no-lakebase; route surface.

git show eb37097 -> diff reviewed in full; no committed secrets (api/demo.py, api/main.py,
                    docs/DEPLOYMENT.md, tests only).
git status (wsl)  -> working tree clean; .agents/dispatch.sh untouched.
```

## Verdict

APPROVED — the check6 blocking finding (Cloudflare header priority) is resolved: `xff_leftmost` is
the Render default and the spoofable CF/True-Client-IP headers are never read in that mode. Unknown
`CLIENT_IP_SOURCE` fails closed at startup, the docs carry the post-deploy verification steps, and
no earlier attack regressed. Only non-blocking residual notes remain (IPv4-mapped key normalisation
and the asserted Render XFF premise, the latter gated by the documented post-deploy check).
===VERDICT END===
