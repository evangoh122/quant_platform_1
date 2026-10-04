===VERDICT START===
# VERDICT: rag-kg-round9 — DeepSeek (checker)
Status: CHANGES_REQUESTED
Round: 9
Range: 3a85da8..HEAD (commits 4c7a833, 2f92f25, dfadfae)

## Blocking findings

1. [api/services/sec_knowledge_graph.py:168-204] Item #6 query path is NOT fixed —
   predicate pushdown was not implemented. `SparkGraphStore.iter_nodes()` selects the
   entire `gold_sec_kg_nodes` table with no `.where()` and no `.limit()`, then streams
   every row to the driver via `toLocalIterator()` (line 185). `iter_edges()` is the
   same (lines 206-237, `toLocalIterator` at 219). The query methods `get_fact` (:371),
   `facts_timeseries` (:473), and `risk_factors` (:536) all call `iter_nodes()` and
   apply ticker/metric/period/as-of filters **in Python after the full scan**. The build
   request (BUILD-rag-kg-round9.md item #6) explicitly required "push predicates
   (ticker/cik, concept, period, as-of) into the Spark/SQL filter and collect only the
   matching rows with a LIMIT", plus "Tests with fake Spark asserting the filter
   predicates and that collect() is not called on an unfiltered table (spy)". The
   round-9 change only swapped `collect()` → `toLocalIterator()`, which caps peak driver
   memory but does not reduce the scan. The CHECK request states this directly:
   "for QUERIES the predicates must be pushed into Spark with a LIMIT before collecting."
   No filter-predicate test and no collect-spy test were added. → A query for one ticker
   still pulls the whole node table to the driver.

## Non-blocking notes

2. [tests/rag/test_sec_knowledge_graph.py:2487-2502] Item #1 fix is correct but the
   requested TZ regression test was not written. grep confirms no `.timestamp()` on a
   naive datetime in sec_kg/, pipelines/build_sec_knowledge_graph.py, scripts/, or
   api/services/sec_knowledge_graph.py — the only `.timestamp()` in that file is
   api/services/sec_knowledge_graph.py:300 on `as_of` already passed through
   `ensure_utc()` (timezone-aware → correct). But the required `TZ=Asia/Singapore` test
   (monkeypatch `os.environ["TZ"]` + `time.tzset()`) does not exist:
   `test_naive_datetime_to_epoch_tz_dependent` is a placeholder that never changes
   process tz and asserts nothing about tz dependence. My mutation (restore naive
   `.timestamp()`) still fails 4 `TestPipelineValidation` tests, but via
   `AttributeError: '_FakeRow' object has no attribute 'accepted_ts'`, not via a
   TZ-specific assertion — the guard is incidental, not the requested proof.

3. [sec_kg/build.py:178-189] Item #3 Decimal dual tolerance is safe. Exact semantics:
   match requires `relative_ok = diff/max_abs < 0.0001` **AND** `absolute_ok = diff <= 0.5`.
   Two distinct integers always differ by ≥ 1 > 0.5, so no two different integers can
   match. Verified: 9007199254740992 vs 9007199254740993 → False; 100 vs 101 → False;
   1000000 vs "1.0 million" → False (no scale-word parsing — `_NUMBER_RE` extracts "1.0").
   Note: the docstring "274.3 million ↔ 274300000" overclaims a feature that does not
   exist; pre-existing, not a round-9 regression.

4. [pipelines/build_sec_knowledge_graph.py:217,224] Item #4 delete is unscoped but safe:
   `main()` (:278-302) exposes no ticker/partition args and `build()` reads the full
   silver universe, so there is no partial-rebuild path today. A future partial rebuild
   would wipe other tickers' rows. Deleted counts are not recorded in the manifest (no
   column exists; build request permits "otherwise log", but neither is currently logged).

5. [agent/tools_retrieval.py:271 vs 276-278] Item #5 implementation is correct — Pydantic
   validation raises before `_get_default_graph()`, so the backend is never invoked for a
   rejected ticker/oversized field. But tests use a 129-char metric (not the requested
   1,000,000-char) and do not explicitly assert "backend not called".

