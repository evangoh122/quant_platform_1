# REVIEW round 2: PR #42 fixes — CI failure + 4 CodeRabbit findings (reviewer: Codex sol)

Branch feat/xbrl-fundamentals (PR #42). CodeRabbit findings: .agents/coderabbit-pr42.md; CI "Python tests" failed because the schema StructTypes imported PySpark (CI installs none).
Fixes: b2454ba, 9adb636, d8e3832, 8f46536, 66ef191. Checker luna: r1 CHANGES_REQUESTED (33 contract tests skipped in CI) → r2 APPROVED
(.agents/deepseek-fallback/VERDICT-xbrl-pr42-fixes-r2.md). Claude: with pyspark/databricks.connect imports BLOCKED → 557 passed, 27 skipped (no contract skipped).
Run the blocked-import run yourself and `python3 -m pytest tests/bronze tests/rag/test_sec_rag_ingest.py -q`. Mutation proofs only in /tmp via `git archive HEAD`. Judge each CodeRabbit finding
fixed or correctly rejected; live write path unchanged. Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line.
Do not edit files.

## Round 2 delta
Your r1 verdict: .agents/codex/VERDICT-xbrl-pr42-fixes.md (only finding: no deterministic race test for the (cik, payload_hash) reservation). Fix bc1e3fd: two workers fetch the same payload;
the first worker's Delta append blocks on a threading.Event until the second has reached the reservation check; exactly one append. Claude: tests/bronze 357 passed; moving the reservation
after the append (mark-seen-after-append) → the new test fails. Test-only change. Confirm your finding is fixed.
