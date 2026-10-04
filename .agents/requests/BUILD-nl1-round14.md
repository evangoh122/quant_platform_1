# BUILD nl1 round 14 (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Commit after each item, descriptive messages.
NEVER delete or weaken existing tests EXCEPT tests/analytics_nl/test_policy.py:982, which codifies wrong behaviour (item 2) — change it and say so.
Codex re-review: .agents/codex/VERDICT-nl1-review2.md (3 High, 1 Medium). Each fix needs a test that kills the named mutation (paste outputs).

1 (High). Output availability = MAX over ALL contributing rows. docs/NL1_PROPOSED_SERVING_VIEWS.md:166 joins adj.return_1d without its availability;
   rolling metrics (:181-224) keep only the current row's timestamp; relative cumulative windows (:330-366) the same. For every windowed/joined
   metric, carry each input's information_available_ts and output MAX(...) OVER the same window (and GREATEST across joined sides).
   Contract test: parse the DDL and assert every output information_available_ts is a window MAX / GREATEST over all inputs. Mutations →
   FAIL: (a) remove the benchmark availability from the final GREATEST; (b) replace a window MAX(information_available_ts) with the current row's.
2 (High). Sparse-data coverage for ALL four operations (aggregate, trend, compare, rank), not just aggregate (analytics_nl/policy.py:253).
   Registry trend/compare/rank entries (semantic_registry_v1.yaml:650, :673, :698) gain sample_count, coverage_ratio, status. Probe: IV with
   12/19,390 coverage → INSUFFICIENT_DATA for trend, compare, rank, aggregate; put_call_ratio → allowed. Fix test_policy.py:982.
   Mutation: restrict enforcement to aggregate again → FAILS.
3 (High). Relative performance over the REQUESTED window: add a :start_date bound to the inputs (alongside :as_of) and compute cumulative returns
   from start_date (window anchored at start_date, not UNBOUNDED inception). Test the semantics: a contract/DuckDB test (extract the view SQL,
   run on a fixture with returns before and inside the window) → cumulative = product over the window only. Mutation: drop the start bound → FAILS.
4 (Medium). tests/analytics_nl/test_source_schema.py:334-345 still unions parsed view columns with source_schemas-derived columns. Check registry
   output fields against the parsed VIEW columns ONLY. Mutation: rename close_price → close_price_bogus in the bounded-bars DDL (both variants)
   only → FAILS.
5. ≤−100% returns: replace GREATEST(1 + return_1d, 1e-10) with explicit anomaly propagation — if any return in the window is ≤ −1 or NULL-invalid,
   the cumulative result is NULL and a status/flag (e.g. invalid_return) is set; do it with a window COUNT/BOOL_OR of invalid rows, not CASE inside
   SUM (SUM skips NULL). Test with a fixture containing a −100% day.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps);
python3 -m analytics_nl.export_schemas --check. .agents/mimo/VERDICT-nl1-round14.md with counts + mutation outputs. Commit everything.
