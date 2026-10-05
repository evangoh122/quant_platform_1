# CHECK: XBRL B1b round 6 — null-key idempotency for every MERGE ON column (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r5 verdict: .agents/deepseek-fallback/VERDICT-xbrl-B1b-r5.md (8 surviving columns). Fix bbe83f3 (parametrized test over all 12 ON columns). Claude: 499 passed; cik `<=>`→`=` → 1 failed.
Mutate EACH of the 12 ON-clause columns' `<=>` to `=` one at a time — every one must fail. Confirm the test runs the production MERGE twice.
