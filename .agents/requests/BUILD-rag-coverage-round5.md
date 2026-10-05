# BUILD rag-coverage round 5 (builder: MiMo; checker: Claude Sonnet subagent standing in for DeepSeek)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Work on branch slice/rag-coverage (do NOT create a new branch).
Commit after each item. NEVER delete or weaken existing tests.
Checker verdict: .agents/deepseek/VERDICT-rag-coverage-round4.md (CHANGES_REQUESTED). Items 1, 2, 6, 7 of round 4 passed; fix the rest.

## 1. Discriminating three-ticker parallel test
`test_three_tickers_parallel` passes on the old serial code (0.8s bound > 0.6s serial). Make it discriminate:
use a barrier/event-based fake loader (each load waits until all 3 have started, with a timeout) or set the bound
strictly below serial time with margin. It MUST fail when loads are serialized (prove in a /tmp copy by making loads serial).

## 2. main() actually writes
Removing the four adapter kwargs from the `run_ingest` call in `main()` currently leaves all tests passing.
Add a write-mode `main()` test with fake adapters/fake Spark (fake_pyspark fixture) and stub SEC HTTP fixtures
that asserts exact rows are written to the filings/chunks writer and to sec_ingest_log.
Mutation proof: remove the adapter kwargs → this test FAILS.

## 3. User-Agent: notebook + wider grep
- `notebooks/` SEC ingest notebook: delegate to `pipelines/sec_rag_ingest.py` (thin wrapper) so it inherits fail-closed UA; no own UA string.
- `notebooks/refresh_bronze_cot.py:69` `contact@example.com` → read from config/secret, fail closed if missing.
- Replace the hardcoded 7-file grep test with a repo-wide scan of *.py and *.yml (excluding tests/ and .agents/) for
  `example.com` / `your_email` placeholders.

## 4. Accession conflict: race path + narrow exception
- Add a test for the race-path conflict (the conflict detected inside the try block after the anti-join, e.g. concurrent insert).
- Replace `except ValueError: raise` with a dedicated `AccessionOwnershipConflict(ValueError)` exception; only that is re-raised; other errors keep existing handling.
- Mutation proof: remove the re-raise → the race-path test FAILS.

## 5. sec_cik_mapping_log
Documented in docs/DATA_SCHEMAS.md but no writer exists. Either implement the writer (if the CIK-mapping step produces
the data) with a test, or remove it from the docs. Prefer implementing if trivial; state which in the verdict.

## 6. Nit
Fix the embedding comment claiming each worker has its own model (`get_embeddings()` is a singleton) — make the comment accurate.

## Acceptance
- python -m pytest tests/rag tests/bronze -q all pass; pyspark hidden: PYTHONPATH=<nps shim> python -m pytest tests/rag -q all pass.
- Report all mutation proofs (items 1, 2, 4) with outputs in .agents/mimo/VERDICT-rag-coverage-round5.md. Commit everything.
