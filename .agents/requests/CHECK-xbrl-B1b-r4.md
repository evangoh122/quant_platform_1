# CHECK: XBRL B1b round 4 — tests call asof_facts() (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r3 verdict: .agents/deepseek-fallback/VERDICT-xbrl-B1b-r3.md. Fix de9d04f. Claude: tests/db 14 passed; production `f.ticker` mutation → 4 failed.
Confirm no test reconstructs query logic (grep tests/db and tests/silver for copied SQL/transform code); repeat the f.ticker and f.concept production mutations; re-run the
four silver production mutations.
