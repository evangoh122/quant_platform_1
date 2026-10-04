# VERDICT: rag-eval-harness-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None remaining. Both blocking issues fixed.

## Fixes applied

### Fix 1: Stored model metadata now reaches the retriever
- **Root cause:** The real `.npz` sidecar (`evals/data/sec_embeddings.npz`) had `embedding_model=""` (empty). The `_load_npz_sidecar` function accepted this silently, `install_offline_corpus` set `hr._stored_embedding_model = ""`, and `vector_search` saw `"" is not None` → True, then `"BAAI/bge-small-en-v1.5" != ""` → True → raised `CorpusUnavailableError`.
- **Fix in `evals/rag_eval/corpus.py:245`:** Added validation in `_load_npz_sidecar` — if `embedding_model` metadata is empty, raise `ValueError` with a clear message to rebuild the sidecar with `--model`.
- **Fix in `evals/rag_eval/build_sidecar.py:92`:** Added validation in `build_sidecar` — `model_name` is now required (raises `ValueError` if empty).
- **Rebuilt sidecar:** `evals/data/sec_embeddings.npz` now has `embedding_model="BAAI/bge-small-en-v1.5"`.
- **Also fixed:** `corpus.py:170` typo `_corpus_sha56` → removed dead branch, now returns `self._corpus_sha256` directly.

### Fix 2: Headline status is now honest
- **`evals/rag_eval/cli.py:282-301`:** PIT gate now reports `INCOMPLETE` (not `PASS`) when any evaluation errored. Summary shows total items, n_evaluated, n_errors. Per-mode breakdown with n_evaluated and n_errors.
- **`evals/rag_eval/metrics.py:364-378`:** Added `per_mode` aggregation to `aggregate_results()` — each mode's metrics include `n_evaluated` and `n_errors`.
- **`evals/rag_eval/models.py:149`:** Added `per_mode_metrics` field to `RunReport`.
- **`evals/rag_eval/report.py:110-123`:** Added per-mode metrics table to Markdown report.

### Round-3 guarantees preserved
- `accepted_epoch` parsing: unchanged (verified by existing tests).
- Missing timestamps counted as violations: unchanged (verified by existing tests).

## Checks run
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → 659 passed, 67 skipped (same with pyspark/databricks.connect hidden)
- `python3 -m evals.rag_eval --golden evals/data/golden_v1.jsonl --corpus evals/data/sec_corpus.jsonl --embeddings evals/data/sec_embeddings.npz --mode all --ticker-filter on` → **320 total, 320 evaluated, 0 errors, PIT: 0 PASS, recall@5=0.0750**
- Sidecar with different model name test: `test_different_model_name_errors_in_dense_mode` passes — the check still works.
- Sidecar with empty model name test: `test_sidecar_missing_model_name_raises` passes — clear error at load time.

## Non-blocking notes
- The smoke fixture sidecar (`tests/rag/fixtures/rag_eval/embeddings_smoke.npz`) already had `embedding_model="BAAI/bge-small-en-v1.5"` — only the real export was missing it.
- Recall@5 improved from 0.0187 (round 3, BM25-only) to 0.0750 (round 4, all modes) because dense and hybrid modes now work.
- All 320 evaluations run with 0 errors across all 4 modes × 2 ticker filters.