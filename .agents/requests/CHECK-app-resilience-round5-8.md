# CHECK: app resilience rounds 5–8 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-app-resilience-round5-8.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Requests: BUILD-app-resilience-round5.md (fixes your r3-4 verdict), -round6.md, -round7.md, -round8.md (Claude live findings). Commits
eabe67e..f189e9b (r5), 90b8a88, 677e368 (r6), 403f8a5 (r7), 1bf9d5d (r8). MiMo's self-reports are NOT evidence.

Claude's LIVE results (WSL, pyspark disabled like the deployed app, real warehouse b15d3d6f837ba428), after r8:
- signals → {"status": "no_signals_published"} (gold_trading_signals has 0 rows) — 6.5 s cold.
- market AAPL 2024-06 → 19 daily split-adjusted bars keyed event_date — 0.8 s.
- options AAPL → 521 rows — r8 asked for a default bound of latest 252 (`days` param): looks NOT applied → verify (blocking if unbounded).
- COT SPY → equity_index, 10 fields — 0.6 s.
- `python3 scripts/check_schema_contract.py` → exit 0 "All tables match", but it reports Delta DESCRIBE's partition section rows
  ('# Partition Information', '# col_name') as extra columns — should stop parsing at the first '#'-prefixed row (minor, include).
Verify every blocking item of your r3-4 verdict is fixed (AST scan, end-to-end warehouse consumers, no thread leak + concurrent probes, real
statement timeout WITH cursor.cancel, /api/health/trace auth, type-only errors), plus r6 (`:name` params everywhere — any `%s`/`?` left in
warehouse SQL is blocking; background warming + "connecting" state; bounded semaphore), r7 (schema contract + queries only use contract
columns), r8 (LIMIT only on SELECT; checker exit codes; agent signal empty state; market event_date/vwap/price_basis; options bound).
Run your named mutations again: drop probe timeout; drop cancel(); put one `%s` back; reference `open` from gold_ohlcv_features; select pyspark
when absent; LIMIT appended to DESCRIBE → each must FAIL a named test.
Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks" (known ml ablation timeout excepted — name it);
frontend build (from WSL if UNC blocks: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-appfe/frontend && npm ci && npm run build'`).
