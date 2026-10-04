# BUILD app resilience round 5 — IMPLEMENT NOW (DeepSeek CHANGES_REQUESTED on rounds 3+4)

You are MiMo. Fix every blocking finding and the three non-blocking notes in
`.agents/deepseek/VERDICT-app-resilience-round3-4.md`. Commit per item, LF endings, do not touch `.agents/dispatch.sh`, never
delete/weaken tests, capture the red phase, mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. No secrets in logs/output.

1. AST-scan test fails on stdlib `contextvars`. Use `sys.stdlib_module_names` (Python ≥3.10) instead of a hand list, plus the local
   package names. Acceptance must be green except the known ml ablation timeout.
2. Warehouse backend must be consumable end-to-end. Give `db/delta_adapter.py` ONE return contract for both backends
   (e.g. always `list[dict]` — convert Spark rows with `asDict()` inside the adapter) and update every consumer:
   `api/routes/signals.py`, `api/routes/market.py`, `api/routes/analytics.py`, `agent/tools_retrieval.py`
   (`get_latest_signal`, `get_market_features`, `get_options_features`, `get_cot_positioning`) — no direct pyspark imports outside
   the adapter's pyspark branch. Tests drive route → tool → adapter with pyspark ABSENT (monkeypatch import / fake connector)
   and assert real rows come back for signals, market, analytics, options and COT. Mutation: return Spark-style objects from the
   warehouse path → route tests FAIL.
3. Health probes must not leak threads: single in-flight probe per dependency (if a previous probe is still running, report
   `ok=false, detail="probe still running"` without starting another) or a bounded executor. Run the two probes concurrently so the
   whole endpoint is bounded by ~max(timeouts)+margin (~6 s). Test: a probe that blocks forever, call /api/health 20 times →
   live thread count grows by at most 1 per dependency; elapsed per call bounded.
4. Apply the warehouse statement timeout for real (connector/session timeout or the SDK `wait_timeout` + cancel on expiry) on every
   warehouse query, not just the health probe. Test with a fake that hangs → query raises a timeout error within the bound.
   Mutation: drop the timeout → FAIL.
5. `/api/health/trace` requires `get_current_user` like other read routes (operator/reviewer-only if roles allow; at minimum
   authenticated). Test 401 without auth in non-demo mode.
6. Non-blocking → do them: `check_warehouse_health` returns exception TYPE only (seeded-secret test on the warehouse path too).
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (only the known ml ablation timeout may fail);
frontend build (from WSL if UNC blocks: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-appfe/frontend && npm ci && npm run build'`).
Verdict: `.agents/mimo/VERDICT-app-resilience-round5.md`.
