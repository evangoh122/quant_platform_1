# REVIEW round 2: baseline-signals PIT (reviewer: Codex)

Your round-1 verdict: .agents/codex/VERDICT-signals-pit.md (refit used all labelled rows). Fix c3543d2: `refit_rows` keeps labels observed no
later than the EARLIEST scored snapshot; the script computes the scoring rows before the refit. DeepSeek APPROVED round 3
(.agents/deepseek/VERDICT-signals-pit-r3.md; 4 mutations fail, incl. refit_rows returning all rows). Claude: tests/ml → 51 passed.
Run `python3 -m pytest tests/ml -q`; mutation proofs only in /tmp copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Do not run the script.
Confirm your finding is fixed. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or
"Status: CHANGES_REQUESTED" and file:line. Do not edit files.
