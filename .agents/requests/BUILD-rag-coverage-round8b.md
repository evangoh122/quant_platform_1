# BUILD rag-coverage round 8b — embeddings, retrieval, coverage SQL (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Commit after EACH item, descriptive messages.
NEVER delete or weaken existing tests. Codex review: .agents/codex/VERDICT-rag-coverage-review.md — this round = findings 7–10.
Every fix needs a test that FAILS on the old code; prove it with a copy made by `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a
cp -r of this worktree) and paste the output in the verdict.

7. Embeddings (pipelines/build_sec_embeddings.py ~:237, :104): parallel workers share ONE temp view `_embed_src` → batches overwrite each other.
   Give each batch a unique view name (e.g. `_embed_src_<uuid>`), drop it after the MERGE, and serialise MERGEs into the same target (a lock or a
   single writer thread) to avoid Delta concurrent-write conflicts. Report actual inserted rows (MERGE operationMetrics), not candidates.
   The documented runbook passes a comma-separated pilot ticker list but :104 does scalar equality → accept a list (`isin`). Declare the model
   dependencies the serverless job needs (sentence-transformers / torch CPU etc.) in the job environment in resources/jobs.yml.
   Tests: two concurrent batches → distinct view names, both batches' rows written; comma list → isin predicate; inserted count from metrics.
8. Retrieval (api/services/hybrid_retriever.py): (a) :424 collects ALL chunks + embeddings and :594 `reload_corpus(None)` eagerly calls it — make
   the all-corpus path bounded or remove the eager call so the per-ticker LRU is the only load path (no full-corpus load at startup);
   (b) dense search :869 must EXCLUDE chunks whose accepted_ts is NULL or unparseable (treat as not-yet-available), not let them through.
   Tests: reload_corpus(None) does not trigger a full collect (spy); a NULL-timestamp chunk is never returned for any as_of.
9. Coverage SQL (gold/07_gold_sec_coverage.sql): replace the hardcoded catalog/schema with the same placeholders the runner substitutes (check
   pipelines/run_silver_gold.py — make it substitute catalog/schema too if it only does dates); restrict rows to universe members (or add an
   explicit in_universe flag and document — prefer restricting, keep a separate count of out-of-universe tickers in the log); take CIK from the
   latest successful sec_cik_mapping_log entry (mapped) rather than bronze filings, so mapped zero-filing tickers still show their CIK.
   Tests: SQL extracted from the file run in DuckDB on fixtures (universe, mapping log, filings, chunks) asserting exact rows.
10. tools_retrieval.py:153 — Spark/table errors from the coverage path must return `retrieval_unavailable` (structured error), not fall through to
   substring retrieval. Test: retriever raises a table error → result status retrieval_unavailable, substring path not called.
Also: the bronze MERGE at pipelines/sec_rag_ingest.py:1570-1573 uses `WHEN NOT MATCHED THEN INSERT *` — use an explicit column list.
Acceptance: python3 -m pytest tests/rag tests/bronze -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-coverage-round8b.md with counts + mutation outputs. Commit everything.
