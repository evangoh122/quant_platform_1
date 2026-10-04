# BUILD app resilience round 6 — IMPLEMENT NOW (Claude LIVE findings on round 5, from WSL against the real warehouse)

You are MiMo. Commit per item, LF endings, do not touch `.agents/dispatch.sh`, never delete/weaken tests, capture the red phase,
mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. No secrets in logs/output.

Live run (pyspark disabled to mimic the deployed app, databricks-sql-connector 4.6.0, warehouse b15d3d6f837ba428):
- `check_warehouse_health()` → (True, 'reachable') but took 8.5 s from cold (> the 5 s probe budget).
- `latest_signals("AAPL", limit=3)` → `ServerOperationError [PARSE_SYNTAX_ERROR] Syntax error at or near '%'`:
  `... WHERE symbol = %s ORDER BY prediction_ts DESC LIMIT 3`.

1. BLOCKING — wrong parameter style. databricks-sql-connector ≥3 uses NATIVE named parameters: `:name` markers with a dict
   (`cursor.execute("... WHERE symbol = :symbol", {"symbol": s})`). Convert every warehouse query (db/delta_adapter.py ~283, ~307, ~312,
   agent/tools_retrieval.py ~77, ~81, and any others) to `:name` + dict; fix the docstrings. Pin `databricks-sql-connector>=3.0.0,<5`.
   Tests must FAIL on `%s`: add a fake cursor that validates the SQL uses only `:name` markers whose names exactly match the params dict
   keys (and rejects `%s`/`?`), used by every warehouse route test. Mutation: put back one `%s` → FAIL.
2. Cold connect exceeds the probe budget. Warm the shared warehouse connection at app startup in the background (non-blocking; startup
   must not wait for it), reuse it, and make the health probe report `warming` (ok=false, detail="connecting") while the first connect is
   in flight instead of a bare timeout. Test with a fake slow connect.
3. Thread-based statement timeout does not cancel the query: after `t.join(timeout)` the warehouse keeps running it and the worker thread
   lives on. On timeout, call `cursor.cancel()` (connector supports it) from the waiting thread, then close the cursor; cap concurrent
   in-flight warehouse queries with a bounded semaphore/executor so stuck calls cannot pile up. Tests: hanging fake cursor → timeout
   error within bound AND cancel() called; 20 hanging calls → bounded live threads. Mutation: drop cancel() → FAIL.
Claude reruns the live checks afterwards (health, signals, market, options, COT through the warehouse backend).
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (only the known ml ablation timeout may fail);
frontend build. Verdict: `.agents/mimo/VERDICT-app-resilience-round6.md`.
