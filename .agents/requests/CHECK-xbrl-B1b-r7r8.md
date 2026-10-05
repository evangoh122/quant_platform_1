# CHECK: XBRL B1b rounds 7+8 — DDL + in-payload dedupe, both from Claude's LIVE runs (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Specs: .agents/requests/BUILD-xbrl-B1b-r7.md, -r8.md. Commits 92b85e9 (DDL), 899a16e (dedupe + conflict flag). Claude: 519 passed. Claude LIVE (real Delta): table dropped/re-created via
the new DDL; MERGE run 1 → 129,822 rows = 129,822 distinct keys; MERGE run 2 → unchanged (was failing with DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE); quality_status ok 59,610 /
unresolved_accession 70,212. Observation: resolved AMD/NVDA facts back to 2009 have acceptance times at exactly 00:00 (older bronze_sec_filings_v2 rows carry date-only accepted_ts) — judge
whether silver should flag that (non-blocking unless it breaks PIT).
Mutations, each must fail: remove the DDL step from run_silver_gold.py; drop a column from the DDL; remove the ROW_NUMBER dedupe; drop the conflict flag. Where is the conflict flag stored
(column name)? Is the dedupe tie-break deterministic?
