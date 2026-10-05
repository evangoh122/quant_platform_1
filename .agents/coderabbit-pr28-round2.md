### api/main.py:305
_🩺 Stability & Availability_ | _🟡 Minor_ | _⚡ Quick win_



### api/services/hybrid_retriever.py:191
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Use the same model resolution here that `vector_search` uses.**

`_get_embedding_model()` always reads `ST_EMBEDDING_MODEL`. `vector_search` uses `HF_EMBEDDING_MODEL` as the active model when `EMBEDDING_PROVIDER` is `huggingface`. If the two settings differ, the loader filters embeddings for the ST model. The corpus then loads with an empty or mismatched `embeddings_map`.

Two failures follow:
- Dense search returns `[]`, and `retrieve` silently tags results as `bm25_only`. It does not raise `EmbeddingConfigError`.
- The SQL filter keeps only one model, so the "Multiple embedding models" check on Lines 293-297 can never run for real data.

Select the model from `config.EMBEDDING_PROVIDER` in one place. Use that helper both for this filter and for the active-model checks in `vector_search`.



### api/services/hybrid_retriever.py:770
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Resolve the alias before you invalidate one ticker.**

The cache stores each corpus under its canonical ticker (Line 375-378 in `get_ticker_corpus`). This branch pops only the normalized input. For example, `reload_corpus("GOOGL")` removes nothing, and the cached `GOOG` corpus stays stale, but the function still returns `True`.



### api/services/hybrid_retriever.py:788
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Declare `_alias_map_loaded` as global in `reload_corpus`. The reset never takes effect.**

The `global` statements on Lines 763-764 do not list `_alias_map_loaded`. Line 788 assigns to that name, so Python treats it as a local variable. The module-level `_alias_map_loaded` keeps its value of `True`. Line 787 still clears the shared dict.

After a full `reload_corpus(None)`, `_load_alias_map` returns the empty map and never reloads it. `_resolve_canonical_ticker` then returns its input unchanged, so `GOOGL` stops resolving to `GOOG`. `check_ticker_coverage("GOOGL")` still passes, but `get_ticker_corpus("GOOGL")` loads zero chunks and raises `NoCoverageError`. Share-class aliases then return `no_coverage` until the process restarts. Newly added aliases are also never loaded.

The existing `test_reload_corpus_none_clears_state` test does not check the alias flag.



### docs/SEC_RAG_COVERAGE_RUNBOOK.md:44
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Define `catalog`, `schema` and `PILOT_TICKERS` before the bash commands use them.**

Every `databricks bundle run` command passes `--catalog ${catalog} --schema ${schema}`. The runbook never sets these shell variables, and `PILOT_TICKERS` is also never set.

If `catalog` is unset, bash expands the arguments to `--catalog --schema --user-agent-secret-scope ...`. Then argparse in `main()` stops with "expected one argument", and the job fails. The SQL blocks can keep `${catalog}` as widget placeholders. The bash blocks need real values.



### evals/rag_eval/corpus.py:489
_🩺 Stability & Availability_ | _🟡 Minor_ | _⚡ Quick win_

**Install an offline alias map as well. Ticker lookups still reach Spark or the warehouse.**

This change patches `check_ticker_coverage`, but `get_ticker_corpus` also calls `_resolve_canonical_ticker`, and that function calls `_load_alias_map()`. Unless the map is already loaded, `_load_alias_map()` calls `_get_spark()`. Outside a Databricks runtime, `_get_spark()` builds a `DatabricksSession` and connects to serverless compute. If databricks-connect is not installed, the function falls back to `_get_warehouse_connection()`.

An offline eval therefore attempts a Databricks connection on its first ticker lookup. On a machine without network access, this blocks until the connection times out. When the attempt fails, the broad `except` sets an empty map as loaded. The run can continue, but it is not offline.

Set an identity alias map from `ticker_docs` with `_alias_map_loaded = True` under `_alias_map_lock`. Restore the original map and flag in `finally`. The tests do not show this problem because the `tests/rag` conftest patches `_resolve_canonical_ticker`.



### pipelines/sec_rag_ingest.py:1593
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Use the CIK whose submissions listed the accession, not an arbitrary member of a set.**

`ticker_ciks` is a `set`. `next(iter(ticker_ciks))` therefore returns an arbitrary member. String hash randomization can change that member from one process to the next.

The fallback branch runs for an override ticker when the accession prefix is not in the group. This is normal when a filing agent submits the filing, for example with prefix `0001193125`. In that case the code can choose a group CIK whose `/Archives/edgar/data/{cik}/...` path does not contain the filing. The fetch then fails with `fetch_failed`, and the run exits 1. A rerun can store a different `cik` for filings of the same ticker.

Record the CIK that discovered each filing during the discovery loop, and use that CIK here.



### pipelines/sec_rag_ingest.py:1682
_🚀 Performance & Scalability_ | _🟠 Major_ | _⚡ Quick win_

**Replace the per-filing full-table read with a lookup for one accession.**

`_process_one` calls `accession_reader.read_existing_accessions(catalog, schema)` once for each planned filing. In production, `SparkAccessionReader` runs `select(accession_number, cik, ticker).distinct().collect()` over all of `bronze_sec_filings_v2` and returns the full result to the driver.

- A universe-wide run plans thousands of filings, for example about 557 tickers × about 8 filings.
- Each planned filing starts one full Spark scan and one driver collect. The work grows with both the number of planned filings and the bronze table size.
- With `--max-workers 4`, four of these scans can run at the same time. They compete with the MERGE path for the same serverless session.

The race check needs the owner of only one accession. Add a targeted reader method and use it here.



### tests/rag/test_hybrid_retriever.py:3362
_📐 Maintainability & Code Quality_ | _🟡 Minor_ | _⚡ Quick win_

**Use `monkeypatch` for the mutation; the direct assignment leaks `_load_ticker_corpus` into later tests.**

Line 3362 assigns `hr._load_ticker_corpus = mock_load_empty` directly on the module. No fixture restores `_load_ticker_corpus`. After this test runs, every later test in the session that reaches `get_ticker_corpus` gets an empty corpus, and `NoCoverageError` follows. The failures then depend on test order.

The class fixture monkeypatches `_resolve_canonical_ticker`, so teardown restores it. Line 3352 still has the same pattern, so convert both lines.



