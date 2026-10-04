# BUILD app resilience round 8 — IMPLEMENT NOW (Claude LIVE findings on round 7; small)

You are MiMo. Commit as you go, LF endings, do not touch `.agents/dispatch.sh`, never delete/weaken tests, capture the red phase.

Round 7 live (pyspark disabled, real warehouse) — mostly WORKING: market 19 daily bars (2.5 s), options 521 rows (1.1 s), COT SPY→equity_index
(0.8 s). Remaining:
1. `scripts/check_schema_contract.py` cannot run as a script (`ModuleNotFoundError: No module named 'db'`) — add the repo root to sys.path
   (or document `python3 -m scripts.check_schema_contract` AND make the plain path work). Run as a module, every DESCRIBE fails:
   `DESCRIBE <table> LIMIT 1000` → PARSE_SYNTAX_ERROR. The adapter appends LIMIT to every statement; only append LIMIT to SELECT statements
   that lack one (or give the checker a dedicated no-LIMIT metadata path). Test: DESCRIBE/SHOW are never given LIMIT; a SELECT without LIMIT
   gets one; a SELECT with LIMIT is unchanged. Exit codes: 0 on no drift, non-zero on drift or query failure (test both).
2. `agent/tools_retrieval.get_latest_signal("AAPL")` returns `{}` while the table is empty — return the same explicit
   `{"status": "no_signals_published"}` the route uses (agent must not read {} as "no signal for this symbol"). Test.
3. Market daily bars: key them `event_date` (not `feature_ts`) and include `adj_vwap` as `vwap` (currently None); label `price_basis:
   "split_adjusted"`. Bound options rows (latest N=252 by default, `days` param) like market. Tests.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (known ml ablation timeout excepted); frontend build.
Verdict: `.agents/mimo/VERDICT-app-resilience-round8.md`.
