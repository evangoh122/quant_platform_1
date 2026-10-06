# CHECK-vwap-compute (Codex gpt-5.6-luna, DeepSeek fallback)
Independent checker of branch fix/vwap-compute (commits a9122d7..1bf6d60) against `.agents/requests/BUILD-vwap-compute.md`. Don't commit or edit tracked files; no Databricks access.
Run `python -m pytest -q tests/gold tests/silver tests/analytics_nl tests/api/test_health_diagnostics.py tests/api/test_market.py` (and the full suite if time allows; on this machine
tests/ml/test_baseline_labels.py fails on origin/main too — ignore it). Verify:
- gold session VWAP is strictly trailing, partitioned exactly like session_high/low, uses vendor vwap else typical price, zero-volume bars keep the prior value, no cross-day blend;
- silver `_minute_vwap` uses the America/New_York trading date and `CONVERT_TIMEZONE` is valid Databricks SQL with the right argument order; vendor vwap wins; symbols with no minute
  bars stay NULL with NULL vwap_source (no proxy); adj_vwap uses the split factor;
- `ALTER TABLE ... ADD COLUMNS (vwap_source STRING)` at silver/08:82-84 must be idempotent — Delta errors if the column already exists, so a second run would fail. Flag it if it is not guarded;
- run_checks guard fails on all-null vwap_deviation; the MERGE writes vwap_source; tests execute the REAL SQL (not copies) and are not vacuous.
Do your own mutation proofs in a /tmp `git archive` copy. One block ===VERDICT START=== Status: APPROVED | CHANGES_REQUESTED, findings with file:line ===VERDICT END===.
