# BUILD app-resilience round 3 — IMPLEMENT NOW (DeepSeek CHANGES_REQUESTED)

You are MiMo. Fix every item in `.agents/deepseek/VERDICT-app-resilience-round2.md`.
Commit per item, LF endings, do not touch `.agents/dispatch.sh`. Never delete/skip/weaken tests.
Mutation copies: `git archive HEAD | tar -x -C /tmp/<dir>`.

1. Bound TOTAL Lakebase connection establishment, not just per-attempt `connect_timeout`.
   In `db/lakebase.py` `_build_pool`: do not block on `open=True` retry loops; use a bounded wait
   (e.g. `pool.wait(timeout=LAKEBASE_CONNECT_TIMEOUT)` / `getconn(timeout=...)`, `reconnect_timeout` bounded,
   failures raise promptly) so the FIRST request against a disabled/hanging endpoint fails in <= ~3-4 s and is counted
   by the circuit breaker; read routes then return in degraded mode.
   Test: a first request against a fake that hangs (e.g. blocking connect / slow pool) — not a pre-tripped breaker —
   returns 200 for a read route within a bounded time (assert elapsed < 5 s). Mutation "remove the timeout bound" must FAIL it.
2. `tests/api/test_market.py`: the local `client` fixture must isolate Lakebase (use the shared fake / monkeypatch
   `db.lakebase.get_lakebase`) so the 7 tests never touch the real endpoint. They must run green offline.
3. `requirements.txt`: add `python-dotenv`, `pyyaml`, `langsmith`, `edgartools` (whatever package provides `edgar`
   as imported in `api/services/sec_client.py`), and any other undeclared top-level third-party import reachable from
   `api/`, `agent/`, `db/`, `config/`. Add the AST-scan test required by the round-2 BUILD: walk those packages,
   collect top-level (module-scope) third-party imports, map import name → distribution, and fail if any is missing
   from requirements.txt (ibapi/pyspark must remain absent and only deferred). Mutation: drop pyyaml → test FAILS.
4. Add a test asserting the degraded user's role is exactly `viewer` and cannot pass `require_role("trader")`/admin.
5. Non-blocking cleanups: take the lock in `lakebase_status()`; fix `docs/DEPLOYMENT.md` resource nesting to match
   `resources/app.yml`; drop the redundant second `gold_options_features` read in the market route if simple.
   Leave `tests/ml/test_ablation.py` alone (out of scope) but mention it.

Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` — 0 failures except the pre-existing
ml ablation timeout (report it separately); `cd frontend && npm ci && npm run build`.
Verdict: `.agents/mimo/VERDICT-app-resilience-round3.md`.
