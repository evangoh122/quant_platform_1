# CHECK: XBRL B1b round 5 — null-safe MERGE (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Finding: .agents/codex/VERDICT-xbrl-B1b-r2.md. Fix f4f7f0b (null-safe `<=>` in the MERGE ON clause) + Claude tiny fix (the idempotency test now really includes a NULL
accession_number fact; before it, the `<=>`→`=` mutation survived). Claude: 487 passed; `<=>`→`=` on accession_number → idempotency test fails.
Mutate each nullable key column's `<=>` to `=` one at a time (accession_number, cik, taxonomy, concept, unit, period fields, frame) — report which survive (a survivor for a
column that can be NULL in bronze is blocking). Confirm the test runs the production MERGE twice.
