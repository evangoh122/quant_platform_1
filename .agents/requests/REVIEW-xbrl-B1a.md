# REVIEW: XBRL B1a — SEC Company Facts client + append-only bronze (reviewer: Codex)

Branch feat/xbrl-fundamentals (based on PR #28's slice/rag-coverage). Plan: docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md §2.1, §2.2,
§2.5 (your plan). Commits 3983aed..80c5c38. DeepSeek: r1 CHANGES_REQUESTED (append untested; no-op skip test) → r2 APPROVED
(.agents/deepseek/VERDICT-xbrl-B1a-r2.md). Claude: tests/bronze/test_sec_companyfacts.py → 42 passed; append→overwrite mutation fails tests;
live `--dry-run --tickers NVDA,XOM` maps 2 tickers / 3 CIKs.
Run `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` (no network needed). Mutation proofs only in /tmp via
`git archive HEAD | tar -x -C /tmp/<dir>`. Focus: SEC fair-access compliance (UA, ≤10 req/s process-wide under concurrency, Retry-After, bounded
retries), append-only bronze + manifest, raw preservation, no secrets/emails in logs, job resource, and whether driver-side Python flattening is
acceptable for B1a (DeepSeek: non-blocking). Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or
"Status: CHANGES_REQUESTED" and file:line. Do not edit files.
