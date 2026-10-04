# VERDICT: rag-databricks-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none)

## Non-blocking notes
- Removed unused `import sys` from `build_sec_embeddings.py`.
- Renamed return key `second_run_rows` → `rows_already_embedded` to reflect the semantic change (measured count of already-embedded chunks, not a second-run zero-marker).
- The existing `test_second_run_writes_zero_rows` test was passing vacuously due to MagicMock closure variable capture — all lambdas shared the last loop value. Fixed with `lambda self, k, cid=cid: cid` default-arg pattern across all 4 embedding tests.

## Defects fixed
1. **CREATE TABLE IF NOT EXISTS** — `_ensure_table(spark)` called before MERGE creates `gold_sec_chunk_embeddings` with the full schema: `chunk_id STRING, accession_number STRING, ticker STRING, accepted_ts TIMESTAMP, embedding ARRAY<FLOAT>, embedding_model STRING, embedded_ts TIMESTAMP`.
2. **Real idempotency count** — `rows_already_embedded = len(all_rows) - len(new_rows)` computed from actual set difference, no longer hard-coded to 0.
3. **Metadata columns** — `accession_number`, `ticker`, `accepted_ts` now read from source table and included in MERGE tuples and DataFrame schema.

## Checks run
- `python -m pytest tests/rag/test_hybrid_retriever.py -v` → **28 passed**, 0 failed