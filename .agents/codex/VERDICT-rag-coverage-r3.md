
# VERDICT: rag-coverage-r3 — Codex

Status: CHANGES_REQUESTED

DeepSeek round-10 approval is present. Repository files remained unmodified.

## Finding

1. **[P1] Missing MERGE metrics can still be silently reported as zero.** Both [sec_rag_ingest.py:1709](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1709) and [build_sec_embeddings.py:278](/home/jianj/code/qp1-ragcov/pipelines/build_sec_embeddings.py:278) initialize the inserted count to `0`. If `DESCRIBE HISTORY` returns no row or an `operationMetrics` map without `numTargetRowsInserted`, they return `0` without a warning. Independent probes reproduced both cases in both writers. Additionally, [build_sec_embeddings.py:155](/home/jianj/code/qp1-ragcov/pipelines/build_sec_embeddings.py:155) converts a batch-level `None` into `0`, so even the exception path ultimately reports a known-zero `rows_written`. This can falsely satisfy the rollout’s idempotency gate. Missing history rows, missing metrics keys, and exceptions must all produce `None` plus `WARNING`, and unknown must propagate through the build-level aggregate.

## Verification

- `python3 -m pytest tests/rag tests/bronze -q`: **652 passed, 36 skipped**.
- Round-10 regression selection: **9 passed**.
- Explicit schema confirmed on all six production-lane `createDataFrame` calls.
- Cold-start reader and table-creation probes passed.
- Pre-existing ownership conflict produced the required failed audit row.
- Production rendering correctly used `evangoh_capstone_prod` in silver 05, silver 06, gold 07, and all relevant job parameters.
- Five independent mutations were killed: schema, cold start, ownership audit, placeholders, and metrics fallback.
- `git diff --check origin/main...HEAD`: passed.
- Worktree remained clean.

