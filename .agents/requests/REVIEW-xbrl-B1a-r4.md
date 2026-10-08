# REVIEW round 4: XBRL B1a — SEC Company Facts client + append-only bronze (reviewer: Codex)

Branch feat/xbrl-fundamentals (based on PR #28's slice/rag-coverage). Plan: docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md §2.1, §2.2,
§2.5 (your plan). Commits 3983aed..80c5c38. DeepSeek: r1 CHANGES_REQUESTED (append untested; no-op skip test) → r2 APPROVED
(.agents/deepseek/VERDICT-xbrl-B1a-r2.md). Claude: tests/bronze/test_sec_companyfacts.py → 42 passed; append→overwrite mutation fails tests;
live `--dry-run --tickers NVDA,XOM` maps 2 tickers / 3 CIKs.
Run `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` (no network needed). Mutation proofs only in /tmp via
`git archive HEAD | tar -x -C /tmp/<dir>`. Focus: SEC fair-access compliance (UA, ≤10 req/s process-wide under concurrency, Retry-After, bounded
retries), append-only bronze + manifest, raw preservation, no secrets/emails in logs, job resource, and whether driver-side Python flattening is
acceptable for B1a (DeepSeek: non-blocking). Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or
"Status: CHANGES_REQUESTED" and file:line. Do not edit files.

## Round 2 delta
Your round-1 verdict: .agents/codex/VERDICT-xbrl-B1a.md (4 blocking: 403 not retried; seen_payloads before the write; weak UA validation;
no http_status; + non-blocking attempt_count/concurrency items). Fixes: rounds 3–5 (6d4413c..07b2a87). DeepSeek: r3 and r4 CHANGES_REQUESTED
(UA error leaked the email; tests not mutation-proof), r5 APPROVED (.agents/deepseek/VERDICT-xbrl-B1a-r5.md; barrier-based concurrency test
fails 10/10 under the shared-counter revert). Claude: 55 passed. Confirm all of your findings are fixed; report anything new.

## Round 3 delta
Your round-2 verdict: .agents/codex/VERDICT-xbrl-B1a-r2.md (retry-exhausted SecClientError lost status_code → manifest http_status=None).
Fix 80f607a (round 6). DeepSeek r6 APPROVED (.agents/deepseek/VERDICT-xbrl-B1a-r6.md). Claude: 261 passed. Confirm the finding is fixed.

## Round 4 delta (after your r3 APPROVED)
Claude's LIVE runs (real Spark + SEC) after your r3 approval found bugs the fakes could not: CANNOT_DETERMINE_TYPE on createDataFrame (no schema);
DELTA_METADATA_MISMATCH on the manifest (http_status not in DDL); non-idempotent ALTER (FIELD_ALREADY_EXISTS); a test polluting the real CIK cache
(/tmp/sec_cache, 1 entry) so NVDA was unmapped. Fixed in rounds 7–10 (3115a96, 2088db2, acf0ede, ad1d2cd): explicit StructTypes as the single source of
truth (DDL + ALTER generated from them), idempotent schema evolution, cache min-size guard + autouse tmp cache fixture + socket guard in tests/bronze.
Checker: DeepSeek r7r8 CHANGES_REQUESTED; Codex luna (DeepSeek out of balance) r9 CHANGES_REQUESTED → r10 APPROVED (.agents/deepseek-fallback/VERDICT-xbrl-B1a-r10.md).
Claude live: XOM 20,909 (both CIKs), NVDA+AAPL 52,416, MSFT 32,671, AMD 23,826 facts; no errors. 556 tests pass. Review the round 7–10 changes.
