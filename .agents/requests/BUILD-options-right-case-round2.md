# BUILD fix/options-right-case round 2 (builder: MiMo)

> CONTINUATION: your previous run timed out. Partial edits are committed as the latest "wip(options): round 2 partial" commit. Run `git show HEAD`, finish every item, run the mutation proof, write the verdict and commit. Do not start over.


IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch fix/options-right-case. Descriptive commits.
NEVER delete or weaken existing tests. Checker verdict: .agents/deepseek/VERDICT-options-right-case.md (CHANGES_REQUESTED).

1 (blocking). Revert the QUOTES path to its previous lowercase output: `_right_from_contract_type`
   (notebooks/refresh_bronze_options.py ~247-253) feeds `shape_quote_row` for bronze_options_quotes and must keep emitting
   'call'/'put' (the spec said do not change quotes; changing it would make bronze_options_quotes mixed-case with no backfill).
   Keep ONLY the day-agg path (parse_opra_symbol / _shape_day) emitting 'PUT'/'CALL'. Restore any quotes-path test
   expectations you changed to lowercase. Add a test asserting the quotes path emits lowercase and the day path uppercase.
2 (blocking). The DuckDB test's `_DAY_CTE` (tests/gold/test_options_right_case.py:49) is a retyped copy. Extract the `day` CTE
   text from gold/02_gold_options_features.sql at test time (parse between `WITH day AS (` and the matching close paren; the
   only allowed shim is replacing the convert_timezone(...)+make_interval(...) availability expression with a literal, and
   the `universe` subquery with a fixture table — document both). Delete the tautological `test_mutation_proof_revert_upper_fails`
   (:117) — it's replaced by the real extraction (this deletion is allowed). Mutation proof (in /tmp copy, paste output): revert
   one UPPER in gold/02 → the DuckDB test FAILS.
3. Widen the repo-wide case-sensitivity regex test to .py files too (pipelines/, ml/, strategies/, api/, analytics_nl/,
   notebooks/), and silver/gold/pipelines .sql; exclude tests/ and .agents/.
4. Maintenance SQL: backtick-quote `right`; trailing newline; header note that this is a deliberate one-off exception to
   docs/BRONZE_REFRESH_PLAN.md:13 ("no Bronze UPDATE"), with the reason.
Acceptance: python -m pytest -q tests/gold tests/bronze tests/silver — all pass except the pre-existing pytz ModuleNotFoundError
failures (7, identical on base bbe7147; do not try to fix those). .agents/mimo/VERDICT-options-right-case-round2.md. Commit everything.
