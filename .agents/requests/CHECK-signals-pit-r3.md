# CHECK: signals PIT round 3 (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Write .agents/deepseek/VERDICT-signals-pit-r3.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Codex finding: .agents/codex/VERDICT-signals-pit.md (refit used all labelled rows). Fix commit c3543d2 (`refit_rows`, script refits on
labels observed no later than the earliest scored snapshot). Claude: tests/ml → 51 passed; mutation `refit_rows` returns all of lab → 1 failed.
Check: the script computes the scoring rows BEFORE the refit and refits on refit_rows(...); comments/docstring match the code; the three
earlier mutations still fail; edge: if one symbol's latest snapshot is very old (the script keeps only >= 2026-09-01), does the earliest-
cutoff rule shrink the refit set drastically? Report the trade-off (non-blocking unless the refit can become empty without an error).
