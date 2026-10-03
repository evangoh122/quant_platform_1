# BUILD: RAG eval harness round 2 (MiMo)

Claude's review of round 1:
1. **Nothing is committed.** Commit your work, with a descriptive message.
2. **Order-dependent failures.** 3 tests in `tests/rag/test_rag_eval_retrieval.py` pass alone (12/12),
   but fail in the full `tests/rag` run with `EmbeddingConfigError: EMBEDDING_PROVIDER is
   'huggingface'…`. Earlier tests (`tests/rag/test_hybrid_retriever.py:~2023,2038`) set the provider
   via monkeypatch. The env var is restored, but a CACHED embedder/config object survives. Fix:
   - add an autouse fixture in `tests/rag/conftest.py` that resets every embedding/retriever
     singleton and cache before and after each test (`get_embeddings` cache, `_corpus*`,
     `_embeddings_map`, `_bm25_*`, stored dim/model);
   - prove it by running `python3 -m pytest -q tests/rag` (full) and
     `python3 -m pytest -q tests/rag -p no:randomly` in both file orders.
3. **Production changes** are allowed only as eval hooks:
   - `HybridRetriever.retrieve_mode()` reuses `bm25_search`, `vector_search`, `rrf_fuse` and `rerank`;
   - `chunk_id` is added to the `search_sec_filings` output.

   Add a test that `retrieve(...)` and `retrieve_mode(mode="hybrid_rerank")` return the same
   documents for the same inputs, so the eval measures the real path. Justify the `sec_analyzer.py`
   change in your verdict, or revert it.
4. You deleted `evals/run_eval.py` and `evals/ragas_eval.py`. Confirm nothing imports them (grep, plus
   the test suite), and that the LLM-judge scorers you kept or ported live in
   `evals/rag_eval/generation.py`.
5. **Golden set dependency.** The golden set is being rebuilt as `golden_v2.jsonl` (quality rules) on
   branch `slice/rag-eval-golden`. The harness must take `--golden <path>` and not hardcode v1. The
   tests use only the small fixture in `tests/rag/fixtures/`.

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`, with 0 failures;
- the same suite with pyspark and databricks.connect hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Commit. Write
`.agents/mimo/VERDICT-rag-eval-harness-round2.md`.
