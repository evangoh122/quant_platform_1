# BUILD nl1 round 13 (builder: MiMo) — fix two vacuous tests + enforce status enum

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Descriptive commits. NEVER delete or weaken existing tests.
DeepSeek verdict: .agents/deepseek/VERDICT-nl1-round12.md. The DDL itself is correct; the TESTS can't detect regressions.

1 (blocking). tests/analytics_nl/test_ddl.py:340 `_has_as_of_filter_before_window`: the last CTE's body swallows the final SELECT, so a filter
   moved AFTER the window (into the final WHERE) still passes. Parse properly: split each view into its CTE list and the final SELECT
   (track parenthesis depth; do not regex-slice to end of string). Assert: some CTE that is read by the windowed/aggregating CTE (directly or
   transitively) contains `information_available_ts <= :as_of`, and the window/aggregate CTE itself does not read the unfiltered base table.
   Mutation proof (in /tmp copy, paste output): in serve_options_metrics_v1 remove the as_of_filtered WHERE and add the filter to the final
   `WHERE rn = 1` → test FAILS. Repeat for one other view.
2 (blocking). tests/analytics_nl/test_source_schema.py:216 `_extract_view_select_columns` never matches because `SELECT` sits alone on its line
   (regex `^\s*SELECT\s` fails after strip). It returns [] for every view and the registry test skips everything (:256 `if not view_cols: continue`).
   Fix the parser (handle SELECT alone on a line, aliases `AS x`, `t.col`, functions with commas inside parentheses), and make an EMPTY
   extraction a test FAILURE (never `continue`). Add a test asserting the extracted column set for serve_daily_prices_v1 equals an explicit
   expected set. Mutation proof: rename close_price → close_price_bogus in one registry output_field → FAILS.
3. Enforce the status enum: the aggregate `status` output field must be bound to CoverageStatus (enum in the contract/registry schema), and
   agg_value nullable only when status == INSUFFICIENT_DATA (model validator). Remove the unused import if it stays unused. Tests for both.
4. Relative performance DDL: guard `return_1d > -1` (or GREATEST(1 + r, tiny)) before LN, and document the assumption in the DDL comment.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps);
python3 -m analytics_nl.export_schemas --check. .agents/mimo/VERDICT-nl1-round13.md with counts + mutation outputs. Commit everything.
