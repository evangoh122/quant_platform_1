# BUILD — Render lane B (R2 + R3 + R4 + R7)

## Scope and ownership

Lane B owns `api/deps.py`, `api/main.py`, new `api/demo.py`, `agent/tools_write.py`, and new tests
`tests/api/test_public_demo_security.py` and `tests/lakebase/test_public_demo_write_guard.py`.
It must not edit Lane A files, route modules, snapshot/export files, fixtures, or Lane C tests.
Section 7 at `docs/RENDER_DEPLOY_PLAN.md:260-364` wins over earlier sections.

## Numbered changes

1. Add `api/demo.py` and define the shared, dependency-light interface
   `is_public_demo() -> bool`. It returns true only for normalized truthy values (`1`, `true`,
   `yes`, `on`) of `PUBLIC_DEMO`; read the environment at call/startup time so tests and app factory
   reloads are deterministic. Define constants `PUBLIC_DEMO_USER_ID = "public-demo"` and
   `PUBLIC_DEMO_ROLE = "viewer"`. This is the exact interface Lane C may import.
2. At `api/deps.py:91-118`, make `get_current_user(request)` immediately return
   `AppUser("public-demo", "viewer", authenticated=False)` when `is_public_demo()` is true. It must
   ignore every identity header and return before `_ensure_user` or any `db.lakebase` import/call.
   Preserve non-demo Databricks behavior. At `api/deps.py:153-169`, extend the exact interface to
   `read_delta(fn: Callable[[], List[dict]], *, snapshot_key: str | None = None) -> Tuple[...]`.
   In public demo, lazily import `api.demo_data.read_snapshot` and call
   `read_snapshot(snapshot_key)` without evaluating `fn`; if no key, module missing, or validation
   fails, return `([], "unavailable", <sanitized detail>)`. Never expose exception text. Outside
   demo preserve current behavior. This lazy seam lets B pass before gated Lane C exists.
3. At `api/main.py:14-60`, introduce `create_app() -> FastAPI`, and export `app = create_app()`.
   In public demo register only health, signals, market, and analytics routers. Do not import or
   register `agent_chat`, `orders`, `watchlists`, or `portfolio` in demo mode; ensure imports are
   conditional so `agent.tools_write`, `db.lakebase`, and broker modules are not imported as a side
   effect. Non-demo route behavior stays unchanged. Disable `/docs`, `/redoc`, and `/openapi.json`
   in demo. Preserve the SPA mount/fallback at `api/main.py:63-75` without intercepting API routes.
4. In `api/demo.py`, define `PublicDemoConfigurationError(RuntimeError)` and
   `validate_public_demo_environment(environ: Mapping[str, str] | None = None) -> None`. When public
   demo is enabled, reject any non-empty key beginning `LAKEBASE_` or `DATABRICKS_`, plus explicit
   broker/credential keys `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `IBKR_ACCOUNT`, `IBKR_USERNAME`,
   `IBKR_PASSWORD`, `BROKER_API_KEY`, and any non-empty key ending `_API_KEY`, `_TOKEN`, or `_SECRET`.
   Error text lists variable names only, never values. Call this synchronously from `create_app()` so
   import/startup refuses unsafe configuration. `PUBLIC_DEMO` itself is not rejected.
5. At every public write entry point in `agent/tools_write.py` anchored at `:168`, `:194`, `:222`,
   `:294`, `:425`, `:701`, and `:784`, call `_reject_public_demo_write()` as the first executable
   statement. Define and export `PublicDemoWriteDisabled(RuntimeError)` and the guard. Cover exactly
   `add_to_watchlist`, `save_research_note`, `create_order_intent`, `record_approval`,
   `approve_and_place_paper_order`, `cancel_paper_order`, and `record_agent_action`. It must raise
   before argument normalization, UUID generation, injected/default DB access, transactions, audit
   logging, market clock, risk engine, or broker acquisition. Do not weaken non-demo behavior.
6. In `api/main.py` add public-demo middleware implementing a per-client-IP, bounded in-memory
   fixed/sliding window for GET/HEAD only: default `RATE_LIMIT_READS=60/minute`; the 61st request in
   the same minute returns 429 with integer `Retry-After`. Trust `request.client.host`, not forwarded
   IP headers. Exempt neither data routes nor health unless documented/tested; tests must use a
   fresh app/resettable limiter. Reject all non-GET/HEAD/OPTIONS `/api` requests in demo with 405.
   Reject bodies over `MAX_REQUEST_BODY_BYTES` (default 1 MiB) from validated `Content-Length` and
   from streamed bytes; return 413. Add a configurable request timeout (default 10 seconds) returning
   504 without exception detail. Add every response header: `X-Content-Type-Options: nosniff`,
   `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, a restrictive CSP, and
   `Cache-Control: no-store` for API responses. Leave CORS middleware entirely absent in demo even
   if `CORS_ORIGINS` is set. Outside demo retain existing opt-in CORS, but set
   `allow_credentials=False`, explicit methods `GET, HEAD, OPTIONS`, and only `Content-Type`.

