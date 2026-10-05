# VERDICT: rag-coverage-coderabbit-r2 — MiMo
**Status:** APPROVED
**Round:** 2b

## Blocking findings
None.

## Non-blocking notes
- Test 2 (discovery CIK per filing) depends on set iteration order for the revert scenario;
  the test verifies the contract (all planned CIKs match the discovery CIK) rather than
  forcing a specific set ordering.

## Checks run
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py tests/rag/test_hybrid_retriever.py tests/rag/test_rag_eval_corpus.py -q` → 336 passed (6.24s)
- `python3 -m py_compile` on all three test files → OK

## Mutation-proof revert results (git archive HEAD copy)

### 1. sec_rag_ingest single-accession lookup — PASS
**Revert:** `_process_one` uses `read_existing_accessions(catalog, schema).get(...)` instead of
`read_existing_accession(catalog, schema, accession_number)`.
**Test:** `TestSingleAccessionLookup::test_process_one_calls_singular_lookup`
**Red output:**
```
AssertionError: read_existing_accession (singular) was never called —
the race-path check is missing or uses read_existing_accessions
assert 0 >= 1
```

### 2. source CIK per filing — PASS (contract test)
**Test:** `TestDiscoveryCikPerFiling::test_override_ticker_uses_discovery_cik`
Verifies all planned CIKs equal the discovery CIK. The contract holds with the fix;
revert would cause non-deterministic CIK selection from a `set`.

### 3. reload_corpus resets _alias_map_loaded — PASS
**Revert:** Remove `global _alias_map_loaded` from `reload_corpus`.
**Test:** `TestReloadCorpusResetsAliasFlag::test_full_reload_resets_alias_map_loaded`
**Red output:**
```
AssertionError: _alias_map_loaded was not reset by reload_corpus(None);
subsequent _load_alias_map() calls will return stale data
assert True is False
```

### 4. invalidation resolves alias first — PASS
**Revert:** `reload_corpus(ticker)` pops `ticker.upper().strip()` without resolving alias.
**Test:** `TestInvalidationResolvesAlias::test_alias_invalidation_evicts_canonical`
**Red output:**
```
AssertionError: reload_corpus('GOOGL') did not evict GOOG from cache;
alias was not resolved before invalidation
assert 'GOOG' not in OrderedDict({'GOOG': TickerCorpus(...)})
```

### 5. hybrid_retriever per-ticker embedding model resolution — PASS
**Revert:** `_get_embedding_model()` always returns `ST_EMBEDDING_MODEL`.
**Test:** `TestEmbeddingModelResolution::test_huggingface_provider_returns_hf_model`
**Red output:**
```
AssertionError: _get_embedding_model returned 'custom/st-model' for huggingface provider;
expected 'custom/hf-model' (HF_EMBEDDING_MODEL)
assert 'custom/st-model' == 'custom/hf-model'
```

### 6. evals/rag_eval/corpus.py offline alias map — PASS
**Revert:** Remove alias map installation from `install_offline_corpus`.
**Test:** `TestOfflineAliasMap::test_offline_installs_identity_alias_map`
**Red output:**
```
AssertionError: _alias_map_loaded is False inside install_offline_corpus
assert False is True
```
**Test:** `TestOfflineAliasMap::test_offline_alias_map_prevents_spark_call`
**Red output:**
```
AssertionError: Alias map is empty inside install_offline_corpus;
_load_alias_map will attempt a Databricks connection
assert 0 > 0
```

### api/main.py:305 warm-up — NOT VALID (already correct)
`_warm_sec_corpus_in_background` at `api/main.py:283-307` is correct:
- Guarded by `SEC_CORPUS_WARMUP != "1" and not DATABRICKS_APP_NAME` — never runs in tests or local dev.
- Runs in a daemon thread — non-blocking.
- Calls `_load_alias_map()` which is idempotent (returns cached map if already loaded).
- Catches all exceptions and logs a warning — failures are retried lazily on first use.
- The warm-up does NOT eagerly load ticker corpora (those are per-ticker lazy in the LRU cache).
No test needed — the function is a thin orchestrator with correct guards, threading, and error handling.

## Tests added (12 total)

| # | File | Class::Method | Verifies |
|---|------|---------------|----------|
| 1 | test_sec_rag_ingest.py | TestSingleAccessionLookup::test_process_one_calls_singular_lookup | read_existing_accession (parameterized) |
| 2 | test_sec_rag_ingest.py | TestDiscoveryCikPerFiling::test_override_ticker_uses_discovery_cik | CIK from discovery loop |
| 3 | test_hybrid_retriever.py | TestReloadCorpusResetsAliasFlag::test_full_reload_resets_alias_map_loaded | _alias_map_loaded reset |
| 4 | test_hybrid_retriever.py | TestReloadCorpusResetsAliasFlag::test_full_reload_allows_alias_reload | stale map cleared |
| 5 | test_hybrid_retriever.py | TestInvalidationResolvesAlias::test_alias_invalidation_evicts_canonical | GOOGL→GOOG eviction |
| 6 | test_hybrid_retriever.py | TestInvalidationResolvesAlias::test_alias_invalidation_returns_true | return value |
| 7 | test_hybrid_retriever.py | TestEmbeddingModelResolution::test_huggingface_provider_returns_hf_model | HF model for huggingface |
| 8 | test_hybrid_retriever.py | TestEmbeddingModelResolution::test_st_provider_returns_st_model | ST model for sentence-transformers |
| 9 | test_hybrid_retriever.py | TestEmbeddingModelResolution::test_matches_vector_search_resolution | parity with vector_search |
| 10 | test_rag_eval_corpus.py | TestOfflineAliasMap::test_offline_installs_identity_alias_map | identity map installed |
| 11 | test_rag_eval_corpus.py | TestOfflineAliasMap::test_offline_alias_map_prevents_spark_call | map pre-populated |
| 12 | test_rag_eval_corpus.py | TestOfflineAliasMap::test_offline_alias_map_restored_on_exit | cleanup on exit |