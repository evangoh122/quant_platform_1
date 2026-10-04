# BUILD: RAG eval harness round 4 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each fix.

Claude reran the harness on the real exported corpus (80 golden items × 4 configs = 320 runs) after
round 3:

    FAIL: 240 item(s) had errors
    PIT Leakage: 0 PASS
    recall@5 0.0187

All 480 recorded errors are the same:
`CorpusUnavailableError: Embedding model mismatch: active model 'BAAI/bge-small-en-v1.5' does not match stored index model ''.`

1. **[Blocking] The stored model metadata never reaches the retriever.** The `.npz` sidecar has
   `embedding_model = BAAI/bge-small-en-v1.5`, but the adapter feeding the production retriever
   (#19 added the stored-model check) leaves the stored model empty. So every dense and hybrid mode
   errors, and only BM25 runs. Fix: when the harness loads the JSONL+npz corpus into the retriever,
   set the stored model and dimension from the sidecar manifest, through the same state the
   retriever's Delta loader sets. Never by disabling the check. Test: an offline fixture run of ALL
   modes has 0 errors, and a sidecar with a different model name produces `embedding_config`
   errors (the check still works).
2. **[Blocking] The headline status lies.**
   - Any item error must make the overall run status FAIL (exit code ≠ 0).
   - The PIT gate must report `INCOMPLETE` (not PASS) when any evaluation errored, because errored
     items were never checked.
   - Per-mode metrics must state `n_evaluated` and `n_errors`.
   - Test: a run with one forced error exits non-zero and prints `PIT: INCOMPLETE`.
3. Keep the round-3 guarantees: `accepted_epoch` parsing, and missing timestamps counted as violations.

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`, with 0 failures;
- the same suite with pyspark and databricks.connect hidden.

Then, if `evals/data/` is present, run:

    python -m evals.rag_eval --golden <v1 path> --corpus evals/data/sec_corpus.jsonl --embeddings evals/data/sec_embeddings.npz --mode all --ticker-filter on

and paste the summary into the verdict.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Write
`.agents/mimo/VERDICT-rag-eval-harness-round4.md`.
