# BUILD: Render lane B round 3, DeepSeek security findings (MiMo)

Read `.agents/deepseek/VERDICT-render-lane-b.md` first. Fix the 2 blocking findings and the
non-blocking items marked REQUIRED. Each fix needs a test that FAILS on the current HEAD (prove it
in /tmp).

## Blocking
1. **`/api/health` touches Lakebase in demo** (`api/routes/health.py:22-35`).
   - In public demo, report `lakebase` and `delta` as `{"ok": false, "detail": "disabled in public demo"}`
     WITHOUT importing `db.lakebase` or spawning a subprocess. Return 200 fast.
   - Test: in demo, `GET /api/health` returns 200 in under 1 s, and `"db.lakebase" not in sys.modules`
     afterwards. Patch `subprocess.run` to raise if called.
   - Extend `test_no_lakebase_import_in_demo` to hit EVERY registered GET route.
2. **Fail-open default.**
   - Render sets `RENDER=true` in every service. In `create_app()`: if `RENDER` is set (any non-empty
     value) and NOT public demo, raise `PublicDemoConfigurationError("refusing to start with write
     routes on Render; set PUBLIC_DEMO=1")`.
   - `is_public_demo()` stays strict, but an unrecognised non-empty `PUBLIC_DEMO` value (e.g. "t",
     "1.0", "0") must raise. It must not silently mean off. Only unset/empty means off (local dev
     and Databricks).
   - Tests:
     - `RENDER=true` without demo → refuses;
     - `RENDER=true PUBLIC_DEMO=1` → starts;
     - `PUBLIC_DEMO=t` → raises;
     - unset → normal app (Databricks path unchanged).

## REQUIRED (from the non-blocking notes)
3. **Security headers on every response**, including the middleware's own 405, 413, 429 and 504.
   Use one helper applied on all paths. Test each status.
4. **Broaden the startup secret check** in `api/demo.py`. Add:
   - suffixes `*_PASSWORD`, `*_KEY`, `*_PASS`, `*_PWD`;
   - prefixes `PG`, `POSTGRES_`, `IBKR_`, `POLYGON_`, `OPENAI_`, `ANTHROPIC_`;
   - exact names `DATABASE_URL`, `HF_TOKEN`.

   Keep an explicit allow-list for the harmless Render/runtime vars Render injects: `RENDER*`,
   `PORT`, `PYTHON_VERSION`, `NODE_VERSION`, `PATH`, `HOME`, and any others Render documents.
   Check Render's documented default env vars, and list the ones you allow-listed in the verdict.
   One parametrised test per family.
5. **Rate limiter behind Render's proxy.** Key on the **rightmost** `X-Forwarded-For` entry when
   `RENDER` is set; that is the address Render's edge saw. Otherwise use `request.client.host`. Bound
   the limiter with an LRU cap of 10,000 keys. Keep the per-IP limit, and add a global ceiling
   (e.g. 600 req/min) as a backstop. Do NOT use `--forwarded-allow-ips='*'`. Document the choice in
   `docs/DEPLOYMENT.md`.
   Tests:
   - a spoofed leftmost XFF doesn't evade the limit;
   - two different rightmost IPs get separate buckets;
   - the key count never exceeds the cap.
6. **Normalise the `/api` prefix check**: collapse repeated slashes, percent-decode and
   case-fold before matching. Test `//api/orders`, `/%2fapi/orders` and `/API/orders`.
7. **Fix the vacuous route-enumeration test.** Enumerate the effective routes via the OpenAPI
   schema generated with demo off-switch internals, or by walking `_IncludedRouter.router.routes`.
   The test must FAIL if a POST route is registered in demo (prove it by mutation).

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`;
- `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q tests/api`;
- both file orders with `tests/api/test_rbac.py`.

LF line endings only. Don't touch `.agents/dispatch.sh`. Commit. Update
`.agents/mimo/VERDICT-render-lane-b.md` (round 3).
