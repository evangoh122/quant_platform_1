===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, round-9 re-check)

**Status:** APPROVED
**Round:** 9 (re-check per `CHECK-render-lane-b.md` "Re-check after round 9", targeting `d7cfc1c`; HEAD `031d420`)
**Branch:** `slice/render-lane-b`

Round 9 closes the two Codex MEDIUM findings (`VERDICT-render-lane-b-3.md`): (1) the
`RATE_LIMIT_DEBUG` opt-in diagnostic now makes post-deploy check (a) actually executable, and (2)
the startup secret check now covers exact names `AUTHORIZATION`/`BASIC_AUTH`/`SESSION_COOKIE`, the
suffixes `_ACCESS_KEY_ID`/`_CERT`/`_COOKIE`/`_AUTH`, and URL query-string credentials. Both are
correct, fail-closed, and introduce no regression. No blocking findings.

## Blocking findings

None.

## Re-verified (round 9 items)

- **`RATE_LIMIT_DEBUG` off by default, no per-request log line.** `_RATE_LIMIT_DEBUG` is `False`
  unless the env var is exactly `1`/`true`/`yes`/`on`. A live TestClient run (debug off) over
  `/api/health` produced **0** `rate_limit_debug` log records.
- **Debug on → redacted key, no full IP / no header value.** With debug on, `X-Forwarded-For:
  203.0.113.7, 8.8.8.8`, `CF-Connecting-IP: 6.6.6.6`, and `Authorization: Bearer supersecret`, the
  only emitted line was `rate_limit_debug client_ip_source=xff_leftmost key=203.0.x.x`. Neither the
  full IP (`203.0.113.7`, `8.8.8.8`) nor any header value leaked. `_redact_ip` verified on a
  corpus of IPv4/IPv6/IPv4-mapped/`unknown`/empty inputs — no full-IP leak in any case.
- **`RATE_LIMIT_DEBUG` is allow-listed** (`api/demo.py:90`), so a demo deploy with debug on does not
  trip its own secret check.
- **Query-param secret detection.** `_has_sensitive_query_param` correctly rejects case variants
  (`?TOKEN=`, `?Token=`), multiple params (`?x=1&token=`, `?page=2&auth=`, `?token=s&other=v`),
  and the full name list (`access_token`, `signature`, `sig`, `key`, `apikey`, `api_key`, `secret`,
  `password`, `pwd`, `auth`). Harmless URLs (`?page=2`, `?q=test&limit=10`, `?format=json`) are
  allowed. Substring false-positive guard holds: `?monkey=` and `?keyword=` are **not** flagged.
- **No false positive on Render defaults.** `validate_public_demo_environment()` over a realistic
  full Render env (all `RENDER_*`, `PORT`, `PYTHON_VERSION`, `NODE_VERSION`, `PATH`, `HOME`,
  `CLIENT_IP_SOURCE`, `RATE_LIMIT_DEBUG`) raised nothing. The allow-list short-circuits before the
  URL check, so `RENDER_EXTERNAL_URL` is never examined.
- **New secret families reject.** `AUTHORIZATION`, `BASIC_AUTH`, `SESSION_COOKIE`,
  `MY_ACCESS_KEY_ID`, `DATABASE_CERT`, `MY_COOKIE`, `CUSTOM_AUTH`, plus prior families
  (`OPENAI_API_KEY`, `PGPASSWORD`, `IBKR_PASSWORD`, `DATABASE_URL`, `HF_TOKEN`, `SENTRY_DSN`, …)
  are all rejected with the value never echoed.

## Earlier attacks — no regression

- **Demo bypass.** `PUBLIC_DEMO` values `true`/` 1 `/`TRUE`/`yes`/`on` → demo ON (`/openapi.json`
  404); `0`/`false`/`""` → **refused** on Render (`RENDER=true`) via `validate_render_environment`.
  `is_public_demo()` is still read at call time, so `create_app()` re-reads it.
