# VERDICT: render-lane-b — MiMo
**Status:** APPROVED
**Round:** 9

## Blocking findings
- None.

## Non-blocking notes
- The `_redact_ip` function uses `lstrip("0") or "0"` to normalize IPv6 hextets; this matches the ipaddress module's canonical form.
- The `_has_sensitive_query_param` regex uses a non-capturing group with `re.IGNORECASE` to match all specified parameter names case-insensitively. False positives on harmless URLs (e.g. `?page=2`) are avoided by the explicit parameter name list.
- `SESSION_COOKIE` is an exact name match; keys like `MY_COOKIE` are caught by the `_COOKIE` suffix. `SESSION_COOKIE_VALUE` would not match either (it ends with `_VALUE`), which is correct — it's not a standard credential form.

## Checks run
- `python3 -m pytest tests/api/test_public_demo_security.py -q -p no:cacheprovider` → 158 passed
- `python3 -m pytest tests/api/test_public_demo_security.py -q -p no:cacheprovider` with `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y` → 158 passed
- `python3 -m pytest tests/api/ -q -p no:cacheprovider` → 208 passed
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase --ignore=tests/ml --ignore=tests/rag --ignore=tests/bronze --ignore=tests/silver --ignore=tests/gold` → 233 passed, 36 skipped
- New tests proved to fail on HEAD (15 FAIL in /tmp/test_new_only.py against pre-change code)
- LF line endings verified via `file` command on all modified files

## Files modified
- `api/demo.py` — added `_has_sensitive_query_param()`, expanded `_SECRET_EXACT`, `_SECRET_SUFFIXES`, `_RENDER_ALLOW_LIST`
- `api/main.py` — added `_RATE_LIMIT_DEBUG`, `_redact_ip()`, per-request diagnostic logging in demo middleware
- `docs/DEPLOYMENT.md` — updated post-deploy check (a) to use `RATE_LIMIT_DEBUG`
- `tests/api/test_public_demo_security.py` — 17 new tests (tests 42–53)