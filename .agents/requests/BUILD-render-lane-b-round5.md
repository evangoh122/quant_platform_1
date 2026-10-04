# BUILD: Render lane B round 5, CRITICAL path traversal (MiMo)

DeepSeek check3 (`.agents/deepseek/VERDICT-render-lane-b-check3.md`): the SPA catch-all in
`api/main.py:~219-221` serves ANY file on the host:

    GET /%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd  -> 200 root:x:0:0...

`candidate = FRONTEND_DIST / full_path` is never confined. This is in both demo and non-demo mode, and
it bypasses the `/api` rate limiter. It has been there since the app scaffold (#7), so main has it too.

## Fix
1. Resolve and confine:
   ```python
   root = FRONTEND_DIST.resolve()
   candidate = (root / full_path).resolve()
   if full_path and candidate.is_file() and candidate.is_relative_to(root):
       return FileResponse(candidate)
   return FileResponse(root / "index.html")
   ```
   Also reject (serve `index.html`) any path whose decoded segments contain `..`, a backslash, a NUL
   byte, or an absolute or drive prefix.
2. Never follow symlinks out of the root. `resolve()` + `is_relative_to` covers this; add a test that
   creates a symlink inside a tmp dist that points outside it.
3. Apply the per-IP rate limit to ALL requests, not only `/api`, so static fetches are bounded too.
   Keep `/api/health` exempt only if Render's health check needs it, and document that.
4. The security headers already cover every response. Keep it that way.

## Tests (with a real tmp `frontend/dist` that has `index.html` and `assets/x.js`, plus a secret file
OUTSIDE dist), each failing on the current HEAD (prove it in /tmp):
- `/../secret.txt`, `/%2e%2e/secret.txt`, `/%2e%2e%2fsecret.txt`, `/..%2fsecret.txt`,
  `/%252e%252e/secret.txt`, `/assets/../../secret.txt`, `/....//secret.txt` and a backslash variant →
  never the secret's contents. Each returns `index.html` or 404.
- A symlink in dist pointing outside → not served.
- A legit `/assets/x.js` → 200 with its content. A deep SPA link `/signals/AAPL` → `index.html`.
- Run the traversal tests in BOTH demo and non-demo mode.
- Also run one check against a real `uvicorn` subprocess on a random port (DeepSeek reproduced it
  there, not only in TestClient). Skip with a reason if the port can't bind.

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`;
- the same suite with `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y` set.

LF line endings only. Don't touch `.agents/dispatch.sh`. Commit. Update
`.agents/mimo/VERDICT-render-lane-b.md` (round 5).
