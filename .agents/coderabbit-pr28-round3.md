### docs/SEC_RAG_COVERAGE_RUNBOOK.md:24
_📐 Maintainability & Code Quality_ | _🟡 Minor_ | _⚡ Quick win_

**Fix the User-Agent environment setup. The example value fails validation, and the local export does not reach the job.**

The section has three problems:
- **Line 39:** The example value `your-email@example.com` matches `@example\.(com|org|net)` in `_validate_user_agent`. If an operator copies this value, `run_ingest` raises `ValueError`.
- **Placement:** `databricks bundle run` runs the task on Databricks. A shell `export` on the operator's machine does not set `SEC_EDGAR_USER_AGENT` for the job. For bundle runs, the env step has no effect, and the job always reads the secret.
- **Line 24:** The text says that values containing "example" are rejected. The validator rejects only placeholder domains and prefixes. `analyst@myexample.org` passes, as the tests show.



### evals/rag_eval/corpus.py:482
_🩺 Stability & Availability_ | _🟡 Minor_ | _⚡ Quick win_

**Save the alias-map originals before `try`. An early setup error otherwise ends in `UnboundLocalError`.**

`orig_alias_map` and `orig_alias_loaded` are assigned inside `try`, at Line 477, after most of the setup. Several earlier steps can raise:
- `adapter.records()`
- `adapter.embedding_map()`
- `BM25Okapi(...)`
- `TickerCorpus(...)`

If one of them raises, `finally` reaches Lines 525-526 and raises `UnboundLocalError`. The new error hides the original setup error. This breaks the docstring guarantee "Restores prior globals even after errors". Take the snapshot next to the other saved originals, before `try`.



### evals/rag_eval/corpus.py:497
_🩺 Stability & Availability_ | _🟡 Minor_ | _⚡ Quick win_

**Return `NoCoverageError` for tickers outside the offline corpus. Do not delegate to the live checker.**

For a ticker outside `offline_tickers`, `_offline_check_ticker_coverage` calls `_orig(ticker)`. That is the real `check_ticker_coverage`, which calls `_get_spark()` or the SQL warehouse. In offline evals, `HybridRetriever.retrieve` resolves tickers from query text through `resolve_ticker_from_query`. That resolver can return any company in the alias patterns. It is not limited to the offline fixture tickers.

A golden question that names a company outside the corpus therefore starts a Databricks connection during an offline run. This is the same leak that the identity alias map was added to stop. Without network access, the run can block until the connection times out. It can also return a non-deterministic error where the result should be `no_coverage`.

The offline corpus is the only source of coverage inside this context. Raise `NoCoverageError` for any ticker that is not in it.



### pipelines/sec_rag_ingest.py:1469
_🗄️ Data Integrity & Integration_ | _🟡 Minor_ | _⚡ Quick win_

**Do not write `sec_cik_mapping_log` during a dry run unless `--log-dry-run` is set.**

The CIK mapping log is written and flushed whether or not `dry_run` is set. Other dry-run side effects are gated:
- `load_company_tickers` skips the cache write.
- `sec_ingest_log` is written only with `log_dry_run`.

The runbook tells operators to dry-run the full universe first. Each of those dry runs adds about 557 audit rows. Those rows look the same as rows from real runs.



### pipelines/sec_rag_ingest.py:2294
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Parameterize the `sec_ingest_log` queries. Stop swallowing every exception as a cold start.**

`read_succeeded_accessions` and `read_max_attempt` interpolate `run_id`, `ticker` and `accession_number` directly into the SQL text. `run_id` comes from the `--run-id` CLI argument. `ticker` comes from `--tickers` or `gold_tradable_universe`. If a value contains a quote, the query fails to parse.

The `except Exception` block then returns `set()` or `0`. This turns a parse error, permission error or transient failure into "no prior attempts". On a resumed run, already-succeeded filings run again, and the `attempt` numbers restart at 1. The audit trail becomes wrong, and no error appears.

`main()` already calls `ensure_ingest_log_table` before any read. The cold-start fallback therefore does not need to hide all errors. `repair_cik_ownership` already uses `args=`, so apply the same pattern here. Log the swallowed error so it is visible.



### tests/rag/test_hybrid_retriever.py:1265
_📐 Maintainability & Code Quality_ | _🟡 Minor_ | _⚡ Quick win_

**Fix the stated contract in these two tests. They pass only because the Spark fallback fails.**

In `test_fallback_results_tagged_with_retrieval_mode` (Lines 1246-1265), the docstring says that a non-corpus exception "must return retrieval_unavailable, not substring fallback." `test_generic_exception_returns_retrieval_unavailable` (Lines 1375-1400) states the same rule. `search_sec_filings` in `agent/tools_retrieval.py` does not have that rule. For any generic `Exception`, it goes to the substring fallback. `test_spark_table_error_triggers_substring_fallback` and `test_fallback_output_keys_match_hybrid_path` confirm this: both raise `RuntimeError("connection timeout")`-style errors and get `substring_fallback` results.

The first test does not patch `_spark`. It returns `retrieval_unavailable` only because the guarded `_get_spark` raises in the test environment. The second test patches `_spark` to raise. In both tests, the "fallback also failed" branch is what produces the result. The test name `test_fallback_results_tagged_with_retrieval_mode` also contradicts its own assertion that `retrieval_mode` is absent.

Restate both tests as "generic error plus unavailable fallback returns retrieval_unavailable." Patch `_spark` explicitly in the first test so that it does not depend on the environment.



### tests/rag/test_sec_rag_ingest.py:16
_📐 Maintainability & Code Quality_ | _🟡 Minor_ | _⚡ Quick win_

**Import `Tuple`. Ruff reports F821 for each use.**

`Tuple` is used at Lines 197, 200, 205, 1462 and 4738, but this line does not import it. `from __future__ import annotations` prevents a runtime `NameError`. Ruff still reports `F821 Undefined name`. If lint runs in CI, the check fails.



### NITPICK (from the review body)
🧹 Nitpick comments (1)
api/services/hybrid_retriever.py (1)
`1082-1090`: _🚀 Performance & Scalability_ | _🔵 Trivial_ | _⚡ Quick win_
**Replace the nested chunk lookup. Each dense query is O(embeddings × docs).**
For each embedding, the per-ticker path scans all of `corpus.docs` to find the matching `chunk_id`. For a ticker with N chunks, every `vector_search` call does about N²/2 Python dict lookups. The global path at Lines 1143-1149 has the same pattern. The PR extends coverage to the full universe, and per-ticker chunk counts grow with each ingest. A ticker with several thousand chunks then adds seconds of CPU time to every request.
Build a `chunk_id → Document` map once. The best place is in `_load_ticker_corpus` (stored on `TickerCorpus`). A map built per query also removes the quadratic cost.
`bm25_search` (Lines 997-1002) also re-tokenizes the PIT-filtered docs and rebuilds `BM25Okapi` on every query. The precomputed `corpus.tokenised` and `corpus.bm25_index` are never used for scoring. Reuse `corpus.tokenised` for the filtered subset, at minimum.
Proposed fix
```diff
         candidates: List[Tuple[float, Document]] = []
+        doc_by_id = {d.metadata.get("chunk_id"): d for d in corpus.docs}
         for cid, vec in corpus.embeddings_map.items():
-            doc = None
-            for d in corpus.docs:
-                if d.metadata.get("chunk_id") == cid:
-                    doc = d
-                    break
+            doc = doc_by_id.get(cid)
             if doc is None:
                 continue