6. [api/services/sec_knowledge_graph.py:489-519] Item #2 correct. Mutation (drop dedupe →
   append every candidate) → `test_after_both_returns_only_latest` and
   `test_mutation_drop_dedupe_fails` both FAIL (2 failed). Note
   `test_between_returns_only_earlier` passes under mutation because only the earlier
   version is eligible at that as-of — expected.

7. Item #7 — no tests deleted/weakened. `git diff 3a85da8..HEAD -- tests` shows 0 removed
   `def test_`/`class Test` lines. The only deletions are fake-row
   `accepted_ts=datetime(...)` → `accepted_epoch=1700000000`; verified
   `datetime.fromtimestamp(1700000000, tz=timezone.utc)` == 2023-11-14 22:13:20+00:00,
   exactly the previous test timestamp, so test-data semantics are preserved.

## Counts (reproduced independently)

- `python3 -m pytest tests/rag -q` → **413 passed, 19 skipped, 0 failed**, 1 warning.
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **413 passed, 19 skipped, 0 failed**, 1 warning.

## Mutation proofs (fresh `/tmp/kg9-mut-*` copies, rerun by me)

- Mutation 1 — restore naive `.timestamp()` in pipelines/build_sec_knowledge_graph.py →
  **4 FAILED** (`TestPipelineValidation::{test_undocumented_rejection_raises_and_no_writes,
  test_documented_reasons_writes_after_validation, test_manifest_row_has_exact_counts,
  test_manifest_schema_explicit_9_columns}`), 409 passed. (via `_FakeRow` AttributeError,
  not a TZ assertion — see note 2.)
- Mutation 2 — drop `facts_timeseries` dedupe (append every candidate) → **2 FAILED**
  (`TestFactsTimeseriesRestatement::{test_after_both_returns_only_latest,
  test_mutation_drop_dedupe_fails}`), 411 passed.
- Mutation 3 — revert `_chunk_text_matches_value` Decimal→float → **1 FAILED**
  (`TestLosslessCitationComparison::test_large_integer_no_match`, assert True is False),
  412 passed.
- Mutation 4 — remove `.whenNotMatchedBySourceDelete()` → **2 FAILED**
  (`TestFullRebuildStaleRows::{test_merge_has_delete_clause,
  test_mutation_remove_delete_clause_fails}`), 411 passed.

## Checks run

- `git log --oneline -15` / `git status` → on `slice/rag-kg`, HEAD `dfadfae`, ahead of origin by 18.
- `git diff 3a85da8..HEAD --stat` → 8 files, +467/-41 (5 source, 2 test, 2 agent files).
- `git diff 3a85da8..HEAD -- tests | grep -cE '^\-.*(def test_|class Test)'` → 0.
- grep `.timestamp()` in sec_kg/, pipelines/, scripts/, api/services/sec_knowledge_graph.py → only
  api/services/sec_knowledge_graph.py:300 (aware datetime, correct).
- `python3 -m pytest tests/rag -q` → pass (413).
- pyspark-hidden shim run → pass (413).
- Decimal tolerance probes → 9007199254740992≠…993, 100≠101, "1.0 million"≠1000000 (all no-match).
- `config.tickers.get_all_ticker_symbols()` → 12350 tickers; "NVDA" in list, "ZZZZZZ" not in list.

## Conclusion

Items 2, 3, 4, 5, 7 are correctly fixed/verified, and all four mutation proofs fail as
required. Item #1's fix is correct but its TZ regression test was not implemented (the
requested `time.tzset` proof is absent). Item #6's **query path is not fixed**: the
required Spark predicate pushdown + LIMIT (with a filter/collect-spy test) was not done;
`iter_nodes()`/`iter_edges()` still full-scan the entire node/edge tables to the driver,
and `get_fact`/`facts_timeseries`/`risk_factors` filter in Python after the scan. The
build request explicitly required this, so CHANGES_REQUESTED for item #6 (and the item #1
TZ test).
===VERDICT END===