## Tests must fail on the current code

Add 10 tests in `tests/api/test_public_demo_security.py`: anonymous fixed viewer; spoofed identity
equivalence; no Lakebase import/call; demo route methods are only GET/HEAD/OPTIONS and prohibited
paths are absent; unsafe-variable parameterized families reject at app construction without values
in errors; safe empty environment starts; 61st read gives 429 plus `Retry-After`; oversized body is
413; security headers are present; demo CORS remains absent. Add one parameterized test in
`tests/lakebase/test_public_demo_write_guard.py` covering all seven tools and proving DB,
transaction, audit, risk, clock, and broker mocks have zero calls. Count: **11 test functions**.

Prove red status from old code in a `/tmp` copy created with `git archive HEAD`: copy only these two
new test files into it and run them. Current code fails because it authenticates via a spoofable
header/DB, registers POST routes, lacks startup validation/limits/headers, and permits tool writes.
Record this proof in the verdict; do not revert or mutate the worktree.

## Acceptance commands

```bash
PUBLIC_DEMO=1 python -m pytest -q tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
python -m pytest -q tests/api tests/lakebase/test_guardrails.py tests/lakebase/test_execution_boundary.py
```

Run with PySpark hidden via the required `sitecustomize` entries:

```bash
hide="$(mktemp -d)"; printf '%s\n' 'import sys' 'for m in ("pyspark", "pyspark.sql", "pyspark.sql.functions", "pyspark.sql.types"):' '    sys.modules[m] = None' > "$hide/sitecustomize.py"
PYTHONPATH="$hide${PYTHONPATH:+:$PYTHONPATH}" PUBLIC_DEMO=1 python -m pytest -q tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
PYTHONPATH="$hide${PYTHONPATH:+:$PYTHONPATH}" python -m pytest -q tests/api tests/lakebase/test_guardrails.py tests/lakebase/test_execution_boundary.py
```

Also enumerate `create_app().routes` under a clean public-demo environment and assert all `/api`
methods are a subset of GET/HEAD/OPTIONS, docs schemas are absent, prohibited paths are 404/405,
and `sys.modules` contains none of `db.lakebase`, `agent.tools_write`, or broker modules after app
construction and an anonymous `/api/signals` request.

## DeepSeek must check

- Fail-closed startup checks operate at app construction/import, cover all named variable families,
  and never leak values.
- Demo identity returns before all header trust and Lakebase imports; non-demo auth/RBAC is intact.
- Conditional imports really remove write/portfolio/chat routes and side-effect imports, not merely
  hide OpenAPI entries.
- All seven write tools guard before every side effect, including injected DB objects and private
  broker construction paths reachable through public functions.
- Rate limiter cannot be bypassed with forwarded headers, has bounded cleanup, and has deterministic
  test reset; body streaming and timeout handling do not consume unbounded memory/tasks.
- Middleware order preserves security headers on 4xx/5xx/429/504 and CORS is absent in demo.
- The `read_delta(..., snapshot_key=...)` seam never calls live `fn` in demo and safely tolerates C
  not yet being merged.

## Delivery constraints

No secrets in any file. Use LF line endings. Do not touch `.agents/dispatch.sh`. Do not edit files
outside this lane's ownership. Commit the lane. Write `.agents/mimo/VERDICT-render-lane-b.md` with
changed files, commands/results, old-code failure proof, and commit SHA.
