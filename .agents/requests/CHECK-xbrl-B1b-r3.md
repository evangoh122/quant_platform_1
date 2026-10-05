# CHECK: XBRL B1b round 3 — asof_facts filter alias (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Finding: .agents/codex/VERDICT-xbrl-B1b.md (filters referenced alias `f`). Fix 6dcea02. Claude: tests/silver + tests/bronze + tests/db → 484 passed.
Confirm the new tests EXECUTE the generated asof SQL (DuckDB) for no filter / ticker / concept / both with bound parameters; mutation: restore the `f.` alias → they fail.
Re-run the four production silver mutations.
