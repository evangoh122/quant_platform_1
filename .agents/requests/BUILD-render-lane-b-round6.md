# BUILD: Render lane B round 6, a round-5 regression (MiMo)

DeepSeek check4 (`.agents/deepseek/VERDICT-render-lane-b-check4.md`): in `api/main.py:~236`,
`(_static_root / decoded).resolve()` raises `OSError ENAMETOOLONG` for any path segment over 255
bytes. Inside `dist`, a symlink loop raises `RuntimeError`. Both escape `_spa`, and both give a 500
WITHOUT security headers, because Starlette's `ServerErrorMiddleware` runs outside the demo guard.
Round 4 returned `index.html` for the same input.

## Fixes
1. In `_spa`, put the resolution and the `is_file`/`is_relative_to` checks inside
   `try/except (OSError, RuntimeError, ValueError)` → serve `index.html`. Also reject over-long input
   before resolving: total path > 2048 bytes or any segment > 255 bytes → `index.html`, or 414.
   Pick one and document it.
2. Add a global exception handler, e.g. `@app.exception_handler(Exception)` or an outermost
   middleware. Any unhandled error → a generic `{"detail":"internal error"}` 500 that carries ALL the
   security headers and no stack trace or path. In demo mode, register it so it wraps everything.
3. Tests, each failing on the current HEAD (prove it in /tmp):
   - `GET /` + 256×"A" and `GET /` + 10,000×"A" → no 500, or a 500 that carries the full security
     headers;
   - a symlink loop in a tmp dist → no crash, `index.html`;
   - a route that raises on purpose (test-only) → a 500 with every security header and no traceback
     text;
   - include one real-uvicorn check of the long-path case.

Keep all the earlier traversal tests passing. Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`;
- the same suite with `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y` set.

LF line endings only. Don't touch `.agents/dispatch.sh`. Commit. Update
`.agents/mimo/VERDICT-render-lane-b.md` (round 6).
