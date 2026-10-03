# VERDICT: rag-databricks-round7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
(none — blocking defect fixed)

## What was fixed

### `accepted_ts` client-timezone drift

**Root cause:** `unix_timestamp()` in Spark returns epoch seconds (TZ-invariant), but
`collect()` returns naive `datetime` objects in the *client machine's local timezone*.
The round-6 code assumed `row["accepted_ts"]` was UTC — wrong by the host's UTC offset
(+8h on WSL Singapore, -5h on US/Eastern, etc.).

**Fix:** Both read paths now select `unix_timestamp(accepted_ts) AS accepted_epoch`
and convert in Python via `datetime.fromtimestamp(epoch, tz=timezone.utc)`.

| File | Change |
|------|--------|
| `api/services/hybrid_retriever.py:263-304` | `_load_corpus` selects `accepted_epoch`, builds UTC ISO string from epoch |
| `pipelines/build_sec_embeddings.py:80-129` | Embedding pipeline selects `accepted_epoch`, converts to UTC datetime for Delta write |

### Round-6 epoch fallback (PIT filter in `tools_retrieval.py:141-144`)
Already correct — uses `F.unix_timestamp(F.col("accepted_ts"))` in Spark directly. No change needed.

## Non-blocking notes
- `_load_corpus` now imports `F` inside the try block (lazy, same pattern as `_get_spark`).
- `build_sec_embeddings.py` already had the `F` import scope established; moved it earlier.

## Tests added

| Test | What it proves |
|------|---------------|
| `test_epoch_produces_correct_utc_in_sgt` | `datetime.fromtimestamp(epoch, tz=UTC)` is correct under `TZ=Asia/Singapore` |
| `test_epoch_produces_correct_utc_in_est` | Same under `TZ=America/New_York` |
| `test_old_code_fails_in_sgt` | Old code (naive→assume UTC) is exactly 28800s off in SGT — proves the bug |
| `test_load_corpus_uses_epoch` | `_load_corpus` with mock Spark `accepted_epoch` row stores `"2024-12-20T22:26:46+00:00"` |

Existing tests updated: mock Spark rows in `TestEmbeddingBuildIdempotency` now use `accepted_epoch` instead of `accepted_ts`.

## Checks run
- `python3 -m pytest tests/rag/test_hybrid_retriever.py -q` → 59 passed
- `python3 -m pytest tests/rag -q` → 264 passed, 19 skipped