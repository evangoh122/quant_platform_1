===VERDICT START===
# VERDICT: rag-coverage round 8a-2 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 8a-2

## Summary

Round 8a-2 fixed two of three blocking items correctly, but three defects remain. Item 2 (concrete
`SparkIngestLogReader` + `main()` wiring) is done and its resume/attempt logic is covered. Item 3 is only
two-thirds done: the acceptance-truncation and stale-cache guards are now genuinely killed by mutation, but
the history-overlap guard still survives (fixture `filingFrom` was moved `2020-01-01 → 2024-06-01`, which is
still `< start_date`, so the old bug is never exercised). Item 1 is half-done: production now reads
`numTargetRowsInserted` from the target table (correct), but `FakeDataWriter` was changed in the *wrong
direction* — it now reports distinct *accessions* (1) instead of inserted *rows* (50), so the exact
production/test divergence that round 8a blocking #1 flagged is re-introduced in inverted form, and the new
`test_merge_rerun_inserts_zero` bakes in `first == 1` instead of `50`. A new SQL-injection defect also landed
in `SparkIngestLogReader` (f-string value interpolation in WHERE filters).

## Blocking findings

1. **[tests/rag/test_sec_rag_ingest.py:182-191 + :1506] FakeDataWriter reports distinct accessions, not
   inserted rows — the 8a divergence is inverted, not fixed.** `append_bronze_rows` dedups by
   `accession_number` and returns `1` for a 50-chunk filing, but production `SparkDataWriter` reads
   `numTargetRowsInserted` from the Delta MERGE, which is `50` (all 50 chunks of a new accession are
   inserted; see `process_filing` emitting one bronze row per chunk at pipelines/sec_rag_ingest.py:880-905).
   `test_merge_rerun_inserts_zero` asserts `first == 1` ("1 new accession → 1 inserted"), directly
   contradicting the build request's explicit acceptance "50-chunk filing → rows_appended 50". Concrete
   failure: a 10-K producing 50 chunks logs `rows_appended=1`/`total_rows_appended=1` under the test double
   while production would log `50`, so any future assertion on exact row counts is wrong and round 8a
   blocking #1 is not actually resolved — the test double still does not mirror MERGE row semantics. The
   re-run→0 half is correct.

2. **[tests/rag/test_sec_rag_ingest.py:1629] history-overlap guard still does not fail on old code.** The
   fixture is `filingFrom="2024-06-01", filingTo="2024-12-31"` with `start_date="2024-09-01"`. The old
   `filingFrom < start_date` branch (`"2024-06-01" < "2024-09-01"` is True) still fetches the history file,
   so the overlap bug (`filingFrom >= start_date` skipped) is never exercised. Build request item 3 requires
   `filingFrom >= start_date` (e.g. `2024-10-01`); the chosen date is still below the cutoff. Proven by
   mutation below (revert → test still passes).

3. **[pipelines/sec_rag_ingest.py:1651,1668-1670] SparkIngestLogReader interpolates values into SQL WHERE
   clauses.** `read_succeeded_accessions` builds `WHERE run_id = '{run_id}'` and `read_max_attempt` builds
   `WHERE run_id = '{run_id}' AND ticker = '{ticker}' AND accession_number = '{accession_number}'` via
   f-string. This is a value-level f-string SQL filter, violating the role mandate "every query:
   parameterized; a single f-string SQL filter is a blocking defect" and the protocol hard rule
   "parameterized queries only". The idiomatic parameterized pattern already exists in this file
   (`SparkAccessionReader` uses `spark.table(...).filter(...)`). Rewrite with the DataFrame API
   (`F.col("run_id") == run_id`, etc.) so values are bound, not interpolated.

## Non-blocking notes

- **[pipelines/sec_rag_ingest.py:1579-1587]** The inserted-count fallback comment says "count rows that were
  NOT matched (new accessions)" but the code is `len(rows)` (counts *all* batch rows, overcounting when the
  batch mixes new and existing accessions). Fallback-only, so non-blocking, but the comment is inaccurate.
- **[pipelines/sec_rag_ingest.py:1580]** `DESCRIBE HISTORY {table} LIMIT 1` assumes the just-run MERGE is the
  latest history entry; under concurrent writers the latest entry may be another operation's metrics. Fine
  for the current single-writer pipeline, worth a comment/guard.
- **[tests/rag/test_sec_rag_ingest.py:1696-1727]** `test_stale_cache_used_on_network_failure` computes
  `result_fresh` (ttl=3600 call) but never asserts it; the inline comments claiming the first call "may fail"
  are wrong — the ttl=3600 call already returns the stale cache via the `ttl=0` fallback inside
  `load_company_tickers`, so only the `result_stale` assertion is meaningful. Harmless, but clean it up.
- **[tests/rag/test_sec_rag_ingest.py:1970-1988]** `test_main_wires_ingest_log_reader` monkeypatches
  `SparkIngestLogReader` to a `MagicMock`, so it verifies the parameter is *passed* but not that the concrete
  class is constructed. The `SparkIngestLogReader` unit tests assert only substring presence (`"run_id"`,
  `"succeeded"`) in the emitted SQL, not that pushed-down predicates actually filter.

## Verified items (request checklist)

1. **Inserted count (partial)** — dead `DESCRIBE HISTORY _merge_src` block removed; production reads
   `numTargetRowsInserted` from target-table history (correct). `FakeDataWriter` mirror is wrong (blocking
   #1). ✔ production / ✗ test double.
2. **Resume/attempt** — concrete `SparkIngestLogReader` with `read_succeeded_accessions`/`read_max_attempt`,
   pushed-down `run_id`/`ticker`/`accession_number` predicates, constructed in `main()` and passed to
   `run_ingest`; `main()` wiring test passes; `run_ingest` guards at :1240/:1264 are now live in production;
   resume-skip and `attempt = max + 1` covered by pre-existing fake-reader tests (killed in 8a). ✔ (except
   blocking #3 on SQL style).
3. **Three mutations** — acceptance-truncation and stale-cache guards now killed; history-overlap guard
   survives (blocking #2). 2/3 killed.

**Out of scope:** `git show 32548c1 --name-only` touches only `pipelines/sec_rag_ingest.py` and
`tests/rag/test_sec_rag_ingest.py`. No `build_sec_embeddings.py`/`hybrid_retriever.py`/`gold/07`/
`tools_retrieval.py` changes. ✔

**No tests deleted/weakened:** the test diff is add/strengthen only (the 19 removed lines are modified
fixtures/assertion bodies, not deletions). ✔

## Mutation results (revert each fix in a `/tmp/rc8a2` copy, run guard test)

| Mutation | Reverted fix | Result |
|---|---|---|
| history_overlap | overlap check → `filingFrom >= start_date` skip | **PASS (survived — weak)** `1 passed` |
| collect_truncation | `_collect_filings` max → min(len…len(acceptance)) | FAIL (killed) — `assert 0 == 1` |
| stale_cache | `sidecar.exists() and ttl > 0` → `sidecar.exists()` | FAIL (killed) — `SecClientError` raised |

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **608 passed, 36 skipped, 0 failed** (18.0s)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **448 passed, 19 skipped, 0 failed** (14.1s)
- `git show 32548c1 --name-only` → in-scope files only
- `git show 32548c1 -- tests` → add-only, no deletion/weakening
- Mutation proofs → 3 reverts, 2 killed / 1 survived (history_overlap; table above)
===VERDICT END===
