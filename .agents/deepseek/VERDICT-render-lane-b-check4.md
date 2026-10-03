===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, round-5 re-check)

**Status:** CHANGES_REQUESTED
**Round:** 4 (re-check per `CHECK-render-lane-b.md`, targeting `04a960a`; HEAD `0100e60`)
**Branch:** `slice/render-lane-b`

The CRITICAL SPA path traversal is **fixed**. Every traversal vector I threw at it —
double/triple encoding, overlong UTF-8, backslashes, NUL bytes, absolute/drive paths,
symlinks out of `dist`, Unicode normalisation, and `/assets` edge cases — now returns
`index.html` (or 404) with no file contents, against both `TestClient` and a real
uvicorn subprocess. The rate limiter now covers static fetches too.

However, the new `Path.resolve()`-based confinement introduced **one regression**:
a path segment longer than 255 bytes now raises an unhandled `OSError` and returns a
**500 without security headers**. The pre-fix code used `candidate.is_file()` (which
swallows `ENAMETOOLONG`); the new code calls `.resolve()` unconditionally, which raises.
This is remotely triggerable by any anonymous client with a single long URL.

## Blocking findings

- **[api/main.py:236] `candidate = (_static_root / decoded).resolve()` raises
  `OSError [Errno 36] File name too long` for any URL path segment >255 bytes, and the
  exception escapes `_spa` uncaught → 500.** Reproduced both via `TestClient` and a real
  uvicorn subprocess:

  ```
  GET /AAA…(256 chars)   -> 500 "Internal Server Error"   (headers: nosniff=None, XFO=None, CSP absent)
  GET /AAA…(10000 chars) -> 500 "Internal Server Error"
  ```

  `Path.resolve()` (strict=False) still raises `ENAMETOOLONG`; `Path.is_file()` does not.
  The round-4 code path (`candidate = FRONTEND_DIST / full_path; candidate.is_file()`)
  returned `index.html` for the same input, so this is a **regression introduced by
  round 5**. Two concrete impacts:
  1. Unauthenticated remote 500 / unhandled-exception log spam (bounded only by the
     60/min per-IP limiter).
  2. The 500 is produced by Starlette's `ServerErrorMiddleware`, which sits **outside**
     the demo guard, so `_apply_security_headers` never runs — the response violates the
     slice's own "security headers on every response" guarantee.

  Fix (one line): wrap the resolve in a `try/except (OSError, RuntimeError)` and fall
  back to `index.html`, or bound the segment length before resolving. `RuntimeError`
  must be caught too — see the symlink-loop note below.

## What I verified as fixed (round 5)

- **Path traversal is gone.** All of these return `index.html` (200) with no file
  contents, in demo *and* non-demo mode, via both `TestClient` and a real uvicorn:
  `/../secret.txt`, `/%2e%2e/secret.txt`, `/%2e%2e%2fsecret.txt`, `/..%2fsecret.txt`,
  `/assets/../../secret.txt`, `/....//secret.txt`, `/..\\secret.txt`, `/..%5csecret.txt`,
  `/%5c..%5c..%5csecret.txt`, `/etc/passwd`, `//etc/passwd`, `/%2fetc/passwd`,
  `/C:%5cWindows%5cwin.ini`, `/..;/secret.txt`, `/.%2e/secret.txt`, and a 5-level
  `%2e%2e%2f` chain.
- **Double & triple encoding** (`/%252e%252e/…`, `/%25252e%25252e%252f…`) → the single
  `unquote` + segment scan (`seg in ("..","")`) is sufficient; no leak.
- **Overlong UTF-8** (`%c0%ae` = overlong `.`, `%c0%af` = overlong `/`) → server/`unquote`
  decodes to replacement chars, never to a `..` segment; 200 index.html, no leak.
- **NUL bytes** → rejected by the ASGI server itself (400) *and* caught by the
  `"\x00" in seg` guard; no leak.
- **Backslashes** → `"\\" in seg` guard; raw and `%5c`-encoded variants both blocked.
- **Symlink out of dist** (`dist/link_out.txt -> ../secret.txt`) → `resolve()` follows it,
  `is_relative_to(_static_root)` is False → served `index.html`, not the secret.
- **Symlink inside dist** (`dist/link_internal.txt -> assets/x.js`) → served (correct).
- **`/assets` mount** → Starlette `StaticFiles` confinement: `/assets/../secret.txt`,
  `/assets/%2e%2e/secret.txt`, `/assets/..%2fsecret.txt` all 404; `/assets/x.js` → 200.
- **HEAD** → `/assets/x.js` HEAD returns 200 (no body).
- **Static files are now rate-limited.** 60× `GET /assets/x.js` → 200, the 61st → 429
  with `Retry-After`. The global ceiling is charged for static fetches too.
- **Traversal tests run in both modes** and are non-vacuous (real tmp `dist` + secret
  file outside it + a real uvicorn subprocess, not just `TestClient`).

## Re-run of earlier attacks — no regression

- Demo matrix / fail-closed Render / secret families / method guard / identity
  spoofing / CORS absence / headers on 405/413/429 — all still hold (unchanged since
  check2/check3; the round-5 diff touches only the SPA catch-all + limiter placement).

## Non-blocking notes

- **[api/main.py:236] Symlink loop inside `dist` → unhandled `RuntimeError` → 500.**
  `dist/loop -> dist/loop` makes `Path.resolve()` raise `RuntimeError("Symlink loop …")`,
  also escaping `_spa` uncaught (no security headers). **Not attacker-reachable** — it
  requires writing a symlink into the deployed `dist`, which a public client cannot do.
  The same `try/except` that fixes the long-path 500 should catch this too.
- **[api/main.py:254-255] `/api/health` is now rate-limited** (documented as non-exempt).
  On Render the health-check source IP differs from end-user IPs, so a user hammering the
  site cannot starve Render's health check — no practical break. An aggressive checker
  (>60 req/min from one IP) would 429; standard Render intervals are far below that.
- **[api/main.py:310] `Cache-Control: no-store` is only set for `/api` responses.**
  Static files (and the SPA `index.html`) are intentionally cacheable while still
  carrying `nosniff`/`XFO`/CSP/`Referrer-Policy`. Correct, not a defect.

## Checks run

```
python3 -m pytest -q -p no:cacheprovider tests/api/test_path_traversal.py
  -> 31 passed

python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
  -> 620 passed, 67 skipped

CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y AWS_ACCESS_KEY_ID=x OPENAI_API_KEY=x \
  python3 -m pytest -q -p no:cacheprovider tests/api/test_path_traversal.py
  -> 31 passed

git show 04a960a | grep -iE 'api_key|secret|password|token|BEGIN.*PRIVATE'  -> no committed secrets

Manual attacks (scratch in /tmp only; worktree left clean):
  T1 TestClient 23-payload traversal matrix -> all 200, no leak
  T2 real uvicorn: NUL/backslash/overlong/fullwidth/long/symlink/assets/HEAD probes
  T3 long-segment OSError reproduction (255 ok / 256 -> ENAMETOOLONG / 500)
  T4 symlink-loop RuntimeError reproduction (500, no headers)
  T5 static rate-limit hammer (60x200 -> 429) + health 2.3ms 200
```

## Verdict

CHANGES_REQUESTED — the path traversal is fixed and the rate limiter correctly covers
static requests, but `api/main.py:236` regressed: a >255-byte path segment now raises an
uncaught `OSError` → 500 with no security headers, remotely triggerable by any client.
One-line fix (catch `OSError`/`RuntimeError` around `.resolve()` and fall back to
`index.html`) resolves it, along with the related symlink-loop 500.
===VERDICT END===
