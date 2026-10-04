===VERDICT START===
# VERDICT: rag-kg-round10b — DeepSeek (checker)
**Status:** APPROVED
**Round:** 10b

## Blocking findings

None. The round-10 blocker (TZ test did not exercise the pipeline) is resolved.

## Verification of the fix (round-10 blocker)

The new `TestPipelineEpochUnderClientTimezone` (tests/rag/test_sec_knowledge_graph.py:3314-3369)
does what the round-10 request required:

- `test_build_keeps_exact_epoch_under_singapore_tz` sets `TZ=Asia/Singapore` +
  `time.tzset()`, constructs `_FakeRow`s carrying **both** `accepted_epoch=1700000000`
  and `accepted_ts=naive_utc` (a naive `datetime(2023,11,14,22,13,20)`), then calls the
  **real** `pipelines.build_sec_knowledge_graph.build(fake_spark, ...)`.
- It monkeypatches only `pipeline_mod.build_graph` with a capture wrapper that records the
  `entities`/`corpus` args and delegates to the real `sec_kg.build.build_graph`, so the
  pipeline's own timestamp conversion path (the `select(..., F.unix_timestamp(...))` +
  `int(row.accepted_epoch)` loop) is exercised end-to-end.
- It asserts the exact epoch for **entities** (`epochs == [1700000000]`) and **chunks**
  (`chunk["accepted_epoch"] == 1700000000`).

Mutation proof (fresh `/tmp/kg10b-mut` copy): reverted the pipeline's select/loop lines
back to naive conversion —
`F.unix_timestamp("accepted_ts").alias("accepted_epoch")` → `"accepted_ts"` (lines 70, 90)
and `int(row.accepted_epoch)` → `int(row.accepted_ts.timestamp())` (lines 78, 99). Result:

```
FAILED tests/rag/test_sec_knowledge_graph.py::TestPipelineEpochUnderClientTimezone::test_build_keeps_exact_epoch_under_singapore_tz
E   AssertionError: entity accepted_epoch shifted under TZ=Asia/Singapore: [1699971200]
E   assert [1699971200] == [1700000000]
```

This is the **TZ assertion** (8-hour = 28800 s shift), not the incidental `AttributeError`
that masked the round-10 defect. The regression is now actually caught. ✓

## Non-blocking notes

1. [api/services/sec_knowledge_graph.py:474-480] `accepted_before` (as-of) is still applied
   **post-collect** on the per-node provenance array, not pushed into Spark `.where()`.
   **Acceptable**: the high-selectivity predicates (node_type, cik, ticker, concept,
   period_start, period_end — lines 435-456) ARE pushed, and a hard `.limit(limit)` is
   applied BEFORE `toLocalIterator()` (line 459). The as-of filter therefore refines a
   bounded candidate set (≤ `limit` rows in the driver), not a full-table scan. Pushing it
   would additionally require a per-array `F.filter` transform plus an empty-array skip
   (matching lines 477-479); correct and bounded as-is, so it remains non-blocking.

2. (carried over, unchanged) `find_edges_by_node_ids` is defined but has zero call sites;
   `deleted_nodes_est`/`deleted_edges_est` at pipelines/build_sec_knowledge_graph.py:257-258
   log the pre-existing row count, mislabeled as deletions. Neither is a blocker.

## Checks run

- `python3 -m pytest tests/rag/test_sec_knowledge_graph.py::TestPipelineEpochUnderClientTimezone -q`
  → **1 passed**.
- `python3 -m pytest tests/rag -q` → **428 passed, 19 skipped, 0 failed**, 1 warning
  (torch FutureWarning).
- `/tmp/kg10b-mut` mutation (naive `.timestamp()` revert) →
  `TestPipelineEpochUnderClientTimezone` **1 failed** with TZ assertion
  `[1699971200] == [1700000000]`; no `AttributeError`.
- `git log --oneline -10` → HEAD `447c24c` on `slice/rag-kg`, clean tree; fix commit
  `0f5c0c0` adds only `tests/rag/test_sec_knowledge_graph.py` (+59/-1).
===VERDICT END===
