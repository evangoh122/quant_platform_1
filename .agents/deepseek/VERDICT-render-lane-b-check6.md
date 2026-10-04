===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, round-7 re-check)

**Status:** CHANGES_REQUESTED
**Round:** 7 (re-check per `CHECK-render-lane-b.md` "Re-check after round 7", targeting `6213f24`; HEAD `d5ccc03`)
**Branch:** `slice/render-lane-b`

Round 7 fixes the Codex CRITICAL (rightmost-XFF spoofing) correctly in spirit — the limiter no
longer trusts the rightmost `X-Forwarded-For` entry, and the hard global ceiling is now a
self-recovering token bucket. But it introduces a new priority inversion: it trusts the
Cloudflare-specific headers `CF-Connecting-IP` / `True-Client-IP` **above** Render's own
documented, guaranteed client-IP position (leftmost XFF). Those Cloudflare headers are
client-spoofable the moment Cloudflare is not actually in the request path, which restores the
exact CRITICAL failure class Codex asked to eliminate.

## Blocking findings

1. **[api/main.py:207-213] `CF-Connecting-IP` / `True-Client-IP` are trusted at higher priority
   than Render's guaranteed leftmost `X-Forwarded-For`, and are client-spoofable when Cloudflare
   is bypassed.**

   `_get_client_ip` checks `cf-connecting-ip` → `true-client-ip` → leftmost XFF → `client.host`.
   The first two are Cloudflare-behaviour headers, not a Render guarantee. Render's documented and
   CEO-confirmed behaviour is "we set the first IP in the list to the real client IP" — i.e. the
   **leftmost XFF entry is always the real client IP**, regardless of any Cloudflare layer. In the
   very feedback thread the round-7 request cites, Render's co-founder Aseem Kishore explicitly
   hedges: "Cloudflare *(most likely)* is also adding `CF-Connecting-IP` … Is it safe to rely on
   Render remaining on CloudFlare?".

   Concrete failure scenario (proved in `/tmp`, `RENDER=true`, `PUBLIC_DEMO=1`):
   - A client sends `CF-Connecting-IP: <rotating>` while Render/Cloudflare is **not** rewriting it
     (Cloudflare bypassed/removed, or an upstream proxy passes it through). `_get_client_ip` returns
     the spoofed value (`chosen for spoofed CF → 6.6.6.6`, ignoring the trustworthy `X-Forwarded-For: 9.9.9.9`).
   - Rotating the spoofed header 200× returned **200/200** (the per-IP 60/min limit never fires).
   - Because per-IP never rejects, every request also charges the global token bucket; after the
     burst a legitimate request (`client.host`) returned **429** — a single attacker can DoS the
     demo's read surface.

   The safe order is the reverse: **leftmost XFF first** (Render's guarantee), with
   `CF-Connecting-IP`/`True-Client-IP` demoted to fallback (or dropped). As written, a spoofable
   header overrides a guaranteed-correct one.

## Verified fixes (round 7)

- **Leftmost-XFF, not rightmost.** With no CF header, `X-Forwarded-For: 2.2.2.2, <junk>` keys on
  `2.2.2.2`; rotating the rightmost value no longer evades (test 29 + `_get_client_ip` probe).
- **Strict IP parsing.** `_parse_ip` strips whitespace and validates via `ipaddress.ip_address`;
  invalid candidates (`"abc"`, `"not-an-ip"`, `"1.2.3.4, 5.6.7.8"`, `""`) fall through to the next
  source (test 30). Confirmed by direct probe.
- **Outside Render, headers ignored.** `_IS_RENDER` false → only `request.client.host` (test 31).
- **Token bucket replaces the hard ceiling.** `_TokenBucket(capacity=600, refill=10/s)`; direct probe:
  600 consumes → all allowed, next is `False, retry_after=1` (brief, self-recovering). Bounded
  memory (three scalars; no collection). The prior minute-long global outage is gone.
- **Generic secret names.** `TOKEN`, `SECRET`, `PASSWORD`, `DOCKER_AUTH_CONFIG` exact names and
  `_CONNECTION_STRING` suffix all reject non-empty values; `_is_unsafe_key` returns `True` for each.
- **No new false positives.** Ran `validate_public_demo_environment()` against a realistic Render
  env (`RENDER`, `RENDER_*` (incl. `RENDER_APP_NAME`), `PORT`, `PYTHON_VERSION`, `NODE_VERSION`,
  `PATH`, `HOME`, `RENDER_EXTERNAL_URL`, …) → **no false positives**, no raise. (Render's managed
  `DATABASE_URL`/`REDIS_URL` would be rejected — that is correct fail-closed behaviour, not a
  false positive.)
- **No dangling refs.** `_global_counts`/`_global_limit` fully removed; `global_limit` remains only
  as the `_FixedWindowLimiter` parameter consumed by the token bucket.

## Re-run of earlier attacks — no regression

- Full suite green (see checks). Path traversal (`tests/api/test_path_traversal.py`), SPA
  confinement, over-long/symlink-loop/`HTTPException`-preserving 500 handler, security headers on
  405/413/429/504, demo identity spoofing, no-`db.lakebase` import, `RENDER` fail-closed, and
  unrecognised `PUBLIC_DEMO` → raise are all still passing and unchanged by round 7 (which touched
  only `api/demo.py`, `api/main.py`, `docs/DEPLOYMENT.md`, and the security test file).

## Non-blocking notes

- **[api/main.py:185-188] IPv4-mapped IPv6 is not collapsed to IPv4.** `str(ipaddress.ip_address(..))`
  normalises equivalent textual forms, but `::ffff:9.9.9.9` → `::ffff:909:909` is a **different key**
  from `9.9.9.9`. A single client alternating IPv4 / IPv4-mapped forms gets 2× the per-IP limit
  (proved: 120 alternating requests → 120×200, no 429). Consider
  `ip.ipv4_mapped` when `isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None`.
- **[api/main.py:207] The CF/True-Client-IP branch is only safe while Render actually fronts the
  app with Cloudflare.** Even with the blocking fix, document that these headers are an untrusted
  optimisation, never the primary key.
- **[docs/DEPLOYMENT.md:198] "Cloudflare, which Render uses as its edge"** overstates the guarantee
  Render provides. Render documents leftmost XFF, not Cloudflare headers; the doc should reflect
  that CF-Connecting-IP is best-effort and leftmost XFF is the authoritative source.
- **[api/main.py:380-389] The 413 check still keys on `Content-Length`** for the read path (POSTs
  are 405'd first), so a chunked GET body is bounded only by the 10s timeout. Pre-existing; low
  risk given demo routes never read a body.

## Checks run

```
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
  -> 643 passed, 67 skipped

PUBLIC_DEMO=1 python3 -m pytest -q -p no:cacheprovider \
    tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
  -> 129 passed

# scratch probes in /tmp only (worktree left clean, /tmp/ds_check6 removed):
#   rotating spoofed CF-Connecting-IP (200) -> 200/200 (per-IP limit bypassed);
#   rotating spoofed True-Client-IP (200) -> 200/200;
#   post-burst legit request -> 429;
#   alternate IPv4/IPv4-mapped (120) -> 120x200 (2x evasion);
#   _parse_ip canonicalisation matrix; realistic Render env -> no false positives;
#   _get_client_ip spoofed-CF precedence proof (6.6.6.6 chosen over leftmost 9.9.9.9).

git show 6213f24 -> diff reviewed in full; no committed secrets.
git status        -> working tree clean (no scratch files left; .agents/dispatch.sh untouched).
```

## Verdict

CHANGES_REQUESTED — one blocking finding: the client-IP extraction trusts Cloudflare headers
(`CF-Connecting-IP`, `True-Client-IP`) above Render's documented leftmost-XFF guarantee, so a
client that can supply those headers (Cloudflare bypassed/absent) evades the per-IP limit and
drains the global token bucket to deny service. Fix is a two-line priority reorder (leftmost XFF
first). Everything else in round 7 is correct and nothing regressed.
===VERDICT END===
