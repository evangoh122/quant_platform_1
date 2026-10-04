# BUILD app resilience round 9 — IMPLEMENT NOW (Codex sol final review CHANGES_REQUESTED)

You are MiMo. Fix EVERY item in `.agents/codex/VERDICT-app-frontend-deploy.md` (7 findings + 2 non-blocking + the requirements-test survivor).
Commit per item as you go (small commits), LF endings, do not touch `.agents/dispatch.sh`, never delete/weaken tests, capture the red phase,
mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.
1. db/lakebase.py:~155 — `ConnectionPool(open=False)` then `wait()` raises PoolClosed: the pool is never opened, so roles always degrade and writes
   never work. Open the pool (`pool.open(wait=False)` then bounded `pool.wait(timeout=...)`), and put a subprocess timeout on token minting (:~59)
   so TOTAL establishment is bounded. Make the fake model the real open/closed state (a closed pool's wait() raises) so this is caught.
2. db/delta_adapter.py — concurrency not bounded: on timeout the worker stays alive but the semaphore is released (:~224). Hold the slot until
   the worker actually finishes (release in the worker's finally), and move connection creation + liveness query inside the timeout boundary
   (:~109). Fix `test_warehouse_query_semaphore_bounded` (:~959) to count concurrent executions (mutation: drop semaphore acquire → FAIL).
3. scripts/smoke_app.py:~71 — the frontend check must require HTML containing the built app (e.g. `<div id="root">` + a hashed asset reference that
   then GETs 200) and FAIL on the missing-build JSON hint or non-HTML. Test both.
4. Schema contract must be derived from the real SQL: build queries from the contract (or parse identifiers from the actual query strings in
   delta_adapter/tools_retrieval) so the test fails if the real intraday query selects `open` (:~415). Mutation per Codex → FAIL.
5. ORDER BY before LIMIT: daily (:~397) and options (tools_retrieval.py:~88) must `ORDER BY <date/ts> DESC LIMIT n` and then return
   chronological order (or document descending) consistently with MarketDashboard.tsx:~32 which treats row 0 as latest — fix the frontend
   assumption to pick the max date explicitly. Test that "latest" is the max date.
6. Global "Account services unavailable" banner in App.tsx when /api/health reports Lakebase degraded/breaker open (frontend test).
7. app.yaml:~9 pins the dev schema — take catalog/schema from env (`CATALOG`/`SCHEMA` set by the bundle/app resources) with no personal default
   in production; bundle and app.yaml paths must agree. Test that app.yaml contains no `evangoh_capstone` literal.
8. tests/test_requirements_completeness.py:~91 truncates `databricks.sql` to `databricks` — map dotted imports correctly so dropping
   databricks-sql-connector FAILS (mutation).
Non-blocking (do them): schema checker stops at '#' partition rows; COT mapping for UUP uses 'FX' vs live 'fx' (case) — normalise; market source
labels say gold_ohlcv_features for daily data from silver_ohlcv_day_adjusted.
Also: the full pytest selection hangs >10 min at the first TestClient health test under Codex's sandbox — make sure no health/TestClient test can
block on real network/threads (all probes faked, bounded joins).
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` finishes (known ml ablation timeout excepted);
frontend tests + build. Verdict: `.agents/mimo/VERDICT-app-resilience-round9.md`.
