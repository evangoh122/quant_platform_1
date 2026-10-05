
# VERDICT: rag-coverage-r4 — Codex

Status: CHANGES_REQUESTED

DeepSeek round-11 approval is present. Repository files remained unmodified.

## Finding

1. **[P1] Unknown ingest metrics are still converted into a job-level zero.** `IngestResult.total_rows_appended` starts as an integer `0` at [sec_rag_ingest.py:1099](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1099). Both threaded and serial aggregation skip `None` values at [sec_rag_ingest.py:1496](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1496) and [sec_rag_ingest.py:1516](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1516), after which the summary reports that retained zero at [sec_rag_ingest.py:1529](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1529). Independent probes with two successful filings whose writer returned `None` produced `rows=0` in both execution modes. This can falsely satisfy the ingestion idempotency gate at [SEC_RAG_COVERAGE_RUNBOOK.md:154](/home/jianj/code/qp1-ragcov/docs/SEC_RAG_COVERAGE_RUNBOOK.md:154). Unknown must propagate through the ingest aggregate and render as unknown, as it now does for embeddings.

## Verification

- `python3 -m pytest tests/rag tests/bronze -q`: **664 passed, 36 skipped**.
- Targeted round-10/11 regressions: **21 passed**.
- Both MERGE writers correctly return `None` plus `WARNING` for empty history, missing metrics, and exceptions.
- Embedding aggregate correctly propagates unknown; its summary safely renders `None`.
- Ingest-log schema is nullable and accepts `rows_appended=None`.
- Schema, cold start, ownership audit, and production SQL/job rendering checks passed.
- Writer mutation: **7 tests failed**.
- Aggregate-coercion mutation: **1 test failed**.
- Red-phase commit `0798921`: **5 tests failed**.
- Worktree remained clean.

