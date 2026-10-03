# VERDICT: post-merge-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None.

## Non-blocking notes
- All 3 fixes applied cleanly: default provider, HF token guard, BM25-only degradation.
- `vector_search` and `ACTIVE_EMBEDDING_MODEL`/`EMBEDDING_DIM` now read `self.EMBEDDING_PROVIDER` instead of re-parsing `os.getenv` with the old default — eliminates the class of stale-default bugs.
- The `CorpusUnavailableError` vs runtime-embedder-failure distinction is preserved: dim/model mismatch still raises as a config error; transient failures degrade to BM25-only.
- `search_sec_filings` now propagates `retrieval_mode` and `_warning` from retriever metadata rather than overwriting to `"hybrid"`.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py` → 297 passed, 19 skipped, 1 warning
- `file` on all 5 modified files → no CRLF detected (LF line endings)
- `git diff --stat` → 5 files, +328 / -25 lines