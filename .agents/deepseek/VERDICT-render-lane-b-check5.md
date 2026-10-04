===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, round-6 re-check)

**Status:** APPROVED
**Round:** 6 (re-check per `CHECK-render-lane-b.md`, targeting `774efae`; HEAD `34174af`)
**Branch:** `slice/render-lane-b`

The round-5 regression (over-long path segment → unhandled `OSError` → 500 without
security headers) and the related symlink-loop crash are both **fixed**, and the new global
exception handler behaves correctly: unhandled errors return a generic 500 carrying every
security header with no traceback, while `HTTPException` codes (404/405/413/429/504) are
**not** swallowed.

## Blocking findings

None.

## What I re-verified (round 6 items)

- **Over-long path guard.** With the SPA catch-all mounted against a real tmp `dist`, segment
  lengths 255/256/300/1000/5000/10000/3000 all returned **200 `index.html`** with
  `X-Frame-Options: DENY` (and the full header set). No 500, no `ENAMETOOLONG` leak. The
  pre-reject (`seg.encode("utf-8") > 255`, `decoded.encode("utf-8") > 2048`) fires before
  `.resolve()`, and the `try/except (OSError, RuntimeError, ValueError)` is a correct
  backstop for total-path >`PATH_MAX` (long `_static_root`) and OS-specific limits.
- **Symlink loop.** `dist/loop -> dist/loop` → **200 `index.html`**, no crash. A symlink out
  of `dist` still refuses the secret (covered by `is_relative_to`), a symlink within `dist`
  is still served.
- **Deliberately raising route → 500.** A route handler registered before the catch-all that
  raises `RuntimeError("secret-internal-12345")` returns **500 `{"detail":"internal error"}`**
  with `nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, CSP, and
  `Cache-Control: no-store`; the body contains no exception class, no traceback, and no secret.
  A raising middleware yields the same result.
- **Global handler does not swallow `HTTPException`.** Confirmed by reading the installed
  Starlette (1.7.0) source — `Exception` handlers become `ServerErrorMiddleware`'s
  `error_handler` (outermost), while `HTTPException` stays in the inner `ExceptionMiddleware`.
  Empirically: a route raising `HTTPException(404)` → **404 `{"detail":"nope"}`** (not 500);
  405/413/429/504 all keep their codes with security headers; non-demo missing route → 404.
  `RequestValidationError` (422) is likewise preserved (specific handler wins).

## Re-run of earlier attacks — no regression

- Traversal (catch-all mounted, fresh limiter): `/../secret.txt`, `/%2e%2e/secret.txt`,
  `/%2e%2e%2fsecret.txt`, `/..%2fsecret.txt`, `/%252e%252e/secret.txt`,
  `/assets/../../secret.txt`, `/..\secret.txt`, `/%5c..%5c..%5csecret.txt`, `/etc/passwd`,
  `/..;/secret.txt`, `/.%2e/secret.txt` — all **200 with no secret**, in addition to
  overlong-UTF-8 / triple-encoding payloads (also no leak). NUL byte rejected by the ASGI
  server (`InvalidURL`) before routing.
- `/assets/x.js` → 200 with content; `/` → 200 `index.html`; HEAD `/assets/x.js` → 200.
- 405 (POST `/api`) / 413 (oversized GET body) / 429 (61st read, integer `Retry-After`) /
  504 (timeout) all carry the full security header set.
- Secret families & Render allow-list: no false positives among Render defaults
  (`RENDER_*`, `PORT`, `PATH`, `HOME`, `PYTHON_VERSION`, `NODE_VERSION`, plus `LANG`,
  `LC_ALL`, `TZ`, `USER`, `PWD`, `HOSTNAME`, `TERM`, `SHELL`, `SHLVL`, `PYTHONPATH`,
  `NODE_OPTIONS`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `GIT_BRANCH`); no false negatives
  across `DATABASE_URL`, `AWS_*`, `GOOGLE_APPLICATION_CREDENTIALS`, `GITHUB_PAT`,
  `REDIS_URL`, `SENTRY_DSN`, `STRIPE_APIKEY`, `PGPASSWORD`, `HF_TOKEN`, `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `POLYGON_API_KEY`, `IBKR_PASSWORD`, and the `_KEY/_PASS/_PWD/_DSN/
  _URI/_PAT/_APIKEY/_CREDENTIALS/_KEY_BASE` suffixes. Error text lists names only — value
  never leaked (`validate_public_demo_environment` with `MY_API_KEY=super-secret-value-9876`
  reported only `MY_API_KEY`).
- Demo identity spoofing, no-`db.lakebase` import, `RENDER` fail-closed, and unrecognised
  `PUBLIC_DEMO` → raise are all still covered and green in the full suite.

## Non-blocking notes

- **[api/main.py:203] The global exception handler is registered unconditionally** (demo and
  non-demo), not only in demo mode as the round-6 request phrased it. In non-demo mode this
  suppresses tracebacks in the response body (replacing Starlette's default). It is *more*
  secure, not less — `ServerErrorMiddleware` still re-raises after sending, so uvicorn logs the
  exception — but it is a behaviour change to the Databricks (non-demo) path worth being aware of.
- **[api/main.py:317-325] The 413 body-size check runs only for `/api` GET/HEAD/OPTIONS**
  (POST/PUT/etc. are 405'd first). So a chunked (no `Content-Length`) body is not size-capped;
  it is bounded only by the 10s request timeout and the fact that demo routes never read a body.
  Pre-existing, not introduced by round 6; low risk given the write surface is 405'd up front.
- **[tests/api/test_path_traversal.py:257] The file lacks a trailing newline** ("\ No newline
  at end of file"), a cosmetic deviation from the round-6 "LF line endings" note.
- **[tests/api/test_path_traversal.py:249-252] `test_long_path_via_real_uvicorn` catches only
  `urllib.error.HTTPError`** for the 10,000-char case; a `ConnectionResetError`/`InvalidURL`
  would fail the test rather than skip. It passes in practice, but it is a slight flake risk.

## Checks run

```
python3 -m pytest -q -p no:cacheprovider tests/api/test_path_traversal.py
  -> 42 passed

python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
  -> 631 passed, 67 skipped

# scratch probes in /tmp only (worktree left clean):
#   long-path 255..10000 -> 200 + headers; symlink loop -> 200; route/middleware raise -> 500
#   {"detail":"internal error"} no traceback; HTTPException 404/405/413/429/504 codes kept;
#   traversal matrix no leak; secret allow-list/false-positive scan; value-leak check.

git show 774efae  -> no committed secrets (diff reviewed in full; only api/main.py + tests)
git status        -> clean
```

## Verdict

APPROVED — round 6 resolves the round-5 ENAMETOOLONG/symlink-loop 500s and adds a correct
catch-all 500 handler that preserves HTTPException codes and carries the full security header
set on every response. No blocking findings; four minor non-blocking notes above.
===VERDICT END===
