# BUILD nl1 round 17 (builder: MiMo) — tests must run the PRODUCTION DDL

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Descriptive commits. NEVER delete or weaken tests
(hard-coded SQL copies you replace may be deleted — list them). DeepSeek verdict: .agents/deepseek/VERDICT-nl1-round16.md (3 not closed).

HARD RULE: NO SQL string may be hand-written in a test to stand in for a view. Every semantic test must obtain the view SQL from
docs/NL1_PROPOSED_SERVING_VIEWS.md at test time.

1. Add a shared test helper `extract_view_sql(view_name, variant=None)` (tests/analytics_nl/_ddl_extract.py) that parses the markdown, finds the
   ```sql block(s) defining `CREATE ... VIEW <view_name>` (adjusted vs fallback variants if both exist), and returns the SQL. Plus a minimal,
   documented `to_duckdb(sql, params)` shim (named-parameter substitution for :as_of/:start_date/:benchmark, catalog prefix stripping, and only
   the specific Databricks-only functions that DuckDB lacks — list each). Test the helper itself.
2. Replace TestRelativePerformanceDuckDB._RELPERF_SQL (test_ddl.py ~1079) with extract_view_sql("serve_relative_performance_v1"). DeepSeek's
   mutations against the DOC must now FAIL: `THEN NULL` → `THEN -0.99`; `WHEN e.has_invalid_return OR b.has_invalid_bench THEN 'invalid_return'`
   → `WHEN FALSE ...`.
3. Momentum: a DuckDB test on the extracted serve_daily_equity_metrics_v1 (both variants) asserting (a) output availability changes when a late
   revision of the t−20 bar has a later information_available_ts, and (b) LAG(close, 20) spans 20 trading rows of the full series (fixture with a
   NULL-return day inside the window). Also make test_output_availability_is_window_max require EVERY availability column defined in the CTE chain
   to appear in the final GREATEST. Mutations: remove momentum_20d_info_ts from the final GREATEST → FAILS; add `WHERE return_1d IS NOT NULL` to
   with_momentum → FAILS.
4. Bounded bars: replace _DEDUP_THEN_LAG_SQL/_LAG_BEFORE_DEDUP_SQL (test_ddl.py ~1275) with the extracted serve_bounded_daily_bars_v1 run on a
   duplicated-row fixture. Mutation: remove `WHERE rn = 1` from with_splits in the DOC → FAILS.
Prove every mutation by editing the DOC in a copy made with `git archive HEAD | tar -x -C /tmp/<dir>` and paste the failing output.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps);
python3 -m analytics_nl.export_schemas --check. .agents/mimo/VERDICT-nl1-round17.md. Commit everything.
