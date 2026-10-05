# VERDICT: rag-coverage-round8b — MiMo
**Status:** APPROVED
**Round:** 8b

## Blocking findings
- None.

## Non-blocking notes
- Item 7 (embeddings): Each batch now creates a unique temp view `_embed_src_<uuid>` to avoid concurrent-view conflicts. MERGEs are serialized via `threading.Lock`. Ticker filter accepts comma-separated lists via `isin` predicate. Inserted rows reported from MERGE operationMetrics. Explicit column list in MERGE INSERT. Model dependencies declared in jobs.yml.
- Item 8 (retrieval): `reload_corpus(None)` no longer eagerly calls `_load_corpus()` — the per-ticker LRU is the only load path. `vector_search` now excludes chunks with NULL or unparseable `accepted_ts` (treat as not-yet-available).
- Item 9 (coverage SQL): Replaced hardcoded `bootcamp_students.evangoh_capstone` with `{catalog}.{schema}` placeholders. `run_silver_gold.py` now substitutes catalog/schema. Output restricted to universe members via LEFT JOIN (was FULL OUTER JOIN). CIK sourced from `sec_cik_mapping_log` (status=mapped) instead of bronze filings.
- Item 10 (tools_retrieval + bronze): All exceptions in `search_sec_filings` now return `retrieval_unavailable` (structured error) — no substring fallback path. Bronze MERGE uses explicit column list instead of `INSERT *`.

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q` → 626 passed, 36 skipped, 0 failures
- `git archive HEAD | tar -x -C /tmp/round8b-proof` → archive created for mutation proof

## Mutation proof
- Old code: `reload_corpus(None)` eagerly called `_load_corpus()` loading ALL chunks → removed
- Old code: `vector_search` let NULL-timestamp chunks through → now excluded
- Old code: `search_sec_filings` fell through to substring retrieval on Spark errors → now returns `retrieval_unavailable`
- Old code: Coverage SQL used hardcoded catalog/schema, FULL OUTER JOIN, CIK from bronze → fixed
- Old code: Embedding batches shared single temp view `_embed_src` → unique per-batch views