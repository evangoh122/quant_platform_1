# BUILD nl1 round 16 (builder: MiMo; checker: DeepSeek; reviewer: Codex / stopgap Sonnet)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Commit after each item, descriptive messages.
NEVER delete or weaken existing tests. Reviewer verdict: .agents/reviewer/VERDICT-nl1-contracts-r3.md (2 High, 5 Medium).
Every test-strengthening item needs a mutation proof in a copy made with `git archive HEAD | tar -x -C /tmp/<dir>` (paste output).

1 (High). test_ddl.py:415 and :776 only check strings / iterate GREATEST args — a final SELECT with NO GREATEST makes zero assertions. For every
   view, REQUIRE the output information_available_ts to be a GREATEST/MAX expression covering every input that contributes (resolve via the CTE
   chain) and FAIL if it's missing. Mutation: remove the benchmark availability from serve_relative_performance_v1's final GREATEST → FAILS;
   replace the whole GREATEST with a single column → FAILS.
2 (High). test_ddl.py:540 checks substrings only for the ≤−100% handling. Test the semantics: extract the relative-performance SQL and run it in
   DuckDB (documented minimal shim only) on a fixture containing a −100% day → cumulative is NULL and status = invalid_return; a normal window →
   numeric value and normal status. Mutations: replace the NULL arm with a computed value → FAILS; disable the invalid_return status → FAILS.
3 (Medium). momentum_20d (LAG(close, 20)) has no availability term in the final GREATEST → add MAX availability over the same 21-row span; and in
   adjusted mode the LAG counts rows AFTER the null-return filter (so "20" spans more than 20 trading days) → compute LAG on the full date-ordered
   series, then apply the filter, and document.
4 (Medium). Bronze fallback views don't filter ingest_ts <= :as_of → late backfills leak into as-of queries. Add the ingest_ts bound to every bronze
   fallback input. Test.
5 (Medium). bounded-bars suspected_split LAG runs before the rn=1 dedup → dedup first, then LAG. Test with a duplicated row fixture (DuckDB).
6 (Medium). Ticker/Index/Sector validators use re.match with `$` → "AAPL\n", "SPY\n", "tech\n" accepted. Use re.fullmatch (or \Z) everywhere
   (grep analytics_nl for re.match/`$` patterns). Tests for trailing newline on each. Regenerate schemas if patterns change.
7 (Medium). policy.py skips the coverage check when coverage_stats is missing → IV query with no stats accepted. Fail closed: no stats for a metric
   whose registry coverage is not "full" → INSUFFICIENT_DATA (or REJECT with a clear code). Tighten the 0.001 threshold to a documented, configurable
   default (e.g. 0.5 for snapshot_only metrics) and test both paths.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps);
python3 -m analytics_nl.export_schemas --check. .agents/mimo/VERDICT-nl1-round16.md with counts + all mutation outputs. Commit everything.
