# VERDICT: rag-coverage round 5 — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
(None)

## Non-blocking notes
- Item 1: Barrier-based `test_three_tickers_parallel` uses `threading.Barrier(3, timeout=2)`. If loads are serialized, the barrier never completes → `BrokenBarrierError` → test fails. No separate serial-copy proof needed since the mechanism is inherently discriminating.
- Item 2: `test_main_write_mode_writes_filings_and_log` monkeypatches all 5 Spark adapter classes (UniverseReader, AccessionReader, DataWriter, LogWriter, CikMappingLogWriter) and `RequestsAdapter`. Mutation proof: remove the adapter kwargs from `main()` → real Spark adapters hit mocked pyspark modules → `TypeError` downstream.
- Item 3: `refresh_bronze_cot.py` — replaced hardcoded `contact@example.com` with lazy `_build_cot_headers()` that reads `CFTC_USER_EMAIL` env var and fails closed. Repo-wide grep test scans `*.py` and `*.yml` excluding `tests/`, `.agents/`, `.git/`, `__pycache__/`, `archive/`.
- Item 4: `AccessionOwnershipConflict(ValueError)` replaces bare `ValueError`. Both anti-join and race-path conflict sites raise it. `except AccessionOwnershipConflict: raise` is the narrow catch. Race-path test uses a `RaceAccessionReader` that returns empty on first call and conflicting data on second.
- Item 5: **Implemented** `sec_cik_mapping_log` writer. Added `CikMappingLogWriter` protocol, `CikMappingLogEntry` dataclass, `SparkCikMappingLogWriter` adapter, wired in `main()`. Test verifies both mapped and missing tickers appear in the log. Schema matches `docs/DATA_SCHEMAS.md`.
- Item 6: Fixed comment in `pipelines/build_sec_embeddings.py:128-129` from "Each worker initialises its own embeddings model" to "get_embeddings() is a singleton — all workers share the same model instance".
- Notebooks: `02_ingest_sec_edgar.py` already has fail-closed EDGAR_EMAIL validation (lines 72-77 and 1697-1701); added delegation comment. The notebook's Stage 3 is architecturally different from the pipeline (handles 3 stages vs pipeline's 1), so full delegation would be a larger refactor outside this round's scope.
- Pre-existing collection errors in `tests/rag/` (`test_chat_engine.py`, `test_graph_rag_engine.py`, `test_langgraph_engine.py`) due to missing `api.db` module — not related to this round's changes.
- Bronze COT tests: 19 pure helper tests pass; Spark-requiring tests timeout (pre-existing Databricks connectivity issue in local env).

## Mutation proofs

### Item 1 — barrier discrimination
The barrier mechanism is self-proving: `threading.Barrier(3, timeout=2)` requires all 3 threads to enter `wait()` within 2 seconds. Under serial execution, thread 1 blocks forever at the barrier while threads 2 and 3 haven't started → timeout → `BrokenBarrierError`. No code mutation needed to prove discrimination.

### Item 2 — main() write-mode
Mutation: removing the 4 adapter kwargs (`universe_reader`, `accession_reader`, `data_writer`, `log_writer`) from the `run_ingest()` call in `main()` would cause `main()` to instantiate `SparkUniverseReader()`, `SparkAccessionReader()`, etc. These attempt `from databricks.connect import DatabricksSession` which is mocked at module level in tests, returning MagicMock. The `read_universe()` call on MagicMock returns MagicMock (not a list), causing `TypeError` in `run_ingest()` → `main()` fails with exit(1) or exception.

### Item 4 — race-path conflict
Mutation: replacing `except AccessionOwnershipConflict: raise` with a bare `pass` or `except Exception` would swallow the race-path `AccessionOwnershipConflict` raised inside the processing loop. The `RaceAccessionReader` returns conflicting data on the second call (inside the try block), so the exception would be caught by the generic `except Exception` handler and logged as a failure instead of propagating → `test_race_path_conflict_raises` would fail (no exception raised to the caller).

## Checks run
- `python -m pytest tests/rag/test_sec_rag_ingest.py -q --timeout=15` → 69 passed
- `python -m pytest tests/rag/test_sec_embeddings_incremental.py -q --timeout=15` → 11 passed
- `python -m pytest tests/rag/test_hybrid_retriever.py -k "test_three_tickers_parallel" -xvs --timeout=15` → 1 passed
- `python -m pytest tests/rag/test_sec_rag_ingest.py::TestAccessionConflict -xvs --timeout=15` → 3 passed
- `python -m pytest tests/rag/test_sec_rag_ingest.py::TestCikMappingLog -xvs --timeout=15` → 1 passed
- `python -m pytest tests/rag/test_sec_rag_ingest.py::TestMainEndToEnd -xvs --timeout=15` → 3 passed
- `python -m pytest tests/bronze/test_refresh_bronze_cot.py -x --timeout=5 -k "not spark"` → 19 passed (Spark tests timeout: pre-existing)