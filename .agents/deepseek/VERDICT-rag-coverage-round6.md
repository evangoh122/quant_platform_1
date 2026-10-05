===VERDICT START===
# VERDICT: rag-coverage-round6 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 6

## Blocking findings

1. **Item 4 — COT cross-suite failure is neither fixed nor correctly root-caused; acceptance criterion "COMBINED all pass" is unmet.**
   `python3 -m pytest tests/rag tests/bronze -q` → **6 failed**, 582 passed, 29 skipped.
   The 6 failures are `tests/bronze/test_refresh_bronze_cot.py`: `TestNaturalKey::{test_anti_join_filters_existing_keys, test_anti_join_deduplicates_incoming, test_com_fin_and_fut_fin_separate_keys}` and `TestIdempotency::{test_detect_revision_conflicts, test_detect_revision_conflicts_zero, test_to_bronze_adds_derived_columns}`.
   → The MiMo verdict's stated root cause ("3 collection errors in `test_chat_engine.py`/`test_graph_rag_engine.py`/`test_langgraph_engine.py` importing `api.db.database`, aborting before any tests run") is **factually wrong**. Verified: those 3 files are *skipped*, not collected-with-error (`pytest tests/rag/test_chat_engine.py tests/rag/test_graph_rag_engine.py tests/rag/test_langgraph_engine.py -q` → `3 skipped`; `openai` is not installed → `pytest.importorskip("openai")` at `test_chat_engine.py:7`). There is no abort and no collection error.

2. **Actual root cause (leak) — `tests/rag/test_sec_rag_ingest.py:26-27`.** Module-level `sys.modules.setdefault("databricks", MagicMock())` / `sys.modules.setdefault("databricks.connect", MagicMock())` run at import (collection) time and permanently pollute `sys.modules` for the whole pytest process. The session-scoped `spark` fixture in `tests/bronze/test_refresh_bronze_cot.py:43-66` does `from databricks.connect import DatabricksSession` first; with the mock installed this returns a `MagicMock`, so `DatabricksSession.builder.serverless(True).getOrCreate()` yields a `MagicMock` (no exception) and the fixture returns that instead of a real local SparkSession. Consequence (pasted): `assert 'report_date' in <MagicMock name='mock.DatabricksSession.builder.serverless().getOrCreate().createDataFrame().withColumn()....columns'>` at `test_refresh_bronze_cot.py:413`.
   Proof of minimal reproducer: `pytest tests/rag/test_sec_rag_ingest.py tests/bronze/test_refresh_bronze_cot.py -q` → same 6 failures (117 passed, 6 failed). `tests/bronze` alone → 167 passed, 10 skipped (real local Spark). The leak line pre-dates 702e617 (present at `702e617:tests/rag/test_sec_rag_ingest.py:26-27`), so it is not a round-6 regression, but it **is this feature's file** and item 4 explicitly asked to "fix the isolation … not the assertions". The fix is small (fixture-scoped monkeypatch of `databricks.connect` instead of module-level `setdefault`, or a type guard in the `spark` fixture). Documenting a *wrong* root cause does not satisfy item 4, and the hard acceptance criterion is not met.

## Non-blocking notes / passed items

3. **Item 1 (notebook → thin wrapper) — PASS.** `notebooks/02_ingest_sec_edgar.py` is 74 lines; `globals().get("dbutils")` at :38, argv builder :36-72, `main(_build_argv())` at :75, header cites `d0d063f` at :12. Grep: 0 × "User-Agent", 0 × "requests", 0 × "BeautifulSoup". `pipelines/sec_rag_ingest.py:1363` `main(argv: Optional[List[str]] = None)` → `parser.parse_args(argv)` at :1377. `docs/MERGE_PLAN.md:38` and `README.md` updated to point at the `sec_rag_ingest` job.

4. **Item 2 (CIK mapping log writer) — PASS.** `pipelines/sec_rag_ingest.py:1295-1358` buffers entries in `append_mapping_log` (:1315-1329) and writes once in `flush` (:1331-1358). Explicit `StructType` :1342-1351 with `cik` nullable (:1346 `StructField("cik", StringType(), True)`). Schema matches `docs/DATA_SCHEMAS.md:495-502` exactly (ticker NOT NULL, lookup_symbol/cik/reason/mapped_ts/run_id nullable, status NOT NULL). `run_ingest` calls `flush` once at :1031. `Protocol` gained `flush` (:164-166).

5. **Item 3 (main() write-mode test content) — PASS.** `tests/rag/test_sec_rag_ingest.py:1325` `test_main_write_mode_writes_filings_and_log` now asserts exact ticker/cik/accession/form/accepted_ts, chunk_ids `[1,1,1,1]`, sections `["item1_business","item1a_risk_factors","item7_mda","item8_financial_statements"]`, and CIK mapping log entry (ticker NVDA, cik 0001045810, status mapped, `flush_count == 1`).

6. **No test deleted/weakened.** `git diff 702e617..HEAD -- tests` → only `tests/rag/test_sec_rag_ingest.py` changed (388 insertions, 6 deletions). The 6 deletions are 3 comment lines, a `lambda: FakeCikMappingLogWriter()` → `lambda: cik_log` strengthening, a closing paren, and `assert writer.total_rows > 0` replaced by the strictly stronger `assert len(all_rows) > 0` plus exact-content assertions. No assertion was dropped.

## Mutation proofs (re-run by DeepSeek in /tmp)

- **Drop schema** (removed `schema=…` from `createDataFrame` in `flush`, `/tmp/rag-coverage-round6-mut-1`):
  `pytest tests/rag/test_sec_rag_ingest.py::TestSparkCikMappingLogWriterSchema::test_schema_matches_documented_schema` → **FAILED** (`AssertionError: Mutation: no schema passed to createDataFrame … assert None is not None`, test line 1002). ✔
- **Per-ticker writes** (moved `createDataFrame`+`saveAsTable` into `append_mapping_log`, `/tmp/rag-coverage-round6-mut-2`):
  `pytest …::TestSparkCikMappingLogWriterSchema::test_batch_single_write_call` → **FAILED** (`AssertionError: Expected 1 createDataFrame call for 5 entries, got 5. Mutation: per-ticker writes would call createDataFrame 5 times.`, test line 1079). ✔

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q` → 6 failed, 582 passed, 29 skipped (FAIL — acceptance not met)
- `python3 -m pytest tests/bronze -q` → 167 passed, 10 skipped (pass)
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py tests/bronze/test_refresh_bronze_cot.py -q` → 6 failed, 117 passed (reproducer)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → 421 passed, 19 skipped (pass)
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → 82 passed (pass)
- `python3 -m pytest tests/rag/test_chat_engine.py tests/rag/test_graph_rag_engine.py tests/rag/test_langgraph_engine.py -q` → 3 skipped (not collection errors)
- `git diff 702e617..HEAD -- tests` → no deleted/weakened test (see finding 6)

## Required for APPROVED
- Fix the `tests/rag/test_sec_rag_ingest.py:26-27` module-level `databricks`/`databricks.connect` `MagicMock` leak (monkeypatch fixture scoped to the tests that need it, or guard the `spark` fixture in `test_refresh_bronze_cot.py` so a `MagicMock` session is not yielded), so that `python -m pytest tests/rag tests/bronze -q` (COMBINED) passes.
- Correct the MiMo verdict's item-4 root-cause note (it currently states a false "3 collection errors abort the run" cause).
===VERDICT END===
