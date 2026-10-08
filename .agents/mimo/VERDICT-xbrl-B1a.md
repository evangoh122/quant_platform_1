# VERDICT: xbrl-B1a — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None.

## Non-blocking notes
- The `sec_companyfacts_ingest` job in `resources/jobs.yml` does not pass `--tickers`; at runtime it relies on `SparkUniverseReader` to read from `gold_tradable_universe`. Until PR #28 is merged and the universe is populated, the job will read whatever tickers are currently in that table (16 in the live snapshot, not 557).
- `CompanyFactsManifestEntry.fetch_status` has a default of `""` rather than being a required field — intentional for constructor convenience; all code paths set it explicitly before writing.

## Checks run
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → 34 passed
- `python3 -m pytest tests/test_bundle_sync.py tests/test_schema_env_override.py tests/test_check_schema_contract.py -q` → 11 passed
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → 194 passed, 6 skipped
- `python3 -m pytest tests/rag/test_sec_embeddings_incremental.py -q -k "job"` → 9 passed
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py tests/test_bundle_sync.py tests/test_schema_env_override.py tests/test_check_schema_contract.py -v` → 45 passed

## Files created/modified
1. **`pipelines/ingest_sec_companyfacts.py`** (new) — Spark entry point: fetch Company Facts JSON per CIK, flatten to rows, append to `bronze_sec_xbrl_facts`, write manifest to `sec_companyfacts_ingest_log`. Reuses `RateLimiter`, `SecClient`, `build_cik_map`, `load_cik_overrides`, `_resolve_user_agent` from `sec_rag_ingest.py`.
2. **`tests/bronze/test_sec_companyfacts.py`** (new) — 34 Spark-free unit tests: Plan B 2.5 items 1 (placeholder UA rejected, UA sent, Retry-After, rate cap), 2 (two changed payloads appended, malformed preserved), 10 partially (XOM two-CIK, manifest, same-payload skip, no email in logs). Named mutation proofs.
3. **`resources/jobs.yml`** (modified) — Added `sec_companyfacts_ingest` job before `sec_knowledge_graph_build`.
4. **`tests/rag/test_sec_embeddings_incremental.py`** (modified) — Added `ingest_sec_companyfacts` to entrypoint→job mapping.

## Commits
- `3983aed` feat(xbrl): add SEC Company Facts XBRL ingestion pipeline
- `fef6644` test(xbrl): add Company Facts ingestion tests (Plan B 2.5 items 1,2,10)
- `859a15c` feat(xbrl): add sec_companyfacts_ingest job to jobs.yml
- `97f9309` test(xbrl): add ingest_sec_companyfacts to job entrypoint mapping