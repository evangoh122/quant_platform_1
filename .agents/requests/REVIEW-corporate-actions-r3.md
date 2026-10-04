# RE-REVIEW: corporate actions after rounds 9–10b (reviewer: Codex gpt-5.6-sol)

Your previous verdict: .agents/codex/VERDICT-corporate-actions-review2.md (3 blocking: jobs/runbook yfinance, checkpoint before append, rate limit on
empty responses). Fix rounds 9, 10, plus Claude's base64 SDK-secret decode fix (10b). DeepSeek: .agents/deepseek/VERDICT-corporate-actions-round10b.md.
Do NOT edit repo files; no network/secrets; mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.
LIVE EVIDENCE (Claude ran this branch live 2026-10-04): write mode over 557 symbols → 514 split rows, 261 symbols with splits, 0 failures, 1,267 s;
silver_ohlcv_day_adjusted 639,369 rows; AMZN 2022-06-06 adjusted return +1.99% (raw −94.9%); data_quality_breaks 237 (63 SPLIT_EXPLAINED,
174 UNEXPLAINED_PENDING masked — ticker reuse/renames/collapses/leveraged ETFs).
Re-run your probes for your 3 findings, review run_batch() crash/resume + ALL-keys verification + DataFrame-join verification, and the key helper.
Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line.
Run: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py
