# VERDICT: rag-coverage-round12 — MiMo
**Status:** APPROVED
**Round:** 12

## Blocking findings
- None.

## Non-blocking notes
- `DataWriter` protocol return type corrected from `-> int` to `-> Optional[int]` to match production `SparkDataWriter` behavior (line 168).
- Thread-safe: the `None` propagation is idempotent — once `total_rows_appended` is set to `None`, subsequent `elif` guards prevent any `int +=` on it.
- Existing tests (770, 790, 835, 870, 1303, 2177, 2252) use `FakeDataWriter` which returns `int`, so they remain unaffected by the `Optional[int]` widening.

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q` → **673 passed, 36 skipped** (9 new tests added)
- New tests against pre-fix code (mutation copy `/tmp/ragcov-r12-pre`) → **5 FAILED, 4 PASSED** (red phase confirmed)
- Mutation test `test_mutation_skip_none_aggregation_fails` against pre-fix → **FAILED** (got `0` instead of `None`)
- Mutation copy saved: `/tmp/ragcov-r12-pre` (pre-fix), `/tmp/ragcov-r12-post` (post-fix)

## Changes made

### `pipelines/sec_rag_ingest.py`
1. `IngestResult.total_rows_appended: int = 0` → `Optional[int] = 0` (line 1099)
2. `DataWriter.append_bronze_rows` return type `-> int` → `-> Optional[int]` (line 168)
3. Threaded aggregation (line 1496): skip-None replaced with None-propagation — if `rows_appended is None`, set `total = None`; elif `total is not None`, accumulate (mirrors embeddings pattern)
4. Serial aggregation (line 1516): same None-propagation logic
5. Summary log (line 1529): `rows=%d` → `rows=%s` with ternary `"unknown" if None else value`

### `docs/SEC_RAG_COVERAGE_RUNBOOK.md`
6. Idempotency gate (line 154): added paragraph stating `rows=unknown` does NOT satisfy the gate; must be proven `0`; instructions to investigate `sec_ingest_log WHERE rows_appended IS NULL`.

### `tests/rag/test_sec_rag_ingest.py`
7. `TestTotalRowsAppendedAggregation` — 9 tests covering both serial and threaded modes:
   - `[None, None]` → `None` (serial + threaded)
   - `[3, None]` → `None` (serial + threaded)
   - `[0, 0]` → `0` (serial + threaded)
   - `[2, 5]` → `7` (serial + threaded)
   - Mutation guard: skip-None aggregation restored → FAILS