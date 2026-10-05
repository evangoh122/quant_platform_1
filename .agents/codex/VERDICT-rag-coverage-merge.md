# VERDICT: rag-coverage merge

Status: CHANGES_REQUESTED

## Finding

1. **[P2] Main’s fallback PIT and output-contract tests were materially weakened.** [test_hybrid_retriever.py:1356](/home/jianj/code/qp1-ragcov/tests/rag/test_hybrid_retriever.py:1356) claims to verify PIT filtering, but provides no future row and never asserts that the `as_of` predicate was applied. Likewise, [test_hybrid_retriever.py:1300](/home/jianj/code/qp1-ragcov/tests/rag/test_hybrid_retriever.py:1300) no longer verifies the fallback output schema; it exercises fallback failure and asserts an error envelope. The main-parent versions explicitly required the ticker plus `as_of` filters and checked every mapped fallback field.

   Mutation proof in isolated `git archive HEAD` copies:

   - Removing the fallback PIT predicate at [tools_retrieval.py:161](/home/jianj/code/qp1-ragcov/agent/tools_retrieval.py:161) still produced **112 passed**.
   - Removing `source_url` from the fallback output at [tools_retrieval.py:187](/home/jianj/code/qp1-ragcov/agent/tools_retrieval.py:187) still produced **119 passed** across both retrieval test modules.

   Restore assertions that an explicit `as_of` causes the PIT `.where(...)` call and that successful fallback results retain the complete output contract.

## Validation

- DeepSeek prerequisite: **APPROVED**.
- Conflict union verified across all six conflicted files; no production behavior from either parent was dropped.
- `NoCoverageError`/`TickerRequiredError` cannot reach substring fallback.
- Fixture snapshot restoration is correct and load-bearing:
  - Fixed tree excluding sandbox-incompatible network tests: **1111 passed, 36 skipped**.
  - Reverting the fixture restoration in an archive copy: **1 failed, 1110 passed, 36 skipped**, reproducing `test_shape_day_emits_uppercase_right`.
- r3–r6 aggregation, cold-start, ownership, SQL-placeholder, secret-resolution, value-leak, jobs configuration, and coverage-gating selection: **51 passed**.
- Exact requested command: **1120 passed, 37 skipped, 7 failed**. All seven failures are `PermissionError: Operation not permitted` from this managed sandbox prohibiting socket creation/send/bind in `test_network_guard.py`, before the tested guard behavior executes.
- Repository files were not edited; worktree remained clean.
