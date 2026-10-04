# RE-REVIEW: SEC RAG coverage (reviewer: Codex gpt-5.6-sol)

Your verdict: .agents/codex/VERDICT-rag-coverage-review.md (10×P1). Stopgap reviewer while you were usage-limited: .agents/reviewer/VERDICT-rag-coverage-r1.md
(9/10 verified; N1 P1 bronze MERGE race; N2–N5 P2). Fix rounds 8a, 8a-2, 8b, 8c, 9. DeepSeek approved round 9 (.agents/deepseek/VERDICT-rag-coverage-round9.md).
Do NOT edit repo files; mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
This code will run UNATTENDED against SEC EDGAR (dry-run → 10 → 50 → 300 → 557 tickers). Re-verify your 10 findings and N1–N5 with your own probes;
in particular concurrency (unique views + lock around MERGE and its metrics read; concurrent Delta writes), the global 429 cool-down with capped
Retry-After, resume semantics (SparkIngestLogReader wired in main), discovery failure recording, and job wiring/deps. Run 3 mutations of your own.
Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line.
Run: python3 -m pytest tests/rag tests/bronze -q (sandbox may block sockets; report sandbox-only failures separately).
