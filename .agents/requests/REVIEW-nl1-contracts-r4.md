# RE-REVIEW: NL1 after rounds 16–18 (reviewer: Codex gpt-5.6-sol)

Your verdicts: .agents/codex/VERDICT-nl1-review.md, -review2.md. Stopgap reviewer (while you were usage-limited): .agents/reviewer/VERDICT-nl1-contracts-r3.md
(2 High, 5 Medium). Fix rounds: BUILD-nl1-round16.md, -17, -18. DeepSeek approved round 18 (.agents/deepseek/VERDICT-nl1-round18.md).
Do NOT edit repo files; mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Review the whole NL1 package vs origin/main with fresh eyes. Specifically re-verify: every view's PIT inputs filtered before windows and output
availability = GREATEST/MAX over all contributing rows (incl. momentum and benchmark); masked NULL returns are EXCLUDED (never interpolated as 0%);
−100% day → NULL + invalid_return; relative performance bounded by :start_date; INSUFFICIENT_DATA for sparse IV across all operations and fail-closed
without stats; entity min counts/kinds; fullmatch validators (no trailing-newline bypass); tests run the PRODUCTION DDL extracted from
docs/NL1_PROPOSED_SERVING_VIEWS.md (no hand-written view SQL). Run 3 mutations of your own against the DOC.
Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line.
Run: python3 -m pytest tests/analytics_nl -q; python3 -m analytics_nl.export_schemas --check
