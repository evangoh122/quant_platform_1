# CHECK: Render lane B, public demo security (DeepSeek)

Branch `slice/render-lane-b`. Spec: `.agents/requests/BUILD-render-lane-b.md` (+ round 2). Read-only;
scratch work goes in /tmp. Write `.agents/deepseek/VERDICT-render-lane-b.md` (===VERDICT START/END===,
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
