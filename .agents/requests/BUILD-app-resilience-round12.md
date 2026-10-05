# BUILD app resilience round 12 — IMPLEMENT NOW (Codex re-review: 4 survivors)

You are MiMo. Stay on branch `slice/app-frontend-deploy` — do NOT create or switch branches (round 11 created `slice/app-resilience-round11`;
Claude fast-forwarded and deleted it). Fix `.agents/codex/VERDICT-app-frontend-deploy-2.md`. Commit per item, LF endings, do not touch
`.agents/dispatch.sh`, never weaken tests, and paste each mutation's FAILED output into your verdict.
1. Source labels: api/routes/market.py:~64,86,87 and frontend MarketDashboard.tsx:~85 must name `silver_ohlcv_day_adjusted` for daily OHLCV
   (and gold_ohlcv_features only for intraday features). Backend test asserts the label per series. Mutation: revert label → FAIL.
2. Smoke tests (tests/test_smoke_app.py:~93,112): mock EVERY endpoint the smoke script calls as healthy, so the ONLY failing condition is the
   frontend check; assert the result is False because of the frontend (check the reported failing step name). Mutation: `_check_frontend_build()`
   always returns True → both tests FAIL.
3. Frontend tests: add Vitest + @testing-library/react (+ jsdom) as devDependencies, an `npm test` script, and tests: (a) MarketDashboard
   picks the MAX event_date from unsorted rows (mutation: use data[0] → FAIL); (b) App shows the global "Account services unavailable" banner
   when /api/health reports Lakebase degraded/breaker open and hides it when healthy (mutation: hard-code false → FAIL). Mock fetch; no network.
   Keep `npm ci && npm run build` working; commit package-lock.json.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"`; `cd frontend && npm ci && npm test -- --run && npm run build`.
Verdict: `.agents/mimo/VERDICT-app-resilience-round12.md`.
