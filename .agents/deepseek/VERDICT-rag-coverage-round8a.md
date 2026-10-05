===VERDICT START===
# VERDICT: rag-coverage round 8a — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 8a

## Summary

All six fixes from `.agents/codex/VERDICT-rag-coverage-review.md` (findings 1–6) are implemented in the
right files (`pipelines/sec_rag_ingest.py`, `api/services/xbrl_client.py`, `docs/DATA_SCHEMAS.md`) and the
full suite is green. However, three things block approval: (a) the "actual inserted count" in the bronze
writer is not actually reported, (b) finding 6's resume + attempt logic has no production implementation and
is never wired in `main()`, and (c) three of the new "guard" tests do **not** fail on the old code, violating
the build request's explicit "each fix needs a test that FAILS on the old code" requirement (proven by
mutation below).

## Blocking findings

1. **[pipelines/sec_rag_ingest.py:1577] "actual inserted count" is not reported — `len(batch_accessions)`
   counts distinct accessions, not inserted rows.** `append_bronze_rows` is called once per filing with
   `rows` = all chunks for that single accession, so `batch_accessions` always has exactly 1 key and
   `inserted` is always `1` regardless of chunk count. The `DESCRIBE HISTORY _merge_src LIMIT 1` block
   (lines 1578–1583) is dead code (a temp view has no history; the comment admits it). The test double
   `FakeDataWriter` returns `len(rows)`, so the tests assert the *row* count while production reports
   *1*, hiding the divergence. Concrete failure: a 10-K producing 50 chunks logs `rows_appended=1` /
   `total_rows_appended=1` (log line `rows=%d` at :1430), and a MERGE re-run inside the writer still
   returns a positive count instead of 0.

2. **[pipelines/sec_rag_ingest.py:1690 + :177] finding 6 resume/attempt is not functional in production.**
   `IngestLogReader` exists only as a `Protocol` (:177); there is no concrete `SparkIngestLogReader` anywhere
   in the repo (grep for `read_succeeded_accessions`/`read_max_attempt`/`SparkIngestLogReader` returns only
   the Protocol + test fakes). `main()` (:1712–1736) constructs `universe_reader`, `accession_reader`,
   `data_writer`, `log_writer`, `cik_mapping_log_writer` but never an `ingest_log_reader`, so the guards
   `if ingest_log_reader is not None` at :1240 and :1264 are always `False` in production. Concrete failure:
   a crashed-and-resumed run re-processes already-succeeded accessions (wasted SEC quota, duplicate
   `succeeded` log rows) and `attempt` is always `1`, so the two sub-requirements
   "attempt = previous attempts + 1 (read sec_ingest_log)" and "resume skips succeeded accessions from the
   log" are only satisfied in the injected-fake test path, not in the shipped pipeline.

3. **Three new guard tests do not fail on the old code (mutation survived).** The build request requires
   "each fix needs a test that FAILS on the old code"; three of the new tests pass identically against the
   pre-fix source:
   - **[tests/rag/test_sec_rag_ingest.py:1594] `test_history_overlap_uses_filing_to`** — fixture
     `filingFrom="2020-01-01"` is already `< start_date`, so the old `filingFrom < start_date` branch also
     fetches the history file; the overlap bug (`filingFrom >= start_date` skipped) is never exercised.
   - **[tests/rag/test_sec_rag_ingest.py:1631] `test_missing_acceptance_datetime_not_dropped`** — the
     `acceptanceDateTime` array is `[None]` (length 1, equal to the other arrays), so the old
     `n = min(len(forms)…len(acceptance))` does not truncate; the fix (min→max + per-index guards) is not
     actually guarded.
   - **[tests/rag/test_sec_rag_ingest.py:1671] `test_stale_cache_used_on_network_failure`** — the cache
     fixture has no `.meta` sidecar, so `_try_load_cache` returns the file in both old and new code; the
     `ttl=0` stale-sidecar regression (`if sidecar.exists()` vs `if sidecar.exists() and ttl > 0`) is not
     exercised.

## Non-blocking notes

- **[tests/rag/test_sec_rag_ingest.py:1479] `test_merge_not_append` does not verify MERGE.** It drives
  `FakeDataWriter`, not `SparkDataWriter`, so no test asserts the emitted SQL is `MERGE` (vs append) or that
  a re-run inserts 0 at the writer level. The `SparkDataWriter` MERGE path is only reached by
  `test_batch_ownership_conflict_raises`, which raises before any `spark.sql` call, so the MERGE string and
  the pre-MERGE existing-conflict query are unasserted.
- **[tests/rag/test_sec_rag_ingest.py:1549] `test_epoch_under_singapore_tz` does not set `TZ`.** It never
  calls `time.tzset()` with `Asia/Singapore`, so it cannot reproduce the UTC+8 shift by itself; the real
  guard is `test_tz_aware_utc` (which is correctly killed by the naive-datetime mutation). Recommend either
  making the test actually set `TZ` or renaming it.
