# CHECK: RAG eval harness (DeepSeek)

Branch `slice/rag-eval-harness`. Spec: `.agents/requests/BUILD-rag-eval-harness.md` plus rounds 2–4.
On the real corpus with golden v1: 320/320 evaluated, 0 errors, PIT 0 PASS, recall@5 0.075.
Read-only. Write `.agents/deepseek/VERDICT-rag-eval-harness.md` (===VERDICT START/END===, Status).

Check, with proofs:
1. **The PIT gate is real, not vacuous.**
   - Timestamps load from `accepted_epoch`.
   - A missing or unparseable timestamp counts as a violation.
   - Any errored item → `PIT: INCOMPLETE` and a non-zero exit.
   - **Mutation:** disable the production `_pit_filter` in a /tmp copy and run the fixture
     end-to-end. The gate must FAIL.
2. **The harness measures the REAL retrieval path.** `retrieve_mode()` uses the same functions as
   `retrieve()`, and a test asserts `retrieve()` and `retrieve_mode("hybrid_rerank")` agree. The
   stored model/dim come from the sidecar via the same state the Delta loader sets; the
   model-mismatch check is NOT disabled.
3. **Metrics:** recall@k, MRR@10 and nDCG@10 match hand-computed values on the fixture. Bootstrap
   CIs are deterministic with the seed. Per-mode `n_evaluated`/`n_errors` are correct.
4. **Ablations:** BM25, dense, hybrid RRF, hybrid+rerank; ticker filter on and off. Each produces
   distinct results, and none silently falls back.
5. **Retiring the stale `evals/run_eval.py` and `evals/ragas_eval.py`:** nothing imports them, and
   the generation scorers are ported and OFF by default, with no paid calls.
6. **Test isolation:** the embedding/retriever caches are reset per test, and the results are the
   same in both file orders.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite with
`--ignore=tests/lakebase`.
