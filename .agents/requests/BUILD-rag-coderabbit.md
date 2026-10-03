# BUILD: rag CodeRabbit findings on PR #18 (MiMo)

Claude verified these against the code. Fix all of them, each with a test that fails on the current code.
Prove that in a /tmp copy, and paste the output in the verdict.

1. **[Major] `api/services/hybrid_retriever.py:~413-450`: BM25 doesn't filter by ticker.**
   `vector_search` drops other tickers; `bm25_search` only boosts the match. So
   `search_sec_filings(symbol="NVDA")` can return other companies' chunks through RRF.
   When `ticker` is set, filter the BM25 candidates to that ticker, before ranking and after the
   point-in-time filter. Keep the boost path only for `ticker` unset / resolved-from-query.
   Test: a corpus with an AAPL chunk that matches the query better than any NVDA chunk; ticker=NVDA
   must return no AAPL chunk.
2. **[Major] `hybrid_retriever.py:~347`: a transient load failure disables retrieval forever.**
   On exception, leave `_corpus_loaded = False`, clear the partial `_corpus`, `_embeddings_map` and
   `_bm25_*` state, and re-raise `CorpusUnavailableError`. The next call must retry.
   Test: the first load raises, the second load succeeds, and retrieve works.
3. **[Major] `api/services/embeddings.py:~177`: the HuggingFace default model is 4096-d.**
   Change the default to `BAAI/bge-small-en-v1.5`. In `vector_search`, check that the query vector
   length == `EMBEDDING_DIM`. On a mismatch, raise a clear error that becomes
   `retrieval_unavailable`, NOT the substring fallback. Test both.
4. **[Minor] `pipelines/build_sec_embeddings.py:~77`: don't swallow existing-ID read errors.**
   Remove the blind `except Exception` that sets `existing_ids = set()`. Let the error propagate.
   Test: the read raises → build raises and writes nothing.

Run, and both must pass:
- `python3 -m pytest -q tests/rag`
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag`, with a sitecustomize that sets
  `sys.modules[m]=None` for pyspark, pyspark.sql, pyspark.sql.functions and pyspark.sql.types.

LF line endings only. Don't touch `.agents/dispatch.sh` or `.github/`. Commit. Write
`.agents/mimo/VERDICT-rag-coderabbit.md`.
