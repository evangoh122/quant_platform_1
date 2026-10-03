# CHECK: Render lane B, public demo security (DeepSeek)

Branch `slice/render-lane-b`. Spec: `.agents/requests/BUILD-render-lane-b.md` (+ round 2). Read-only;
scratch work goes in /tmp. Write `.agents/deepseek/VERDICT-render-lane-b-check2.md` (===VERDICT START/END===,
Status). This is the security lane: try to BREAK it.

Claude's smoke test (`PUBLIC_DEMO=1`, clean env, no frontend build):
- POSTs to orders, approve, watchlists and agent/chat → 405;
- `/openapi.json` → 404;
- a spoofed `x-forwarded-email` gives the identical response;
- `db.lakebase` and `agent.tools_write` are never imported;
- `LAKEBASE_HOST` set → `PublicDemoConfigurationError`.

Attack it:
1. **Bypass demo mode.**
   - Values of `PUBLIC_DEMO` like "true", " 1 ", "TRUE", "yes", "0", "".
   - Can the env var change after import?
   - Does `create_app()` re-read it?
   - Is there any path where demo is off by accident on Render, and what is the default?
2. **Reach a write.**
   - HEAD, PUT, PATCH, DELETE, method override headers, trailing slashes, `//api/orders`,
     URL-encoded paths.
   - The SPA catch-all `/{full_path:path}` (build `frontend/dist` with a stub `index.html` in /tmp).
     Could the catch-all ever shadow or expose anything?
3. **Startup secret check.** Which credential-like vars slip through? E.g. `PGPASSWORD`, `PG*`,
   `IBKR_*`, `POLYGON_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `*_PASSWORD`, `*_KEY`,
   `DATABASE_URL`, `HF_TOKEN`. List each one and recommend.
4. **Rate limiter and size limits.**
   - Does the per-IP key trust `X-Forwarded-For` blindly? With `--proxy-headers` on Render, is
     that spoofable to evade limits?
   - Memory growth bound?
   - Does the 413 check rely on Content-Length only (chunked bodies)?
5. **Tests.** Do they fail on old main? Do they stay isolated (env, `sys.modules`)?

Run `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`.

## Re-check after round 3 (this run)
MiMo round 3 (commit 5282117) addresses your blocking findings 1–2 and the REQUIRED items in
`.agents/requests/BUILD-render-lane-b-round3.md`. Re-verify each one with the same attacks:
- `/api/health` in demo: no `db.lakebase` import, no subprocess, fast 200.
- `RENDER=true` without demo → refuses to start. An unrecognised `PUBLIC_DEMO` value → raises.
- Security headers on the middleware's 405/413/429/504.
- The broadened secret families, and the Render allow-list. Is anything sensitive allow-listed?
- The rate limiter keys on the rightmost XFF when `RENDER` is set, has the LRU cap and the global
  ceiling. Try evasion and memory growth.
- Path normalisation: `//api`, `%2f`, upper case.
- The route-enumeration test is no longer vacuous (mutation: register a POST route in demo → the
  test fails).

Also look for anything NEW the round-3 changes broke. Write `.agents/deepseek/

## Re-check after round 4 (this run)
Codex's review (`.agents/codex/VERDICT-render-lane-b.md`) found 2 limiter defects. MiMo round 4
(commit 88ca7b8) claims to fix them and broadens the secret check. Re-verify:
- **Per-IP is checked before global.** One IP sending 10× the global ceiling must not block another
  IP's first request.
- **One bounded structure.** `lru_max=5` with 1,000 IPs → every internal structure holds ≤ 5 entries.
- **New secret families** (AWS_/AZURE_/GOOGLE_/GITHUB_/STRIPE_/SENTRY_, `_DSN`, `_URI`, `_PAT`,
  `_APIKEY`, `_CREDENTIALS`, `*_URL` with credentials). Did any harmless Render default get caught?
  A false positive would stop the app from starting on Render.

Re-run your earlier attacks to confirm nothing regressed. Write
`.agents/deepseek/VERDICT-render-lane-b-check3.md`.