- **Global limiter clock capture:** `get_global_limiter()` pins the *first* clock/`max_rps` into the
  process-wide singleton; a test-injected `FakeClock` from an early `run_ingest` call is retained by later
  tests. Harmless today (suite green) but fragile for future test ordering.

## Verified items (request checklist)

1. **Bronze write** — explicit `StructType` (17 fields, `raw_payload` nullable `StringType`) passed to
   `createDataFrame`; `MERGE INTO … ON accession_number WHEN NOT MATCHED THEN INSERT *` (not append); batch
   CIK-conflict detection; pre-MERGE existing-table conflict query. Re-run dedup at DB level is correct; the
   *reported* count is not (blocking #1).
2. **UTC** — `parse_sec_timestamp` returns tz-aware UTC; epoch `1740076200` preserved (test `test_epoch_equality`
   asserts `== 1740076200`). ✔
3. **Discovery** — exhausted submissions now raise `SecClientError` (kill-confirmed); `run_ingest` records
   `failed`/`discovery_failed` per ticker. Overlap and truncation fixes are correct in code but their guard
   tests are weak (blocking #3).
4. **CIK** — `build_cik_map` emits `ambiguous` for duplicate-ticker/different-CIK (kill-confirmed);
   `ambiguous` added to `docs/DATA_SCHEMAS.md:499`. `dry_run` skips cache write (kill-confirmed). Stale-cache
   `ttl=0` fix correct but unguarded (blocking #3).
5. **Fair access** — `get_global_limiter()` singleton (kill-confirmed); `xbrl_client` now uses it; HTTP-date
   `Retry-After` via `parsedate_to_datetime` (kill-confirmed). ✔
6. **Resume + workers** — `max_workers` drives a bounded `ThreadPoolExecutor`; `in_progress` persisted before
   work; ownership conflict records `failed` then raises; attempt increment + resume-skip logic present and
   unit-tested (kill-confirmed) but not wired to production (blocking #2).

**Out of scope:** `git diff 640f64e..HEAD --name-only` touches only `pipelines/sec_rag_ingest.py`,
`api/services/xbrl_client.py`, `docs/DATA_SCHEMAS.md`, `tests/rag/test_sec_rag_ingest.py`, plus two
`.agents/` docs. `build_sec_embeddings.py`, `hybrid_retriever.py`, `gold/07`, `tools_retrieval.py` were NOT
touched (round 8b scope respected). ✔

**No tests deleted/weakened:** `git diff 640f64e..HEAD -- tests` is add-only on `test_sec_rag_ingest.py`
(+428/−10; the 10 removals are tz-aware assertion *strengthenings*, e.g. `tzinfo is None` →
`tzinfo == timezone.utc` + `epoch == 1740076200`). ✔

## Mutation results (revert each fix in a `/tmp/rc8a-mut-*` copy, run guard test)

| Mutation | Reverted fix | Result |
|---|---|---|
| item1_batch_conflict | batch CIK-conflict raise in `SparkDataWriter` | FAIL (killed) — "DID NOT RAISE AccessionOwnershipConflict" |
| item2_naive_ts | `parse_sec_timestamp` → naive UTC | FAIL (killed) — `test_tz_aware_utc` + `test_epoch_equality` |
| item3_exhausted | `discover_filings` silent `return []` on error | FAIL (killed) — "DID NOT RAISE SecClientError" |
| item3_collect | `_collect_filings` min→max + per-index guards | **PASS (survived — weak)** |
| item3_history_overlap | overlap check → `filingFrom < start_date` | **PASS (survived — weak)** |
| item4_ambiguous | `ambiguous` branch → always mapped | FAIL (killed) — status `mapped` not `ambiguous` |
| item4_dryrun | `if cache_path and not dry_run` → `if cache_path` | FAIL (killed) — cache file written |
| item4_stalecache | `sidecar.exists() and ttl > 0` → `sidecar.exists()` | **PASS (survived — weak)** |
| item5_httpdate | HTTP-date parse removed | FAIL (killed) — returned `None` |
| item5_singleton | `get_global_limiter` always new instance | FAIL (killed) — `l1 is not l2` |
| item6_resume | resume skip disabled (`if False`) | FAIL (killed) — `skipped_existing_count=0` |
| item6_attempt | attempt pinned to `1` | FAIL (killed) — `attempt=1` not `4` |

Killed 9/12. The three survivors correspond to the weak guards in blocking #3.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **603 passed, 36 skipped, 0 failed** (13.9s)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **443 passed, 19 skipped, 0 failed** (13.1s)
- `git diff 640f64e..HEAD -- tests` → add-only, no deletion/weakening (see above)
- `git diff 640f64e..HEAD --name-only` → out-of-scope files untouched
- Mutation proofs → 12 reverts, 9 killed / 3 survived (table above)
===VERDICT END===
