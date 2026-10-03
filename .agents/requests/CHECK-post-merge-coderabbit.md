# CHECK: post-merge CodeRabbit fixes (DeepSeek)

Branch `fix/post-merge-coderabbit` = main + fixes for CodeRabbit's findings on #18/#14 (merged
before the findings were addressed). Read-only. Review `git diff origin/main` (ignore `.agents/`).
Write `.agents/deepseek/VERDICT-post-merge-coderabbit.md` (===VERDICT START/END===, Status).

Check, hardest first:
1. **RAG ticker filter** (`api/services/hybrid_retriever.py::bm25_search`).
   - Correct when `ticker` is explicit vs resolved from the query in `HybridRetriever.retrieve`?
   - Does the hard filter wrongly drop results when the query resolves a different ticker?
   - Point-in-time filter still before scoring?
   - Prove the new test fails if the filter is removed (mutate in /tmp).
2. **Corpus load retry.**
   - After a failure, all partial state is cleared and the next call retries.
   - No path leaves `_corpus_loaded=True` with an empty corpus.
   - Is the error surfaced as `CorpusUnavailableError` → `retrieval_unavailable`, not the
     substring fallback?
3. **Embedding dimension guard and HF default.** A mismatch must become `retrieval_unavailable`,
   not a silent fallback.
4. **`build_sec_embeddings`.** A read error now propagates and nothing is written.
5. **CI/CD.**
   - Each pinned SHA matches its tag. Verify with `git ls-remote`.
   - `persist-credentials: false` on every checkout.
   - The bundle-validate gate needs complete auth.
   - `start_app` defaults to false and only runs `bundle run quant_platform`. No jobs or pipelines
     are run.
   - Schema plumbing: the app `config.env` SCHEMA and the job `--schema` parameter reach
     `pipelines/run_silver_gold.py` (the `FQN` rebind) and `api/config.py`.
   - Tests don't leak module state.

Run `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`, plus `tests/rag` with pyspark
hidden (sitecustomize that sets `sys.modules[m]=None` for pyspark, pyspark.sql, pyspark.sql.functions
and pyspark.sql.types).
