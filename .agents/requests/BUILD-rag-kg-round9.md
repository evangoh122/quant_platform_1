# BUILD rag-kg round 9 (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Commit after each item with descriptive messages.
NEVER delete or weaken existing tests. Codex review: .agents/codex/VERDICT-rag-kg-review2.md (CHANGES_REQUESTED, 4×P1, 2×P2).

## 1 (P1). Driver-timezone-dependent timestamps
pipelines/build_sec_knowledge_graph.py:59, :73 call `.timestamp()` on Spark-returned naive datetimes. Databricks Connect returns
naive datetimes in the CLIENT's local tz (here UTC+8), so accepted_ts/valid_from shift 8h earlier → facts visible before acceptance.
Fix (the pattern used elsewhere in this repo): select `unix_timestamp(col)` (or `CAST(col AS BIGINT)`/epoch seconds) in Spark and
convert with `datetime.fromtimestamp(epoch, tz=timezone.utc)`; never call `.timestamp()` on a naive datetime. grep the lane
(sec_kg/, pipelines/, api/services/sec_knowledge_graph.py, scripts/) for every `.timestamp()` / naive datetime from Spark.
Test: run the conversion under `TZ=Asia/Singapore` (monkeypatch os.environ["TZ"] + time.tzset()) and assert UTC epoch unchanged.
Mutation proof: restore `.timestamp()` on naive → test FAILS.

## 2 (P1). facts_timeseries must apply restatement selection
api/services/sec_knowledge_graph.py:464-498 returns all fact versions. After PIT filtering, keep only the latest eligible version
per series (cik, concept, period_start, period_end, unit) ordered by (accepted_ts, accession). Test: two versions 100 (earlier) and
110 (restated) → as-of after both returns only 110; as-of between returns only 100. Mutation: drop the dedupe → FAILS.

## 3 (P1). Lossless citation value comparison
sec_kg/build.py:127-175 converts to float; 9007199254740992 vs 9007199254740993 match. Use decimal.Decimal end-to-end (parse text
numbers with commas/parentheses/negatives/scale words exactly as now, but into Decimal). Test with that pair → no match; existing
matching cases still match. Mutation: revert to float → FAILS.

## 4 (P1). Full rebuild leaves stale rows
pipelines/build_sec_knowledge_graph.py:199-214 MERGE only updates/inserts. For a full rebuild, delete rows whose IDs are absent from
the current build (MERGE ... WHEN NOT MATCHED BY SOURCE THEN DELETE, scoped to the rebuilt universe/partitions), or overwrite the
affected partitions atomically. Record deleted counts in the build-run manifest only if a column exists for it; otherwise log.
Test with fake Spark: a node present in run 1 and absent in run 2 is deleted (assert the DELETE clause / overwrite is issued with the
right scope). Mutation: remove the delete clause → FAILS.

## 5 (P2). Agent tool inputs bounded + allow-listed
agent/tools_retrieval.py:223-226 has no max length for `metric`/`period`; :251-254 uses normalize_symbol (regex only,
agent/guardrails.py:43-53) without the configured allow-list. Add max lengths (e.g. metric ≤ 128, period ≤ 32 or the enum/regex the
spec uses) and check the ticker against the configured allow-list (universe). Tests: non-allow-listed ticker rejected before backend;
1,000,000-char metric rejected before backend (assert backend not called).

## 6 (P2). No driver-wide collects
pipelines/build_sec_knowledge_graph.py:48-67 collects all source chunks/entities; api/services/sec_knowledge_graph.py:168-203 collects
every graph node per query. Build: process via Spark (mapInPandas / groupBy-applyInPandas per accession, or iterate with
toLocalIterator in bounded batches) — no collect() of whole tables. Query: push predicates (ticker/cik, concept, period, as-of) into
the Spark/SQL filter and collect only the matching rows with a LIMIT. Tests with fake Spark asserting the filter predicates and that
collect() is not called on an unfiltered table (spy).

## Acceptance
python -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps)
all pass. .agents/mimo/VERDICT-rag-kg-round9.md with counts + every mutation output. Commit everything.
