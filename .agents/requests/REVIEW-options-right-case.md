# REVIEW: options right-case fix (reviewer: Codex gpt-5.6-sol)

Independent REVIEWER after DeepSeek approved (.agents/deepseek/VERDICT-options-right-case-round2.md). Do NOT edit repo files; mutation
proofs in /tmp copies. Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED",
numbered findings with file:line, counts, mutation results.

Scope: branch fix/options-right-case vs origin/main. Context: .agents/requests/BUILD-options-right-case.md (live finding: bronze_options_day.right
uppercase PUT/CALL through 2026-09-04, lowercase put/call 2026-09-08..2026-10-01 = 5,986,723 rows; gold/02 compared uppercase only;
gold_options_features ends 2026-09-04).
Review for:
1. Correctness of gold/02 after the change (put_volume/call_volume/put_call_ratio, p25/c25 quote CTEs); any other consumer of option
   side anywhere in the repo (silver/03, silver/04, ml/, strategies/, api/) left case-sensitive.
2. The one-off maintenance UPDATE: safe on Delta (idempotent, touches only 'put'/'call', backticked `right`), and the plan after it —
   gold_options_features must be recomputed for 2026-09-08 onward (is the gold MERGE incremental or full? will a rerun pick up the
   missing dates, or does it need a date-range parameter?). State the exact rerun steps.
3. Ingestion canonical case (day path uppercase, quotes path lowercase) documented in docs/DATA_SCHEMAS.md; is the deliberate
   difference between the two tables a trap for future code? Recommend.
4. Tests meaningful; run 2 mutations of your own.
Run: python3 -m pytest -q tests/gold tests/bronze tests/silver (pytz ModuleNotFoundError failures are pre-existing).
