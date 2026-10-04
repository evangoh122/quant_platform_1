# BUILD corporate-actions round 7 (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Descriptive commits.
NEVER delete or weaken existing tests (item 3 replaces a retyped-SQL test — allowed). LF endings.
Checker verdict: .agents/deepseek/VERDICT-corporate-actions-round6.md (CHANGES_REQUESTED). Verified OK in r6: ±3-day
suppression (factor 20, not 400), key-leak redaction, docs.

1 (blocking). SPLIT_SINGLE_SOURCE is documented but never emitted. In silver/08_silver_ohlcv_day_adjusted.sql, emit a
   data_quality_breaks row (explicit columns) for every applied yfinance split with no massive row within ±3 days
   (reason/classification SPLIT_SINGLE_SOURCE). Also massive-only splits when the run fetched yfinance (`both` mode)? —
   NO: only yfinance-only, since massive is primary. Keep docs consistent with exactly what's emitted.
2 (blocking). Near-match pairs are not reported: case 1 of `_split_source_mismatches` joins only on equal ex_date, so AMZN
   massive 06-06 / yfinance 06-03 yields no row. Report SPLIT_SOURCE_MISMATCH for any massive/yfinance pair of the same symbol
   within ±3 days where ex_date differs OR |r_m/r_y − 1| > 0.001 (one row per pair; include both dates/ratios in the detail columns
   that exist on data_quality_breaks — check its DDL).
3 (blocking). The "mutation" test runs a hand-retyped round-5 SQL string. Delete it; every semantic test must extract SQL from
   silver/08 at test time. Mutation proofs (in /tmp copies, paste output): `WHERE rn = 1` → `WHERE 1=1` in `_resolved_splits`
   → a test FAILS (currently 8/8 survive — so add a fixture where dedupe matters on its own: two rows same (symbol, ex_date) from
   massive and yfinance, same day — without rn=1 the factor squares); removing ±3-day suppression → FAILS.
4 (blocking). Test data_quality_breaks output: run the real `_split_source_mismatches` (and the SPLIT_SINGLE_SOURCE CTE) in DuckDB
   on fixtures and assert exact rows: (a) AMZN 06-06/06-03 → one SPLIT_SOURCE_MISMATCH; (b) same day, ratio 20 vs 10 → one
   SPLIT_SOURCE_MISMATCH; (c) same day, same ratio → no row; (d) yfinance-only → one SPLIT_SINGLE_SOURCE; (e) massive-only → no row.
5. Non-blocking but do it: notebook-boundary leak tests must exercise the notebook's real catch/redact function (extract it into an
   importable helper the notebook calls), not a re-implementation; resume tests must call real code, not grep source text;
   in `both` mode skip an already-completed (symbol, source) and checkpoint failures under the adapter that failed.
6. Add duckdb to requirements (dev/test section, or requirements.txt) to match CI.
Acceptance: python -m pytest -q tests/bronze tests/silver tests/test_security.py — all pass except the 5 pre-existing
tests/bronze/test_refresh_bronze_cot.py::TestComputeReleaseTs failures (don't touch); pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) same.
.agents/mimo/VERDICT-corporate-actions-round7.md with counts + mutation outputs. Commit everything.