- **Write reach.** `POST`/`PUT`/`PATCH`/`DELETE` to `/api/orders`, trailing-slash, `/api/watchlists`,
  `/api/agent/chat`, `/%2fapi/orders`, `/API/orders` → **405**; `X-HTTP-Method-Override` → 405;
  `GET /api/orders` → 404 (write routers absent). No write path reachable.
- **Rate limiter.** Per-IP checked before global: with production limits (60/600) one IP sending
  6000 requests is capped at 60 accepted, and a different IP's **first** request is still allowed.
  Single bounded `OrderedDict`: `lru_max=5` over 1000 IPs → `key_count=5`, `len(_counts)=5`. Token
  bucket self-recovers (`retry_after` nonzero, no hard outage).
- **Path traversal / SPA confinement.** `tests/api/test_path_traversal.py` green (encodings,
  backslash, NUL, symlinks, symlink loop, drive/absolute, over-long segments, `/assets`, HEAD).
- **Security headers / exception handler.** Covered by the suite; 404/405/413/429 preserve codes,
  unhandled exception → generic 500 with all headers.

## Non-blocking notes

- **[api/main.py:43] `RATE_LIMIT_DEBUG` is case-sensitive.** `"TRUE"`/`"Yes"`/`"ON"` are not
  recognised (unlike `is_public_demo`, which lowercases). The fail direction is safe (debug stays
  off), but it is inconsistent and may silently not enable diagnostics for a user expecting
  case-insensitivity. Recommend `.strip().lower() in (...)`.
- **[api/demo.py:96-110] Query-param detection misses two encodings.** URL-encoded param *names*
  (`?to%6ben=secret`) and fragment-embedded credentials (`#token=secret`) are not detected. Both
  require an unusual env-var encoding and are low severity; consider decoding names and scanning the
  fragment for completeness.
- **[api/demo.py:96-110] `key=` is generic.** A benign `?key=<sort-key>` URL would be rejected
  (fail-closed, startup-only). Also `?token=` with an empty value is flagged. Acceptable for a
  demo-mode gate; just be aware the "key" pattern is broader than the others.
- **[api/main.py:220-238] `_redact_ip` reveals 16 bits of the client IP** (first two octets/hextets)
  — intentional per spec, and IPv4-mapped `::ffff:1.2.3.4` redacts to `0:0::/32` (does not leak the
  embedded IPv4). The residual check7 note (limiter keys IPv4-mapped addresses separately) is
  unchanged and unrelated to this round.

## Checks run

```
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
  -> 679 passed, 67 skipped

CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q \
    -p no:cacheprovider tests/api/test_public_demo_security.py tests/api/test_path_traversal.py
  -> 200 passed

# scratch probes in /tmp only (worktree clean):
#   _redact_ip corpus -> no full-IP leak; RATE_LIMIT_DEBUG value semantics (off default;
#     lowercase truthy only); live debug log on/off -> redacted key, no header leak;
#   _is_unsafe_key/_has_sensitive_query_param matrix (case/multi/access_token/signature/sig
#     detected; monkey/keyword/apitoken/fragment/encoded-name not detected);
#   realistic Render env -> no false positive; new secret families -> rejected;
#   limiter: per-IP-before-global (victim allowed), LRU<=5, token-bucket recovery;
#   demo bypass values + write reach (405/404) + method-override + path normalisation.

git show d7cfc1c -> diff reviewed in full (api/demo.py, api/main.py, docs/DEPLOYMENT.md,
                    tests/api/test_public_demo_security.py); no committed secrets.
git status      -> working tree clean; .agents/dispatch.sh untouched.
```

## Verdict

APPROVED — both Codex MEDIUM findings are resolved: the opt-in `RATE_LIMIT_DEBUG` diagnostic logs a
privacy-reduced key (off by default, never a full IP or header value) making post-deploy check (a)
executable, and the secret check now rejects the specified exact names, suffixes, and URL
query-string credentials with no false positives on Render defaults. No earlier attack regressed.
Only non-blocking hardening notes remain (case-insensitive debug flag, URL-encoded/fragment
credential detection, and the intentionally broad `key=` pattern).
===VERDICT END===
